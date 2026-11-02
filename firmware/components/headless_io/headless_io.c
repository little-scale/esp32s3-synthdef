/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "headless_io.h"
#include "sdkconfig.h"
#include "driver/gpio.h"
#include "esp_timer.h"
#include <stdatomic.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#ifdef CONFIG_SYNTHDEF_ANALOG_INPUTS
#include "esp_adc/adc_oneshot.h"
static adc_oneshot_unit_handle_t adc;
static float smooth[2];
#endif
static atomic_uint bank[3];
static unsigned previous_button,stable_button;
static int64_t next_poll;
static void store(unsigned index,float value){uint32_t bits;memcpy(&bits,&value,4);atomic_store_explicit(&bank[index],bits,memory_order_relaxed);}
esp_err_t headless_io_init(void)
{
    gpio_config_t button={.pin_bit_mask=1ULL<<GPIO_NUM_0,.mode=GPIO_MODE_INPUT,.pull_up_en=GPIO_PULLUP_ENABLE};
    esp_err_t result=gpio_config(&button);if(result!=ESP_OK)return result;
#ifdef CONFIG_SYNTHDEF_ANALOG_INPUTS
    adc_oneshot_unit_init_cfg_t unit={.unit_id=ADC_UNIT_1};result=adc_oneshot_new_unit(&unit,&adc);if(result!=ESP_OK)return result;
    adc_oneshot_chan_cfg_t channel={.atten=ADC_ATTEN_DB_12,.bitwidth=ADC_BITWIDTH_12};
    if((result=adc_oneshot_config_channel(adc,ADC_CHANNEL_0,&channel))!=ESP_OK)return result;
    if((result=adc_oneshot_config_channel(adc,ADC_CHANNEL_1,&channel))!=ESP_OK)return result;
#endif
    return ESP_OK;
}
void headless_io_poll(void)
{
    int64_t now=esp_timer_get_time();if(now<next_poll)return;next_poll=now+10000;
    unsigned pressed=gpio_get_level(GPIO_NUM_0)==0;
    if(pressed==previous_button){if(stable_button<2)++stable_button;if(stable_button==2)store(2,(float)pressed);}
    else {previous_button=pressed;stable_button=0;}
#ifdef CONFIG_SYNTHDEF_ANALOG_INPUTS
    for(unsigned i=0;i<2;++i){int raw;if(adc_oneshot_read(adc,(adc_channel_t)i,&raw)==ESP_OK){smooth[i]+=.2f*((float)raw/4095.0f-smooth[i]);store(i,smooth[i]);}}
#endif
}
void headless_io_values(float values[3])
{for(unsigned i=0;i<3;++i){uint32_t bits=atomic_load_explicit(&bank[i],memory_order_relaxed);memcpy(&values[i],&bits,4);}}
int headless_io_info(char *out,size_t size)
{
    float values[3];headless_io_values(values);
#ifdef CONFIG_SYNTHDEF_ANALOG_INPUTS
    const char *analog="true";
#else
    const char *analog="false";
#endif
    return snprintf(out,size,"{\"analog_enabled\":%s,\"buses\":[8,9,10],\"gpio\":[1,2,0],\"values\":[%.6f,%.6f,%.0f]}",analog,(double)values[0],(double)values[1],(double)values[2])>0;
}
