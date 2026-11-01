/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#ifdef ESP_PLATFORM
#include "sdkconfig.h"
#endif
#ifndef PATCH_FM1_COMPAT
#ifdef CONFIG_SYNTHDEF_FM1_COMPAT
#define PATCH_FM1_COMPAT 1
#else
#define PATCH_FM1_COMPAT 0
#endif
#endif
#if PATCH_FM1_COMPAT
#define PATCH_POLICY "fm1-compat-v1"
#else
#define PATCH_POLICY "catalog-voice-v2"
#endif
