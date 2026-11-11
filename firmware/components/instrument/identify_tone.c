/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "identify_tone.h"
#include <math.h>

void identify_tone_start(identify_tone *tone, unsigned rate)
{
    *tone = (identify_tone){.rate = rate, .frames = rate * IDENTIFY_TONE_MS / 1000u,
                            .fade = rate / 200u};
    if (tone->fade < 2) tone->fade = 2;
}
void identify_tone_cancel(identify_tone *tone) { tone->position = tone->frames; }
int identify_tone_active(const identify_tone *tone) { return tone->position < tone->frames; }

void identify_tone_apply(identify_tone *tone, int16_t *pcm, unsigned frames,
                         unsigned channels, float volume)
{
    if (!identify_tone_active(tone)) return;
    if (!isfinite(volume) || volume < 0) volume = 0;
    if (volume > 1) volume = 1;
    const float tau = 6.2831853071795864769f;
    const float increment = tau * IDENTIFY_TONE_HZ / tone->rate;
    for (unsigned i = 0; i < frames && identify_tone_active(tone); ++i) {
        unsigned remaining = tone->frames - 1u - tone->position;
        unsigned edge = tone->position < remaining ? tone->position : remaining;
        float mix = edge < tone->fade ? (float)edge / tone->fade : 1.0f;
        float cue = sinf(tone->phase) * (16383.0f * volume);
        for (unsigned channel = 0; channel < channels; ++channel) {
            unsigned at = i * channels + channel;
            pcm[at] = (int16_t)((1.0f - mix) * pcm[at] + mix * cue);
        }
        if ((tone->phase += increment) >= tau) tone->phase -= tau;
        ++tone->position;
    }
}
