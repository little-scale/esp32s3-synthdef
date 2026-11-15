/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "voice_pe_controls.h"
#include <math.h>
static float unit(float value)
{return !isfinite(value) || value<0?0:value>1?1:value;}
void vpe_led_resolve(const float main_rgb[39],uint64_t main_mask,
                     const float fx_rgb[39],uint64_t fx_mask,float out_rgb[39])
{
    for(unsigned i=0;i<VPE_LED_CHANNELS;++i){
        uint64_t bit=UINT64_C(1)<<i,all=UINT64_C(1)<<(36+i%3);
        /* A graph's individual channels override its own shared colour.
         * Any explicit FX writer has priority over Main on that channel. */
        out_rgb[i]=unit(fx_mask&bit?fx_rgb[i]:i<36 && (fx_mask&all)?fx_rgb[36+i%3]:
                       main_mask&bit?main_rgb[i]:i<36 && (main_mask&all)?main_rgb[36+i%3]:0);
    }
}
void vpe_led_pack(const float rgb[36],uint8_t grb[36])
{
    for(unsigned led=0;led<VPE_RING_LEDS;++led){
        unsigned physical=(led+7)%12;
        grb[physical*3]=(uint8_t)(unit(rgb[led*3+1])*VPE_LED_MAX_BYTE+.5f);
        grb[physical*3+1]=(uint8_t)(unit(rgb[led*3])*VPE_LED_MAX_BYTE+.5f);
        grb[physical*3+2]=(uint8_t)(unit(rgb[led*3+2])*VPE_LED_MAX_BYTE+.5f);
    }
}

unsigned vpe_startup_volume(unsigned requested,unsigned acknowledged)
{
    unsigned maximum=acknowledged?100:5;
    return requested>maximum?maximum:requested;
}
