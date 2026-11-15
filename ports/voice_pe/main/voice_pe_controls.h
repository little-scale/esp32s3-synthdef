/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stdint.h>
enum {
    VPE_BUS_DIAL=1, VPE_BUS_MIC_MUTE=2, VPE_BUS_BUTTON=0,
    VPE_BUS_LED_BASE=3, VPE_LED_CHANNELS=39, VPE_RING_LEDS=12,
    VPE_BUS_ALL_LEDS=39, VPE_GROVE_RESERVED_BASE=42,
    VPE_LED_MAX_BYTE=51 /* 20% physical brightness cap for initial USB-powered port */
};
/* Each graph adds its own Out.kr writers. Explicit FX writes override Main on
 * that channel; an unwritten channel is black. No pointer is retained. */
void vpe_led_resolve(const float main_rgb[39],uint64_t main_mask,
                     const float fx_rgb[39],uint64_t fx_mask,float out_rgb[39]);
/* Logical LED 0 maps to physical 7, following the official ring remapping.
 * Input is RGB, output is physical GRB with bounded linear brightness. */
void vpe_led_pack(const float rgb[36],uint8_t grb[36]);

/* First upgrade from the quiet codec profile starts at <=5%; acknowledged
 * unity-gain boots preserve normal user volume choices. */
unsigned vpe_startup_volume(unsigned requested,unsigned unity_profile_acknowledged);
