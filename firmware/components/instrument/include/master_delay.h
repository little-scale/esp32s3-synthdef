/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include "fm_synth.h"
#include <stdbool.h>
#define MASTER_DELAY_SAMPLES 262144u
#define MASTER_DELAY_SECONDS 5.0f
typedef struct {
    fm_graph *graph;
    fm_voice *voice;
    float *arena;
    unsigned capacity,rate;
    int index[3];
    float value[3]; /* seconds, feedback fraction, wet fraction */
    bool suppressed,bypass,definition_only;
    uint64_t faults;
} master_delay;
int master_delay_init(master_delay *,fm_graph *,fm_voice *,float *,unsigned,unsigned,fm_scratch *);
/* Generic stereo master processor; uses authored controls and can be identity. */
int master_effect_init(master_delay *,fm_graph *,fm_voice *,float *,unsigned,unsigned,fm_scratch *);
int master_effect_define(master_delay *,fm_graph *,fm_voice *,float *,unsigned,unsigned,fm_scratch *);
int master_effect_start(master_delay *,fm_scratch *,const float *controls);
int master_delay_set(master_delay *,unsigned,float);
/* Reset clears the arena: call only at startup or after DMA has stopped. */
int master_delay_reset(master_delay *,fm_scratch *);
/* Panic is constant-time; suppress until a parked reset acknowledges empty rings. */
void master_delay_panic(master_delay *);
void master_delay_render(master_delay *,fm_scratch *,const float *,float *);
