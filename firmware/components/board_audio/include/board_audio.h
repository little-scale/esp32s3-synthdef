/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
#include "sdkconfig.h"
#include "../../instrument/include/synthdef_rate.h"

#if defined(CONFIG_SYNTHDEF_VOICE_PE)
#define BOARD_AUDIO_CHANNELS 2
#define BOARD_MODEL "Home Assistant Voice PE"
#elif defined(CONFIG_SYNTHDEF_HEADLESS)
#define BOARD_AUDIO_CHANNELS 2
#define BOARD_MODEL "XIAO ESP32-S3"
#else
#define BOARD_AUDIO_CHANNELS 1
#define BOARD_MODEL "Waveshare AMOLED 1.8 V2"
#endif
#ifdef CONFIG_SYNTHDEF_NO_DISPLAY
#define BOARD_CAPTURE_CHUNK_BYTES 1024u
int board_audio_capture_command(const char *,const unsigned char *,size_t,char *,size_t);
void board_audio_activity(bool active);
#endif

#ifdef CONFIG_SYNTHDEF_VOICE_PE
/* Control owner drains deferred codec mute; never called by the audio task. */
void board_audio_maintenance(void);
esp_err_t board_audio_early_init(void);
/* CPU conversion time excludes blocking DMA waits. Audio owner only. */
uint32_t board_audio_processing_us(void);
uint64_t board_audio_conversion_clips(void);
#else
static inline void board_audio_maintenance(void) {}
static inline esp_err_t board_audio_early_init(void) {return ESP_OK;}
static inline uint32_t board_audio_processing_us(void) {return 0;}
static inline uint64_t board_audio_conversion_clips(void) {return 0;}
#endif

esp_err_t board_audio_init(uint32_t rate);
esp_err_t board_audio_write(const int16_t *pcm, size_t frames, size_t *written);
esp_err_t board_audio_mute(void);
esp_err_t board_audio_pause(void);
esp_err_t board_audio_resume(void);
/* Called by the audio owner only, between writes. No codec/I2C operations. */
esp_err_t board_audio_stop_dma(void);
esp_err_t board_audio_start_dma(void);
uint32_t board_audio_dma_errors(void);
