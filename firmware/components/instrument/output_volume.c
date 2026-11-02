/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "output_volume.h"
void output_volume_init(output_volume *v,unsigned percent,unsigned rate)
{
    if(percent>100)percent=100;
    *v=(output_volume){.current=percent*.01f,.target=percent*.01f,
                       .ramp_samples=rate/50?rate/50:1};
}
void output_volume_pcm(output_volume *v,unsigned percent,const float stereo[FM_BLOCK*2],
                       int16_t mono[FM_BLOCK],float gain,uint64_t *nonfinite,uint64_t *clipped)
{
    if(percent>100)percent=100;
    float target=percent*.01f;
    if(target!=v->target){v->target=target;v->remaining=v->ramp_samples;v->step=(target-v->current)/v->remaining;}
    if(!v->remaining){instrument_pcm(stereo,mono,gain*v->current,nonfinite,clipped);return;}
    float scaled[FM_BLOCK*2];
    for(unsigned i=0;i<FM_BLOCK;++i){
        if(v->remaining){v->current+=v->step;if(!--v->remaining)v->current=v->target;}
        scaled[2*i]=stereo[2*i]*v->current;scaled[2*i+1]=stereo[2*i+1]*v->current;
    }
    instrument_pcm(scaled,mono,gain,nonfinite,clipped);
}
void output_volume_pcm_stereo(output_volume *v,unsigned percent,const float stereo[FM_BLOCK*2],int16_t pcm[FM_BLOCK*2],float gain,uint64_t *nonfinite,uint64_t *clipped)
{
    if(percent>100)percent=100;
    float target=percent*.01f;
    if(target!=v->target){v->target=target;v->remaining=v->ramp_samples;v->step=(target-v->current)/v->remaining;}
    if(!v->remaining){instrument_pcm_stereo(stereo,pcm,gain*v->current,nonfinite,clipped);return;}
    float scaled[FM_BLOCK*2];
    for(unsigned i=0;i<FM_BLOCK;++i){
        if(v->remaining){v->current+=v->step;if(!--v->remaining)v->current=v->target;}
        scaled[2*i]=stereo[2*i]*v->current;scaled[2*i+1]=stereo[2*i+1]*v->current;
    }
    instrument_pcm_stereo(scaled,pcm,gain,nonfinite,clipped);
}
