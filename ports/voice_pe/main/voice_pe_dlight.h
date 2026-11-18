/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stdatomic.h>
enum { VPE_DLIGHT_ADDRESS=0x23, VPE_DLIGHT_NORMALISE_LUX=1000 };
typedef struct {
    void *context;
    bool (*command)(void *,uint8_t);
    bool (*receive)(void *,uint8_t[2]);
} vpe_dlight_io;
typedef struct {
    int64_t due_us,last_sample_us;
    uint32_t samples,errors;
    uint16_t raw;
    unsigned phase;
    bool available;
} vpe_dlight;
void vpe_dlight_init(vpe_dlight *,int64_t now_us);
/* At most one bounded transaction; true only for a newly received sample.
 * Errors retain the last sample, mark unavailable and retry after one second. */
bool vpe_dlight_poll(vpe_dlight *,const vpe_dlight_io *,int64_t now_us);
float vpe_dlight_lux(uint16_t raw);
float vpe_dlight_normalised(uint16_t raw);
typedef struct {atomic_uint sequence,raw;} vpe_dlight_mailbox;
void vpe_dlight_mailbox_init(vpe_dlight_mailbox *);
void vpe_dlight_publish(vpe_dlight_mailbox *,uint16_t raw);
/* Bounded audio-side read. No spinning, locks, I2C or bus writes without new data. */
bool vpe_dlight_consume(const vpe_dlight_mailbox *,uint32_t *last_sequence,float values[2]);
