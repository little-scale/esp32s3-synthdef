/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stddef.h>
#include <stdint.h>
/* Signed S16 stereo to MSB-aligned S32 stereo. Separate, nonoverlapping buffers.
 * Capacity and return value are sample counts (2 samples per stereo frame). */
int voice_pe_pack_s16(const int16_t *input, size_t frames, int32_t *output, size_t capacity);
