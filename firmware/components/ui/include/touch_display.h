/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stdbool.h>
#include "esp_err.h"
esp_err_t touch_display_start(void);
typedef struct {bool present,charging,usb;int percent;} touch_battery;
esp_err_t touch_display_battery(touch_battery *sample);
#ifdef CONFIG_SYNTHDEF_DIAGNOSTICS
/* Control task only; audio must be parked. Raw, read-only controller capture. */
esp_err_t touch_display_trace(unsigned duration_ms);
#endif
