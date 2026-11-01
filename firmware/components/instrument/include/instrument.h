/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include "fm_synth.h"

typedef enum {
    INST_NOTE_OFF, INST_FREQ, INST_AMP,
    INST_KNOB1, INST_KNOB2, INST_KNOB3, INST_KNOB4, INST_TOUCH_X, INST_TOUCH_Y, INST_NOTE_ON
} inst_event_type;
#define INST_CONTROL_COUNT 8
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
    float buses[FM_CONTROL_BUSES];
    unsigned bus_mode,gate_low_blocks,continuous,suspended_continuous,suspended_restart;
    float rendered_gate;
    unsigned knob_mask;
    int16_t control_index[7]; /* freq, amp, gate, knob1..4; graph stays immutable */
    int held;
    unsigned defer_note_render,deferred_blocks;
    uint32_t arena_needed,arena_cleared;
    unsigned preparing_memory,pristine_arena;
    uint32_t seed_next,seed_active;
    unsigned random_starts;
} instrument;

/* All calls belong to one audio owner. Caller owns every supplied allocation.
 * Graph must be successfully parsed by fm_load and stay immutable until reinit. */
int instrument_init(instrument *, fm_graph *, fm_voice *, fm_scratch *,
                    float *arena, uint32_t arena_samples, uint32_t sample_rate);
int instrument_apply(instrument *, const inst_event *);
/* Start bus-driven graphs with touch gate low, or continuous graphs at their
 * authored defaults. Audio owner only. */
int instrument_arm_bus(instrument *);
/* Audio owner: restart an inactive remote voice with its complete parameter bank. */
int instrument_start_remote(instrument *,const float *controls);
int instrument_init_definition(instrument *,fm_graph *,fm_voice *,fm_scratch *,float *,uint32_t,uint32_t,int managed);
/* Parked owner only: definition preparation clears memory without constructing a voice. */
void instrument_preclear(instrument *);
/* Opt in to a fresh deterministic seed sequence for real starts. Tests retain
 * seed zero by default. Maintenance resumes retain the current start's seed. */
void instrument_randomize(instrument *,uint32_t first_seed);
/* Park/resume preserve an active continuous program; Panic cancels its resume. */
void instrument_suspend(instrument *);
int instrument_resume(instrument *);
void instrument_apply_batch(instrument *, const inst_event *, unsigned count);
void instrument_panic(instrument *);
void instrument_render(instrument *, int16_t mono[FM_BLOCK]);
/* Render the voice before master effects, preserving start fade and lifecycle. */
void instrument_render_stereo(instrument *,float stereo[FM_BLOCK*2]);
void instrument_pcm(const float stereo[FM_BLOCK * 2], int16_t mono[FM_BLOCK],
                    float gain, uint64_t *nonfinite, uint64_t *clipped);
