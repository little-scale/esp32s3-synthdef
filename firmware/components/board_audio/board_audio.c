/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Pin/codec setup derived from Waveshare BSP 2.0.3 (Apache-2.0).
 * This adapter owns I2S; do not call bsp_audio_init() elsewhere. */
#include "board_audio.h"
#include "bsp/esp-bsp.h"
#include "esp_codec_dev_defaults.h"
#include "esp_check.h"
#include "esp_heap_caps.h"
#include <stdatomic.h>

static i2s_chan_handle_t tx;
static esp_codec_dev_handle_t codec;
static const audio_codec_ctrl_if_t *codec_control;
static atomic_uint dma_errors;
static uint32_t startup_events;
static const char *TAG = "board_audio";

static bool IRAM_ATTR dma_error(i2s_chan_handle_t h, i2s_event_data_t *e, void *ctx)
{
    (void)h; (void)e; (void)ctx;
    atomic_fetch_add_explicit(&dma_errors, 1, memory_order_relaxed);
    return false;
}

esp_err_t board_audio_init(uint32_t rate)
{
    if (codec || tx) return ESP_ERR_INVALID_STATE;
    ESP_RETURN_ON_ERROR(bsp_i2c_init(), TAG, "I2C init");
    i2s_chan_config_t channel = I2S_CHANNEL_DEFAULT_CONFIG(CONFIG_BSP_I2S_NUM, I2S_ROLE_MASTER);
    channel.dma_desc_num = 6;
    channel.dma_frame_num = 128;
    channel.auto_clear = true;
    ESP_RETURN_ON_ERROR(i2s_new_channel(&channel, &tx, NULL), TAG, "I2S channel");
    i2s_std_config_t standard = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(rate),
        .slot_cfg = I2S_STD_PHILIP_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO),
        .gpio_cfg = { .mclk = BSP_I2S_MCLK, .bclk = BSP_I2S_SCLK, .ws = BSP_I2S_LCLK,
                      .dout = BSP_I2S_DOUT, .din = GPIO_NUM_NC },
    };
    ESP_RETURN_ON_ERROR(i2s_channel_init_std_mode(tx, &standard), TAG, "I2S format");
    i2s_event_callbacks_t callbacks = { .on_send_q_ovf = dma_error };
    ESP_RETURN_ON_ERROR(i2s_channel_register_event_callback(tx, &callbacks, NULL), TAG, "I2S events");
    audio_codec_i2s_cfg_t data_cfg = { .port = CONFIG_BSP_I2S_NUM, .tx_handle = tx };
    const audio_codec_data_if_t *data = audio_codec_new_i2s_data(&data_cfg);
    audio_codec_i2c_cfg_t ctrl_cfg = { .port = BSP_I2C_NUM, .addr = ES8311_CODEC_DEFAULT_ADDR,
                                     .bus_handle = bsp_i2c_get_handle() };
    const audio_codec_ctrl_if_t *ctrl = audio_codec_new_i2c_ctrl(&ctrl_cfg);
    codec_control=ctrl;
    const audio_codec_gpio_if_t *gpio = audio_codec_new_gpio();
    if (!data || !ctrl || !gpio) return ESP_ERR_NO_MEM;
    es8311_codec_cfg_t config = {
        .ctrl_if = ctrl, .gpio_if = gpio, .codec_mode = ESP_CODEC_DEV_WORK_MODE_DAC,
        .pa_pin = BSP_POWER_AMP_IO, .pa_reverted = false, .master_mode = false,
        .use_mclk = true, .digital_mic = false,
        .hw_gain = { .pa_voltage = 5.0f, .codec_dac_voltage = 3.3f },
    };
    const audio_codec_if_t *device = es8311_codec_new(&config);
    if (!device) return ESP_ERR_NO_MEM;
    esp_codec_dev_cfg_t dev_cfg = { .dev_type = ESP_CODEC_DEV_TYPE_OUT,
                                  .codec_if = device, .data_if = data };
    codec = esp_codec_dev_new(&dev_cfg);
    if (!codec) return ESP_ERR_NO_MEM;
    esp_codec_dev_sample_info_t sample = { .sample_rate = rate, .channel = 1,
        .bits_per_sample = 16, .mclk_multiple = 256 };
    if (esp_codec_dev_open(codec, &sample) != ESP_CODEC_DEV_OK) return ESP_FAIL;
    if (esp_codec_dev_set_out_vol(codec, 100) != ESP_CODEC_DEV_OK) return ESP_FAIL;
    ESP_LOGI(TAG, "Codec output level=100/100; bounded software master gain follows");
    /* Codec open enables I2S before its startup delays complete. Its DMA buffers
     * contain only zeros, and no producer exists yet. Stop it here; the audio
     * owner starts the measured stream. Retain pre-owner events explicitly. */
    ESP_RETURN_ON_ERROR(i2s_channel_disable(tx),TAG,"park initial DMA");
    startup_events=atomic_load_explicit(&dma_errors,memory_order_relaxed);
    ESP_LOGI(TAG,"Pre-owner startup DMA event overflows=%lu; DMA now stopped",(unsigned long)startup_events);
    return ESP_OK;
}

esp_err_t board_audio_write(const int16_t *mono, size_t frames, size_t *written)
{
    *written = 0;
    return i2s_channel_write(tx, mono, frames * sizeof *mono, written, 100);
}

esp_err_t board_audio_mute(void)
{
    return board_audio_pause();
}

uint32_t board_audio_dma_errors(void)
{
    return atomic_load_explicit(&dma_errors, memory_order_relaxed)-startup_events;
}

static esp_err_t set_mute(bool muted)
{
    if(!codec || !codec_control)return ESP_ERR_INVALID_STATE;
    /* Codec-device 1.5.11 discards the codec's mute callback result. Use the
     * existing control interface, preserve other REG31 bits and verify the
     * transaction before acknowledging maintenance. No second I2C driver. */
    uint8_t value=0,check=0;
    if(codec_control->read_reg(codec_control,0x31,1,&value,1)!=ESP_CODEC_DEV_OK)return ESP_FAIL;
    value=(value&0x9f)|(muted?0x60:0);
    if(codec_control->write_reg(codec_control,0x31,1,&value,1)!=ESP_CODEC_DEV_OK ||
       codec_control->read_reg(codec_control,0x31,1,&check,1)!=ESP_CODEC_DEV_OK || check!=value)return ESP_FAIL;
    return ESP_OK;
}
esp_err_t board_audio_pause(void) {return set_mute(true);}
esp_err_t board_audio_resume(void) {return set_mute(false);}
esp_err_t board_audio_stop_dma(void) {return i2s_channel_disable(tx);}
esp_err_t board_audio_start_dma(void) {return i2s_channel_enable(tx);}
