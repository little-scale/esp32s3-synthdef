/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stddef.h>
#include "esp_err.h"
esp_err_t headless_io_init(void);
void headless_io_poll(void);
/* Audio owner copies a stable scalar per channel; no ADC calls on that task. */
void headless_io_values(float values[3]);
int headless_io_info(char *,size_t);
