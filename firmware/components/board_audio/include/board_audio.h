/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

esp_err_t board_audio_init(uint32_t rate);
esp_err_t board_audio_write(const int16_t *mono, size_t frames, size_t *written);
esp_err_t board_audio_mute(void);
esp_err_t board_audio_pause(void);
esp_err_t board_audio_resume(void);
/* Called by the audio owner only, between writes. No codec/I2C operations. */
esp_err_t board_audio_stop_dma(void);
esp_err_t board_audio_start_dma(void);
uint32_t board_audio_dma_errors(void);
