/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include "lvgl.h"
#include <stdbool.h>
#include <stddef.h>
lv_obj_t *sc_code_view_create(lv_obj_t *parent,lv_event_cb_t play);
/* Display lock held by caller. Copies original bytes into owned PSRAM. */
bool sc_code_view_source(const char *text,size_t bytes);
/* Zero-based line/column, clamped to the document; display lock held. */
void sc_code_view_scroll_to(uint32_t line,uint32_t column);
void sc_code_view_position(uint32_t *line,uint32_t *column);
