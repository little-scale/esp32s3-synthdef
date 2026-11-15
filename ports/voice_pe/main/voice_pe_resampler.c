/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "voice_pe_resampler.h"
#include <limits.h>
#include <string.h>
#include "voice_pe_resampler_coeffs.inc"
void vpe_resampler_reset(vpe_resampler *s){if(s)memset(s,0,sizeof *s);}
static int32_t wire_sample(vpe_resampler *s,float x)
{
    if(x>=32768.0f){++s->clipped;return INT32_MAX;}
    if(x< -32768.0f){++s->clipped;return INT32_MIN;}
    /* The largest float below 32768 times 65536 still fits in int32_t. */
    return (int32_t)(x*65536.0f);
}
int vpe_resampler_process(vpe_resampler *s,const int16_t *input,size_t frames,int32_t *output,size_t capacity)
{
    if(!s || !input || !output || s->cursor>=VPE_RESAMPLE_TAPS ||
       frames>(size_t)INT_MAX/3 || frames>SIZE_MAX/(6*sizeof *output) || frames>capacity/3)return -1;
    for(size_t n=0;n<frames;++n){
        unsigned at=s->cursor;
        s->history[0][at]=input[2*n];s->history[1][at]=input[2*n+1];
        float sum[2][2]={{0}};
        for(unsigned k=0;k<VPE_RESAMPLE_TAPS;++k){
            unsigned pos=at+k;if(pos>=VPE_RESAMPLE_TAPS)pos-=VPE_RESAMPLE_TAPS;
            for(unsigned channel=0;channel<2;++channel){
                float x=s->history[channel][pos];
                sum[0][channel]+=x*coefficients[0][k];sum[1][channel]+=x*coefficients[1][k];
            }
        }
        unsigned middle=at+10;if(middle>=VPE_RESAMPLE_TAPS)middle-=VPE_RESAMPLE_TAPS;
        for(unsigned channel=0;channel<2;++channel){
            output[6*n+channel]=wire_sample(s,sum[0][channel]);
            output[6*n+2+channel]=wire_sample(s,s->history[channel][middle]);
            output[6*n+4+channel]=wire_sample(s,sum[1][channel]);
        }
        s->cursor=at?at-1:VPE_RESAMPLE_TAPS-1;
    }
    return (int)(frames*3);
}
