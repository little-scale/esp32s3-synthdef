/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "voice_pe_board.h"
#include "voice_pe_pins.h"
#include "driver/gpio.h"

esp_err_t voice_pe_safe_init(void)
{
    /* Preload low before enabling outputs. No codec/XMOS/I2C activity. */
    esp_err_t err = gpio_set_level(VPE_AMP_ENABLE, 0);
    if (err != ESP_OK) return err;
    err = gpio_set_level(VPE_LED_POWER, 0);
    if (err != ESP_OK) return err;
    gpio_config_t outputs = {
        .pin_bit_mask = (1ULL << VPE_AMP_ENABLE) | (1ULL << VPE_LED_POWER),
        /* Enable pad input as well so safety checks read the actual logic
         * level. gpio_get_level() returns zero for an input-disabled pad. */
        .mode = GPIO_MODE_INPUT_OUTPUT
    };
    err = gpio_config(&outputs);
    if (err != ESP_OK) return err;
    if (gpio_get_level(VPE_AMP_ENABLE) || gpio_get_level(VPE_LED_POWER))
        return ESP_ERR_INVALID_STATE;
    gpio_config_t inputs = {
        .pin_bit_mask = (1ULL << VPE_BUTTON) | (1ULL << VPE_MUTE_SENSE) |
                        (1ULL << VPE_JACK_SENSE) | (1ULL << VPE_ENCODER_A) |
                        (1ULL << VPE_ENCODER_B),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE, .pull_down_en = GPIO_PULLDOWN_DISABLE
    };
    return gpio_config(&inputs);
}

voice_pe_inputs voice_pe_read_inputs(void)
{
    return (voice_pe_inputs){gpio_get_level(VPE_BUTTON), gpio_get_level(VPE_MUTE_SENSE),
        gpio_get_level(VPE_JACK_SENSE), gpio_get_level(VPE_ENCODER_A), gpio_get_level(VPE_ENCODER_B)};
}

esp_err_t voice_pe_i2s_config(unsigned rate, i2s_chan_config_t *channel,
                            i2s_std_config_t *standard)
{
    if (!channel || !standard || (rate !=16000 && rate !=48000)) return ESP_ERR_INVALID_ARG;
    *channel = (i2s_chan_config_t)I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_SLAVE);
    channel->dma_desc_num = 6;
    channel->dma_frame_num = 128;
    channel->auto_clear = true;
    *standard = (i2s_std_config_t){
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(rate),
        .slot_cfg = I2S_STD_PHILIP_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_32BIT, I2S_SLOT_MODE_STEREO),
        .gpio_cfg = {.mclk = I2S_GPIO_UNUSED, .bclk = VPE_TX_BCLK,
                     .ws = VPE_TX_WS, .dout = VPE_TX_DATA, .din = I2S_GPIO_UNUSED}
    };
    return ESP_OK;
}

esp_err_t voice_pe_audio_start(void)
{
    /* A successful return would falsely imply codec/clock readiness. */
    return ESP_ERR_NOT_SUPPORTED;
}
