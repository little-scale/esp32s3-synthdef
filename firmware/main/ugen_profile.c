/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "sdkconfig.h"
#ifdef CONFIG_SYNTHDEF_DIAGNOSTICS
#include "diagnostics.h"
#include "esp_cpu.h"
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Only this diagnostic uses the separately instrumented renderer. */
extern void fm_ugen_render(const fm_graph *,fm_voice *,fm_scratch *,float *);
extern uint64_t fm_ugen_cycles[FM_NODES];
extern uint32_t fm_ugen_calls[FM_NODES];
enum { PROFILE_BLOCKS=1024,WARM_BLOCKS=128 };
static struct {
    const fm_graph *graph;
    uint64_t normal,measured;
    uint32_t hash[2],state[2],arena[2];
    unsigned ready,matched;
} result;

static uint32_t digest(uint32_t h,const void *data,size_t bytes)
{
    const unsigned char *p=data;
    for(size_t i=0;i<bytes;++i)h=(h^p[i])*16777619u;
    return h;
}
int diagnostic_ugen_profile(instrument *s)
{
    memset(&result,0,sizeof result);result.graph=s->graph;
    size_t arena_bytes=(size_t)s->arena_needed*sizeof(float);
    fm_voice *backup=heap_caps_malloc(sizeof *backup,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    void *arena=arena_bytes?heap_caps_malloc(arena_bytes,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT):NULL;
    fm_scratch *scratch=heap_caps_malloc(sizeof *scratch,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!backup || (arena_bytes && !arena) || !scratch){free(backup);free(arena);free(scratch);return 1;}
    memcpy(backup,s->voice,sizeof *backup);memcpy(scratch,s->scratch,sizeof *scratch);
    if(arena_bytes)memcpy(arena,s->arena,arena_bytes);
    for(unsigned pass=0;pass<2;++pass){
        memcpy(s->voice,backup,sizeof *backup);memcpy(s->scratch,scratch,sizeof *scratch);
        if(arena_bytes)memcpy(s->arena,arena,arena_bytes);
        s->voice->active=1;
        float out[FM_BLOCK*2];
        for(unsigned b=0;b<WARM_BLOCKS;++b){memset(out,0,sizeof out);fm_render(s->graph,s->voice,s->scratch,out);}
        memset(fm_ugen_cycles,0,FM_NODES*sizeof *fm_ugen_cycles);
        memset(fm_ugen_calls,0,FM_NODES*sizeof *fm_ugen_calls);
        uint64_t total=0;uint32_t hash=2166136261u;
        for(unsigned b=0;b<PROFILE_BLOCKS;++b){
            memset(out,0,sizeof out);uint32_t begin=esp_cpu_get_cycle_count();
            if(pass)fm_ugen_render(s->graph,s->voice,s->scratch,out);
            else fm_render(s->graph,s->voice,s->scratch,out);
            total+=(uint32_t)(esp_cpu_get_cycle_count()-begin);
            hash=digest(hash,out,sizeof out);
            if((b&63)==63)vTaskDelay(1);
        }
        if(pass)result.measured=total;else result.normal=total;
        result.hash[pass]=hash;result.state[pass]=digest(2166136261u,s->voice,sizeof *s->voice);
        result.arena[pass]=arena_bytes?digest(2166136261u,s->arena,arena_bytes):0;
        if(s->voice->fault || !s->voice->active)break;
        result.ready=pass+1;
    }
    result.matched=result.ready==2 && result.hash[0]==result.hash[1] &&
        result.state[0]==result.state[1] && result.arena[0]==result.arena[1];
    memcpy(s->voice,backup,sizeof *backup);memcpy(s->scratch,scratch,sizeof *scratch);
    if(arena_bytes)memcpy(s->arena,arena,arena_bytes);
    free(backup);free(arena);free(scratch);return 1;
}
void diagnostic_ugen_report(void)
{
    printf("UGEN_PROFILE graph=%s blocks=%u ready=%u matched=%u normal_cycles=%" PRIu64 " measured_cycles=%" PRIu64 " audio_hash=%08" PRIx32 "\n",
           result.graph->name,PROFILE_BLOCKS,result.ready,result.matched,result.normal,result.measured,result.hash[0]);
    if(result.ready==2)for(unsigned i=0;i<result.graph->nodes;++i){
        const fm_node *n=&result.graph->node[i];
        printf("UGEN_NODE index=%u type=%s rate=%u special=%d cycles=%" PRIu64 " calls=%" PRIu32 "\n",
               i,fm_type_name(n->type),n->rate,n->special,fm_ugen_cycles[i],fm_ugen_calls[i]);
    }
    puts("UGEN_END");
}
#endif
