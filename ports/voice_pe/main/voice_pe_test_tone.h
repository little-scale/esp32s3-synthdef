/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stdint.h>
enum { VPE_TONE_RATE = 48000, VPE_TONE_FRAMES = 153600, VPE_TONE_PEAK = 1638 };
/* Left 440 Hz, gap, right 660 Hz, gap, both 550 Hz. Each note one second,
 * 50 ms ramps, maximum approximately 5% PCM amplitude. Out of range = zero. */
void vpe_test_tone_sample(uint32_t frame, int16_t stereo[2]);
int vpe_test_tone_command_matches(const char *line, uint32_t token);
