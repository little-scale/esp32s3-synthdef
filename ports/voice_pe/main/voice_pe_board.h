/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include "esp_err.h"
#include "driver/i2s_std.h"
#include <stdbool.h>
typedef struct { int button, mute, jack, encoder_a, encoder_b; } voice_pe_inputs;
esp_err_t voice_pe_safe_init(void);
voice_pe_inputs voice_pe_read_inputs(void);
/* Configuration values only. Does NOT allocate a channel or touch GPIO. */
esp_err_t voice_pe_i2s_config(unsigned rate, i2s_chan_config_t *channel,
                            i2s_std_config_t *standard);
/* Deliberate hard stop until codec/clock/recovery bring-up is completed. */
esp_err_t voice_pe_audio_start(void);
