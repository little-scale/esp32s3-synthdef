/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include "pattern_vm.h"
#include "remote_control.h"
typedef struct {
 pg_vm *vm;const fm_graph *graph;
 uint32_t boot,revision,stream,sequence;uint64_t anchor,next_us,emitted,rests;
 double beat;unsigned active,ended;
 int16_t control[PG_SYMBOLS];uint16_t width[PG_SYMBOLS];
 unsigned char writable[FM_CONTROLS];int gate,freq,amp;
 char error[128];
} pg_player;
/* Called off the audio task. remote_control remains owned by the audio task. */
int pg_player_start(pg_player *,pg_vm *,const fm_graph *,uint32_t boot,uint32_t revision,uint32_t stream,uint64_t now,uint32_t seed);
/* 1: timed rc_event, 2: rest advanced, 0: wait/natural end, -1: fault. */
int pg_player_poll(pg_player *,uint64_t now,rc_event *);
void pg_player_cancel(pg_player *,rc_event *);
