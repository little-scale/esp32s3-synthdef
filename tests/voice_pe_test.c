/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "voice_pe_format.h"
#include "voice_pe_probe.h"
#include "master_delay.h"
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static fm_graph graph;
static fm_voice voice;
static fm_scratch scratch;
static size_t read_fixture(const char *path, unsigned char *bytes)
{
    FILE *f = fopen(path, "rb"); assert(f);
    size_t size = fread(bytes, 1, FM_FILE_BYTES, f);
    assert(!ferror(f)); fclose(f); return size;
}
int main(int argc, char **argv)
{
    assert(argc == 3);
    /* Exhaust every signed 16-bit value, retaining order across stereo frames. */
    int16_t *input = malloc(65536 * sizeof *input);
    int32_t *output = malloc(65538 * sizeof *output);
    assert(input && output);
    for (int i = 0; i < 65536; ++i) input[i] = (int16_t)(i - 32768);
    output[0] = output[65537] = 1234567;
    assert(voice_pe_pack_s16(input, 32768, output+1, 65536) == 65536);
    for (int i = 0; i < 65536; ++i) assert(output[i+1] == (int32_t)input[i] * 65536);
    assert(output[0] == 1234567 && output[65537] == 1234567);
    int32_t sentinel[4] = {1,2,3,4};
    assert(voice_pe_pack_s16(input, 2, sentinel, 3) == -1 && sentinel[0] == 1);
    assert(voice_pe_pack_s16(input, SIZE_MAX, sentinel, 4) == -1);
    assert(voice_pe_pack_s16(NULL, 1, sentinel, 4) == -1);
    assert(voice_pe_pack_s16(input, 1, NULL, 4) == -1);
    assert(voice_pe_pack_s16(input, 0, sentinel, 4) == 0);
    free(input); free(output);
    unsigned char bytes[FM_FILE_BYTES];
    size_t n = read_fixture(argv[1], bytes);
    for (unsigned i = 0; i < 2; ++i) {
        unsigned rate = i ? 48000 : 44100;
        voice_pe_probe_result result;
        assert(voice_pe_render_probe(bytes, n, rate, &result));
        printf("Core sine probe: rate=%u frames=%u crossings=%u peak=%.8f\n",
               rate, result.frames, result.crossings, result.peak);
    }
    voice_pe_probe_result result;
    assert(!voice_pe_render_probe(bytes, 4, 48000, &result));
    assert(!voice_pe_render_probe(bytes, n, 32000, &result));
    n = read_fixture(argv[2], bytes);
    char error[160]; assert(fm_load(&graph, bytes, n, error, sizeof error));
    unsigned n44 = fm_delay_required(&graph, 44100), n48 = fm_delay_required(&graph, 48000);
    assert(n44 != UINT32_MAX && n48 != UINT32_MAX);
    float *arena = calloc(MASTER_DELAY_SAMPLES, sizeof *arena); assert(arena);
    master_delay fx;
    assert(master_effect_init(&fx, &graph, &voice, arena, MASTER_DELAY_SAMPLES, 44100, &scratch));
    /* Both supported wrapper rates must admit; unsupported rates still fail. */
    assert(master_effect_init(&fx, &graph, &voice, arena, MASTER_DELAY_SAMPLES, 48000, &scratch));
    assert(!master_effect_init(&fx, &graph, &voice, arena, MASTER_DELAY_SAMPLES, 32000, &scratch));
    printf("Existing master-delay graph arena: 44.1k=%u 48k=%u samples; production FX wrapper accepts both rates\n", n44, n48);
    free(arena);
    puts("PASS: all S16 values, stereo order, bounds, invalid input, two engine rates, dual-rate FX admission");
}
