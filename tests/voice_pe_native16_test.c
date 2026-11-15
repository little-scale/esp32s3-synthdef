/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Rate integration smoke test, not an audio-quality or hardware benchmark. */
#include "fm_synth.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static fm_graph g;
static fm_voice v;
static fm_scratch s;
static uint64_t render(unsigned rate,float *arena,unsigned capacity,float *peak)
{
    assert(fm_start(&v,&g,rate));
    assert(fm_bind_delay(&v,&g,arena,capacity));
    assert(fm_seed(&v,12345));
    float buses[FM_CONTROL_BUSES]={0};buses[1]=.5f;
    assert(fm_bind_control_buses(&v,buses,FM_CONTROL_BUSES));
    fm_prepare(&g,&v,&s);
    uint64_t hash=UINT64_C(14695981039346656037);
    for(unsigned at=0;at<rate*4;at+=FM_BLOCK){
        float audio[FM_BLOCK*2]={0},input[FM_BLOCK*2];
        for(unsigned i=0;i<FM_BLOCK;++i){
            input[2*i]=.03f*sinf(6.283185307179586f*330*(at+i)/rate);
            input[2*i+1]=.03f*sinf(6.283185307179586f*550*(at+i)/rate);
        }
        fm_render_input(&g,&v,&s,audio,input);assert(!v.fault);
        for(unsigned i=0;i<FM_BLOCK*2;++i){
            assert(isfinite(audio[i]) && fabsf(audio[i])<10000);
            if(fabsf(audio[i])>*peak)*peak=fabsf(audio[i]);
            uint32_t bits;memcpy(&bits,&audio[i],sizeof bits);
            hash=(hash^bits)*UINT64_C(1099511628211);
        }
        for(unsigned i=0;i<FM_CONTROL_OUTPUTS;++i)assert(isfinite(v.control_outputs[i]));
    }
    return hash;
}
int main(int argc,char **argv)
{
    assert(argc>1);
    for(int p=1;p<argc;++p){
        FILE *f=fopen(argv[p],"rb");assert(f);unsigned char bytes[FM_FILE_BYTES];
        size_t n=fread(bytes,1,sizeof bytes,f);assert(!ferror(f));fclose(f);
        char error[160];assert(fm_load(&g,bytes,n,error,sizeof error));
        const unsigned rates[]={16000,48000};
        for(unsigned k=0;k<2;++k){
            unsigned capacity=fm_delay_required(&g,rates[k]);assert(capacity!=UINT32_MAX);
            float *arena=calloc(capacity?capacity:1,sizeof *arena);assert(arena);
            float peak=0;uint64_t a=render(rates[k],arena,capacity,&peak);
            memset(arena,0,(capacity?capacity:1)*sizeof *arena);
            uint64_t b=render(rates[k],arena,capacity,&peak);assert(a==b);
            printf("%s %u Hz: peak=%g delay_floats=%u repeat_hash=%016llx\n",argv[p],rates[k],peak,capacity,(unsigned long long)a);
            free(arena);
        }
    }
    puts("PASS: finite audio/control outputs, bounded arenas, seeded restart determinism at 16/48k");
}
