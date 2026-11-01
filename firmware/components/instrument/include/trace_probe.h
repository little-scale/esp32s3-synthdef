/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include "fm_synth.h"
#define TRACE_BLOCKS 8192u
#define TRACE_WINDOWS 40u
#define TRACE_FLOATS (TRACE_WINDOWS*FM_BLOCK*2u)
extern const uint16_t trace_windows[TRACE_WINDOWS];
typedef struct {
    uint32_t blocks,faults,nonfinite,guard_failures,event_updates,event_rejections;
    uint32_t initial_rejections,unexpected_initial_accepts,restarts,max_render_us;
    float peak,rms;
} trace_summary;
/* Non-real-time diagnostic only. Requires a parked/muted owner. Borrows the
 * voice/scratch and guards both ends of a caller-owned arena; allocates nothing. */
int trace_probe(const fm_graph *,fm_voice *,fm_scratch *,float *,uint32_t,
                float capture[TRACE_FLOATS],trace_summary *,uint64_t (*clock_us)(void),void (*yield_fn)(void));
