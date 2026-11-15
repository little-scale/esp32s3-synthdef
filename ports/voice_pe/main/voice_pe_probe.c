/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "voice_pe_probe.h"
#include "fm_synth.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>
int voice_pe_render_probe(const unsigned char *fixture, size_t bytes, unsigned rate,
                         voice_pe_probe_result *result)
{
    if (!fixture || !result || (rate != 44100 && rate != 48000)) return 0;
    memset(result, 0, sizeof *result);
    fm_graph *graph = calloc(1, sizeof *graph);
    fm_voice *voice = calloc(1, sizeof *voice);
    fm_scratch *scratch = calloc(1, sizeof *scratch);
    int ok = 0;
    char error[160];
    if (!graph || !voice || !scratch) goto done;
    if (!fm_load(graph, fixture, bytes, error, sizeof error) ||
        fm_delay_required(graph, rate) != 0 || !fm_start(voice, graph, rate) ||
        !fm_bind_delay(voice, graph, NULL, 0) || !fm_seed(voice, 12345)) goto done;
    float previous = 0;
    for (unsigned block = 0; block < (rate + FM_BLOCK - 1) / FM_BLOCK; ++block) {
        float output[FM_BLOCK * 2] = {0};
        fm_render(graph, voice, scratch, output);
        if (voice->fault) goto done;
        for (unsigned i = 0; i < FM_BLOCK && result->frames < rate; ++i) {
            float left = output[2*i], right = output[2*i+1];
            if (!isfinite(left) || !isfinite(right) || fabsf(left-right) > 1e-6f) goto done;
            if (fabsf(left) > result->peak) result->peak = fabsf(left);
            if (result->frames >= rate/4 && previous <= 0 && left > 0) ++result->crossings;
            previous = left;
            ++result->frames;
        }
    }
    /* Fixture: 440 Hz centered sine, gate=1, amp=.1 with an ADSR. */
    ok = result->peak > .01f && result->peak < .11f &&
         result->crossings >= 329 && result->crossings <= 331;
done:
    free(scratch); free(voice); free(graph);
    return ok;
}
