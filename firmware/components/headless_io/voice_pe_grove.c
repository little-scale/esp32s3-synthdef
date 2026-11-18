/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "headless_io.h"
#include "voice_pe_dlight.h"
#include "voice_pe_pins.h"
#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "esp_timer.h"
#include "esp_log.h"
#include <stdio.h>
static vpe_dlight_mailbox mailbox;
static atomic_uint available,samples,errors,last_sample_ms,audio_sequence;
static atomic_int last_error;
static vpe_dlight sensor;
static i2c_master_bus_handle_t bus;
static i2c_master_dev_handle_t device;
static bool ready;
static bool command(void *unused,uint8_t byte)
{(void)unused;esp_err_t e=i2c_master_transmit(device,&byte,1,5);atomic_store(&last_error,e);return e==ESP_OK;}
static bool receive(void *unused,uint8_t bytes[2])
{(void)unused;esp_err_t e=i2c_master_receive(device,bytes,2,5);atomic_store(&last_error,e);return e==ESP_OK;}
void voice_pe_grove_init(void)
{
    vpe_dlight_mailbox_init(&mailbox);
#ifdef CONFIG_SYNTHDEF_VOICE_PE_DLIGHT
    esp_err_t err=gpio_set_level(VPE_GROVE_POWER,0);
    gpio_config_t power={.pin_bit_mask=1ULL<<VPE_GROVE_POWER,.mode=GPIO_MODE_OUTPUT};
    if(err==ESP_OK)err=gpio_config(&power);
    if(err==ESP_OK)err=gpio_set_level(VPE_GROVE_POWER,1);
    i2c_master_bus_config_t config={.i2c_port=-1,.sda_io_num=VPE_GROVE_SDA,.scl_io_num=VPE_GROVE_SCL,
        .clk_source=I2C_CLK_SRC_DEFAULT,.glitch_ignore_cnt=7,.flags.enable_internal_pullup=true};
    if(err==ESP_OK)err=i2c_new_master_bus(&config,&bus);
    i2c_device_config_t chip={.dev_addr_length=I2C_ADDR_BIT_LEN_7,.device_address=VPE_DLIGHT_ADDRESS,.scl_speed_hz=100000};
    if(err==ESP_OK)err=i2c_master_bus_add_device(bus,&chip,&device);
    atomic_store(&last_error,err);
    if(err!=ESP_OK){
        if(bus){i2c_del_master_bus(bus);bus=NULL;}
        gpio_set_level(VPE_GROVE_POWER,0);
        ESP_LOGW("voice_pe_grove","DLight unavailable: %s; existing controls retained",esp_err_to_name(err));return;
    }
    vpe_dlight_init(&sensor,esp_timer_get_time());ready=true;
    ESP_LOGI("voice_pe_grove","DLight: SDA=%d SCL=%d power=%d address=0x23; buses 42 normalised / 43 lux",VPE_GROVE_SDA,VPE_GROVE_SCL,VPE_GROVE_POWER);
#endif
}
void voice_pe_grove_poll(void)
{
    if(!ready)return;
    const vpe_dlight_io io={.command=command,.receive=receive};
    if(vpe_dlight_poll(&sensor,&io,esp_timer_get_time())){
        atomic_store(&last_sample_ms,(uint32_t)(sensor.last_sample_us/1000));
        vpe_dlight_publish(&mailbox,sensor.raw);
    }
    atomic_store(&available,sensor.available);atomic_store(&samples,sensor.samples);atomic_store(&errors,sensor.errors);
}
bool headless_io_grove_sample(uint32_t *sequence,float values[2])
{
    bool fresh=vpe_dlight_consume(&mailbox,sequence,values);
    if(fresh)atomic_store(&audio_sequence,*sequence);
    return fresh;
}
int voice_pe_grove_info(char *out,size_t size)
{
    uint32_t sequence=0;float value[2]={0};bool has_sample=vpe_dlight_consume(&mailbox,&sequence,value);
    int64_t age=has_sample?(int64_t)(uint32_t)((uint32_t)(esp_timer_get_time()/1000)-atomic_load(&last_sample_ms)):-1;
    return snprintf(out,size,"\"grove_light\":{\"enabled\":%s,\"available\":%s,\"has_sample\":%s,\"model\":\"BH1750FVI\",\"address\":35,\"buses\":[42,43],\"labels\":[\"light_normalised\",\"light_lux\"],\"values\":[%.6f,%.3f],\"normalise_lux\":1000,\"poll_ms\":200,\"samples\":%u,\"errors\":%u,\"sequence\":%lu,\"audio_sequence\":%u,\"age_ms\":%lld,\"last_error\":%d,\"hold_last\":true}",ready?"true":"false",atomic_load(&available)?"true":"false",has_sample?"true":"false",(double)value[0],(double)value[1],atomic_load(&samples),atomic_load(&errors),(unsigned long)sequence,atomic_load(&audio_sequence),(long long)age,atomic_load(&last_error));
}
