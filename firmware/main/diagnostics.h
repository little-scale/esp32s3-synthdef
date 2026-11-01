/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include "instrument.h"
#include "master_delay.h"
void diagnostic_benchmark(instrument *s);
void diagnostic_report(void);
int diagnostic_init(void);
void diagnostic_delay(master_delay *,fm_scratch *);
void diagnostic_delay_report(void);
void diagnostic_trace(instrument *);
void diagnostic_trace_report(void);
void diagnostic_control_buses(instrument *);
void diagnostic_control_buses_report(void);

int diagnostic_ugen_profile(instrument *);
void diagnostic_ugen_report(void);
