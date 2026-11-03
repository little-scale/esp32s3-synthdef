/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "instrument.h"
#include "playback_mode.h"
#include <math.h>
#include <string.h>
static const char *const knob_names[4] = {"knob1", "knob2", "knob3", "knob4"};

static int live_index(const fm_graph *g, const char *name)
{
    unsigned i, j;
    for (i = 0; i < g->names; ++i) {
        if (strcmp(g->control_name[i].name, name)) continue;
        unsigned index = g->control_name[i].index;
        int found=0;
        for (j = 0; j < g->nodes; ++j) {
            const fm_node *n = &g->node[j];
            if(n->type!=FM_Control || n->special<0 || index<(unsigned)n->special ||
               index>=(unsigned)n->special+n->outputs)continue;
            /* A scalar alias would make fm_set reject updates after prepare.
             * Reject it up front rather than bypassing that engine contract. */
            if(n->rate==0)return -1;
            if(n->rate==1)found=1;
        }
        return found?(int)index:-1;
    }
    return -1;
}

int instrument_init_definition(instrument *s, fm_graph *g, fm_voice *v, fm_scratch *scratch,
                    float *arena, uint32_t samples, uint32_t rate,int managed)
{
    if (!s || !g || !v || !scratch || (rate != 44100 && rate != 48000)) return 0;
    int16_t indices[7];
    static const char *const names[]={"freq","amp","gate","knob1","knob2","knob3","knob4"};
    for(unsigned i=0;i<7;++i)indices[i]=(int16_t)live_index(g,names[i]);
    unsigned bus_mode=0;
    int continuous=managed?1:graph_continuous_mode(g);
    for(unsigned i=0;i<g->nodes;++i)if(g->node[i].type==FM_In && g->node[i].rate==1)bus_mode=1;
    uint32_t need = fm_delay_required(g, (float)rate);
    if (need == UINT32_MAX || need > samples || (need && !arena) ||
        continuous<0 || (!continuous && !bus_mode && (indices[0]<0 || indices[1]<0 || indices[2]<0))) return 0;
    memset(s, 0, sizeof *s);
    memset(v, 0, sizeof *v);
    memcpy(v->control,g->defaults,sizeof v->control);v->sample_rate=(float)rate;
    s->graph = g; s->voice = v; s->scratch = scratch;
    s->arena = arena; s->arena_samples = samples; s->sample_rate = rate;
    s->arena_needed=need;
    s->bus_mode=bus_mode;s->buses[0]=s->buses[1]=.5f;
    s->continuous=(unsigned)continuous;
    s->managed_definition=managed!=0;
    memcpy(s->control_index,indices,sizeof indices);
    s->frequency = 440.0f; s->amplitude = 0.5f; s->master_gain = 0.8f;
    for(unsigned i=0;i<g->names;++i) {
        if(!strcmp(g->control_name[i].name,"freq"))s->frequency=g->defaults[g->control_name[i].index];
        if(!strcmp(g->control_name[i].name,"amp"))s->amplitude=g->defaults[g->control_name[i].index];
    }
    for (unsigned k = 0; k < 4; ++k) {
        if (indices[3+k]<0) continue;
        s->knob_mask |= 1u << k;
        for (unsigned i = 0; i < g->names; ++i)
            if (!strcmp(g->control_name[i].name, knob_names[k]))
                s->knob[k] = g->defaults[g->control_name[i].index];
    }
    return 1;
}

int instrument_init(instrument *s,fm_graph *g,fm_voice *v,fm_scratch *scratch,
                    float *arena,uint32_t samples,uint32_t rate)
{return instrument_init_definition(s,g,v,scratch,arena,samples,rate,0);}

void instrument_panic(instrument *s)
{
    s->voice->active = 0;
    s->held = 0;
    s->note_id=0;s->touch_note_id=0;
    s->buses[2]=0;s->rendered_gate=0;s->gate_low_blocks=0;
    s->release_frames = 0;
    s->deferred_blocks=0;
    s->preparing_memory=0;s->arena_cleared=0;
    s->suspended_continuous=s->suspended_restart=0;
}

