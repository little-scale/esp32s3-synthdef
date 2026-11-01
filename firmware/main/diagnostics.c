/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "sdkconfig.h"
#ifdef CONFIG_SYNTHDEF_DIAGNOSTICS
#include "diagnostics.h"
#include "trace_probe.h"
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
static unsigned delay_failures;
static trace_summary trace_result;
static int trace_passed;
static const float delay_times[]={.02f,.35f,1,5};
enum { DELAY_WINDOWS=4,DELAY_CASE_FLOATS=4*FM_BLOCK };
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

void diagnostic_delay(master_delay *bus,fm_scratch *scratch)
{
    float saved[3];memcpy(saved,bus->value,sizeof saved);delay_failures=0;
    float *captured=(float *)waveforms;
    memset(captured,0,4*DELAY_CASE_FLOATS*sizeof(float));
    for(unsigned c=0;c<4;++c) {
        master_delay_set(bus,0,delay_times[c]);master_delay_set(bus,1,.35f);master_delay_set(bus,2,1);
        if(!master_delay_reset(bus,scratch)) {++delay_failures;continue;}
        unsigned distance=(unsigned)lroundf(delay_times[c]*44100);
        unsigned start[]={0,distance-16,2*distance-16};
        for(unsigned base=0;base<2*distance+FM_BLOCK;base+=FM_BLOCK) {
            float input[FM_BLOCK*2]={0},output[FM_BLOCK*2];if(!base)input[0]=input[1]=.25f;
            master_delay_render(bus,scratch,input,output);
            for(unsigned j=0;j<FM_BLOCK;++j)for(unsigned w=0;w<3;++w)
                if(base+j>=start[w] && base+j<start[w]+FM_BLOCK)
                    captured[c*DELAY_CASE_FLOATS+w*FM_BLOCK+base+j-start[w]]=.5f*(output[2*j]+output[2*j+1]);
            if((base/FM_BLOCK)%64==0)vTaskDelay(1);
        }
        master_delay_panic(bus);float input[FM_BLOCK*2]={0},output[FM_BLOCK*2];
        master_delay_render(bus,scratch,input,output);
        for(unsigned j=0;j<FM_BLOCK;++j) {captured[c*DELAY_CASE_FLOATS+3*FM_BLOCK+j]=output[2*j];if(output[2*j]!=0)++delay_failures;}
        if(bus->faults)++delay_failures;
    }
    for(unsigned k=0;k<3;++k)master_delay_set(bus,k,saved[k]);
    if(!master_delay_reset(bus,scratch))++delay_failures;
}
void diagnostic_delay_report(void)
{
    printf("DELAY_BENCH_BEGIN cases=4 rate=44100 floats_per_case=%u failures=%u\n",DELAY_CASE_FLOATS,delay_failures);
    for(unsigned c=0;c<4;++c) {
        const unsigned char *data=waveforms+c*DELAY_CASE_FLOATS*sizeof(float);
        char hex[DELAY_CASE_FLOATS*sizeof(float)*2+1];
        for(unsigned k=0;k<DELAY_CASE_FLOATS*sizeof(float);++k)snprintf(hex+2*k,3,"%02x",data[k]);
        printf("DELAY_BENCH_PCM %u %08lx %s\n",c,(unsigned long)patch_crc32(data,DELAY_CASE_FLOATS*sizeof(float)),hex);
    }
    puts("DELAY_BENCH_END");
}
static unsigned buses_passed,buses_max_us;
static const unsigned bus_windows[]={63,127,255,447};
void diagnostic_control_buses(instrument *s)
{
    instrument saved=*s;float bank[FM_CONTROL_BUSES]={0},out[FM_BLOCK*2];unsigned window=0;
    buses_passed=s->bus_mode && fm_start(s->voice,s->graph,(float)s->sample_rate) &&
        fm_bind_delay(s->voice,s->graph,s->arena,s->arena_samples) &&
        fm_bind_control_buses(s->voice,bank,FM_CONTROL_BUSES);
    buses_max_us=0;bank[0]=.25f;bank[1]=.7f;bank[2]=1;
    for(unsigned b=0;b<448 && buses_passed;++b){
        if(b==64)bank[0]=.8f;
        if(b==128)bank[1]=.2f;
        if(b==192)bank[2]=0;
        if(b==256){bank[0]=.5f;bank[1]=.7f;bank[2]=1;}
        if(b==320)bank[2]=0;
        memset(out,0,sizeof out);uint64_t begin=clock_us();fm_render(s->graph,s->voice,s->scratch,out);
        unsigned elapsed=(unsigned)(clock_us()-begin);if(elapsed>buses_max_us)buses_max_us=elapsed;
        if(s->voice->fault)buses_passed=0;
        if(window<4 && b==bus_windows[window]){memcpy(waveforms+window*sizeof out,out,sizeof out);++window;}
        if(b%16==0)vTaskDelay(1);
    }
    if(window!=4)buses_passed=0;
    *s=saved;instrument_panic(s);
}
void diagnostic_control_buses_report(void)
{
    printf("BUSES_BEGIN passed=%u blocks=448 windows=4 max_us=%u\n",buses_passed,buses_max_us);
    if(buses_passed)for(unsigned w=0;w<4;++w){
        const unsigned char *data=waveforms+w*FM_BLOCK*2*sizeof(float);char hex[FM_BLOCK*2*sizeof(float)*2+1];
        for(unsigned i=0;i<FM_BLOCK*2*sizeof(float);++i)snprintf(hex+i*2,3,"%02x",data[i]);
        printf("BUSES_BLOCK %u %u %08lx %s\n",w,bus_windows[w],(unsigned long)patch_crc32(data,FM_BLOCK*2*sizeof(float)),hex);
    }puts("BUSES_END");
}
static void trace_yield(void) {vTaskDelay(1);}
void diagnostic_trace(instrument *s)
{
    /* Parked/muted diagnostic only: temporary full arena plus two canaries.
     * Production voice pools and their real-time allocation policy are intact. */
    float *arena=heap_caps_malloc((FM_DELAY_LIMIT+2)*sizeof(float),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    memset(&trace_result,0,sizeof trace_result);trace_passed=0;
    if(arena) {
        trace_passed=trace_probe(s->graph,s->voice,s->scratch,arena,FM_DELAY_LIMIT+2,
                                 (float *)waveforms,&trace_result,clock_us,trace_yield);
        heap_caps_free(arena);
    }
    instrument_panic(s);
}
void diagnostic_trace_report(void)
{
    trace_summary *s=&trace_result;
    printf("TRACE_BEGIN passed=%u blocks=%lu windows=%u rate=44100 block=64 faults=%lu nonfinite=%lu guards=%lu updates=%lu rejected=%lu initial_rejections=%lu initial_accepts=%lu restarts=%lu max_us=%lu peak=%.9g rms=%.9g\n",
        trace_passed, (unsigned long)s->blocks,TRACE_WINDOWS,(unsigned long)s->faults,(unsigned long)s->nonfinite,
        (unsigned long)s->guard_failures,(unsigned long)s->event_updates,(unsigned long)s->event_rejections,
        (unsigned long)s->initial_rejections,(unsigned long)s->unexpected_initial_accepts,(unsigned long)s->restarts,
        (unsigned long)s->max_render_us,s->peak,s->rms);
    for(unsigned w=0;w<TRACE_WINDOWS;++w) {
        const unsigned char *data=waveforms+w*FM_BLOCK*2*sizeof(float);char hex[FM_BLOCK*2*sizeof(float)*2+1];
        for(unsigned i=0;i<FM_BLOCK*2*sizeof(float);++i)snprintf(hex+2*i,3,"%02x",data[i]);
        printf("TRACE_BLOCK %u %u %08lx %s\n",w,trace_windows[w],(unsigned long)patch_crc32(data,FM_BLOCK*2*sizeof(float)),hex);
    }
    puts("TRACE_END");
}
#endif
