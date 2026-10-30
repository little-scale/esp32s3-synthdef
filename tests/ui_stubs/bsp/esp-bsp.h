#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "lvgl.h"
#include "esp_err.h"
typedef struct { int task_affinity,task_priority,task_stack,task_max_sleep_ms; } preview_port_cfg;
typedef struct {
    preview_port_cfg lvgl_port_cfg;
    unsigned buffer_size;
    struct { bool buff_spiram; } flags;
} bsp_display_cfg_t;
#define ESP_LVGL_PORT_INIT_CONFIG() {0}
lv_disp_t *bsp_display_start_with_config(const bsp_display_cfg_t *cfg);
bool bsp_display_lock(uint32_t ms);
void bsp_display_unlock(void);
esp_err_t bsp_display_brightness_set(int percent);
