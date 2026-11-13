/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "remote_control.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#if FM_CONTROLS > 64
#error Remote control baseline masks require at most 64 controls
#endif
static uint32_t get32(const unsigned char *p){return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
void rc_init(remote_control *r,uint32_t boot){memset(r,0,sizeof *r);r->boot=boot?boot:1;}
void rc_clear(remote_control *r){r->count=0;memset(r->streams,0,sizeof r->streams);for(unsigned k=0;k<2;++k){r->stage[k].release=0;r->stage[k].owner=0;r->stage[k].retrigger=0;if(++r->stage[k].revision==0)r->stage[k].revision=1;}}
void rc_bind(remote_control *r,unsigned stage,const fm_graph *g,fm_voice *v)
{
    if(stage>1)return;
    rc_stage *s=&r->stage[stage];uint32_t revision=s->revision+1;if(!revision)revision=1;
    for(unsigned i=0;i<RC_STREAMS;++i)r->streams[i].baseline[stage].valid=0;
    memset(s,0,sizeof *s);s->revision=revision;s->graph=g;s->voice=v;s->gate=-1;
    memcpy(s->shadow,g->defaults,sizeof s->shadow);
    for(unsigned j=0;j<g->nodes;++j){const fm_node *n=&g->node[j];
        if(n->type!=FM_Control && n->type!=FM_LagControl && n->type!=FM_TrigControl)continue;
        for(unsigned k=0;k<n->outputs;++k){unsigned i=(unsigned)n->special+k;
            if(i>=FM_CONTROLS)continue;
            if(n->rate==0)s->rate[i]=2;else if(s->rate[i]!=2)s->rate[i]=1;
            s->trigger[i]|=n->type==FM_TrigControl;
        }
    }
    for(unsigned i=0;i<g->controls;++i)s->writable[i]=s->rate[i]==1;
    for(unsigned i=0;i<g->names;++i){const fm_control_name *c=&g->control_name[i];
        if(!strncmp(c->name,"__esp32_",8))s->writable[c->index]=0;
        if(!strcmp(c->name,"gate") && s->writable[c->index])s->gate=c->index;
    }
    /* An activation invalidates only its own stage's pending events. */
    unsigned out=0;for(unsigned i=0;i<r->count;++i)if(r->event[i].stage!=stage)r->event[out++]=r->event[i];
        r->count=out;
}
int rc_decode(rc_event *e,const unsigned char *p,size_t bytes)
{
    if(bytes<RC_HEADER)return 0;
    memset(e,0,sizeof *e);e->boot=get32(p);e->revision=get32(p+4);e->stream=get32(p+8);e->sequence=get32(p+12);
    e->at=(uint64_t)get32(p+16)|((uint64_t)get32(p+20)<<32);e->duration=get32(p+24);
    e->kind=p[28];e->stage=p[29];e->count=p[30];e->flags=p[31];
    if((e->flags & ~RC_DELTA) || (e->kind==2 && e->flags) || e->kind>2 || e->stage>1 || e->count>RC_PAIRS || bytes!=RC_HEADER+e->count*5u || !e->stream || !e->sequence)return 0;
    for(unsigned i=0;i<e->count;++i){e->index[i]=p[32+i*5];uint32_t bits=get32(p+33+i*5);memcpy(&e->value[i],&bits,4);if(!isfinite(e->value[i]))return 0;}
    return 1;
}
int rc_reopen_main_program(remote_control *r,uint32_t id,uint32_t revision)
{
    if(!id || revision!=r->stage[0].revision || r->stage[0].owner==id)return 0;
    for(unsigned k=0;k<r->count;k++)if(r->event[k].stream==id)return 0;
    for(unsigned k=0;k<RC_STREAMS;k++)if(r->streams[k].id==id){
        rc_stream *s=&r->streams[k];
        if(s->baseline[1].revision || s->baseline[0].revision==revision)return 0;
        memset(s,0,sizeof *s);
        return 1;
    }
    return 1;
}
int rc_enqueue(remote_control *r,const rc_event *e,uint64_t now)
{
    if(e->stage>1 || e->kind>2 || e->count>RC_PAIRS || (e->flags & ~RC_DELTA) || (e->kind==2 && e->flags)){++r->rejected;return 0;}
    rc_stage *s=&r->stage[e->stage];
    if(e->boot!=r->boot || e->revision!=s->revision || !s->graph || !e->stream || !e->sequence)goto reject;
    if(e->kind!=2 && ((e->at && e->at+100000<now) || e->at>now+5000000))goto reject;
    if(e->kind==1 && (e->stage || s->gate<0 || !e->duration || e->duration>60000000))goto reject;
    if(e->kind==2 && e->count)goto reject;
    for(unsigned i=0;i<e->count;++i){unsigned index=e->index[i];if(index>=s->graph->controls || !s->writable[index] || !isfinite(e->value[i]))goto reject;
        if(e->kind==1 && (int)index==s->gate)goto reject;
        for(unsigned j=0;j<i;++j)if(e->index[j]==index)goto reject;
    }
    rc_stream *stream=NULL,*free_slot=NULL;
    for(unsigned i=0;i<RC_STREAMS;++i){rc_stream *v=&r->streams[i];
        if(v->id==e->stream){stream=v;break;}
        if(!v->id || (v->touched+10000000<now))free_slot=v;
    }
    if(stream && (stream->cancelled || e->sequence<=stream->sequence))goto reject;
    if(e->kind!=2 && r->count==RC_EVENTS)goto reject;
    if(e->flags==RC_DELTA && (!stream || !stream->baseline[e->stage].valid ||
        stream->baseline[e->stage].revision!=e->revision || stream->baseline[e->stage].kind!=e->kind))return RC_NEED_FULL;
    if(!stream){if(!free_slot)goto reject;stream=free_slot;memset(stream,0,sizeof *stream);stream->id=e->stream;}
    rc_event resolved=*e;
    rc_baseline *baseline=&stream->baseline[e->stage];
    uint64_t mask=e->flags==RC_DELTA?baseline->mask:0;
    for(unsigned i=0;i<e->count;++i)mask|=UINT64_C(1)<<e->index[i];
    if(e->flags==RC_DELTA){
        /* Only update an existing field set. Field additions/removals use a
         * full packet, so Pbindef edits cannot keep old arguments alive. */
        if(mask!=baseline->mask)goto reject;
        uint8_t position[FM_CONTROLS];resolved.count=0;
        for(unsigned index=0;index<FM_CONTROLS;++index)if(mask & (UINT64_C(1)<<index)){
            unsigned at=resolved.count++;position[index]=(uint8_t)at;resolved.index[at]=(uint8_t)index;resolved.value[at]=baseline->value[index];
        }
        for(unsigned j=0;j<e->count;++j)resolved.value[position[e->index[j]]]=e->value[j];
    }
    stream->sequence=e->sequence;stream->touched=now;
    if(e->kind==2){
        stream->cancelled=1;unsigned out=0;
        for(unsigned i=0;i<r->count;++i)if(r->event[i].stream!=e->stream)r->event[out++]=r->event[i];
        r->count=out;
        for(unsigned k=0;k<2;++k){rc_stage *v=&r->stage[k];if(v->owner==e->stream){if(v->gate>=0)v->voice->control[v->gate]=v->shadow[v->gate]=0;v->owner=0;v->release=0;v->retrigger=0;}}
        return 1;
    }
    baseline->mask=mask;baseline->revision=e->revision;baseline->kind=e->kind;baseline->valid=1;
    for(unsigned i=0;i<resolved.count;++i)baseline->value[resolved.index[i]]=resolved.value[i];
    /* Queue a complete snapshot, never a reference to a mutable baseline.
     * Other streams, immediate sets and later deltas cannot change this note. */
    resolved.flags=0;r->event[r->count++]=resolved;return 1;
reject:++r->rejected;return 0;
}
static void apply_values(rc_stage *s,const rc_event *e)
{
    for(unsigned i=0;i<e->count;++i){unsigned k=e->index[i];s->voice->control[k]=e->value[i];if(!s->trigger[k])s->shadow[k]=e->value[i];
        if(!e->kind && (int)k==s->gate){s->owner=0;s->release=0;s->retrigger=0;}
    }
}
int rc_instance(remote_control *r,instrument *synth,master_delay *master,int start,const rc_event *e)
{
    if(e->stage>1 || e->count>RC_PAIRS)return 0;
    rc_stage *s=&r->stage[e->stage];
    if(e->boot!=r->boot || e->revision!=s->revision || !s->graph || (!start && e->count))return 0;
    float controls[FM_CONTROLS];memcpy(controls,s->graph->defaults,sizeof controls);
    for(unsigned i=0;i<e->count;++i){unsigned index=e->index[i];
        if(index>=s->graph->controls || !s->rate[index] || !isfinite(e->value[i]))return 0;
        for(unsigned j=0;j<i;++j)if(e->index[j]==index)return 0;
        for(unsigned j=0;j<s->graph->names;++j)if(s->graph->control_name[j].index==index &&
            !strncmp(s->graph->control_name[j].name,"__esp32_",8))return 0;
        controls[index]=e->value[i];
    }
    int ok=1;
    if(start){if(!e->stage)instrument_preclear(synth);ok=e->stage?master_effect_start(master,synth->scratch,controls):instrument_start_remote(synth,controls);}
    else if(e->stage){master->definition_only=true;master_delay_panic(master);s->voice->active=s->voice->prepared=0;}
    else {instrument_panic(synth);s->voice->prepared=0;instrument_preclear(synth);}
    if(ok){const fm_graph *g=s->graph;fm_voice *v=s->voice;rc_bind(r,e->stage,g,v);memcpy(r->stage[e->stage].shadow,v->control,sizeof controls);}
    return ok;
}
void rc_tick(remote_control *r,instrument *synth,uint64_t now)
{
    /* A local touch has taken the monophonic gate. Expiry/cancellation of the
     * previous network note must not release that newer local note. Future
     * queued network events are retained and may take ownership in turn. */
    if(synth->managed_definition && synth->held && synth->note_id){
        r->stage[0].owner=0;r->stage[0].release=0;r->stage[0].retrigger=0;
    }
    unsigned gate_was_high=0;
    for(unsigned k=0;k<2;++k){rc_stage *s=&r->stage[k];if(!s->voice)continue;
        if(s->gate>=0 && s->voice->control[s->gate]>0)gate_was_high|=1u<<k;
        if(s->release && now>=s->release){s->voice->control[s->gate]=s->shadow[s->gate]=0;s->release=0;s->owner=0;s->retrigger=0;if(k==0)synth->held=0;}
        else if(s->retrigger){s->voice->control[s->gate]=1;s->retrigger=0;}
    }
    /* Sorted by due time, with arrival order breaking ties. */
    for(unsigned n=0;n<RC_EVENTS;++n){unsigned best=r->count;uint64_t due=UINT64_MAX;
        for(unsigned i=0;i<r->count;++i)if((!r->event[i].at || r->event[i].at<=now) && r->event[i].at<due){best=i;due=r->event[i].at;}
        if(best==r->count)break;
        rc_event e=r->event[best];memmove(&r->event[best],&r->event[best+1],(--r->count-best)*sizeof e);
        rc_stage *s=&r->stage[e.stage];if(e.revision!=s->revision)continue;
        if(e.at && now>e.at+100000){++r->late;continue;}
        if(e.kind==1){
            /* A release above is not visible to the DSP until this tick is
             * rendered. Preserve the low block when the next note is due in
             * the same tick, even though the control is already zero here. */
            int was_high=s->voice->control[s->gate]>0 || (gate_was_high&(1u<<e.stage));apply_values(s,&e);s->shadow[s->gate]=1;
            if(!s->voice->active){if(!instrument_start_remote(synth,s->shadow)){++r->rejected;continue;}}
            else if(was_high){s->voice->control[s->gate]=0;s->retrigger=1;}
            else{s->voice->control[s->gate]=1;s->retrigger=0;}
            synth->held=1;
            synth->note_id=0;synth->gate_low_blocks=0;
            s->owner=e.stream;s->owner_sequence=e.sequence;s->release=(e.at?e.at:now)+e.duration;
        }else {
            apply_values(s,&e);
            if(!e.stage && synth->managed_definition){
                for(unsigned i=0;i<e.count;++i)if((int)e.index[i]==s->gate){
                    synth->note_id=0;synth->gate_low_blocks=0;synth->held=e.value[i]>0;
                }
            }
        }
        ++r->applied;
    }
}
int rc_snapshot(const remote_control *r,unsigned stage,uint64_t now,rc_status *status)
{
    if(stage>1 || !r->stage[stage].graph)return 0;
    const rc_stage *s=&r->stage[stage];memset(status,0,sizeof *status);
    status->graph=s->graph;status->boot=r->boot;status->revision=s->revision;status->queued=r->count;
    status->now=now;status->applied=r->applied;status->rejected=r->rejected;status->late=r->late;
    status->active=s->voice->active;status->prepared=s->voice->prepared;
    memcpy(status->values,s->voice->control,sizeof status->values);memcpy(status->rate,s->rate,sizeof status->rate);
    memcpy(status->trigger,s->trigger,sizeof status->trigger);memcpy(status->writable,s->writable,sizeof status->writable);return 1;
}
#define APPEND(...) do { if(at>=bytes)return 0;int written=snprintf(out+at,bytes-at,__VA_ARGS__);if(written<0 || (size_t)written>=bytes-at)return 0;at+=(size_t)written; } while(0)
int rc_info(const rc_status *s,unsigned page,char *out,size_t bytes)
{
    if(page>8 || !s->graph)return 0;
    const fm_graph *g=s->graph;size_t at=0;
    APPEND("{\"boot\":%lu,\"revision\":%lu,\"now_us\":%llu,\"active\":%s,\"prepared\":%s,\"queued\":%u,\"applied\":%llu,\"rejected\":%llu,\"late\":%llu,\"total\":%u,\"controls\":[",(unsigned long)s->boot,(unsigned long)s->revision,(unsigned long long)s->now,s->active?"true":"false",s->prepared?"true":"false",(unsigned)s->queued,(unsigned long long)s->applied,(unsigned long long)s->rejected,(unsigned long long)s->late,g->names);
    unsigned end=(page+1)*8;if(end>g->names)end=g->names;
    for(unsigned i=page*8;i<end;++i){const fm_control_name *c=&g->control_name[i];unsigned count=g->controls-c->index;
        for(unsigned j=0;j<g->names;++j)if(g->control_name[j].index>c->index && (unsigned)(g->control_name[j].index-c->index)<count)count=g->control_name[j].index-c->index;
        char hex[129]={0};for(unsigned j=0;j<strlen(c->name);++j)snprintf(hex+2*j,3,"%02x",(unsigned char)c->name[j]);
        APPEND("%s{\"name_hex\":\"%s\",\"index\":%u,\"count\":%u,\"rate\":%u,\"trigger\":%s,\"writable\":%s,\"values\":[",i%8?",":"",hex,c->index,count,s->rate[c->index]==2?0:1,s->trigger[c->index]?"true":"false",s->writable[c->index]?"true":"false");
        for(unsigned j=0;j<count;++j)APPEND("%s%.9g",j?",":"",(double)s->values[c->index+j]);
        APPEND("]}");
    }
    APPEND("]}");return 1;
}
