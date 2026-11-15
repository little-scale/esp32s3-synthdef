/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "voice_pe_test_tone.h"
#include "voice_pe_format.h"
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>

int main(void)
{
    unsigned crossings[3] = {0}, nonzero[3] = {0};
    int previous = 0, peak = 0;
    for (uint32_t frame = 0; frame < VPE_TONE_FRAMES+100; ++frame) {
        int16_t out[2], again[2];
        vpe_test_tone_sample(frame, out); vpe_test_tone_sample(frame, again);
        assert(out[0] == again[0] && out[1] == again[1]);
        for (unsigned i = 0; i < 2; ++i) {
            assert(abs(out[i]) <= VPE_TONE_PEAK);
            if (abs(out[i]) > peak) peak = abs(out[i]);
        }
        int segment = frame < 48000 ? 0 : frame >= 52800 && frame < 100800 ? 1 :
                      frame >= 105600 && frame < 153600 ? 2 : -1;
        if (segment < 0) { assert(!out[0] && !out[1]); previous = 0; continue; }
        if (segment == 0) assert(!out[1]);
        if (segment == 1) assert(!out[0]);
        if (segment == 2) assert(out[0] == out[1]);
        int sample = out[segment == 1 ? 1 : 0];
        if (sample) ++nonzero[segment];
        if (previous <= 0 && sample > 0) ++crossings[segment];
        previous = sample;
        unsigned local = frame-(segment == 0 ? 0 : segment == 1 ? 52800 : 105600);
        if (local < 100 || local > 47899) assert(abs(sample) <= 69);
        if (local == 0 || local == 47999) assert(!sample);
        int32_t wire[2];
        assert(voice_pe_pack_s16(out, 1, wire, 2) == 2);
        assert(wire[0] == (int32_t)out[0]*65536 && wire[1] == (int32_t)out[1]*65536);
    }
    const unsigned frequency[] = {440,660,550};
    for (unsigned i = 0; i < 3; ++i) {
        assert(crossings[i] >= frequency[i]-1 && crossings[i] <= frequency[i]+1);
        assert(nonzero[i] > 45000);
    }
    assert(peak == VPE_TONE_PEAK);
    int16_t last[2]; vpe_test_tone_sample(UINT32_MAX, last); assert(!last[0] && !last[1]);
    assert(vpe_test_tone_command_matches("VPE_TONE 1234abcd",0x1234abcd));
    const char *bad[] = {"VPE_TONE 1234abce","VPE_TONE 1234ABCD","VPE_TONE 1234abcd ",
        "VPE_TONE 1234abcd\n","VPE_TONE 01234abcd","VPE_TONE +234abcd","VPE_TONE", "t", "", NULL};
    for (unsigned i = 0; i < sizeof bad/sizeof bad[0]; ++i)
        assert(!vpe_test_tone_command_matches(bad[i],0x1234abcd));
    printf("PASS: bounded 3.2-second PCM, channel isolation, ramps, S32 packing, restart determinism, %u/%u/%u cycles and exact fresh-command matching\n",crossings[0],crossings[1],crossings[2]);
}
