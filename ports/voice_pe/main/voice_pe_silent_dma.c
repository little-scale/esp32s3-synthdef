/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "voice_pe_silent_dma.h"
#include "voice_pe_board.h"
#include "voice_pe_pins.h"
#include "voice_pe_test_tone.h"
#include "voice_pe_format.h"
#include "driver/gpio.h"
#include "driver/usb_serial_jtag.h"
#include "esp_timer.h"
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

static esp_err_t run_dma(vpe_codec *codec, voice_pe_silent_dma_result *result)
{
    if (!result) return ESP_ERR_INVALID_ARG;
    memset(result, 0, sizeof *result);
    if (gpio_get_level(VPE_AMP_ENABLE) != 0) {
        (void)gpio_set_level(VPE_AMP_ENABLE, 0);
        if (codec) (void)vpe_codec_mute(codec);
        return ESP_ERR_INVALID_STATE;
    }
    if (codec && (!codec->ready || !codec->muted || gpio_get_level(VPE_JACK_SENSE))) {
        (void)vpe_codec_mute(codec);
        return ESP_ERR_INVALID_STATE;
    }
    i2s_chan_config_t channel_config;
    i2s_std_config_t standard;
    esp_err_t err = voice_pe_i2s_config(VPE_RATE, &channel_config, &standard);
    if (err != ESP_OK) return err;
    i2s_chan_handle_t tx = NULL;
    bool enabled = false;
    size_t preload_size = (size_t)channel_config.dma_desc_num*
                          channel_config.dma_frame_num*2*sizeof(int32_t);
    void *preload = calloc(1, preload_size);
    if (!preload) return ESP_ERR_NO_MEM;
    err = i2s_new_channel(&channel_config, &tx, NULL);
    if (err != ESP_OK) goto cleanup;
    err = i2s_channel_init_std_mode(tx, &standard);
    if (err != ESP_OK) goto cleanup;
    /* Initialize the complete ring before enabling. The boot test stays zero;
     * the explicitly requested tone starts only after a zero-stream lead-in. */
    err = i2s_channel_preload_data(tx, preload, preload_size, &result->preloaded_bytes);
    if (err != ESP_OK) goto cleanup;
    if (result->preloaded_bytes != preload_size) {
        err = ESP_ERR_INVALID_SIZE;
        goto cleanup;
    }
    err = i2s_channel_enable(tx);
    if (err != ESP_OK) goto cleanup;
    enabled = true;
    int32_t samples[64*2] = {0};
    int16_t pcm[64*2];
    int64_t begin = esp_timer_get_time();
    unsigned blocks = codec ? (VPE_TONE_FRAMES/64)+300 : 1500;
    for (unsigned i = 0; i < blocks; ++i) {
        if (esp_timer_get_time()-begin > (codec ? 5000000 : 3000000)) {
            err = ESP_ERR_TIMEOUT;
            ++result->timeouts;
            break;
        }
        if (codec) {
            unsigned char incoming[16];
            int count = usb_serial_jtag_read_bytes(incoming, sizeof incoming, 0);
            bool abort = gpio_get_level(VPE_BUTTON) == 0 || gpio_get_level(VPE_JACK_SENSE);
            for (int k = 0; k < count; ++k) if (incoming[k] == '!') abort = true;
            if (abort) { err = ESP_ERR_INVALID_STATE; break; }
            if (i == 75) {
                if (!vpe_codec_unmute_test(codec)) { err = ESP_ERR_INVALID_RESPONSE; break; }
                err = gpio_set_level(VPE_AMP_ENABLE, 1);
                if (err != ESP_OK) break;
            }
            /* 200 ms of zeros before/after the ramped test notes. */
            for (unsigned k = 0; k < 64; ++k) {
                if (i >= 150 && i < 150+VPE_TONE_FRAMES/64)
                    vpe_test_tone_sample((i-150)*64+k, &pcm[2*k]);
                else pcm[2*k] = pcm[2*k+1] = 0;
            }
            if (voice_pe_pack_s16(pcm, 64, samples, 128) != 128) {
                err = ESP_ERR_INVALID_SIZE;
                break;
            }
        }
        size_t written = 0;
        int64_t before = esp_timer_get_time();
        err = i2s_channel_write(tx, samples, sizeof samples, &written, 100);
        int64_t elapsed = esp_timer_get_time()-before;
        if (elapsed > result->max_write_us) result->max_write_us = elapsed;
        ++result->writes;
        result->submitted_bytes += written;
        if (written != sizeof samples) ++result->partial_writes;
        if (err == ESP_ERR_TIMEOUT) ++result->timeouts;
        if (err != ESP_OK) break;
        if (written != sizeof samples) {
            err = ESP_ERR_INVALID_SIZE;
            break;
        }
    }
    result->elapsed_us = esp_timer_get_time()-begin;
cleanup:
    if (codec) {
        /* Remove speaker gain immediately, before any I2C operation/cleanup. */
        esp_err_t amp = gpio_set_level(VPE_AMP_ENABLE, 0);
        if (err == ESP_OK) err = amp;
        if (!vpe_codec_mute(codec) && err == ESP_OK) err = ESP_ERR_INVALID_RESPONSE;
    }
    if (enabled) {
        esp_err_t stop = i2s_channel_disable(tx);
        if (err == ESP_OK) err = stop;
    }
    if (tx) {
        esp_err_t release = i2s_del_channel(tx);
        if (err == ESP_OK) err = release;
    }
    free(preload);
    /* Idle data low after stopping; WS/BCLK/MCLK remain XMOS inputs. */
    esp_err_t low = gpio_set_level(VPE_TX_DATA, 0);
    gpio_config_t idle = {
        .pin_bit_mask = 1ULL << VPE_TX_DATA, .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE, .pull_down_en = GPIO_PULLDOWN_DISABLE
    };
    if (err == ESP_OK) err = low;
    esp_err_t idle_error = gpio_config(&idle);
    if (err == ESP_OK) err = idle_error;
    if (gpio_get_level(VPE_AMP_ENABLE) != 0 && err == ESP_OK)
        err = ESP_ERR_INVALID_STATE;
    return err;
}
esp_err_t voice_pe_silent_dma(voice_pe_silent_dma_result *result)
{
    return run_dma(NULL, result);
}
esp_err_t voice_pe_tone_test(vpe_codec *codec, voice_pe_silent_dma_result *result)
{
    if (!codec) return ESP_ERR_INVALID_ARG;
    return run_dma(codec, result);
}