void instrument_randomize(instrument *s,uint32_t first_seed)
{
    s->random_starts=1;s->seed_next=first_seed;
}
static int start_seed(instrument *s,int fresh)
{
    if(fresh){
        s->seed_active=s->random_starts?s->seed_next:0;
        if(s->random_starts)s->seed_next+=0x9e3779b9u;
    }
    return fm_seed(s->voice,s->seed_active);
}
static int start_controls(instrument *s,int fresh,const float *controls)
{
    unsigned pristine=s->pristine_arena;s->pristine_arena=0;
    instrument_panic(s);
    if(!fm_start(s->voice,s->graph,(float)s->sample_rate))return 0;
    if(!start_seed(s,fresh))return 0;
    s->buses[2]=0;
    if(controls)memcpy(s->voice->control,controls,sizeof s->voice->control);
    else if(!s->continuous && s->control_index[2]>=0)s->voice->control[s->control_index[2]]=0;
    if(!fm_bind_control_buses(s->voice,s->buses,FM_CONTROL_BUSES))return 0;
    s->preparing_memory=s->defer_note_render && s->arena_needed && !pristine;
    if(!s->preparing_memory){
        if(!(pristine?fm_bind_delay_precleared(s->voice,s->graph,s->arena,s->arena_samples):fm_bind_delay(s->voice,s->graph,s->arena,s->arena_samples)))return 0;
        fm_prepare(s->graph,s->voice,s->scratch);
    }
    s->deferred_blocks=s->defer_note_render?1:0;s->fade_frame=0;
    return !s->voice->fault;
}
static int arm_bus(instrument *s,int fresh){return (!s->bus_mode && !s->continuous)?1:start_controls(s,fresh,NULL);}
int instrument_arm_bus(instrument *s){return arm_bus(s,1);}
int instrument_start_remote(instrument *s,const float *controls){return controls && start_controls(s,1,controls);}
void instrument_preclear(instrument *s)
{
    if(s->arena_needed)memset(s->arena,0,s->arena_needed*sizeof(float));
    s->pristine_arena=1;
}

void instrument_suspend(instrument *s)
{
    unsigned active=s->continuous && s->voice->active && !s->voice->fault;
    unsigned restart=s->preparing_memory || (s->deferred_blocks && !s->voice->blocks);
    instrument_panic(s);s->suspended_continuous=active;s->suspended_restart=restart;
}
int instrument_resume(instrument *s)
{
    unsigned active=s->suspended_continuous,restart=s->suspended_restart;
    s->suspended_continuous=s->suspended_restart=0;
    if(!active || !s->continuous || s->voice->active)return 1;
    if(restart)return arm_bus(s,0);
    s->voice->active=1;s->fade_frame=0;return 1;
}

