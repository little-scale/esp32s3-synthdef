/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "fm_synth.h"
#include <assert.h>
#include <stdio.h>
static fm_graph graph;
static fm_voice voice;
static fm_scratch scratch;
int main(int argc, char **argv)
{
    assert(argc == 3);
    unsigned char bytes[FM_FILE_BYTES]; char error[192];
    FILE *f = fopen(argv[1], "rb"); assert(f);
    size_t n = fread(bytes, 1, sizeof bytes, f); assert(!ferror(f)); fclose(f);
    assert(fm_load(&graph, bytes, n, error, sizeof error));
    assert(fm_start(&voice, &graph, 44100));
    assert(fm_bind_delay(&voice, &graph, NULL, 0));
    assert(fm_seed(&voice, 0));
    f = fopen(argv[2], "wb"); assert(f);
    for (unsigned b = 0; b < 345; ++b) {
        float stereo[FM_BLOCK * 2] = {0};
        if (b == 68) assert(fm_set(&voice, &graph, "knob1", 0.75f));
        if (b == 137) assert(fm_set(&voice, &graph, "knob2", 0.3f));
        if (b == 172) assert(fm_set(&voice, &graph, "gate", 0));
        fm_render(&graph, &voice, &scratch, stereo);
        assert(!voice.fault);
        assert(fwrite(stereo, sizeof(float), FM_BLOCK * 2, f) == FM_BLOCK * 2);
    }
    assert(!voice.active);
    assert(fclose(f) == 0);
}
