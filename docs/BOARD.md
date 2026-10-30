# Board identity and ownership

Target: Waveshare ESP32-S3-Touch-AMOLED-1.8 **V2**, confirmed by the user on
30 October 2026. Expected display CO5300 and touch CST820. The BSP driver package
is named `esp_lcd_touch_cst816s`; that package name does not change the hardware
identity to CST816. Display/touch have not yet been initialized by this project.

The ROM tool identified an ESP32-S3 QFN56 revision 0.2, 40 MHz crystal, embedded
8 MB PSRAM and 16 MB quad flash. App-level PSRAM startup remains a separate check.

Pins below come from the selected official BSP **2.0.3**, repository commit
`9f4030c6e5cb888ad4cc268bfa7584c93ad53e30`,
`bsp/esp32_s3_touch_amoled_1_8`. Board-specific electrical routing, expander
signals and polarities still require comparison with the exact V2 schematic. The
official board check initialized all 8 MB of PSRAM; the codec example detected V2.

| Signal | GPIO / source constant | Owner | Polarity/format | Hardware status |
| --- | --- | --- | --- | --- |
| I2C SDA | 15 / `BSP_I2C_SDA` | BSP shared bus, controller 1 | Open-drain | Codec communication passed |
| I2C SCL | 14 / `BSP_I2C_SCL` | Same bus | Open-drain | Codec communication passed |
| Codec MCLK | 16 / `BSP_I2S_MCLK` | `board_audio` I2S1 TX | Non-inverted, requested 256 fs | Pending measurement |
| Codec BCLK | 9 / `BSP_I2S_SCLK` | Same | Non-inverted | Pending measurement |
| Codec WS | 45 / `BSP_I2S_LCLK` | Same | Philips, 16-bit mono/left | Pending slot verification |
| Codec data out | 8 / `BSP_I2S_DOUT` | Same | S16 PCM | SynthDef audible; recording pending |
| Codec microphone data | 10 / `BSP_I2S_DSIN` | Unused | RX not created | Deferred |
| Amplifier enable | 46 / `BSP_POWER_AMP_IO` | Codec GPIO interface | Active high (`pa_reverted=false`) | Audible output demonstrated |
| Display CS | 12 / `BSP_LCD_CS` | BSP, not started | SPI chip-select | Deferred |
| Display clock | 11 / `BSP_LCD_PCLK` | BSP, not started | QSPI clock | Deferred |
| Display D0–D3 | 4–7 / `BSP_LCD_DATA0`–`3` | BSP, not started | QSPI | Deferred |
| Display reset | NC / `BSP_LCD_RST` | BSP | No direct GPIO declared | Schematic gate |
| Touch reset | NC / `BSP_LCD_TOUCH_RST` | BSP | No direct GPIO declared | Schematic gate |
| Touch interrupt | 21 / `BSP_LCD_TOUCH_INT` | BSP, not started | Revision-specific | Deferred |
| SD CMD / CLK / D0 | 1 / 2 / 3, `BSP_SD_*` | BSP, not mounted | One-bit SDMMC | Deferred |
| Display reset | TCA9554 P0 at 0x20 | UI startup power helper | Low asserts reset | Official mapping; display operation confirmed |
| Display power enable | TCA9554 P1 at 0x20 | Same | Active high | Official mapping; display operation confirmed |
| PMU/rail enables | AXP2101 | Future BSP/PMU service | No guessed register writes | USB bring-up only |
| Native USB D− / D+ | Fixed ESP32-S3 USB peripheral; no application pin override | USB Serial/JTAG | Observed ROM console | ROM communication passed |

One I2C bus is shared; later display/touch/PMU/sensor code must use
`bsp_i2c_get_handle()`. `board_audio` owns I2S channel creation and codec interfaces.
Do not also call `bsp_audio_init()` or the BSP speaker initializer in this app.

The display helper reads the expander's existing output/direction registers,
sets only P0/P1 and preserves every other pin. Do not initialize a second generic
TCA9554 driver casually: its constructor resets all pin configuration. P0/P1
mapping and timing come from the pinned official `board_variant.c`, retained in
`upstream/waveshare-examples/reference/`. The LVGL integration uses the SPI
adapter and DMA-completion ownership; the BSP RGB convenience helper is bypassed.

The custom adapter follows the official codec example at board repository commit
`78e13f852929c2ab4f9d5e0ad1c50ea378dbf2b4`, while checking raw I2S byte counts.
The BSP codec-write wrapper returns success/error without exposing partial writes.
The codec is mono. Stereo float DSP is deliberately averaged to the mono sink;
inverted stereo content can cancel. Speaker outputs are not a stereo line output.
