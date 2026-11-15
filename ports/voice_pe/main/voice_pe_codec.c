/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "voice_pe_codec.h"
#include "voice_pe_pins.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <string.h>

static int codec_write(void *context, uint8_t reg, uint8_t value)
{
    voice_pe_codec_device *d = context;
    uint8_t bytes[2] = {reg, value};
    d->last_error = i2c_master_transmit(d->device, bytes, sizeof bytes, 50);
    return d->last_error == ESP_OK;
}
static int codec_read(void *context, uint8_t reg, uint8_t *value)
{
    voice_pe_codec_device *d = context;
    d->last_error = i2c_master_transmit_receive(d->device, &reg, 1, value, 1, 50);
    return d->last_error == ESP_OK;
}
static void codec_delay(void *context, unsigned ms)
{
    (void)context;
    vTaskDelay(pdMS_TO_TICKS(ms));
}
static esp_err_t init_gain(voice_pe_codec_device *d,int gain_db,unsigned rate)
{
    if (!d) return ESP_ERR_INVALID_ARG;
    memset(d, 0, sizeof *d);
    if (gpio_get_level(VPE_AMP_ENABLE) != 0) return ESP_ERR_INVALID_STATE;
    i2c_master_bus_config_t bus = {
        .i2c_port = -1, .sda_io_num = VPE_I2C_SDA, .scl_io_num = VPE_I2C_SCL,
        .clk_source = I2C_CLK_SRC_DEFAULT, .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = false
    };
    esp_err_t err = i2c_new_master_bus(&bus, &d->bus);
    if (err != ESP_OK) return err;
    i2c_device_config_t chip = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = VPE_CODEC_ADDRESS, .scl_speed_hz = 400000
    };
    err = i2c_master_bus_add_device(d->bus, &chip, &d->device);
    if (err != ESP_OK) {
        (void)voice_pe_codec_close(d);
        return err;
    }
    vpe_codec_io io = {d, codec_write, codec_read, codec_delay};
    if (!vpe_codec_init_muted_rate(&d->sequence, &io,gain_db,rate)) {
        err = d->last_error == ESP_OK ? ESP_ERR_INVALID_RESPONSE : d->last_error;
        (void)voice_pe_codec_close(d);
        return err;
    }
    return ESP_OK;
}
esp_err_t voice_pe_codec_close(voice_pe_codec_device *d)
{
    if (!d) return ESP_ERR_INVALID_ARG;
    esp_err_t err = gpio_set_level(VPE_AMP_ENABLE, 0);
    if (d->device) {
        if (!vpe_codec_mute(&d->sequence) && err == ESP_OK) err = ESP_FAIL;
        esp_err_t remove = i2c_master_bus_rm_device(d->device);
        if (err == ESP_OK) err = remove;
        d->device = NULL;
    }
    if (d->bus) {
        esp_err_t remove = i2c_del_master_bus(d->bus);
        if (err == ESP_OK) err = remove;
        d->bus = NULL;
    }
    d->sequence.ready = 0;
    return err;
}

esp_err_t voice_pe_codec_init(voice_pe_codec_device *d){return init_gain(d,-24,48000);}
esp_err_t voice_pe_codec_init_playback(voice_pe_codec_device *d){return init_gain(d,0,48000);}
esp_err_t voice_pe_codec_init_playback_at_rate(voice_pe_codec_device *d,unsigned rate){return init_gain(d,0,rate);}
