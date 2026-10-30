/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "touch_display.h"
#include "bsp/esp-bsp.h"
#include "bsp/touch.h"
#include "esp_check.h"

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
    ESP_RETURN_ON_ERROR(display_power(),"display","power/reset sequence");
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
    if (!lvgl_port_add_touch(&input)) return ESP_FAIL;
    return bsp_display_brightness_init();
}
