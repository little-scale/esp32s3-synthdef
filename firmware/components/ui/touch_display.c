/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "touch_display.h"
#include "bsp/esp-bsp.h"
#include "bsp/touch.h"
#include "esp_check.h"
#include "esp_heap_caps.h"
#include <stdio.h>
#include <string.h>

static i2c_master_dev_handle_t pmu;
#ifdef CONFIG_SYNTHDEF_DIAGNOSTICS
static esp_lcd_touch_handle_t trace_touch;
static lv_indev_t *trace_input;
esp_err_t touch_display_trace(unsigned duration_ms)
{
    if(!trace_touch || !trace_input || !duration_ms || duration_ms>60000)return ESP_ERR_INVALID_ARG;
    if(!bsp_display_lock(1000))return ESP_ERR_TIMEOUT;
    lv_indev_enable(trace_input,false);bsp_display_unlock();
    uint8_t id[3]={0};esp_err_t err=esp_lcd_panel_io_rx_param(trace_touch->io,0xa7,id,sizeof id);
    printf("TOUCH_BEGIN duration_ms=%u id_error=%d id=%02x%02x%02x\n",duration_ms,(int)err,id[0],id[1],id[2]);
    uint8_t previous[15]={0};bool previous_valid=false;unsigned samples=0,errors=0,maximum=0;
    TickType_t start=xTaskGetTickCount();
    do {
        uint8_t raw[15];err=esp_lcd_panel_io_rx_param(trace_touch->io,0,raw,sizeof raw);
        if(err==ESP_OK){
            unsigned contacts=raw[2];if(contacts>maximum)maximum=contacts;
            if(!previous_valid || memcmp(raw,previous,sizeof raw)){
                char hex[31];for(unsigned i=0;i<sizeof raw;++i)snprintf(hex+i*2,3,"%02x",raw[i]);
                printf("TOUCH_RAW ms=%lu contacts=%u x=%u y=%u raw=%s\n",
                    (unsigned long)((xTaskGetTickCount()-start)*portTICK_PERIOD_MS),contacts,
                    ((raw[3]&15)<<8)|raw[4],((raw[5]&15)<<8)|raw[6],hex);
                memcpy(previous,raw,sizeof raw);previous_valid=true;
            }++samples;
        }else ++errors;
        vTaskDelay(pdMS_TO_TICKS(20));
    }while((xTaskGetTickCount()-start)*portTICK_PERIOD_MS<duration_ms);
    printf("TOUCH_END samples=%u errors=%u max_contacts=%u\n",samples,errors,maximum);
    if(!bsp_display_lock(1000))return ESP_ERR_TIMEOUT;
    lv_indev_enable(trace_input,true);bsp_display_unlock();return ESP_OK;
}
#endif
static void battery_start(void)
{
    const i2c_device_config_t cfg={.dev_addr_length=I2C_ADDR_BIT_LEN_7,.device_address=0x34,.scl_speed_hz=100000};
    if(i2c_master_bus_add_device(bsp_i2c_get_handle(),&cfg,&pmu)!=ESP_OK)return;
    uint8_t reg=0x03,id=0;
    if(i2c_master_transmit_receive(pmu,&reg,1,&id,1,20)!=ESP_OK || id!=0x4a){
        i2c_master_bus_rm_device(pmu);pmu=NULL;ESP_LOGW("battery","AXP2101 unavailable");
    }
}
esp_err_t touch_display_battery(touch_battery *sample)
{
    *sample=(touch_battery){.percent=-1};
    if(!pmu)return ESP_ERR_NOT_FOUND;
    /* Read-only AXP2101 telemetry, following Waveshare's pinned XPowers
     * reference. Never change rails, charge settings or gauge configuration. */
    uint8_t reg=0,status[2];
    esp_err_t err=i2c_master_transmit_receive(pmu,&reg,1,status,2,20);
    if(err!=ESP_OK)return err;
    sample->present=(status[0]&8)!=0;sample->charging=(status[1]>>5)==1;
    sample->usb=(status[0]&32)!=0 && (status[1]&8)==0;
    if(sample->present){
        uint8_t percent;reg=0xa4;
        err=i2c_master_transmit_receive(pmu,&reg,1,&percent,1,20);
        if(err==ESP_OK && percent<=100)sample->percent=percent;
        /* Presence/charging remain useful when the gauge is unavailable. */
    }
    return ESP_OK;
}

