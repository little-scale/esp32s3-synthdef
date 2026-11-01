/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "instrument.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static fm_graph graph;
static fm_voice voice;
static fm_scratch scratch;
static instrument synth;

static void event(inst_event_type kind, uint32_t id, float value)
{
    inst_event e = { kind, id, value };
    assert(instrument_apply(&synth, &e));
}

static void run_rate(unsigned rate, FILE *output)
{
    assert(instrument_init(&synth, &graph, &voice, &scratch, NULL, 0, rate));
    event(INST_AMP,0,0.5f); /* Preserve this fixture's established test preset. */
    int16_t pcm[FM_BLOCK];
    instrument_render(&synth, pcm);
    for (unsigned i = 0; i < FM_BLOCK; ++i) assert(pcm[i] == 0);
    event(INST_NOTE_ON, 12, 0);
    long long energy = 0;
    for (unsigned b = 0; b < 200; ++b) {
        instrument_render(&synth, pcm);
        for (unsigned i = 0; i < FM_BLOCK; ++i) energy += abs(pcm[i]);
        if (output) assert(fwrite(pcm, sizeof *pcm, FM_BLOCK, output) == FM_BLOCK);
    }
    assert(energy > 1000000 && synth.held && voice.active && !voice.fault);
    event(INST_NOTE_OFF, 11, 0); /* stale release must not release another note */
    assert(synth.held);
    event(INST_NOTE_OFF, 12, 0);
    for (unsigned b = 0; b < rate / FM_BLOCK; ++b) {
        instrument_render(&synth, pcm);
        if (output) assert(fwrite(pcm, sizeof *pcm, FM_BLOCK, output) == FM_BLOCK);
    }
    assert(!synth.held && !voice.active);
    for (unsigned i = 0; i < FM_BLOCK; ++i) assert(pcm[i] == 0);
    event(INST_FREQ, 0, 880);
    event(INST_AMP, 0, 0.2f);
    event(INST_NOTE_ON, 13, 0);
    energy = 0;
    int positive_crossings = 0;
    int16_t previous = 0;
    for (unsigned b = 0; b < rate / FM_BLOCK; ++b) {
        instrument_render(&synth, pcm);
        for (unsigned i = 0; i < FM_BLOCK; ++i) {
            if (previous <= 0 && pcm[i] > 0) ++positive_crossings;
            previous = pcm[i]; energy += abs(pcm[i]);
        }
    }
    assert(positive_crossings >= 878 && positive_crossings <= 881 && energy > 1000000);
    instrument_panic(&synth);
    instrument_render(&synth, pcm);
    for (unsigned i = 0; i < FM_BLOCK; ++i) assert(pcm[i] == 0);
    inst_event cancelled[] = { {INST_NOTE_ON, 14, 0}, {INST_NOTE_OFF, 14, 0} };
    instrument_apply_batch(&synth, cancelled, 2);
    assert(!synth.held && !voice.active);
    inst_event retrigger[] = { {INST_NOTE_OFF, 14, 0}, {INST_NOTE_ON, 15, 0} };
    instrument_apply_batch(&synth, retrigger, 2);
    assert(synth.held && synth.note_id == 15 && voice.active);
    inst_event steals_then_releases[] = {
        {INST_NOTE_ON, 16, 0}, {INST_NOTE_ON, 17, 0}, {INST_NOTE_OFF, 17, 0}
    };
    instrument_apply_batch(&synth, steals_then_releases, 3);
    assert(!synth.held && !voice.active); /* never resurrect the replaced note */
    inst_event bad = { INST_FREQ, 0, NAN };
    assert(!instrument_apply(&synth, &bad));
    bad.type = INST_AMP; bad.value = INFINITY;
    assert(!instrument_apply(&synth, &bad));
    bad.value = -1;
    assert(!instrument_apply(&synth, &bad));
    assert(synth.rejected == 3 && synth.faults == 0);
}

