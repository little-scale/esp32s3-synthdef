# First touch instrument

The touchscreen is running on the V2 board; the user confirmed screen, sound and
finger-lift release. SPI integration and display power/reset fixes resolved the
initial black screen. The earlier M3 30-second requested redraw test stayed below
the conservative 70% margin (maximum 52.30%), with zero reported output/numerical
failures and DMA event overflows. Full release stability/recording checks remain.

The later M4 interaction investigation reproduced timing overruns during actual
control changes. Internal instruction placement of the rendering kernels resolved
the tested case: three consecutive exercise rounds peaked at 761 µs / 52.44%,
with no timing violations or reported output errors. See `PERFORMANCE.md` for the
source-specific comparisons and remaining acceptance scope.

## Controls

Hold the large pad to gate one note. Horizontal movement controls pitch;
vertical movement controls level. Leaving the pad while held retains ownership
until release, so the correct note receives its note-off. Panic acts on press.
The four sliders also work independently of the pad.

PATCHES opens the numbered saved library, with LOAD and SAVE HERE controls.
Factory slot 0 is always retained. See [PATCHES.md](PATCHES.md) for compilation,
upload, recovery and the meaning of saved defaults. The Mac Sine example uses
330 Hz as its base frequency; custom labels and normalized displays are supported.

| Control | Graph parameter | Mapping at base frequency 440 Hz |
| --- | --- | --- |
| Pitch | `knob1` | 220–880 Hz, exponential; center 440 Hz |
| Level | `knob2` | Linear 0–100%, multiplied by note amplitude |
| Attack | `knob3` | 2–200 ms, applied at the next attack |
| Release | `knob4` | 20–1,000 ms, read when release begins |

The engine retains the 64-frame boundary contract. GUI events cannot call into
the voice directly. Continuous updates enter atomic latest-value mailboxes;
notes use the bounded queue with unique shared IDs. Queue overflow requests
panic. The default base amplitude is 0.5 and software master gain 0.8; codec
level 100 avoids the attenuation that made the earlier board test too quiet.
Actual speaker quality/gain preferences still require listening.

## Build variants

```sh
python3 host/prepare.py
# Current audio-only build (includes patch service):
host/idf.sh build
python3 host/record_build.py

# Prepared touchscreen variant:
SYNTHDEF_BUILD_DIR=build-ui host/idf.sh -D IDF_TARGET=esp32s3 \
  -D "SDKCONFIG=$PWD/firmware/build-ui/sdkconfig" \
  -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;$PWD/docs/ui.defaults" build
python3 host/record_build.py --build-dir build-ui --output esp32-ui-build.json
```

After the port is re-identified (last observed `/dev/cu.usbmodem101`):

```sh
SYNTHDEF_BUILD_DIR=build-ui host/idf.sh -p /dev/cu.usbmodem101 flash monitor
```

The BSP uses a 20-line partial buffer. The LVGL task is pinned to core 0 with a
10 KiB stack. LVGL has a fixed 64 KiB heap and theme transitions are disabled;
the expanded library exhausted the earlier 32 KiB pool during repeated changes.
The host interaction test now uses these same bounded allocator settings.
The audio task remains on core 1. UI refresh is capped at 25 Hz, uses no
full-frame buffer in the audio heap, and starts before the audio task.
The port uses BSP panel/touch creation with `lvgl_port_add_disp`, the SPI adapter,
instead of BSP 2.0.3's RGB convenience helper. A single 20-line draw buffer is
explicitly internal/DMA-capable and is reused only after transfer completion.
P0/P1 of the TCA9554 enable/reset the display before initialization, preserving
the other expander pins. Inspect heap/stack margins on-device before claiming
resource headroom with this corrected integration.

## Reproduce host checks

After managed components have been resolved by the ESP-IDF build:

```sh
python3 host/test.py
python3 host/test_touch.py
python3 host/preview_ui.py
```

`preview_ui.py` compiles the actual widgets against LVGL 8.4.0 with simulated
display/touch and allocation shims. It tests gestures and writes
`evidence/ui-idle-preview.png` and `ui-playing-preview.png`. It does not emulate
ESP32 timing, actual I2C touch behavior, DMA, display byte order or audio.

To regenerate the touch patch after source edits, use SuperCollider 3.14.1:

```sh
/Applications/SuperCollider.app/Contents/MacOS/sclang -D host/export-touch.scd
python3 host/test_touch.py
python3 host/prepare.py
```

## Recorded device checks and next tests

`evidence/ui-device.png` is an actual onboard screen snapshot. Host simulation
previews remain separately named. The target touch patch matches the host over
22,080 frames; the user confirmed touch sound and release. Runtime results are
in `evidence/realtime-ui-summary.json`.

Confirm screen alignment/colors and touch-down, drag, release outside the pad,
fast retriggers, slider extremes and panic. USB `d` toggles a 25 Hz pad redraw
stress animation without altering audio controls. USB `s` requests panic, waits
for an inactive snapshot and emits an RGB565 screen dump from a PSRAM buffer.
Neither operation runs on the audio task; screenshot transfer is a separate
diagnostic, not part of a realtime benchmark.

Compare the same source build's telemetry before/after redraw stress. Keep the
70% margin target, count output failures/partial writes, and listen/record for
discontinuities; reported counters alone cannot certify continuity.

If this board remains in download mode after an otherwise verified flash, use
the IDF Python environment's recovery reset:

```sh
python -m esptool --chip esp32s3 --port /dev/cu.usbmodem101 \
  --after watchdog_reset chip_id
```

The final restore was programmed from `firmware/build-ui` with
`python -m esptool --chip esp32s3 --port /dev/cu.usbmodem101 --after watchdog_reset write_flash @flash_args`.
This starts the ordinary playable application; it does not erase the whole flash.
