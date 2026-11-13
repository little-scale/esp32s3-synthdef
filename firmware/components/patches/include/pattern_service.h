/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
const char *pattern_service_error(void);
#include "patch_service.h"
int pattern_service_init(int (*remote)(const char *,const unsigned char *,size_t,char *,size_t),
                         int (*instance)(bool,const unsigned char *,size_t));
void pattern_service_bind(const fm_graph *,const unsigned char hash[32],bool store_available);
/* Same control owner as patches_line/exchange/tick. Never called by audio. */
void pattern_service_tick(bool available);
int pattern_service_command(const char *,const unsigned char *,size_t,unsigned channel,char *,size_t);
void pattern_service_stop(void);
