/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stddef.h>
#include "esp_err.h"
#include "esp_heap_caps.h"

/* Keep LVGL's fixed TLSF pool, but leave internal RAM for Wi-Fi and DMA.
 * lv_mem_deinit() calls lv_mem_init() again; retain this allocation for reuse.
 * As with LVGL initialization itself, calls belong to the UI owner. */
static inline void *synthdef_lvgl_pool_alloc(size_t bytes)
{
    static void *pool;
    static size_t pool_bytes;
    ESP_ERROR_CHECK(pool && pool_bytes != bytes ? ESP_ERR_INVALID_SIZE : ESP_OK);
    if (!pool) {
        pool = heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
        ESP_ERROR_CHECK(pool ? ESP_OK : ESP_ERR_NO_MEM);
        pool_bytes = bytes;
    }
    return pool;
}
