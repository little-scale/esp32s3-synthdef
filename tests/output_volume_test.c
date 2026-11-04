/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "output_volume.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(void)
{
    output_volume v;float audio[FM_BLOCK*2];int16_t actual[FM_BLOCK],reference[FM_BLOCK],stereo[FM_BLOCK*2];
    uint64_t nonfinite=0,clipped=0,nref=0,cref=0;
    assert(OUTPUT_VOLUME_DEFAULT_PERCENT==20);
    output_volume_init(&v,OUTPUT_VOLUME_DEFAULT_PERCENT,44100);
    assert(fabsf(v.current-.2f)<1e-7f && v.target==v.current && !v.remaining);
    for(unsigned i=0;i<FM_BLOCK*2;++i)audio[i]=.5f;
    output_volume_pcm(&v,OUTPUT_VOLUME_DEFAULT_PERCENT,audio,actual,1,&nonfinite,&clipped);
    for(unsigned i=0;i<FM_BLOCK;++i)assert(actual[i]==3277);
    output_volume_pcm_stereo(&v,OUTPUT_VOLUME_DEFAULT_PERCENT,audio,stereo,1,&nonfinite,&clipped);
    for(unsigned i=0;i<FM_BLOCK*2;++i)assert(stereo[i]==3277);
    output_volume_init(&v,100,44100);
    for(unsigned b=0;b<200;++b){
        for(unsigned i=0;i<FM_BLOCK*2;++i)audio[i]=sinf((b*FM_BLOCK*2+i)*.017f)*1.2f;
        instrument_pcm(audio,reference,.75f,&nref,&cref);
        output_volume_pcm(&v,100,audio,actual,.75f,&nonfinite,&clipped);
        assert(!memcmp(actual,reference,sizeof actual));
    }
    assert(nonfinite==nref && clipped==cref);
    for(unsigned i=0;i<FM_BLOCK*2;++i)audio[i]=.5f;
    int previous=32767;unsigned frames=0;
    while(frames<1024){
        output_volume_pcm(&v,0,audio,actual,1,&nonfinite,&clipped);
        for(unsigned i=0;i<FM_BLOCK;++i){assert(actual[i]<=previous && actual[i]>=0);previous=actual[i];}
        frames+=FM_BLOCK;
    }
    assert(v.current==0 && !v.remaining && previous==0);
    output_volume_pcm(&v,100,audio,actual,1,&nonfinite,&clipped);float mid=v.current;
    output_volume_pcm(&v,0,audio,actual,1,&nonfinite,&clipped);assert(v.current<mid && v.current>0);
    output_volume_init(&v,50,44100);output_volume_pcm(&v,50,audio,actual,1,&nonfinite,&clipped);
    instrument_pcm(audio,reference,.5f,&nref,&cref);assert(!memcmp(actual,reference,sizeof actual));
    audio[0]=NAN;audio[1]=INFINITY;
    output_volume_pcm(&v,50,audio,actual,1,&nonfinite,&clipped);assert(!actual[0] && nonfinite==1);
    output_volume_init(&v,100,44100);nonfinite=clipped=0;
    for(unsigned i=0;i<FM_BLOCK;++i){audio[2*i]=.25f;audio[2*i+1]=-.75f;}
    output_volume_pcm_stereo(&v,100,audio,stereo,1,&nonfinite,&clipped);
    for(unsigned i=0;i<FM_BLOCK;++i){assert(stereo[2*i]==8192);assert(stereo[2*i+1]==-24575);}
    assert(!nonfinite && !clipped);
    /* All UI percentages match the linear amplitude underlying the dB readout. */
    for(unsigned percent=0;percent<=100;++percent){
        output_volume_init(&v,percent,44100);
        output_volume_pcm_stereo(&v,percent,audio,stereo,1,&nonfinite,&clipped);
        int left=(int)lrintf(.25f*(percent*.01f)*32767.f);
        int right=(int)lrintf(-.75f*(percent*.01f)*32767.f);
        for(unsigned i=0;i<FM_BLOCK;++i){assert(abs(stereo[2*i]-left)<=1);assert(abs(stereo[2*i+1]-right)<=1);}
    }
    audio[1]=NAN;output_volume_pcm_stereo(&v,100,audio,stereo,1,&nonfinite,&clipped);
    assert(stereo[0]==8192 && !stereo[1] && nonfinite==1);
    for(unsigned i=0;i<FM_BLOCK*2;++i)audio[i]=.5f;
    previous=32767;
    for(unsigned b=0;b<16;++b){
        output_volume_pcm_stereo(&v,0,audio,stereo,1,&nonfinite,&clipped);
        for(unsigned i=0;i<FM_BLOCK;++i){assert(stereo[2*i]==stereo[2*i+1] && stereo[2*i]<=previous && stereo[2*i]>=0);previous=stereo[2*i];}
    }
    assert(!v.remaining && !v.current && !previous);
    puts("PASS: mono output stays bit-exact; stereo preserves channel separation; both formats ramp smoothly, saturate and protect nonfinite output.");
}
