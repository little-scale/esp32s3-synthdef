/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "identify_tone.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(void)
{
    const unsigned rate = 44100, total = rate / 2;
    int16_t pcm[256 * 2], before[256 * 2];
    identify_tone tone = {0};
    for (unsigned i = 0; i < 512; ++i) pcm[i] = before[i] = (int16_t)(i - 256);
    identify_tone_apply(&tone, pcm, 256, 2, 1);
    assert(!memcmp(pcm, before, sizeof pcm));
    for (unsigned channels = 1; channels <= 2; ++channels) {
        for (unsigned block = 1; block <= 256; block *= 4) {
            identify_tone_start(&tone, rate);
            unsigned crossings = 0, position = 0;
            int previous = 0, peak = 0;
            double squares = 0;
            while (identify_tone_active(&tone)) {
                memset(pcm, 0, sizeof pcm);
                identify_tone_apply(&tone, pcm, block, channels, 1);
                for (unsigned i = 0; i < block; ++i, ++position) {
                    int sample = pcm[i * channels];
                    if (channels == 2) assert(sample == pcm[i * channels + 1]);
                    if (position >= total) { assert(sample == 0); continue; }
                    if (sample > 0 && previous <= 0) ++crossings;
                    previous = sample;
                    if (abs(sample) > peak) peak = abs(sample);
                    squares += (double)sample * sample;
                }
            }
            assert(tone.position == total);
            assert(peak >= 16380 && peak <= 16383);
            assert(crossings == 220);
            assert(sqrt(squares / total) > 11400 && sqrt(squares / total) < 11600);
            identify_tone_cancel(&tone);
            memcpy(pcm, before, sizeof pcm);
            identify_tone_apply(&tone, pcm, block, channels, 1);
            assert(!memcmp(pcm, before, sizeof pcm));
        }
    }
    /* Existing audio returns at the exact final sample and stays bit-identical. */
    identify_tone_start(&tone, rate);
    for (unsigned i = 0; i < total + 1; ++i) {
        pcm[0] = 24000;
        identify_tone_apply(&tone, pcm, 1, 1, .2f);
        assert(pcm[0] >= -3277 && pcm[0] <= 24000);
        if (!i || i >= total - 1) assert(pcm[0] == 24000);
    }
    for (unsigned i = 0; i < 3; ++i) {
        float volume[] = {0, NAN, -1};
        identify_tone_start(&tone, rate);
        memset(pcm, 0, sizeof pcm);
        identify_tone_apply(&tone, pcm, 256, 2, volume[i]);
        for (unsigned j = 0; j < 512; ++j) assert(pcm[j] == 0);
    }
    puts("Identify tone passed mono/stereo, timing, frequency, fades, level, mute and idle preservation");
    return 0;
}
