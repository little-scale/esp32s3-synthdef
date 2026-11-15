/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stddef.h>
typedef struct { unsigned frames, crossings; float peak; } voice_pe_probe_result;
/* Offline core-engine smoke check only; no board, I/O, FX wrapper or admission. */
int voice_pe_render_probe(const unsigned char *fixture, size_t bytes, unsigned rate,
                         voice_pe_probe_result *result);
