/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include "fm_synth.h"

typedef enum {
    INST_NOTE_OFF, INST_FREQ, INST_AMP,
    INST_KNOB1, INST_KNOB2, INST_KNOB3, INST_KNOB4, INST_NOTE_ON
} inst_event_type;
#define INST_CONTROL_COUNT 6
typedef struct { inst_event_type type; uint32_t note_id; float value; } inst_event;
typedef struct {
    fm_graph *graph;
    fm_voice *voice;
    fm_scratch *scratch;
    float *arena;
    uint32_t arena_samples, sample_rate, note_id, fade_frame;
    uint64_t frame, release_frames, faults, clipped, nonfinite, rejected;
    uint64_t (*clock_us)(void); /* Optional target clock; no host timing claim. */
    uint32_t preparation_max_us;
    /* Last-operation diagnostics; the audio owner publishes compact snapshots. */
    uint32_t reset_us, controls_us, prepare_us, dsp_us, pcm_us;
    float frequency, amplitude, master_gain;
    float knob[4];
    unsigned knob_mask;
    int16_t control_index[7]; /* freq, amp, gate, knob1..4; graph stays immutable */
    int held;
} instrument;

/* All calls belong to one audio owner. Caller owns every supplied allocation.
 * Graph must be successfully parsed by fm_load and stay immutable until reinit. */
int instrument_init(instrument *, fm_graph *, fm_voice *, fm_scratch *,
                    float *arena, uint32_t arena_samples, uint32_t sample_rate);
int instrument_apply(instrument *, const inst_event *);
void instrument_apply_batch(instrument *, const inst_event *, unsigned count);
void instrument_panic(instrument *);
void instrument_render(instrument *, int16_t mono[FM_BLOCK]);
void instrument_pcm(const float stereo[FM_BLOCK * 2], int16_t mono[FM_BLOCK],
                    float gain, uint64_t *nonfinite, uint64_t *clipped);
