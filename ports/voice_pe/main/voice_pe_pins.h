/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
/* Source anchors and schematic net names: ../SOURCES.md. No GPIO remapping. */
enum {
    VPE_BUTTON = 0, VPE_MUTE_SENSE = 3, VPE_XMOS_RESET = 4,
    VPE_I2C_SDA = 5, VPE_I2C_SCL = 6,
    VPE_GROVE_SDA = 1, VPE_GROVE_SCL = 2, VPE_GROVE_POWER = 46,
    VPE_TX_WS = 7, VPE_TX_BCLK = 8, VPE_TX_DATA = 10,
    VPE_RX_BCLK = 13, VPE_RX_WS = 14, VPE_RX_DATA = 15,
    VPE_ENCODER_A = 16, VPE_JACK_SENSE = 17, VPE_ENCODER_B = 18,
    VPE_LED_DATA = 21, VPE_LED_POWER = 45, VPE_AMP_ENABLE = 47,
    VPE_CODEC_ADDRESS = 0x18, VPE_XMOS_ADDRESS = 0x42,
    VPE_RATE = 48000, VPE_CHANNELS = 2, VPE_SLOT_BITS = 32,
    VPE_LED_COUNT = 12
};
/* GPIO9 is wired to XMOS's MCLK net. Never drive it as XIAO DOUT. */
