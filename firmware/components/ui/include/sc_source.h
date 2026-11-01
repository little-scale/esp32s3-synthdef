/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stddef.h>
#include <stdint.h>
enum { SC_TEXT,SC_STRING,SC_CLASS,SC_GLOBAL,SC_KEYWORD,SC_NUMBER,SC_COMMENT };
#define SC_SOURCE_MAX 65536u
/* One style byte per original UTF-8 byte; no text mutation or allocation. */
void sc_source_highlight(const char *text,size_t bytes,uint8_t *styles);
uint32_t sc_source_codepoint(const char *text,size_t bytes,size_t *offset);
uint32_t sc_source_color(unsigned style);
