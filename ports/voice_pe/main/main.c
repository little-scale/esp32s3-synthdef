/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "voice_pe_board.h"
#include "voice_pe_pins.h"
#include "voice_pe_probe.h"
#include "voice_pe_survey.h"
#include "voice_pe_silent_dma.h"
#include "voice_pe_codec.h"
#include "voice_pe_test_tone.h"
#include "driver/usb_serial_jtag.h"
#include "driver/usb_serial_jtag_vfs.h"
#include "esp_random.h"
#include "driver/gpio.h"
#include "esp_flash.h"
#include "esp_log.h"
#include "esp_psram.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <inttypes.h>
#include <string.h>
extern const unsigned char probe_start[] asm("_binary_probe_scsyndef_start");
extern const unsigned char probe_end[] asm("_binary_probe_scsyndef_end");
static voice_pe_codec_device codec;
static uint32_t tone_token;
static void bench_status(void)
{
    ESP_LOGI("voice_pe_probe", "TONE_READY token=%08" PRIx32 " ready=%u muted=%u amp=%d jack=%d",
             tone_token, codec.sequence.ready, codec.sequence.muted,
             gpio_get_level(VPE_AMP_ENABLE), gpio_get_level(VPE_JACK_SENSE));
}
void app_main(void)
{
    const char *tag = "voice_pe_probe";
    ESP_ERROR_CHECK(voice_pe_safe_init());
    usb_serial_jtag_driver_config_t usb = {.rx_buffer_size = 512, .tx_buffer_size = 4096};
    ESP_ERROR_CHECK(usb_serial_jtag_driver_install(&usb));
    usb_serial_jtag_vfs_use_driver();
    uint32_t flash_size = 0;
    ESP_ERROR_CHECK(esp_flash_get_size(NULL, &flash_size));
    ESP_LOGW(tag, "UNVALIDATED SILENT SCAFFOLD. Audio start is intentionally blocked.");
    ESP_LOGI(tag, "IDF=%s flash=%" PRIu32 " PSRAM=%u", esp_get_idf_version(),
             flash_size, (unsigned)esp_psram_get_size());
    if (flash_size != 16u*1024u*1024u || esp_psram_get_size() != 8u*1024u*1024u) {
        ESP_LOGE(tag, "Memory differs from expected board; stopping probe.");
        return;
    }
    i2s_chan_config_t channel;
    i2s_std_config_t standard;
    ESP_ERROR_CHECK(voice_pe_i2s_config(VPE_RATE, &channel, &standard));
    ESP_LOGI(tag, "I2S proposal: slave, 48000 Hz, stereo S32, no ESP MCLK; zero-only test gated by survey");
    voice_pe_probe_result result;
    int ok = voice_pe_render_probe(probe_start, (size_t)(probe_end-probe_start), VPE_RATE, &result);
    ESP_LOGI(tag, "Offline engine probe: %s frames=%u crossings=%u peak=%f (no playback)",
             ok ? "PASS" : "FAIL", result.frames, result.crossings, (double)result.peak);
    if (!ok) return;
    voice_pe_survey_result survey;
    esp_err_t survey_error = voice_pe_survey(&survey);
    if (survey_error == ESP_OK) {
        ESP_LOGI(tag, "SURVEY codec_0x18=%s xmos_0x42=%s "
                 "ws_hz=%.1f bclk_hz=%.1f ws_pulses=%d bclk_pulses=%d "
                 "ws_us=%" PRId64 " bclk_us=%" PRId64,
                 esp_err_to_name(survey.codec), esp_err_to_name(survey.xmos),
                 survey.ws.hz, survey.bclk.hz, survey.ws.pulses, survey.bclk.pulses,
                 survey.ws.elapsed_us, survey.bclk.elapsed_us);
        bool nominal = survey.codec == ESP_OK && survey.xmos == ESP_OK &&
            survey.ws.hz > 47040 && survey.ws.hz < 48960 &&
            survey.bclk.hz > 3010560 && survey.bclk.hz < 3133440;
        ESP_LOGI(tag, "SURVEY nominal_presence_and_clocks=%d; audio remains blocked", nominal);
        if (nominal) {
            esp_err_t codec_error = voice_pe_codec_init(&codec);
            ESP_LOGI(tag, "CODEC status=%s ready=%u muted=%u checks=%u power=0x%02x amp=%d",
                     esp_err_to_name(codec_error), codec.sequence.ready, codec.sequence.muted,
                     codec.sequence.checks, codec.sequence.power_flags, gpio_get_level(VPE_AMP_ENABLE));
            if (codec_error != ESP_OK) return;
            voice_pe_silent_dma_result dma;
            esp_err_t dma_error = voice_pe_silent_dma(&dma);
            ESP_LOGI(tag, "SILENT_DMA status=%s preloaded=%u submitted=%u writes=%" PRIu32
                     " partial=%" PRIu32 " timeouts=%" PRIu32
                     " elapsed_us=%" PRId64 " max_write_us=%" PRId64 " amp=%d",
                     esp_err_to_name(dma_error), (unsigned)dma.preloaded_bytes,
                     (unsigned)dma.submitted_bytes, dma.writes, dma.partial_writes,
                     dma.timeouts, dma.elapsed_us, dma.max_write_us,
                     gpio_get_level(VPE_AMP_ENABLE));
            int verified_mute = vpe_codec_check_muted(&codec.sequence);
            ESP_LOGI(tag, "CODEC after_dma_muted=%d amp=%d", verified_mute,
                     gpio_get_level(VPE_AMP_ENABLE));
            if (!verified_mute || dma_error != ESP_OK) {
                (void)voice_pe_codec_close(&codec);
                return;
            }
        }
    } else {
        ESP_LOGE(tag, "SURVEY failed: %s; audio remains blocked", esp_err_to_name(survey_error));
    }
    /* Sample quickly, report slowly. These are raw transitions, not debounced
     * presses or encoder detents. They expose bounce and missed Gray-code steps
     * instead of claiming to qualify a decoder from one-Hz level snapshots. */
    voice_pe_inputs previous = voice_pe_read_inputs();
    uint32_t button_edges = 0, mute_edges = 0, jack_edges = 0;
    uint32_t encoder_edges = 0, encoder_invalid = 0, polls = 0;
    int64_t last_poll = esp_timer_get_time(), next_report = last_poll;
    uint32_t max_gap_us = 0;
    tone_token = esp_random();
    bench_status();
    char command[48];
    unsigned command_used = 0;
    bool command_dropped = false;
    int64_t tone_after = 0;
    for (;;) {
        int64_t now = esp_timer_get_time();
        uint32_t gap = (uint32_t)(now-last_poll);
        if (gap > max_gap_us) max_gap_us = gap;
        last_poll = now;
        voice_pe_inputs in = voice_pe_read_inputs();
        button_edges += in.button != previous.button;
        mute_edges += in.mute != previous.mute;
        jack_edges += in.jack != previous.jack;
        unsigned changed = (unsigned)(in.encoder_a != previous.encoder_a)
                         + (unsigned)(in.encoder_b != previous.encoder_b);
        encoder_edges += changed != 0;
        encoder_invalid += changed == 2;
        ++polls;
        previous = in;
        unsigned char incoming[32];
        int received = usb_serial_jtag_read_bytes(incoming, sizeof incoming, 0);
        for (int i = 0; i < received; ++i) {
            unsigned char ch = incoming[i];
            if (ch == '!') {
                (void)gpio_set_level(VPE_AMP_ENABLE, 0);
                (void)vpe_codec_mute(&codec.sequence);
                tone_token = esp_random();
                tone_after = esp_timer_get_time()+5000000;
                command_used = 0; command_dropped = true;
                continue;
            }
            if (ch == '\r') continue;
            if (ch == '\n') {
                command[command_used] = 0;
                if (!command_dropped && strcmp(command, "VPE_STATUS") == 0) bench_status();
                else if (!command_dropped && vpe_test_tone_command_matches(command, tone_token)) {
                    tone_token = esp_random(); /* Consume challenge before doing any work. */
                    if (esp_timer_get_time() < tone_after) {
                        ESP_LOGW(tag, "TONE_REFUSED cooldown");
                    } else {
                        voice_pe_silent_dma_result tone;
                        esp_err_t tone_error = voice_pe_tone_test(&codec.sequence, &tone);
                        ESP_LOGI(tag, "TONE_DONE status=%s writes=%" PRIu32 " partial=%" PRIu32
                                 " timeouts=%" PRIu32 " elapsed_us=%" PRId64 " muted=%u amp=%d",
                                 esp_err_to_name(tone_error), tone.writes, tone.partial_writes,
                                 tone.timeouts, tone.elapsed_us, codec.sequence.muted,
                                 gpio_get_level(VPE_AMP_ENABLE));
                        tone_after = esp_timer_get_time()+5000000;
                    }
                    bench_status();
                }
                command_used = 0; command_dropped = false;
            } else if (ch < 32 || ch > 126 || command_used >= sizeof command-1) {
                command_used = 0; command_dropped = true;
            } else if (!command_dropped) command[command_used++] = (char)ch;
        }
        if (now >= next_report) {
            ESP_LOGI(tag, "INPUT button=%d mute=%d jack=%d A=%d B=%d "
                     "edges=%" PRIu32 ",%" PRIu32 ",%" PRIu32
                     " encoder=%" PRIu32 " invalid=%" PRIu32
                     " polls=%" PRIu32 " max_gap_us=%" PRIu32,
                     in.button, in.mute, in.jack, in.encoder_a, in.encoder_b,
                     button_edges, mute_edges, jack_edges, encoder_edges,
                     encoder_invalid, polls, max_gap_us);
            next_report = now+1000000;
        }
        vTaskDelay(pdMS_TO_TICKS(1));
    }
}
