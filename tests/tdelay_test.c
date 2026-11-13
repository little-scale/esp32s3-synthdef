/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "fm_synth.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static fm_graph graph;
static fm_voice voice, other;
static fm_scratch scratch;

int main(int argc, char **argv)
{
    assert(argc == 6);
    unsigned char bytes[FM_FILE_BYTES];
    char error[256];
    FILE *file = fopen(argv[1], "rb"); assert(file);
    size_t size = fread(bytes, 1, sizeof bytes, file);
    assert(!ferror(file)); fclose(file);
    int loaded = fm_load(&graph, bytes, size, error, sizeof error);
    if (!strcmp(argv[5], "reject")) {
        assert(!loaded); puts(error); return 0;
    }
    if (!loaded) { fprintf(stderr, "%s\n", error); return 1; }
    assert(fm_delay_required(&graph, 44100) == 0);
    unsigned blocks = (unsigned)strtoul(argv[4], NULL, 10);
    float *input = calloc(blocks * FM_BLOCK * 2, sizeof(float)); assert(input);
    float *first = calloc(blocks * FM_BLOCK * 2, sizeof(float)); assert(first);
    file = fopen(argv[2], "rb"); assert(file);
    assert(fread(input, sizeof(float), blocks * FM_BLOCK * 2, file) == blocks * FM_BLOCK * 2);
    fclose(file);
    int want_fault = !strcmp(argv[5], "fault");
    unsigned faults = 0;
    /* Repeat from fm_start, with a second independent voice and dirty shared
     * scratch between calls. Pending countdowns must remain voice-owned. */
    for (unsigned pass = 0; pass < 2; ++pass) {
        assert(fm_start(&voice, &graph, 44100) && fm_bind_delay(&voice, &graph, NULL, 0));
        assert(fm_start(&other, &graph, 44100) && fm_bind_delay(&other, &graph, NULL, 0));
        for (unsigned block = 0; block < blocks; ++block) {
            float dummy[FM_BLOCK * 2] = {0}, poison[FM_BLOCK * 2] = {0};
            poison[0] = block % 2 ? 1 : 0;
            for (unsigned j = 0; j < FM_BLOCK; ++j) poison[2*j+1] = .25f;
            fm_render_input(&graph, &other, &scratch, dummy, poison);
            memset(&scratch, 0xa5, sizeof scratch);
            float output[FM_BLOCK * 2] = {0};
            fm_render_input(&graph, &voice, &scratch, output, input + block * FM_BLOCK * 2);
            for (unsigned j = 0; j < FM_BLOCK * 2; ++j) {
                assert(isfinite(output[j]));
                if (!pass) first[block * FM_BLOCK * 2 + j] = output[j];
                else assert(output[j] == first[block * FM_BLOCK * 2 + j]);
                if (voice.fault) assert(output[j] == 0);
            }
            faults += voice.fault != 0;
            assert(want_fault || (voice.active && !voice.fault));
        }
    }
    assert(!want_fault || faults > 0);
    file = fopen(argv[3], "wb"); assert(file);
    assert(fwrite(first, sizeof(float), blocks * FM_BLOCK * 2, file) == blocks * FM_BLOCK * 2);
    assert(!fclose(file)); free(input); free(first);
    printf("{\"passed\":true,\"fault_blocks\":%u,\"delay_samples\":0}\n", faults);
}
