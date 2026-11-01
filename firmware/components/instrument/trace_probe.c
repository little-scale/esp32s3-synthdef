/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "trace_probe.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>
const uint16_t trace_windows[TRACE_WINDOWS]={0,1,2,3,4,7,8,15,16,31,63,64,127,172,344,516,688,1023,1024,1722,2047,2048,2755,3444,3445,3446,4095,4096,4097,4098,4268,4440,5120,6143,6890,6891,7540,7541,7542,8191};
int trace_probe(const fm_graph *g,fm_voice *v,fm_scratch *scratch,float *arena,uint32_t capacity,
                float capture[TRACE_FLOATS],trace_summary *s,uint64_t (*clock_us)(void),void (*yield_fn)(void))
{
    memset(s,0,sizeof *s);memset(capture,0,TRACE_FLOATS*sizeof(float));
    if(!arena || capacity<2)return 0;
    arena[0]=12345.5f;arena[capacity-1]=-5678.25f;
    if(!fm_start(v,g,44100) || !fm_bind_delay(v,g,arena+1,capacity-2) || !fm_seed(v,0))return 0;
    int rate_probe=!strncmp(g->name,"rate-probe-",11);
    unsigned window=0;float energy=0,compensation=0;
    for(unsigned block=0;block<TRACE_BLOCKS;++block) {
        if(rate_probe && block==4096) {
            if(!fm_start(v,g,44100) || !fm_bind_delay(v,g,arena+1,capacity-2) || !fm_seed(v,0))return 0;
            if(!fm_set(v,g,"probe_initial",.75f) || !fm_set(v,g,"probe_live",.75f))return 0;
            ++s->restarts;
        }
        if(rate_probe && (block==4 || block==8 || block==16 || block==64 || block==344)) {
            float value=block==8?.5f:(block==16 || block==344)?.25f:.75f;
            if(fm_set(v,g,"probe_live",value))++s->event_updates;else ++s->event_rejections;
            if(fm_set(v,g,"probe_initial",value))++s->unexpected_initial_accepts;else ++s->initial_rejections;
        }
        for(unsigned n=0;n<g->names;++n) {
            const char *name=g->control_name[n].name;
            if(!strncmp(name,"trace_ev_",9) && strtoul(name+9,NULL,10)==block) {
                float value=g->defaults[g->control_name[n].index];
                if(fm_set(v,g,"src_gate",value))++s->event_updates;else ++s->event_rejections;
            }
        }
        float input[FM_BLOCK*2]={0},out[FM_BLOCK*2]={0};
        if(block==0 || block==1722)input[0]=input[1]=block==0?.25f:.125f;
        uint64_t begin=clock_us?clock_us():0;
        fm_render_input(g,v,scratch,out,input);
        if(clock_us) {uint64_t elapsed=clock_us()-begin;if(elapsed>s->max_render_us)s->max_render_us=(uint32_t)elapsed;}
        if(window<TRACE_WINDOWS && block==trace_windows[window]) {
            memcpy(capture+window*FM_BLOCK*2,out,sizeof out);++window;
        }
        float block_energy=0;
        for(unsigned i=0;i<FM_BLOCK*2;++i) {
            float x=out[i];if(!isfinite(x)) {++s->nonfinite;continue;}
            if(fabsf(x)>s->peak)s->peak=fabsf(x);
            block_energy+=x*x;
        }
        float corrected=block_energy-compensation,next=energy+corrected;
        compensation=(next-energy)-corrected;energy=next;
        if(v->fault)++s->faults;
        if(arena[0]!=12345.5f || arena[capacity-1]!=-5678.25f)++s->guard_failures;
        ++s->blocks;
        if(yield_fn && !(block%32))yield_fn();
    }
    s->rms=sqrtf(energy/(TRACE_BLOCKS*FM_BLOCK*2u));
    v->active=0;
    return window==TRACE_WINDOWS && !s->faults && !s->nonfinite && !s->guard_failures && !s->unexpected_initial_accepts;
}
