/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#ifdef ESP_PLATFORM
#include "sdkconfig.h"
#endif
#if defined(CONFIG_SYNTHDEF_VOICE_PE_LOW_RATE) && defined(CONFIG_SYNTHDEF_VOICE_PE_NATIVE_16K)
#error Select either native 16k or converted 16k, not both
#endif
#if defined(CONFIG_SYNTHDEF_VOICE_PE) && (defined(CONFIG_SYNTHDEF_VOICE_PE_LOW_RATE) || defined(CONFIG_SYNTHDEF_VOICE_PE_NATIVE_16K))
#define SYNTHDEF_SAMPLE_RATE 16000u
#elif defined(CONFIG_SYNTHDEF_VOICE_PE)
#define SYNTHDEF_SAMPLE_RATE 48000u
#else
#define SYNTHDEF_SAMPLE_RATE 44100u
#endif
#if defined(CONFIG_SYNTHDEF_VOICE_PE_NATIVE_16K)
#define SYNTHDEF_OUTPUT_SAMPLE_RATE 16000u
#elif defined(CONFIG_SYNTHDEF_VOICE_PE)
#define SYNTHDEF_OUTPUT_SAMPLE_RATE 48000u
#else
#define SYNTHDEF_OUTPUT_SAMPLE_RATE SYNTHDEF_SAMPLE_RATE
#endif
static inline int synthdef_rate_valid(unsigned rate)
{
    return rate == 16000 || rate == 44100 || rate == 48000;
}
