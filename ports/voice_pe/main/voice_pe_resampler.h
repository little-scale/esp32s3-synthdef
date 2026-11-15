/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stddef.h>
#include <stdint.h>
enum { VPE_RESAMPLE_PHASES=3, VPE_RESAMPLE_TAPS=21 };
typedef struct {
    float history[2][VPE_RESAMPLE_TAPS];
    unsigned cursor;
    uint64_t clipped;
} vpe_resampler;
void vpe_resampler_reset(vpe_resampler *);
/* Stereo S16 16 kHz -> MSB-aligned S32 48 kHz. Separate buffers; capacity and
 * return value are output stereo frames. Invalid calls leave state untouched. */
int vpe_resampler_process(vpe_resampler *,const int16_t *,size_t,int32_t *,size_t);
