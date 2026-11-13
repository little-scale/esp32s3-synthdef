/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include "esp_err.h"
#include <stdbool.h>
#include <stddef.h>

/* Keep input polling nonblocking for standalone buttons/network work. Output
 * uses the SDK's bounded, yielding buffered transport instead of FIFO spins. */
esp_err_t usb_console_init(void);

/* Packet-sized protocol writes, serialized with stdout. An unread host gets
 * a bounded yielding wait; a retry starts on a fresh line after truncation. */
bool usb_console_write_frame(const char *wire, size_t bytes);
