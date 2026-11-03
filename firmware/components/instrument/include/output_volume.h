/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include "instrument.h"
#define OUTPUT_VOLUME_DEFAULT_PERCENT 20u
typedef struct { float current,target,step; unsigned remaining,ramp_samples; } output_volume;
void output_volume_init(output_volume *,unsigned percent,unsigned sample_rate);
void output_volume_pcm_stereo(output_volume *,unsigned percent,const float stereo[FM_BLOCK*2],int16_t pcm[FM_BLOCK*2],float base_gain,uint64_t *,uint64_t *);
/* Final output scaling only; never changes synth controls or feedback state. */
void output_volume_pcm(output_volume *,unsigned percent,const float stereo[FM_BLOCK*2],
                       int16_t mono[FM_BLOCK],float base_gain,uint64_t *,uint64_t *);
