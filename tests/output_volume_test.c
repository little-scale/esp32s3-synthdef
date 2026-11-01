/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "output_volume.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
int main(void)
{
    output_volume v;float audio[FM_BLOCK*2];int16_t actual[FM_BLOCK],reference[FM_BLOCK];
    uint64_t nonfinite=0,clipped=0,nref=0,cref=0;
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
    puts("PASS: unity output is bit-exact, half volume scales correctly, mute ramps monotonically in 20 ms, changes reverse from the current gain, nonfinite output stays protected.");
}