int instrument_apply(instrument *s, const inst_event *e)
{
    if (!e) return 0;
    if(s->continuous && !s->managed_definition && (e->type==INST_NOTE_ON || e->type==INST_NOTE_OFF))return 1;
    switch (e->type) {
    case INST_NOTE_OFF:
        if(s->managed_definition && e->note_id==s->touch_note_id){
            s->buses[2]=0;s->touch_note_id=0;
        }
        if (s->held && e->note_id == s->note_id) {
            if(s->defer_note_render && !s->voice->blocks) {instrument_panic(s);return 1;}
            if(s->control_index[2]>=0)s->voice->control[s->control_index[2]]=0;
            s->buses[2]=0;
            s->held = 0; s->release_frames = 0;
        }
        return 1;
    case INST_FREQ:
        if (!isfinite(e->value) || e->value < 20.0f || e->value > 20000.0f) break;
        s->frequency = e->value;
        if (s->voice->active && s->control_index[0]>=0) s->voice->control[s->control_index[0]]=e->value;
        return 1;
    case INST_AMP:
        if (!isfinite(e->value) || e->value < 0.0f || e->value > 1.0f) break;
        s->amplitude = e->value;
        if (s->voice->active && s->control_index[1]>=0) s->voice->control[s->control_index[1]]=e->value;
        return 1;
    case INST_TOUCH_X: case INST_TOUCH_Y: {
        if(!isfinite(e->value) || e->value<0 || e->value>1)break;
        unsigned k=e->type==INST_TOUCH_X?0:1;s->buses[k]=e->value;
        /* Existing saved patches keep their familiar knob1/knob2 mapping. */
        if(!s->continuous && (s->knob_mask&(1u<<k))){
            s->knob[k]=e->value;
            if(s->voice->active)s->voice->control[s->control_index[3+k]]=e->value;
        }return 1;
    }
    case INST_KNOB1: case INST_KNOB2: case INST_KNOB3: case INST_KNOB4: {
        unsigned k = (unsigned)e->type - INST_KNOB1;
        if (!(s->knob_mask & (1u << k)) || !isfinite(e->value) || e->value < 0 || e->value > 1) break;
        s->knob[k] = e->value;
        if (s->voice->active) s->voice->control[s->control_index[3+k]]=e->value;
        return 1;
    }
    case INST_NOTE_ON: {
        uint64_t begin = s->clock_us ? s->clock_us() : 0;
        if(s->managed_definition){
            /* A managed definition has persistent instance lifetime, but is
             * still playable. Preserve an existing voice and its parameter
             * bank; only a genuinely inactive instance needs construction. */
            if(!s->voice->active){
                float controls[FM_CONTROLS];memcpy(controls,s->voice->control,sizeof controls);
                if(s->control_index[2]>=0)controls[s->control_index[2]]=1;
                if(!start_controls(s,1,controls))break;
            }else if(s->rendered_gate>0 || (s->control_index[2]>=0 && s->voice->control[s->control_index[2]]>0)){
                s->gate_low_blocks=1;
            }
            s->buses[2]=1;s->note_id=e->note_id;s->touch_note_id=e->note_id;
            s->held=1;s->release_frames=0;
            if(s->control_index[2]>=0)s->voice->control[s->control_index[2]]=1;
            return 1;
        }
        if(s->bus_mode && s->voice->active){
            /* Preserve oscillator/effect state across ordinary touch gates.
             * If a release/retrigger fits in one block, deliver a low block
             * first so the SynthDef can observe the next rising edge. */
            if(s->rendered_gate>0)s->gate_low_blocks=1;
            s->buses[2]=1;s->note_id=e->note_id;s->held=1;s->release_frames=0;
            if(s->control_index[2]>=0)s->voice->control[s->control_index[2]]=1;
            return 1;
        }
        instrument_panic(s);
        if (!fm_start(s->voice, s->graph, (float)s->sample_rate)) break;
        s->preparing_memory=s->defer_note_render && s->arena_needed;
        if(!s->preparing_memory && !fm_bind_delay(s->voice,s->graph,s->arena,s->arena_samples))break;
        uint64_t reset_done=s->clock_us?s->clock_us():0;
        if(!start_seed(s,1))break;
        if(s->control_index[0]>=0)s->voice->control[s->control_index[0]]=s->frequency;
        if(s->control_index[1]>=0)s->voice->control[s->control_index[1]]=s->amplitude;
        if(s->control_index[2]>=0)s->voice->control[s->control_index[2]]=1;
        s->buses[2]=1;
        if(!fm_bind_control_buses(s->voice,s->buses,FM_CONTROL_BUSES))break;
        for (unsigned k = 0; k < 4; ++k)
            if (s->knob_mask & (1u << k)) s->voice->control[s->control_index[3+k]]=s->knob[k];
        uint64_t controls_done=s->clock_us?s->clock_us():0;
        if(!s->preparing_memory)fm_prepare(s->graph, s->voice, s->scratch);
        s->deferred_blocks=s->defer_note_render?1:0;
        if (s->clock_us) {
            uint64_t end=s->clock_us();
            s->reset_us=(uint32_t)(reset_done-begin);
            s->controls_us=(uint32_t)(controls_done-reset_done);
            s->prepare_us=(uint32_t)(end-controls_done);
            uint64_t elapsed = end - begin;
            if (elapsed > s->preparation_max_us)
                s->preparation_max_us = elapsed > UINT32_MAX ? UINT32_MAX : (uint32_t)elapsed;
        }
        if (s->voice->fault) { ++s->faults; instrument_panic(s); break; }
        s->note_id = e->note_id; s->held = 1; s->fade_frame = 0;
        return 1;
    }
    default: break;
    }
    ++s->rejected;
    return 0;
}

void instrument_pcm(const float stereo[FM_BLOCK * 2], int16_t mono[FM_BLOCK],
                    float gain, uint64_t *nonfinite, uint64_t *clipped)
{
    for (unsigned i = 0; i < FM_BLOCK; ++i) {
        float l = stereo[2*i], r = stereo[2*i+1];
        float x = (0.5f*l + 0.5f*r) * gain;
        if (!isfinite(l) || !isfinite(r) || !isfinite(x)) { x = 0; ++*nonfinite; }
        if (x > 1.0f) { x = 1.0f; ++*clipped; }
        if (x < -1.0f) { x = -1.0f; ++*clipped; }
        /* Explicit nearest/even rounding after finite checks and saturation.
         * Xtensa has fast bounded float/int conversions; lrintf takes a library
         * call for every sample. Keep the established quantization rule. */
        float scaled = x * 32767.0f;
        int32_t quantized = (int32_t)scaled;
        float fraction = scaled - (float)quantized;
        if (fraction > 0.5f || (fraction == 0.5f && (quantized & 1))) ++quantized;
        else if (fraction < -0.5f || (fraction == -0.5f && (quantized & 1))) --quantized;
        mono[i] = (int16_t)quantized;
    }
}

void instrument_pcm_stereo(const float stereo[FM_BLOCK*2],int16_t pcm[FM_BLOCK*2],float gain,uint64_t *nonfinite,uint64_t *clipped)
{
    for(unsigned i=0;i<FM_BLOCK*2;++i){
        float x=stereo[i]*gain;
        if(!isfinite(x)){x=0;++*nonfinite;}
        if(x>1){x=1;++*clipped;}if(x< -1){x=-1;++*clipped;}
        float scaled=x*32767.0f;int32_t q=(int32_t)scaled;float fraction=scaled-(float)q;
        if(fraction>.5f || (fraction==.5f && (q&1)))++q;
        else if(fraction< -.5f || (fraction== -.5f && (q&1)))--q;
        pcm[i]=(int16_t)q;
    }
}

