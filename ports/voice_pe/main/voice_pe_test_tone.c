/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "voice_pe_test_tone.h"
#include <math.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
int vpe_test_tone_command_matches(const char *line, uint32_t token)
{
    char expected[32];
    snprintf(expected, sizeof expected, "VPE_TONE %08" PRIx32, token);
    return line && strcmp(line, expected) == 0;
}
void vpe_test_tone_sample(uint32_t frame, int16_t stereo[2])
{
    stereo[0] = stereo[1] = 0;
    unsigned local, mask, frequency;
    if (frame < 48000) { local = frame; mask = 1; frequency = 440; }
    else if (frame >= 52800 && frame < 100800) { local = frame-52800; mask = 2; frequency = 660; }
    else if (frame >= 105600 && frame < VPE_TONE_FRAMES) { local = frame-105600; mask = 3; frequency = 550; }
    else return;
    unsigned ramp = local < 2400 ? local : 2400;
    if (47999-local < ramp) ramp = 47999-local;
    float value = sinf(6.283185307179586f*(float)frequency*(float)local/48000.0f);
    int16_t sample = (int16_t)lrintf(value*(float)VPE_TONE_PEAK*(float)ramp/2400.0f);
    if (mask & 1) stereo[0] = sample;
    if (mask & 2) stereo[1] = sample;
}
