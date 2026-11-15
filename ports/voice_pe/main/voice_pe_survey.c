/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "voice_pe_survey.h"
#include "voice_pe_pins.h"
#include "driver/i2c_master.h"
#include "driver/pulse_cnt.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <stdbool.h>
#include <string.h>

static void retain_error(esp_err_t *first, esp_err_t next)
{
    if (*first == ESP_OK) *first = next;
}

static esp_err_t count_clock(int gpio, voice_pe_clock_sample *out)
{
    pcnt_unit_handle_t unit = NULL;
    pcnt_channel_handle_t channel = NULL;
    bool enabled = false, started = false, watched = false;
    pcnt_unit_config_t unit_config = {
        .high_limit = 30000, .low_limit = -30000,
        .flags.accum_count = true
    };
    pcnt_chan_config_t channel_config = {
        .edge_gpio_num = gpio, .level_gpio_num = -1
    };
    esp_err_t err = pcnt_new_unit(&unit_config, &unit);
    if (err != ESP_OK) return err;
    err = pcnt_new_channel(unit, &channel_config, &channel);
    if (err != ESP_OK) goto cleanup;
    err = pcnt_channel_set_edge_action(channel, PCNT_CHANNEL_EDGE_ACTION_INCREASE,
                                      PCNT_CHANNEL_EDGE_ACTION_HOLD);
    if (err != ESP_OK) goto cleanup;
    err = pcnt_channel_set_level_action(channel, PCNT_CHANNEL_LEVEL_ACTION_KEEP,
                                       PCNT_CHANNEL_LEVEL_ACTION_KEEP);
    if (err != ESP_OK) goto cleanup;
    /* The high-limit watch point activates accumulated overflow accounting.
     * A 3.072 MHz input crosses this limit about ten times in the gate. */
    err = pcnt_unit_add_watch_point(unit, 30000);
    if (err != ESP_OK) goto cleanup;
    watched = true;
    err = pcnt_unit_enable(unit);
    if (err != ESP_OK) goto cleanup;
    enabled = true;
    err = pcnt_unit_clear_count(unit);
    if (err != ESP_OK) goto cleanup;
    int64_t begin = esp_timer_get_time();
    err = pcnt_unit_start(unit);
    if (err != ESP_OK) goto cleanup;
    started = true;
    /* Missing clocks produce zero counts, never an unbounded wait. This is a
     * coarse frequency survey, not a duty-cycle, phase or I2S format test. */
    vTaskDelay(pdMS_TO_TICKS(100));
    err = pcnt_unit_stop(unit);
    if (err != ESP_OK) goto cleanup;
    started = false;
    out->elapsed_us = esp_timer_get_time()-begin;
    err = pcnt_unit_get_count(unit, &out->pulses);
    if (err != ESP_OK) goto cleanup;
    if (out->elapsed_us <= 0 || out->pulses < 0) {
        err = ESP_ERR_INVALID_STATE;
        goto cleanup;
    }
    out->hz = (double)out->pulses*1000000.0/(double)out->elapsed_us;
cleanup:
    if (started) retain_error(&err, pcnt_unit_stop(unit));
    if (enabled) retain_error(&err, pcnt_unit_disable(unit));
    if (watched) retain_error(&err, pcnt_unit_remove_watch_point(unit, 30000));
    if (channel) retain_error(&err, pcnt_del_channel(channel));
    retain_error(&err, pcnt_del_unit(unit));
    return err;
}

esp_err_t voice_pe_survey(voice_pe_survey_result *result)
{
    if (!result) return ESP_ERR_INVALID_ARG;
    memset(result, 0, sizeof *result);
    i2c_master_bus_handle_t bus = NULL;
    i2c_master_bus_config_t config = {
        .i2c_port = -1,
        .sda_io_num = VPE_I2C_SDA, .scl_io_num = VPE_I2C_SCL,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags.enable_internal_pullup = false
    };
    esp_err_t err = i2c_new_master_bus(&config, &bus);
    if (err != ESP_OK) return err;
    result->codec = i2c_master_probe(bus, VPE_CODEC_ADDRESS, 50);
    result->xmos = i2c_master_probe(bus, VPE_XMOS_ADDRESS, 50);
    err = i2c_del_master_bus(bus);
    if (err != ESP_OK) return err;
    err = count_clock(VPE_TX_WS, &result->ws);
    if (err != ESP_OK) return err;
    return count_clock(VPE_TX_BCLK, &result->bclk);
}
