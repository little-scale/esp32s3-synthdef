/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "headless_io.h"
#include "voice_pe_controls.h"
#include "voice_pe_pins.h"
#include "driver/gpio.h"
#include "driver/rmt_tx.h"
#include "driver/rmt_encoder.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <stdatomic.h>
#include <string.h>
static rmt_channel_handle_t channel;
static rmt_encoder_handle_t encoder;
static atomic_uint sequence,words[36];
static uint32_t last_sequence;
static int64_t next_refresh,last_update;
static bool powered,failed;
static uint8_t previous[36];
static rmt_symbol_word_t symbols[36*8+1];
/* Single producer (audio), single consumer (controls). Atomic cells plus an
 * even sequence prevent torn frames without locks or waiting on the audio task. */
void headless_io_led_values(const float rgb[36])
{
    unsigned seq=atomic_load_explicit(&sequence,memory_order_relaxed);
    atomic_store_explicit(&sequence,seq+1,memory_order_seq_cst);
    for(unsigned i=0;i<36;++i){uint32_t bits;memcpy(&bits,&rgb[i],4);atomic_store_explicit(&words[i],bits,memory_order_seq_cst);}
    atomic_store_explicit(&sequence,seq+2,memory_order_seq_cst);
}
esp_err_t voice_pe_led_init(void)
{
    rmt_tx_channel_config_t config={.gpio_num=VPE_LED_DATA,.clk_src=RMT_CLK_SRC_DEFAULT,
        .resolution_hz=40000000,.mem_block_symbols=192,.trans_queue_depth=1};
    esp_err_t err=rmt_new_tx_channel(&config,&channel);if(err!=ESP_OK)return err;
    rmt_copy_encoder_config_t copy={0};err=rmt_new_copy_encoder(&copy,&encoder);
    if(err==ESP_OK)err=rmt_enable(channel);
    if(err!=ESP_OK){if(encoder){rmt_del_encoder(encoder);encoder=NULL;}rmt_del_channel(channel);channel=NULL;}
    return err;
}
void voice_pe_led_poll(void)
{
    if(failed || !channel)return;
    int64_t now=esp_timer_get_time();if(now<next_refresh)return;next_refresh=now+25000;
    unsigned seq=atomic_load_explicit(&sequence,memory_order_seq_cst);
    if(seq&1)return;
    float rgb[36];
    for(unsigned i=0;i<36;++i){uint32_t bits=atomic_load_explicit(&words[i],memory_order_seq_cst);memcpy(&rgb[i],&bits,4);}
    if(seq!=atomic_load_explicit(&sequence,memory_order_seq_cst))return;
    if(seq!=last_sequence){last_sequence=seq;last_update=now;}
    if(!last_update || now-last_update>200000)memset(rgb,0,sizeof rgb);
    uint8_t grb[36];vpe_led_pack(rgb,grb);
    bool any=false;for(unsigned i=0;i<36;++i)any|=grb[i]!=0;
    if(!any && !powered)return;
    if(powered && !memcmp(previous,grb,sizeof grb))return;
    if(!powered){gpio_set_level(VPE_LED_POWER,1);vTaskDelay(pdMS_TO_TICKS(1));powered=true;}
    unsigned at=0;
    for(unsigned i=0;i<36;++i)for(unsigned bit=0;bit<8;++bit){
        bool one=(grb[i]&(0x80u>>bit))!=0;
        /* Official 300/975ns zero, 650/650ns one; exact at 40 MHz. */
        symbols[at++]=(rmt_symbol_word_t){.level0=1,.duration0=one?26:12,.level1=0,.duration1=one?26:39};
    }
    symbols[at++]=(rmt_symbol_word_t){.level0=0,.duration0=6000,.level1=0,.duration1=6000};
    rmt_transmit_config_t transmit={.loop_count=0};
    esp_err_t err=rmt_transmit(channel,encoder,symbols,at*sizeof *symbols,&transmit);
    if(err==ESP_OK)err=rmt_tx_wait_all_done(channel,10);
    if(err!=ESP_OK){gpio_set_level(VPE_LED_POWER,0);powered=false;failed=true;ESP_LOGE("voice_pe_leds","Ring disabled after bounded RMT failure: %s",esp_err_to_name(err));return;}
    memcpy(previous,grb,sizeof grb);
    if(!any){gpio_set_level(VPE_LED_POWER,0);powered=false;}
}
