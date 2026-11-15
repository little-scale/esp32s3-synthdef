/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include "esp_err.h"
#include <stdint.h>

typedef struct {
    int pulses;
    int64_t elapsed_us;
    double hz;
} voice_pe_clock_sample;

typedef struct {
    esp_err_t codec, xmos;
    voice_pe_clock_sample ws, bclk;
} voice_pe_survey_result;

/* Address-only I2C probes and input-only pulse counters. Never writes codec or
 * XMOS registers, drives clocks, creates I2S DMA, or changes output mute. The
 * caller first holds AMP_ENABLE and LED_POWER low via voice_pe_safe_init(). */
esp_err_t voice_pe_survey(voice_pe_survey_result *result);
