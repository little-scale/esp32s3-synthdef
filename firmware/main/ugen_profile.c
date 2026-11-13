/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "sdkconfig.h"
#ifdef CONFIG_SYNTHDEF_DIAGNOSTICS
#include "diagnostics.h"
#include "fm_build_profile.h"
#include "esp_cpu.h"
#include "esp_private/esp_clk.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"
#include "mbedtls/sha256.h"
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
enum { PROFILE_BLOCKS=1024,WARM_BLOCKS=128,PROFILE_SEED=12345 };
static struct {
    const fm_graph *graph;
    uint64_t normal,measured,wall[2];
    uint32_t hash[2],state[2],arena[2],scratch[2],rng[2][3];
    unsigned char warm_sha[2][32],audio_sha[2][32];
    unsigned ready,matched,fixed,cpu_mhz,rate;
} result;

static uint32_t digest(uint32_t h,const void *data,size_t bytes)
{
    const unsigned char *p=data;
    for(size_t i=0;i<bytes;++i)h=(h^p[i])*16777619u;
    return h;
}
static int profile(instrument *s,unsigned fixed)
{
    memset(&result,0,sizeof result);result.graph=s->graph;result.fixed=fixed;result.rate=s->sample_rate;
    result.cpu_mhz=esp_clk_cpu_freq()/1000000;
    uint32_t need=fm_delay_required(s->graph,s->sample_rate);
    if(need>s->arena_samples || s->arena_needed>s->arena_samples)return 1;
    size_t arena_bytes=(size_t)(need>s->arena_needed?need:s->arena_needed)*sizeof(float);
    fm_voice *backup=heap_caps_malloc(sizeof *backup,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    void *arena=arena_bytes?heap_caps_malloc(arena_bytes,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT):NULL;
    fm_scratch *scratch=heap_caps_malloc(sizeof *scratch,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!backup || (arena_bytes && !arena) || !scratch){free(backup);free(arena);free(scratch);return 1;}
    memcpy(backup,s->voice,sizeof *backup);memcpy(scratch,s->scratch,sizeof *scratch);
    if(arena_bytes)memcpy(arena,s->arena,arena_bytes);
    float buses[FM_CONTROL_BUSES]={0};
    for(unsigned pass=0;pass<2;++pass){
        memcpy(s->voice,backup,sizeof *backup);memcpy(s->scratch,scratch,sizeof *scratch);
        if(arena_bytes)memcpy(s->arena,arena,arena_bytes);
        if(fixed){
            if(!fm_start(s->voice,s->graph,s->sample_rate) || !fm_seed(s->voice,PROFILE_SEED) ||
               !fm_bind_delay(s->voice,s->graph,s->arena,s->arena_samples) ||
               !fm_bind_control_buses(s->voice,buses,FM_CONTROL_BUSES))break;
            memset(s->scratch,0,sizeof *s->scratch);
            fm_prepare(s->graph,s->voice,s->scratch);fm_prepare(s->graph,s->voice,s->scratch);
        }
        s->voice->active=1;
        float out[FM_BLOCK*2];
        mbedtls_sha256_context sha;mbedtls_sha256_init(&sha);
        int ok=mbedtls_sha256_starts(&sha,0)==0;
        for(unsigned b=0;b<WARM_BLOCKS && ok;++b){
            memset(out,0,sizeof out);fm_render(s->graph,s->voice,s->scratch,out);
            ok=mbedtls_sha256_update(&sha,(const unsigned char *)out,sizeof out)==0;
        }
        ok=ok && mbedtls_sha256_finish(&sha,result.warm_sha[pass])==0;
        ok=ok && mbedtls_sha256_starts(&sha,0)==0;
        memset(fm_ugen_cycles,0,FM_NODES*sizeof *fm_ugen_cycles);
        memset(fm_ugen_calls,0,FM_NODES*sizeof *fm_ugen_calls);
        uint64_t total=0;uint32_t hash=2166136261u;
        for(unsigned b=0;b<PROFILE_BLOCKS && ok;++b){
            memset(out,0,sizeof out);int64_t wall_begin=esp_timer_get_time();uint32_t begin=esp_cpu_get_cycle_count();
            if(pass)fm_ugen_render(s->graph,s->voice,s->scratch,out);
            else fm_render(s->graph,s->voice,s->scratch,out);
            total+=(uint32_t)(esp_cpu_get_cycle_count()-begin);
            result.wall[pass]+=esp_timer_get_time()-wall_begin;
            hash=digest(hash,out,sizeof out);
            ok=mbedtls_sha256_update(&sha,(const unsigned char *)out,sizeof out)==0;
            if((b&63)==63)vTaskDelay(1);
        }
        ok=ok && mbedtls_sha256_finish(&sha,result.audio_sha[pass])==0;
        mbedtls_sha256_free(&sha);
        if(pass)result.measured=total;else result.normal=total;
        result.hash[pass]=hash;result.state[pass]=digest(2166136261u,s->voice,sizeof *s->voice);
        result.arena[pass]=arena_bytes?digest(2166136261u,s->arena,arena_bytes):0;
        result.scratch[pass]=digest(2166136261u,s->scratch,sizeof *s->scratch);
        memcpy(result.rng[pass],s->voice->random,sizeof result.rng[pass]);
        if(!ok || s->voice->fault || !s->voice->active)break;
        result.ready=pass+1;
    }
    result.matched=result.ready==2 && result.hash[0]==result.hash[1] &&
        result.state[0]==result.state[1] && result.arena[0]==result.arena[1] && result.scratch[0]==result.scratch[1] &&
        !memcmp(result.warm_sha[0],result.warm_sha[1],32) && !memcmp(result.audio_sha[0],result.audio_sha[1],32);
    memcpy(s->voice,backup,sizeof *backup);memcpy(s->scratch,scratch,sizeof *scratch);
    if(arena_bytes)memcpy(s->arena,arena,arena_bytes);
    free(backup);free(arena);free(scratch);return 1;
}
int diagnostic_ugen_profile(instrument *s){return profile(s,0);}
int diagnostic_ugen_profile_seeded(instrument *s){return profile(s,1);}
void diagnostic_ugen_report(void)
{
    printf("UGEN_PROFILE graph=%s blocks=%u ready=%u matched=%u normal_cycles=%" PRIu64 " measured_cycles=%" PRIu64 " audio_hash=%08" PRIx32 "\n",
           result.graph->name,PROFILE_BLOCKS,result.ready,result.matched,result.normal,result.measured,result.hash[0]);
    printf("UGEN_SETUP mode=%s seed=%u warm_blocks=%u rate=%u frames=%u nodes=%u cpu_mhz=%u qualified=%u mix=%u normal_wall_us=%" PRIu64 " measured_wall_us=%" PRIu64 " warm_sha256=",
           result.fixed?"fixed":"snapshot",result.fixed?PROFILE_SEED:0,WARM_BLOCKS,result.rate,FM_BLOCK,result.graph->nodes,result.cpu_mhz,FM_QUALIFIED_KERNELS_ENABLED,FM_MIX_KERNELS_ENABLED,result.wall[0],result.wall[1]);
    for(unsigned i=0;i<32;++i)printf("%02x",result.warm_sha[0][i]);
    printf(" audio_sha256=");for(unsigned i=0;i<32;++i)printf("%02x",result.audio_sha[0][i]);
    printf(" rng=%08" PRIx32 ":%08" PRIx32 ":%08" PRIx32 "\n",result.rng[0][0],result.rng[0][1],result.rng[0][2]);
    if(result.ready==2)for(unsigned i=0;i<result.graph->nodes;++i){
        const fm_node *n=&result.graph->node[i];
        printf("UGEN_NODE index=%u type=%s rate=%u special=%d cycles=%" PRIu64 " calls=%" PRIu32 "\n",
               i,fm_type_name(n->type),n->rate,n->special,fm_ugen_cycles[i],fm_ugen_calls[i]);
    }
    puts("UGEN_END");
}
#endif