void instrument_apply_batch(instrument *s, const inst_event *events, unsigned count)
{
    s->reset_us=s->controls_us=s->prepare_us=0;
    /* One voice admits only the newest start at a boundary. A later release
     * cancels that start and its implied steal, rather than resurrecting an
     * older pending/held note that the producer already replaced. */
    unsigned newest = count;
    for (unsigned i = 0; i < count; ++i)
        if (events[i].type == INST_NOTE_ON) newest = i;
    for (int kind = INST_NOTE_OFF; kind <= INST_NOTE_ON; ++kind) {
        for (unsigned i = 0; i < count; ++i) {
            if ((int)events[i].type != kind) continue;
            if(s->continuous && !s->managed_definition &&
               (kind==INST_NOTE_ON || kind==INST_NOTE_OFF))continue;
            int cancelled = 0;
            if (kind == INST_NOTE_ON) {
                if (i != newest) continue;
                for (unsigned j = i + 1; j < count; ++j)
                    if (events[j].type == INST_NOTE_OFF && events[j].note_id == events[i].note_id)
                        cancelled = 1;
            }
            if (cancelled) instrument_panic(s);
            else instrument_apply(s, &events[i]);
        }
    }
}

void instrument_render_stereo(instrument *s,float stereo[FM_BLOCK*2])
{
    uint64_t begin=s->clock_us?s->clock_us():0;
    memset(stereo,0,FM_BLOCK*2*sizeof(float));
    if(s->preparing_memory) {
        /* Clear at most 4 KiB per block. No allocation or whole-arena clear on
         * note-on; master effects can continue while this voice is prepared.
         * The final constructor pass gets its own silent block. */
        if(s->arena_cleared<s->arena_needed) {
            uint32_t count=s->arena_needed-s->arena_cleared;
            if(count>1024)count=1024;
            memset(s->arena+s->arena_cleared,0,count*sizeof(float));
            s->arena_cleared+=count;
        } else {
            int ok=fm_bind_delay_precleared(s->voice,s->graph,s->arena,s->arena_samples);
            if(ok)fm_prepare(s->graph,s->voice,s->scratch);
            s->preparing_memory=0;s->deferred_blocks=0;
            if(!ok || s->voice->fault) {++s->faults;instrument_panic(s);}
        }
        s->frame+=FM_BLOCK;
        if(s->clock_us)s->dsp_us=(uint32_t)(s->clock_us()-begin);
        return;
    }
    /* The target reserves the note-on block for construction; persistent bus
     * effects still render that block. Raw graph/reference callers default off. */
    if(s->deferred_blocks) {
        --s->deferred_blocks;s->frame+=FM_BLOCK;
        if(s->clock_us)s->dsp_us=(uint32_t)(s->clock_us()-begin);
        return;
    }
    if (s->voice->active) {
        float desired_gate=s->buses[2];
        unsigned restore_touch_gate=s->gate_low_blocks && s->managed_definition && s->held && s->note_id;
        if(s->gate_low_blocks){
            s->buses[2]=0;--s->gate_low_blocks;
            if(s->control_index[2]>=0)s->voice->control[s->control_index[2]]=0;
        }
        fm_render(s->graph, s->voice, s->scratch, stereo);
        s->rendered_gate=s->buses[2];s->buses[2]=desired_gate;
        if(((s->bus_mode && !s->continuous) || restore_touch_gate) && s->control_index[2]>=0)s->voice->control[s->control_index[2]]=desired_gate;
        if (s->voice->fault) {
            ++s->faults; instrument_panic(s); memset(stereo, 0, FM_BLOCK*2*sizeof(float));
        } else {
            for (unsigned i = 0; i < FM_BLOCK && s->fade_frame < 128; ++i, ++s->fade_frame) {
                float fade = (float)s->fade_frame / 128.0f;
                stereo[2*i] *= fade; stereo[2*i+1] *= fade;
            }
        }
        if (!s->held && !s->bus_mode && !s->continuous) {
            s->release_frames += FM_BLOCK;
            if (s->release_frames >= (uint64_t)s->sample_rate * 10) instrument_panic(s);
        }
    }
    if(s->clock_us)s->dsp_us=(uint32_t)(s->clock_us()-begin);
    s->frame += FM_BLOCK;
}
void instrument_render(instrument *s, int16_t mono[FM_BLOCK])
{
    float stereo[FM_BLOCK*2];instrument_render_stereo(s,stereo);
    uint64_t dsp_done=s->clock_us?s->clock_us():0;
    instrument_pcm(stereo, mono, s->master_gain, &s->nonfinite, &s->clipped);
    if(s->clock_us)s->pcm_us=(uint32_t)(s->clock_us()-dsp_done);
}
