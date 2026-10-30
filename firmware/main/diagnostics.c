/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "sdkconfig.h"
#ifdef CONFIG_SYNTHDEF_DIAGNOSTICS
#include "diagnostics.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"
#include "patch_format.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
typedef struct {
    float frequency,pitch,timbre,attack,release;
    uint32_t reset,controls,prepare,dsp,pcm,total,live;
} bench_result;
static bench_result *results;
static uint32_t pow_time,exp2_time;
static unsigned failures;
static unsigned char *waveforms;
enum { CASE_BYTES=FM_BLOCK*2*3, CASES=5*7*2*2*2 };
int diagnostic_init(void)
{
    results=heap_caps_malloc(CASES*sizeof *results,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    waveforms=heap_caps_malloc(CASES*CASE_BYTES,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    return results!=NULL && waveforms!=NULL;
}
static uint64_t clock_us(void) {return esp_timer_get_time();}
static void apply(instrument *s,inst_event_type type,float v) {inst_event e={type,1,v};if(!instrument_apply(s,&e))++failures;}

/* Invoked only on the parked audio owner. Reuses its preallocated voice and
 * scratch; output is discarded, no I2C/flash or logging occurs in this routine.
 * Restore controls/counters and leave the voice inactive before returning. */
void diagnostic_benchmark(instrument *s)
{
    instrument saved=*s,trial;int16_t pcm[FM_BLOCK];unsigned index=0;
    static const float pitches[]={0,.13f,.37f,.5f,.63f,.87f,1};
    static const float frequencies[]={20,110,440,1760,20000};
    failures=0;
    for(unsigned f=0;f<5;++f)for(unsigned p=0;p<7;++p)for(unsigned t=0;t<2;++t)for(unsigned a=0;a<2;++a)for(unsigned r=0;r<2;++r) {
        bench_result *result=&results[index++];
        result->frequency=frequencies[f];result->pitch=pitches[p];result->timbre=(float)t;result->attack=(float)a;result->release=(float)r;
        if(!instrument_init(&trial,saved.graph,saved.voice,saved.scratch,saved.arena,saved.arena_samples,saved.sample_rate)) {++failures;continue;}
        trial.clock_us=clock_us;
        apply(&trial,INST_FREQ,result->frequency);apply(&trial,INST_KNOB1,result->pitch);
        apply(&trial,INST_KNOB2,result->timbre);apply(&trial,INST_KNOB3,result->attack);apply(&trial,INST_KNOB4,result->release);
        uint64_t begin=clock_us();apply(&trial,INST_NOTE_ON,0);instrument_render(&trial,pcm);
        result->total=(uint32_t)(clock_us()-begin);result->reset=trial.reset_us;
        result->controls=trial.controls_us;result->prepare=trial.prepare_us;
        result->dsp=trial.dsp_us;result->pcm=trial.pcm_us;
        memcpy(waveforms+(index-1)*CASE_BYTES,pcm,sizeof pcm);
        begin=clock_us();apply(&trial,INST_KNOB1,1-result->pitch);apply(&trial,INST_KNOB2,1-result->timbre);instrument_render(&trial,pcm);
        result->live=(uint32_t)(clock_us()-begin);
        memcpy(waveforms+(index-1)*CASE_BYTES+sizeof pcm,pcm,sizeof pcm);
        apply(&trial,INST_NOTE_OFF,0);instrument_render(&trial,pcm);
        memcpy(waveforms+(index-1)*CASE_BYTES+2*sizeof pcm,pcm,sizeof pcm);
        if(trial.faults || trial.nonfinite || trial.clipped)++failures;
        if(index%8==0)vTaskDelay(1);
    }
    float (*volatile power)(float,float)=powf;
    float (*volatile exponential)(float)=exp2f;
    volatile float sink=0;
    uint64_t begin=clock_us();
    for(unsigned i=0;i<512;++i)sink=power(2,((float)(i%199)-99)/100);
    pow_time=(uint32_t)(clock_us()-begin);begin=clock_us();
    for(unsigned i=0;i<512;++i)sink=exponential(((float)(i%199)-99)/100);
    exp2_time=(uint32_t)(clock_us()-begin);(void)sink;
    *s=saved;instrument_panic(s);
}
void diagnostic_report(void)
{
    printf("BENCH_BEGIN cases=%u rate=44100 block=64 failures=%u pow512_us=%lu exp2512_us=%lu\n",CASES,failures,(unsigned long)pow_time,(unsigned long)exp2_time);
    for(unsigned i=0;i<CASES;++i) {
        bench_result *r=&results[i];
        printf("BENCH_CASE %u freq=%.0f pitch=%.2f timbre=%.0f attack=%.0f release=%.0f reset=%lu controls=%lu prepare=%lu dsp=%lu pcm=%lu total=%lu live=%lu\n",i,r->frequency,r->pitch,r->timbre,r->attack,r->release,(unsigned long)r->reset,(unsigned long)r->controls,(unsigned long)r->prepare,(unsigned long)r->dsp,(unsigned long)r->pcm,(unsigned long)r->total,(unsigned long)r->live);
        char hex[CASE_BYTES*2+1];
        for(unsigned k=0;k<CASE_BYTES;++k)snprintf(hex+2*k,3,"%02x",waveforms[i*CASE_BYTES+k]);
        printf("BENCH_PCM %u %08lx %s\n",i,(unsigned long)patch_crc32(waveforms+i*CASE_BYTES,CASE_BYTES),hex);
    }
    puts("BENCH_END");
}
#endif
