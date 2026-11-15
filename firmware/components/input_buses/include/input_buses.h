/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stddef.h>
#include <stdint.h>

/* Experimental portable core. No GPIO, allocation, task or storage operations.
 * One owner must serialize ALL calls, including publication, at block boundaries.
 * This is NOT a thread-safe sensor mailbox. The eventual adapter supplies one.
 * Bus layout is the Voice PE draft-2 proposal; existing 0..15 are preserved. */
enum { IB_SLOTS = 8, IB_VALUE_BASE = 16, IB_VALID_BASE = 24, IB_BUS_COUNT = 32 };
typedef enum { IB_CONTINUOUS = 0, IB_BINARY = 1 } ib_kind;
typedef struct {
    uint32_t source_id; /* 0 = unassigned; stable installed-instance/channel ID */
    float minimum, maximum, fallback;
    uint64_t stale_after_us;
    ib_kind kind;
    unsigned invert;
} ib_config;
typedef struct {
    uint32_t source_id;
    float raw;
    uint64_t sampled_at_us;
    unsigned valid; /* 0 = failed read; never refreshes last good reading */
} ib_sample;
typedef struct {
    float normalized;
    uint64_t last_good_us, last_seen_us;
    unsigned has_good, has_seen, clipped;
} ib_channel_state;
typedef struct {
    ib_config config[IB_SLOTS];
    ib_channel_state channel[IB_SLOTS];
    uint64_t clock_us, configured_at_us;
    uint32_t generation;
} ib_bank;
typedef struct {
    float value[IB_SLOTS], valid[IB_SLOTS];
    unsigned clipped[IB_SLOTS];
    uint32_t generation;
    uint64_t at_us;
} ib_snapshot;

void ib_init(ib_bank *bank);
/* Full fixed slot table; validates before mutation. Success resets cached data,
 * advances generation and preserves explicit holes. IDs must be unique.
 * Disabled entries' other fields are ignored. Invalid config leaves bank intact. */
int ib_configure(ib_bank *bank, const ib_config config[IB_SLOTS], uint64_t now_us);
/* All-or-nothing batch admission: reject wrong generation, duplicate/unknown IDs,
 * future/backward/pre-configuration timestamps or malformed validity flags. Invalid/nonfinite raw
 * readings are admitted as failed reads, holding last good value until timeout.
 * Equal timestamps are allowed (clock resolution); driver order is authoritative.
 * No allocation and at most IB_SLOTS samples per batch. */
int ib_ingest(ib_bank *bank, uint32_t generation, const ib_sample *samples,
              size_t count, uint64_t now_us);
/* Coherent values/validity; expires at age >= stale_after_us. Monotonic time only.
 * Repeated calls with the same time are allowed. No smoothing or voice lifecycle. */
int ib_snapshot_at(ib_bank *bank, uint64_t now_us, ib_snapshot *out);
/* Writes only buses 16..31, after validating the whole snapshot and capacity.
 * Caller keeps the output array stable through fm_prepare/fm_render and binds
 * it after EVERY fm_start. Does not bind the engine or restart a stopped voice. */
int ib_write_buses(const ib_snapshot *snapshot, float *buses, size_t count);
