/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "voice_pe_format.h"
#include <limits.h>
int voice_pe_pack_s16(const int16_t *input, size_t frames, int32_t *output, size_t capacity)
{
    if (!input || !output || frames > (size_t)INT_MAX / 2 || frames > capacity / 2) return -1;
    size_t samples = frames * 2;
    for (size_t i = 0; i < samples; ++i)
        /* Multiplication is defined even for negative samples; signed << is not. */
        output[i] = (int32_t)input[i] * 65536;
    return (int)samples;
}
