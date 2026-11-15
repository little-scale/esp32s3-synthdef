/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include "esp_err.h"
#include <stddef.h>
#include <stdint.h>
#include "voice_pe_codec_sequence.h"
typedef struct {
    size_t preloaded_bytes, submitted_bytes;
    uint32_t writes, partial_writes, timeouts;
    int64_t elapsed_us, max_write_us;
} voice_pe_silent_dma_result;
/* Single-owner diagnostic: literal zeros only, no codec/XMOS writes or amp
 * enable. Survey external clocks first. This is not the production sink. */
esp_err_t voice_pe_silent_dma(voice_pe_silent_dma_result *result);
/* Explicit commissioning command only. Refuses an inserted jack, accepts
 * center-button or USB '!' abort, and restores amp-off/mute on every exit. */
esp_err_t voice_pe_tone_test(vpe_codec *codec, voice_pe_silent_dma_result *result);
