# Source register and board map

The register below preserves the original 5 November source survey. The
[19 November DLight integration](GROVE_DLIGHT.md) subsequently verified the
external Grove pin assignments against the [official Grove I2C configuration](https://github.com/esphome/home-assistant-voice-pe/blob/dev/modules/grove-i2c.yaml):
SDA GPIO1, SCL GPIO2 and active-high power enable GPIO46. The new driver uses a
dedicated controller, separate from the codec/XMOS bus on GPIO5/6. The M5Stack
U136 at address 0x23 produced changing light readings on the attached Voice PE;
its bus map is 42 normalised / 43 lux. Other Grove devices are not identified or
activated automatically.

Checked 5 November 2026. Confidence labels: **source-confirmed** means a direct match between named source files, not a measurement of the ordered unit; **inferred** means a consequence of those sources; **pending** needs a physical check. No electrical datasheet qualification or ready-to-fabricate review is claimed.

## Pinned sources

1. [SynthDef repository](https://github.com/little-scale/esp32s3-synthdef/tree/b7fd8ac210a7a08ac4d94431104076907dbe5c78): `firmware/main/main.c`, `main/Kconfig.projbuild`, component CMake files, `board_audio`, `headless_io`, `instrument`, `patches`, `host/xiao.sh`, `host/xiao.defaults`, `host/engine_profile.py`, `host/prepare.py` and checked-in sine/delay fixtures.
2. [Official board configuration](https://github.com/esphome/home-assistant-voice-pe/blob/d4e6fa43d6a1a7d342b7d4d403567e06516719de/home-assistant-voice.yaml): CPU, memory, GPIOs, I²S roles/formats, encoder, LED timing and amplifier defaults. `esp32-s3-devkitc-1` is ESPHome's generic platform selector, not a complete native ESP-IDF BSP for this product.
3. [Official KiCad hardware](https://github.com/esphome/home-assistant-voice-pe/tree/d4e6fa43d6a1a7d342b7d4d403567e06516719de/hardware/KiCad): `ESP32S3.kicad_sch`, `XMOS.kicad_sch`, `DAC.kicad_sch`, `Power.kicad_sch`, `LED & Connector.kicad_sch` and the included `Home Assistant Voice PE.pdf`. Use sheet names: the PDF physical page order differs from the sheet Id printed in title blocks. Hardware is CERN-OHL-P v2.
4. [Voice Kit component](https://github.com/esphome/home-assistant-voice-pe/tree/d4e6fa43d6a1a7d342b7d4d403567e06516719de/esphome/components/voice_kit): `__init__.py` defaults to I²C address 0x42; `voice_kit.cpp` resets, waits 3 s, queries firmware and may automatically perform DFU on a version mismatch. The stock YAML references XMOS v1.3.1; the delivered unit's version is unknown.
5. [ESPHome AIC3204 driver](https://github.com/esphome/esphome/tree/fc106564ed1fd2e1047428878b0333baf1cbcd29/esphome/components/aic3204): `aic3204.cpp`, `aic3204.h`, `audio_dac.py`. Address 0x18, 32-bit I²S, SCLK/MFP3 input routing, clock-divider settings, output routing, volume/mute and startup delay. This is a reference implementation, not a drop-in ESP-IDF C driver.
6. [ESP-IDF v5.5 I²S API](https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32s3/api-reference/peripherals/i2s.html): standard-mode slave TX, 32-bit slots and channel lifecycle. Locally compiled against IDF commit `8c750b088c7cd857d079c0eeb495da199b359461` (`v5.5`).
7. [Espressif BSP catalogue](https://github.com/espressif/esp-bsp#supported-boards), inspected 5 November 2026: no Voice PE entry was present in the listed boards. This is a bounded catalogue observation, not proof that no third-party port exists.
8. [Independent ESP-IDF project](https://github.com/ayourtch-llm/nabu-custom-fw/blob/main/README.md), inspected 5 November 2026: useful comparison for USB and I²S integration; explicitly contains bench TODOs. Treat its status as the author's claims. It is neither the official BSP nor hardware validation of this starter.
9. [Official reinstall instructions](https://support.nabucasa.com/hc/en-us/articles/25800241218717-Reinstalling-the-firmware-on-Home-Assistant-Voice-Preview-Edition), [bootloader recovery](https://support.nabucasa.com/hc/en-us/articles/25800285426589-Reinstalling-the-firmware-on-Home-Assistant-Voice-Preview-Edition-from-bootloader-mode), and [installer](https://esphome.github.io/home-assistant-voice-pe/).
10. [esptool flash operations](https://docs.espressif.com/projects/esptool/en/latest/esp32s3/esptool/basic-commands.html). The installed IDF tool is `esptool.py v4.12.dev2`; its local `--help` was checked without connecting to a device. RECOVERY.md uses that version's underscore command spelling; newer versions use hyphens.

The deliverable includes `source-manifest.json` with repository revisions and SHA-256 hashes of relevant inspected files. Sources were read as evidence, not as authority to flash or update another processor.

One source discrepancy matters: the included block-diagram sheet labels ESP flash as 8 MB, while the current official YAML selects 16 MB and the detailed ESP32 sheet populates U15 ZB25VQ128 (128 Mbit = 16 MB; the alternative U16 is marked unpopulated). The scaffold follows the current official configuration and requires checking the actual unit; it does not treat the block diagram as an authoritative capacity map.

## GPIO map

All assignments below are source-confirmed in the pinned official YAML and cross-checked against the named schematic sheets. Actual revision, assembly options, polarities at the connector and functionality remain pending on the ordered unit.

| Function | ESP32 GPIO / address | Schematic anchor and intended use |
|---|---|---|
| Center button | 0, active low | `ESP_BOOT`, U1 pin 5; boot strap, read only after boot |
| Hardware mic mute sense | 3 | `ESP_MUTE_DET`; stock firmware treats high as muted; not a DAC/synth mute |
| XMOS reset control | 4 | `XU316_RST` → Q3 → `RST_N`; GPIO high asserts reset through inversion |
| Internal I²C | SDA 5, SCL 6 | `I2C_SDA`, `I2C_SCL`; stock 400 kHz |
| Codec | 0x18 | U8 TLV320AIC3204, DAC sheet |
| XMOS control | 0x42 | Voice Kit schema; protocol address, not an I²C codec register map |
| Playback word/bit clocks | WS 7, BCLK 8 | R93/R94 → `I2S_LRCK`/`I2S_BCLK`; **inputs to ESP** |
| Playback data | 10 | R96 → `I2S_DIN_SEC` → U8 **SCLK/MFP3 pin 8** |
| MCLK net | 9 is physically connected | R95 → `I2S_MCLK`; leave GPIO9 untouched, do not generate MCLK |
| Other audio data route | 11 | R97 → `I2S_DIN_ESP` → U8 DIN/MFP1; not the stock playback output |
| Mic input bus | BCLK 13, WS 14, DIN 15 | `I2S2_BCLK`, `I2S2_LRCLK`, `I2S2_DATA`; stock 16 kHz stereo S32 slave RX; deferred |
| Encoder | A 16, B 18 | `ECO_A`, `ECO_B`; stock resolution 2; direction/debounce pending |
| Jack detect | 17 | `Audio_DET`; stock high means plugged; 200 ms stock debounce |
| Native USB | D− 19, D+ 20 | `ESP_USB_N/P`; reserve for USB Serial/JTAG |
| LED ring | data 21, power 45 | `ESP_WS2812`, `WS2812_PWR`; 12 GRB LEDs; not XIAO's active-low GPIO LED |
| Speaker amplifier | 47, high enables | `AUDIO_PA_EN` → R36/R25 → `AMP_CTL`/U9 shutdown; jack circuitry also gates it |
| Grove | 1/2, power 46 | Leave untouched in first port |

The ESP32S3 schematic's U1 symbol calls physical pin 37 `SPICLK_P`; the stock firmware identifies that pad's GPIO47 function. Do not confuse physical pad numbers with GPIO numbers.

## Audio topology and traps

XMOS supplies the shared playback BCLK, LRCLK and codec MCLK. ESPHome sets the ESP playback port to `secondary` (slave). The codec driver expects 24.576 MHz MCLK with NDAC=2, MDAC=2, DOSR=128 for 48 kHz. **Inferred nominal** BCLK is 48,000 × 2 × 32 = 3.072 MHz; these clocks have not been measured here.

The codec's selected audio input is the alternate SCLK/MFP3 route, not merely the pin named DIN. A generic AIC3204 initialization may therefore produce silence even with correct ESP pins. The driver also routes headphone and line outputs and delays DAC power-up for 2.5 s. Preserve mute while adapting that sequence; do not copy its final unmute into first boot.

GPIO4 reset polarity is source-confirmed by the Q3 inversion and the official high-then-low reset sequence. Still leave it untouched initially. No XMOS firmware binary is bundled. The current official component's automatic update behavior must not be imported into the port.

USB data is switched by U17/SW3: `USB_SEL=0` selects ESP32 (default), `1` selects XMOS. Leave the internal switch in its factory ESP position; ordinary USB recovery does not require opening the case. An ESP flash dump does not contain XMOS's separate U3 flash.

KiCad schematic extraction was run and critical routes were checked against raw symbols/wires and the published PDF. Its aggregate findings are not an electrical review: no datasheet-backed analysis was available. PCB, EMC, SPICE, thermal and manufacturing reviews were not performed because this task ports firmware to an existing product.


## Playback-rate review (14 November 2026)

The official XMOS source at `ef04d4b59d172dfbe5c85ba982bf05fcc85f77f3`
sets `appconfI2S_MODE_MASTER`, `appconfI2S_AUDIO_SAMPLE_RATE=48000` and
`MIC_ARRAY_CONFIG_MCLK_FREQ=24576000` in
[`ffva_int.cmake`](https://github.com/esphome/voice-kit-xmos-firmware/blob/ef04d4b59d172dfbe5c85ba982bf05fcc85f77f3/src/ffva/ffva_int.cmake).
Its [how-to](https://github.com/esphome/voice-kit-xmos-firmware/blob/ef04d4b59d172dfbe5c85ba982bf05fcc85f77f3/doc/programming_guide/howto.rst)
documents 16/48 kHz conversion paths, not a 44.1 kHz mode. The physical board
measurements agree with 48 kHz. This is not proof that different custom XMOS
firmware could never provide 44.1 kHz. The user chose **48 kHz for now**; XMOS
firmware and GPIO9/MCLK remain untouched. The original scope table above is the
historical source survey; measured results are in the linked evidence.

## Native 16 kHz investigation (15 November 2026)

This was a source-only investigation: no USB/I2C requests, clock writes, resets
or firmware uploads were made. The installed XMOS version is still unknown.
Results describe the official v1.3.1 source (`1a1df7c2b3e578431b1550a8defe8ae2c8b54d93`)
and current dev (`ef04d4b59d172dfbe5c85ba982bf05fcc85f77f3`), whose differences
are confined to CI workflows in this comparison. Pinned driver dependencies
are `esphome/xmos_fwk_rtos` at `656e31cc784254d7f404f915a1663438ac46356c`
and `esphome/xmos_fwk_io` at `0fc6f7c9c7608f3ffaa05238df04cc5ba50718fc`.

Native 16 kHz is a plausible **custom XMOS build**, not a confirmed runtime
setting in the installed binary:

- The official [rate how-to](https://github.com/esphome/voice-kit-xmos-firmware/blob/ef04d4b59d172dfbe5c85ba982bf05fcc85f77f3/doc/programming_guide/howto.rst)
  explicitly allows `appconfI2S_AUDIO_SAMPLE_RATE=16000`. The shipping INT target
  overrides that setting to 48000 in `src/ffva/ffva_int.cmake`.
- `src/ffva/src/app_conf.h` explicitly sets `appconfAUDIO_CLOCK_FREQUENCY` to
  `MIC_ARRAY_CONFIG_MCLK_FREQ`, which is 24.576 MHz in this target. This overrides
  the platform fallback to PDM frequency: the nearby 3.072 MHz comments in
  `platform_start.c` are not the effective I2S clock source.
- NC-VOICE-KIT's `i2s_start()` calculates its divider from that clock and the
  compile-time I2S sample rate. For stereo 32-bit slots, 16 kHz needs 1.024 MHz
  BCLK and an MCLK/BCLK ratio of 24, versus 3.072 MHz BCLK and ratio 8 at 48 kHz.
  The pinned low-level master uses a divide-by-two clock divisor; both ratios
  are even and fit that implementation. The 24.576 MHz app PLL can stay as-is.
- The internal voice pipeline is already 16 kHz. The primary I2S port enables
  its 3:1 conversion callbacks only when wire rate is three times pipeline rate;
  that condition is false at a 16 kHz wire rate. The second microphone-output
  I2S port is separately configured for 16 kHz. This is supporting source
  evidence, not an on-board qualification of a changed primary port.
- Ordinary configuration resource 241 has exactly three commands in the
  reviewed [command map](https://github.com/esphome/voice-kit-xmos-firmware/blob/ef04d4b59d172dfbe5c85ba982bf05fcc85f77f3/src/ffva/src/configuration/configuration_servicer.h):
  VNR readback and two microphone processing-stage selectors. The other
  registered resource is DFU, including firmware version. Neither exposes a
  playback-rate setting; the I2S driver restart callback returns NO_RESTART.
  Unused configuration-flash helper functions do not provide a rate command.

The codec and ESP32 must also change together. At unchanged 24.576 MHz MCLK,
the current NDAC=2, MDAC=2, DOSR=128 gives 48 kHz. An arithmetic candidate is
NDAC=6, MDAC=2, DOSR=128 for 16 kHz, retaining the current MDAC/DOSR processing
ratio. This needs a datasheet/register review and muted clock/DAC qualification
before use; no register sequence has been declared qualified at 16 kHz. ESP32
slave-I2S configuration and clock-survey bounds must match the physical 16 kHz
WS and 1.024 MHz BCLK; changing its nominal sample rate alone is insufficient.

At the initial source review, no XMOS compiler was installed. The follow-up
build found the official public XMOS compiler container and successfully built
a native-16k companion image with two toolchain compatibility fixes. See
[NATIVE_16K.md](NATIVE_16K.md) for pinned sources, patches, build hashes and
testing status. Historical branches named `i2s_fw` and `i2s_fw_48khz`
were checked too; both still select 48 kHz in their INT build, so their names
are not evidence of a ready-to-flash native 16 kHz image.

The follow-up hardware trial is now underway. The factory image was read twice
and matched official v1.3.1, then a stock upgrade recovery and the custom native16
upgrade each passed reboot/readback checks while preserving the factory image.
The matched ESP image reports measured startup WS=15,996.5 Hz and
BCLK=1,023,986.6 Hz. Stereo pitch, delay timing, live controls, separate FX tails
and actual SC Function/SynthDef/Pbind operations pass. Cold-power, physical IO and user listening checks pass; [NATIVE_16K.md](NATIVE_16K.md) records the exact scope and
links the current evidence. Full ESP backups still do not contain XMOS flash.
