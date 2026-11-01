/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "master_delay.h"
#include <math.h>
#include <string.h>
int master_delay_set(master_delay *s,unsigned k,float value)
{
    static const float low[]={.02f,0,0},high[]={MASTER_DELAY_SECONDS,.8f,1};
    if(k>=3 || !isfinite(value) || value<low[k] || value>high[k])return 0;
    s->value[k]=value;
    if(s->voice->active && s->index[k]>=0)s->voice->control[s->index[k]]=value;
    return 1;
}
int master_effect_start(master_delay *s,fm_scratch *scratch,const float *controls)
{
    s->suppressed=true;
    if(!fm_start(s->voice,s->graph,(float)s->rate) ||
       !fm_bind_delay(s->voice,s->graph,s->arena,s->capacity) || !fm_seed(s->voice,0))return 0;
    if(controls)memcpy(s->voice->control,controls,sizeof s->voice->control);
    else for(unsigned i=0;i<3;++i)if(s->index[i]>=0)s->voice->control[s->index[i]]=s->value[i];
    fm_prepare(s->graph,s->voice,scratch);
    if(s->voice->fault)return 0;
    s->suppressed=false;s->definition_only=false;return 1;
}
int master_delay_reset(master_delay *s,fm_scratch *scratch)
{
    if(s->definition_only){s->suppressed=true;s->voice->active=0;return 1;}
    return master_effect_start(s,scratch,NULL);
}
int master_delay_init(master_delay *s,fm_graph *graph,fm_voice *voice,float *arena,unsigned capacity,unsigned rate,fm_scratch *scratch)
{
    if(!s || !graph || !voice || !arena || !scratch || rate!=44100 ||
       fm_delay_required(graph,(float)rate)!=MASTER_DELAY_SAMPLES || capacity<MASTER_DELAY_SAMPLES)return 0;
    if(!master_effect_init(s,graph,voice,arena,capacity,rate,scratch))return 0;
    for(unsigned k=0;k<3;++k)if(s->index[k]<0)return 0;
    return 1;
}
static int effect_init(master_delay *s,fm_graph *graph,fm_voice *voice,float *arena,unsigned capacity,unsigned rate,fm_scratch *scratch,int define)
{
    if(!s || !graph || !voice || !scratch || rate!=44100)return 0;
    uint32_t need=fm_delay_required(graph,(float)rate);
    if(need==UINT32_MAX || need>capacity || (need && !arena))return 0;
    memset(s,0,sizeof *s);s->graph=graph;s->voice=voice;s->arena=arena;s->capacity=capacity;s->rate=rate;
    s->definition_only=define!=0;
    if(define){memset(voice,0,sizeof *voice);memcpy(voice->control,graph->defaults,sizeof voice->control);voice->sample_rate=(float)rate;}
    s->value[0]=.35f;s->value[1]=.35f;s->value[2]=.25f;
    static const char *const names[]={"time","feedback","wet"};
    for(unsigned k=0;k<3;++k) {
        s->index[k]=-1;
        for(unsigned n=0;n<graph->names;++n)if(!strcmp(names[k],graph->control_name[n].name)) {
            unsigned index=graph->control_name[n].index;
            for(unsigned i=0;i<graph->nodes;++i) {
                const fm_node *node=&graph->node[i];
                if(node->type==FM_Control && node->rate==1 && node->special>=0 && index>=(unsigned)node->special && index<(unsigned)node->special+node->outputs)s->index[k]=(int)index;
            }
        }
        if(s->index[k]>=0)s->value[k]=graph->defaults[s->index[k]];
    }
    /* Exact In.ar(0,2) -> Out.ar(0,...) has no state to advance. */
    if(graph->nodes==2 && graph->node[0].type==FM_In && graph->node[0].rate==2 && graph->node[0].outputs==2 &&
       graph->node[1].type==FM_Out && graph->node[1].inputs==3){
        const fm_node *n=&graph->node[1];const fm_ref *left=&graph->ref[n->input+1],*right=&graph->ref[n->input+2];
        s->bypass=left->node==0 && left->output==0 && right->node==0 && right->output==1;
    }
    return master_delay_reset(s,scratch);
}
int master_effect_init(master_delay *s,fm_graph *g,fm_voice *v,float *a,unsigned c,unsigned r,fm_scratch *b)
{return effect_init(s,g,v,a,c,r,b,0);}
int master_effect_define(master_delay *s,fm_graph *g,fm_voice *v,float *a,unsigned c,unsigned r,fm_scratch *b)
{return effect_init(s,g,v,a,c,r,b,1);}
void master_delay_panic(master_delay *s) {s->suppressed=true;}
void master_delay_render(master_delay *s,fm_scratch *scratch,const float *input,float *output)
{
    if(s->suppressed || s->bypass) {memcpy(output,input,FM_BLOCK*2*sizeof(float));return;}
    memset(output,0,FM_BLOCK*2*sizeof(float));
    fm_render_input(s->graph,s->voice,scratch,output,input);
    if(s->voice->fault || !s->voice->active) {
        ++s->faults;s->suppressed=true;memset(output,0,FM_BLOCK*2*sizeof(float));
    }
}
