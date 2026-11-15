/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stdint.h>

typedef struct {
    void *context;
    int (*write)(void *, uint8_t reg, uint8_t value);
    int (*read)(void *, uint8_t reg, uint8_t *value);
    void (*delay_ms)(void *, unsigned ms);
} vpe_codec_io;

typedef struct {
    vpe_codec_io io;
    unsigned ready, muted, checks;
    uint8_t power_flags;
    int gain_db;
    unsigned sample_rate;
} vpe_codec;

/* No GPIO, allocation or device addressing here. The ESP adapter restricts
 * all transactions to the board's codec, never to XMOS. Single owner. */
/* The original commissioning entry point always selects -24 dB. */
int vpe_codec_init_muted(vpe_codec *codec, const vpe_codec_io *io);
/* Only the two audited profiles are accepted: -24 dB bench or 0 dB playback. */
int vpe_codec_init_muted_gain(vpe_codec *codec,const vpe_codec_io *io,int gain_db);
/* Native output profiles with unchanged 24.576 MHz MCLK. */
int vpe_codec_init_muted_rate(vpe_codec *,const vpe_codec_io *,int gain_db,unsigned rate);
int vpe_codec_unmute(vpe_codec *codec);
int vpe_codec_mute(vpe_codec *codec);
int vpe_codec_check_muted(vpe_codec *codec);
/* Commissioning only: caller already streams zeros and controls the amplifier.
 * Fixed DAC gain is -24 dB. Rejects a unity-gain playback profile. */
int vpe_codec_unmute_test(vpe_codec *codec);
