/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include "instrument.h"
#include "master_delay.h"
#define RC_EVENTS 16
#define RC_STREAMS 32
#define RC_PAIRS 64
#define RC_HEADER 32
#define RC_DELTA 1
#define RC_NEED_FULL 2
/* Every function is called by the audio owner. State lives in preallocated PSRAM. */
typedef struct {
    uint32_t boot,revision,stream,sequence,duration;
    uint64_t at;
    uint8_t kind,stage,count,flags,index[RC_PAIRS];
    float value[RC_PAIRS];
} rc_event;
typedef struct {
    const fm_graph *graph;fm_voice *voice;
    uint32_t revision,owner,owner_sequence;
    uint64_t release;
    int gate;unsigned retrigger;
    float shadow[FM_CONTROLS];
    uint8_t rate[FM_CONTROLS],trigger[FM_CONTROLS],writable[FM_CONTROLS];
} rc_stage;
typedef struct {
    uint64_t mask;float value[FM_CONTROLS];uint32_t revision;
    uint8_t valid,kind;
} rc_baseline;
typedef struct {uint32_t id,sequence;uint64_t touched;uint8_t cancelled;rc_baseline baseline[2];} rc_stream;
typedef struct {
    uint32_t boot;rc_stage stage[2];rc_event event[RC_EVENTS];unsigned count;
    rc_stream streams[RC_STREAMS];
    uint64_t applied,rejected,late;
} remote_control;
void rc_init(remote_control *,uint32_t boot);
void rc_bind(remote_control *,unsigned stage,const fm_graph *,fm_voice *);
void rc_clear(remote_control *);
int rc_decode(rc_event *,const unsigned char *,size_t);
int rc_enqueue(remote_control *,const rc_event *,uint64_t now);
void rc_tick(remote_control *,instrument *,uint64_t now);
/* Explicit instance creation/free runs only while the audio owner is parked. */
int rc_instance(remote_control *,instrument *,master_delay *,int start,const rc_event *);
/* Names are represented as hex in JSON to preserve arbitrary UTF-8 safely. */
typedef struct {
    const fm_graph *graph;uint32_t boot,revision,queued;uint64_t now,applied,rejected,late;
    unsigned active,prepared;float values[FM_CONTROLS];uint8_t rate[FM_CONTROLS],trigger[FM_CONTROLS],writable[FM_CONTROLS];
} rc_status;
int rc_snapshot(const remote_control *,unsigned stage,uint64_t now,rc_status *);
/* Format the immutable snapshot off the audio task. */
int rc_info(const rc_status *,unsigned page,char *,size_t);
