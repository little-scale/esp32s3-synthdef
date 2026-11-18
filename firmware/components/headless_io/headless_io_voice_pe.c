/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "headless_io.h"
#include "driver/gpio.h"
#include "driver/pulse_cnt.h"
#include "esp_timer.h"
#include <stdatomic.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
esp_err_t voice_pe_led_init(void);
void voice_pe_led_poll(void);
void voice_pe_grove_init(void);
void voice_pe_grove_poll(void);
int voice_pe_grove_info(char *,size_t);
static atomic_uint bank[3];
static pcnt_unit_handle_t encoder;
static int previous_count;
static float dial=.5f;
static unsigned button_previous,button_stable;
static int64_t next_poll;
static void store(unsigned k,float value)
{uint32_t bits;memcpy(&bits,&value,4);atomic_store_explicit(&bank[k],bits,memory_order_relaxed);}
esp_err_t headless_io_init(void)
{
    gpio_config_t pins={.pin_bit_mask=(1ULL<<0)|(1ULL<<3),.mode=GPIO_MODE_INPUT};
    esp_err_t err=gpio_config(&pins);if(err!=ESP_OK)return err;
    pcnt_unit_config_t unit={.low_limit=-30000,.high_limit=30000,.flags.accum_count=true};
    err=pcnt_new_unit(&unit,&encoder);if(err!=ESP_OK)return err;
    pcnt_channel_handle_t a,b;
    pcnt_chan_config_t ca={.edge_gpio_num=16,.level_gpio_num=18};
    pcnt_chan_config_t cb={.edge_gpio_num=18,.level_gpio_num=16};
    if((err=pcnt_new_channel(encoder,&ca,&a))!=ESP_OK)return err;
    if((err=pcnt_new_channel(encoder,&cb,&b))!=ESP_OK)return err;
    if((err=pcnt_channel_set_edge_action(a,PCNT_CHANNEL_EDGE_ACTION_DECREASE,PCNT_CHANNEL_EDGE_ACTION_INCREASE))!=ESP_OK)return err;
    if((err=pcnt_channel_set_edge_action(b,PCNT_CHANNEL_EDGE_ACTION_INCREASE,PCNT_CHANNEL_EDGE_ACTION_DECREASE))!=ESP_OK)return err;
    if((err=pcnt_channel_set_level_action(a,PCNT_CHANNEL_LEVEL_ACTION_KEEP,PCNT_CHANNEL_LEVEL_ACTION_INVERSE))!=ESP_OK)return err;
    if((err=pcnt_channel_set_level_action(b,PCNT_CHANNEL_LEVEL_ACTION_KEEP,PCNT_CHANNEL_LEVEL_ACTION_INVERSE))!=ESP_OK)return err;
    if((err=pcnt_unit_add_watch_point(encoder,30000))!=ESP_OK)return err;
    if((err=pcnt_unit_add_watch_point(encoder,-30000))!=ESP_OK)return err;
    if((err=pcnt_unit_enable(encoder))!=ESP_OK)return err;
    if((err=pcnt_unit_clear_count(encoder))!=ESP_OK)return err;
    if((err=pcnt_unit_start(encoder))!=ESP_OK)return err;
    store(0,dial);store(1,(float)gpio_get_level(3));store(2,0);
    err=voice_pe_led_init();if(err!=ESP_OK)return err;
    voice_pe_grove_init();return ESP_OK;
}
void headless_io_poll(void)
{
    voice_pe_led_poll();
    int64_t now=esp_timer_get_time();if(now<next_poll)return;next_poll=now+10000;
    voice_pe_grove_poll();
    int count;
    if(pcnt_unit_get_count(encoder,&count)==ESP_OK){
        int64_t delta=(int64_t)count-previous_count;previous_count=count;
        if(delta>=-1000 && delta<=1000){dial+=(float)delta*.0125f;if(dial<0)dial=0;if(dial>1)dial=1;store(0,dial);}
    }
    store(1,(float)gpio_get_level(3));
    unsigned pressed=gpio_get_level(0)==0;
    if(pressed==button_previous){if(button_stable<2)++button_stable;if(button_stable==2)store(2,(float)pressed);}
    else {button_previous=pressed;button_stable=0;}
}
void headless_io_values(float out[3])
{for(unsigned i=0;i<3;++i){uint32_t bits=atomic_load(&bank[i]);memcpy(&out[i],&bits,4);}}
int headless_io_info(char *out,size_t size)
{
    float value[3];headless_io_values(value);
#ifdef CONFIG_SYNTHDEF_VOICE_PE_DLIGHT
    unsigned next_reserved=44;
#else
    unsigned next_reserved=42;
#endif
    gpio_io_config_t a={0},b={0};
    bool configured=gpio_get_io_config(16,&a)==ESP_OK && gpio_get_io_config(18,&b)==ESP_OK;
    int used=snprintf(out,size,"{\"led_buses\":{\"base\":3,\"count\":39,\"all_rgb_base\":39,\"grove_reserved_base\":%u,\"leds\":12,\"order\":\"RGB\",\"maximum_brightness\":0.2},\"analog_enabled\":false,\"buses\":[1,2,0],\"labels\":[\"dial\",\"microphone_mute\",\"button\"],\"gpio\":[16,18,3,0],\"values\":[%.6f,%.0f,%.0f],\"encoder_pullups\":[%d,%d],\"encoder_inputs\":[%d,%d],\"encoder_count\":%d,\"raw_ab\":[%d,%d],\"amplifier_enabled\":%d,\"led_power\":%d}",next_reserved,(double)value[0],(double)value[1],(double)value[2],configured && a.pu,configured && b.pu,configured && a.ie,configured && b.ie,previous_count,gpio_get_level(16),gpio_get_level(18),gpio_get_level(47),gpio_get_level(45));
    if(used<=0 || (size_t)used>=size)return 0;
    out[used-1]=',';
    int extra=voice_pe_grove_info(out+used,size-(size_t)used);
    if(extra<=0 || (size_t)extra+1>=size-(size_t)used)return 0;
    out[used+extra]='}';out[used+extra+1]=0;return 1;
}
