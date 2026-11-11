/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stdint.h>

#define IDENTIFY_TONE_MS 500u
#define IDENTIFY_TONE_HZ 440u
typedef struct {
    unsigned position, frames, fade, rate;
    float phase;
} identify_tone;

/* Owned exclusively by the audio task. PCM is already output-volume scaled. */
void identify_tone_start(identify_tone *, unsigned sample_rate);
void identify_tone_cancel(identify_tone *);
int identify_tone_active(const identify_tone *);
void identify_tone_apply(identify_tone *, int16_t *pcm, unsigned frames,
                         unsigned channels, float output_volume);