int main(int argc, char **argv)
{
    assert(argc == 4);
    unsigned char bytes[FM_FILE_BYTES];
    FILE *f = fopen(argv[1], "rb"); assert(f);
    size_t n = fread(bytes, 1, sizeof bytes, f); assert(!ferror(f)); fclose(f);
    char error[192]; assert(fm_load(&graph, bytes, n, error, sizeof error));
    FILE *out = fopen(argv[2], "wb"); assert(out);
    run_rate(44100, out); assert(fclose(out) == 0);
    run_rate(48000, NULL);
    assert(!instrument_init(&synth, &graph, &voice, &scratch, NULL, 0, 0));
    /* Initial-rate controls must not be advertised as live controls. */
    graph.node[0].rate = 0;
    assert(!instrument_init(&synth, &graph, &voice, &scratch, NULL, 0, 44100));
    float stereo[FM_BLOCK * 2] = {0}; int16_t pcm[FM_BLOCK];
    uint64_t nonfinite = 0, clips = 0;
    stereo[0] = 1; stereo[1] = -1;
    stereo[2] = INFINITY; stereo[3] = 1;
    stereo[4] = NAN; stereo[5] = -1;
    stereo[6] = 4; stereo[7] = 4;
    stereo[8] = -4; stereo[9] = -4;
    instrument_pcm(stereo, pcm, 1, &nonfinite, &clips);
    assert(pcm[0] == 0 && pcm[1] == 0 && pcm[2] == 0);
    assert(pcm[3] == 32767 && pcm[4] == -32767 && nonfinite == 2 && clips == 2);
    /* Independent library oracle across integer boundaries, half-way values
     * and adjacent representable floats. No waveform/DSP tolerance change. */
    for (int n = -32767; n < 32767; ++n) {
        float middle = ((float)n + 0.5f) / 32767.0f;
        float cases[] = {(float)n / 32767.0f, middle,
                         nextafterf(middle, -INFINITY), nextafterf(middle, INFINITY)};
        for (unsigned k = 0; k < 4; ++k) stereo[2*k] = stereo[2*k+1] = cases[k];
        instrument_pcm(stereo, pcm, 1, &nonfinite, &clips);
        for (unsigned k = 0; k < 4; ++k) assert(pcm[k] == (int16_t)lrintf(cases[k] * 32767.0f));
    }
    puts("PASS: 44.1/48 kHz, pitch, release, stale note IDs, panic, same-block cancellation, initial-rate rejection, finite PCM and clipping");
    puts("PASS: 262136 PCM conversions agree with the lrintf nearest/even oracle");
    f=fopen(argv[3],"rb"); assert(f);
    n=fread(bytes,1,sizeof bytes,f); fclose(f);
    assert(fm_load(&graph,bytes,n,error,sizeof error));
    assert(instrument_init(&synth,&graph,&voice,&scratch,NULL,0,44100));
    assert(synth.knob_mask==15);
    for (unsigned k=0;k<4;++k) event((inst_event_type)(INST_KNOB1+k),0,0.25f);
    event(INST_NOTE_ON,20,0);
    for (unsigned k=0;k<4;++k) assert(synth.knob[k]==0.25f);
    for (unsigned b=0;b<80;++b) instrument_render(&synth,pcm);
    event(INST_KNOB1,0,0.75f); event(INST_KNOB2,0,0.8f);
    event(INST_NOTE_OFF,20,0);
    for (unsigned b=0;b<200;++b) instrument_render(&synth,pcm);
    assert(!voice.active && !voice.fault);
    /* Cached writes must never bypass the engine's scalar-control rule. */
    graph.node[graph.nodes]=graph.node[0];graph.node[graph.nodes].rate=0;++graph.nodes;
    assert(!instrument_init(&synth,&graph,&voice,&scratch,NULL,0,44100));--graph.nodes;
    assert(instrument_init(&synth,&graph,&voice,&scratch,NULL,0,44100));synth.defer_note_render=1;
    event(INST_NOTE_ON,30,0);instrument_render(&synth,pcm);
    for(unsigned i=0;i<FM_BLOCK;++i)assert(pcm[i]==0);
    assert(voice.active && voice.prepared && !voice.blocks && !synth.deferred_blocks);
    instrument_render(&synth,pcm);assert(voice.blocks==1);
    unsigned audible=0;for(unsigned i=0;i<FM_BLOCK;++i)audible+=pcm[i]!=0;assert(audible);
    event(INST_NOTE_ON,31,0);instrument_panic(&synth);assert(!synth.deferred_blocks && !voice.active);
    event(INST_NOTE_ON,32,0);event(INST_NOTE_OFF,32,0);
    for(unsigned b=0;b<1000;++b) {instrument_render(&synth,pcm);for(unsigned i=0;i<FM_BLOCK;++i)assert(pcm[i]==0);}
    assert(!voice.active && !synth.held);
    puts("PASS: four normalized controls, live changes, touch-patch release and bounded one-block note preparation");
    return 0;
}
