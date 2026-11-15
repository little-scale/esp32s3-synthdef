/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include "voice_pe_codec_sequence.h"
#include "driver/i2c_master.h"
#include "esp_err.h"
typedef struct {
    vpe_codec sequence;
    i2c_master_bus_handle_t bus;
    i2c_master_dev_handle_t device;
    esp_err_t last_error;
} voice_pe_codec_device;
esp_err_t voice_pe_codec_init(voice_pe_codec_device *device);
/* Shared app: unity DAC gain; commissioning init above remains -24 dB. */
esp_err_t voice_pe_codec_init_playback(voice_pe_codec_device *device);
esp_err_t voice_pe_codec_init_playback_at_rate(voice_pe_codec_device *device,unsigned rate);
esp_err_t voice_pe_codec_close(voice_pe_codec_device *device);