static esp_err_t display_power(void)
{
    /* Official board_variant.c at board repo 78e13f8: TCA9554 P0 is
     * LCD_RESET (low asserts), P1 is display power-enable (high enables).
     * Preserve all other latches/directions; the generic driver constructor
     * resets the entire expander, so use this one startup device handle. */
    ESP_RETURN_ON_ERROR(bsp_i2c_init(),"display","shared I2C");
    const i2c_device_config_t cfg={.dev_addr_length=I2C_ADDR_BIT_LEN_7,
        .device_address=0x20,.scl_speed_hz=100000};
    i2c_master_dev_handle_t device=NULL;
    ESP_RETURN_ON_ERROR(i2c_master_bus_add_device(bsp_i2c_get_handle(),&cfg,&device),"display","power expander");
    uint8_t output,direction,reg=1;
    esp_err_t err=i2c_master_transmit_receive(device,&reg,1,&output,1,100);
    reg=3;
    if (err==ESP_OK) err=i2c_master_transmit_receive(device,&reg,1,&direction,1,100);
    if (err==ESP_OK) {
        ESP_LOGI("display","Power/reset before: output=%02x direction=%02x",output,direction);
        uint8_t data[]={1,(uint8_t)(output|3)};
        err=i2c_master_transmit(device,data,2,100);
        data[0]=3; data[1]=direction & ~3u;
        if (err==ESP_OK) err=i2c_master_transmit(device,data,2,100);
        vTaskDelay(pdMS_TO_TICKS(150));
        data[0]=1; data[1]=(output|2u)&~1u;
        if (err==ESP_OK) err=i2c_master_transmit(device,data,2,100);
        vTaskDelay(pdMS_TO_TICKS(20));
        data[1]=output|3u;
        if (err==ESP_OK) err=i2c_master_transmit(device,data,2,100);
        vTaskDelay(pdMS_TO_TICKS(150));
    }
    esp_err_t removed=i2c_master_bus_rm_device(device);
    if (err!=ESP_OK) return err;
    ESP_LOGI("display","Display power enabled and hardware reset released");
    return removed;
}

static void round_area(lv_area_t *area)
{
    area->x1 &= ~1; area->y1 &= ~1;
    area->x2 |= 1; area->y2 |= 1;
}

esp_err_t touch_display_start(void)
{
    /* BSP 2.0.3's convenience LVGL helper selects the RGB/vsync adapter for a
     * CO5300 QSPI panel. Keep its panel/touch setup but register the SPI adapter,
     * whose DMA-completion callback owns draw-buffer reuse. */
    lvgl_port_cfg_t port=ESP_LVGL_PORT_INIT_CONFIG();
    port.task_affinity=0; port.task_priority=4;
    port.task_stack=10240; port.task_max_sleep_ms=40;
    /* INTERNAL|DEFAULT excludes IDF's reserved DMA/internal pool. The task
     * needs byte-addressable internal RAM, including that pool, just like
     * the audio/control stacks; DEFAULT can fail with larger caches. */
    port.task_stack_caps=MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT;
    ESP_RETURN_ON_ERROR(display_power(),"display","power/reset sequence");
    battery_start();
    ESP_RETURN_ON_ERROR(lvgl_port_init(&port),"display","LVGL initialization");
    esp_lcd_panel_handle_t panel=NULL;
    esp_lcd_panel_io_handle_t io=NULL;
    bsp_display_config_t panel_cfg={.max_transfer_sz=368*20*2};
    ESP_RETURN_ON_ERROR(bsp_display_new(&panel_cfg,&panel,&io),"display","panel initialization");
    esp_lcd_touch_handle_t touch=NULL;
    ESP_RETURN_ON_ERROR(bsp_touch_new(NULL,&touch),"display","touch initialization");
    lvgl_port_display_cfg_t cfg={
        .io_handle=io, .panel_handle=panel,
        .buffer_size=368*20, .hres=368, .vres=448,
        .rounder_cb=round_area,
        .flags={.buff_dma=true,.buff_spiram=false},
    };
    lv_display_t *display=lvgl_port_add_disp(&cfg);
    if (!display) return ESP_ERR_NO_MEM;
    lvgl_port_touch_cfg_t input={.disp=display,.handle=touch};
    lv_indev_t *pointer=lvgl_port_add_touch(&input);
    if (!pointer) return ESP_FAIL;
#ifdef CONFIG_SYNTHDEF_DIAGNOSTICS
    trace_touch=touch;trace_input=pointer;
#endif
    return bsp_display_brightness_init();
}
