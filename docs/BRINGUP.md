# Reproduce board bring-up

Use USB power first. The observed board is V2; the observed port was
`/dev/cu.usbmodem3101`. Recheck the port after reconnecting. This project uses the
native USB Serial/JTAG console; close other monitors before flashing/capturing.

## Recovery copy

Before the first flash, the entire 16 MiB original flash was read to
`recovery/before-synthdef-2026-10-30.bin`. `recovery/backup.json` records its SHA-256.
The binary is local and excluded from Git. Keep it if restoring the prior board
state matters. Normal project flashing does not erase the whole flash.

To restore that exact saved state, with the IDF Python environment active:

```sh
python -m esptool --chip esp32s3 --port /dev/cu.usbmodem3101 \
  write_flash 0 recovery/before-synthdef-2026-10-30.bin
```

## Official diagnostics

These are pinned vendor examples. Their own generated dependency locks are kept
separate from the application. The overrides select the USB console and tone
settings without editing vendor source.

```sh
SYNTHDEF_PROJECT_DIR="$PWD/upstream/waveshare-examples/00_board_check" \
  host/idf.sh -D IDF_TARGET=esp32s3 \
  -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;$PWD/docs/serial-console.defaults" build
SYNTHDEF_PROJECT_DIR="$PWD/upstream/waveshare-examples/00_board_check" \
  host/idf.sh -p /dev/cu.usbmodem3101 flash monitor

SYNTHDEF_PROJECT_DIR="$PWD/upstream/waveshare-examples/12_i2s_codec" \
  host/idf.sh -D IDF_TARGET=esp32s3 \
  -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;$PWD/docs/serial-console.defaults;$PWD/docs/codec-tone.defaults" build
SYNTHDEF_PROJECT_DIR="$PWD/upstream/waveshare-examples/12_i2s_codec" \
  host/idf.sh -p /dev/cu.usbmodem3101 flash monitor
```

The vendor tone starts immediately and continues until reset/reflash. The first
test at codec volume 35 produced no sound according to the user. That setting
maps to about -32.5 dB in the selected codec library's volume curve; the official
V2 example instead defaults to 90 (about -5 dB). `codec-tone.defaults` now selects
that official V2 setting at 44.1 kHz and 440 Hz. Check the latest listening result
in `STATUS.md`; successful codec initialization alone is not audible acceptance.

Existing generated `sdkconfig` values take precedence over defaults. If changing
an existing example's tone level, use `host/idf.sh menuconfig` with that example
selected, or explicitly change its generated configuration before rebuilding.

The official codec example logs an attempted disable of an initially disabled
I2S channel before completing codec setup. Preserve the log; distinguish this
startup diagnostic from runtime output failures.

## Silent target numerical comparison

```sh
python3 host/prepare.py
SYNTHDEF_BUILD_DIR=build-capture host/idf.sh -D IDF_TARGET=esp32s3 \
  -D "SDKCONFIG=$PWD/firmware/build-capture/sdkconfig" \
  -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;$PWD/docs/offline-capture.defaults" build
SYNTHDEF_BUILD_DIR=build-capture host/idf.sh -p /dev/cu.usbmodem3101 flash
# Run with the IDF Python environment (pyserial/esptool) active:
python host/serial_capture.py --port /dev/cu.usbmodem3101 --reset --seconds 10 \
  --output evidence/offline-capture.log
python3 host/compare_capture.py evidence/offline-capture.log
```

This mode renders 345 stereo float blocks at 44.1 kHz, seed zero, with gate-off
at block 172. It stores the output in a bounded PSRAM capture, then transfers hex
after rendering. It never starts the codec. The comparison uses the existing
upstream peak/RMS waveform tolerance; hashes are diagnostics, not a requirement
for cross-processor bit identity. It passed on the connected ESP32.

## Normal instrument and bounded control test

```sh
python3 host/prepare.py
host/idf.sh build
python3 host/record_build.py
host/idf.sh -p /dev/cu.usbmodem3101 flash
python host/serial_capture.py --port /dev/cu.usbmodem3101 --reset --seconds 15 \
  --events-file tests/control-stress.json --output evidence/realtime-controls.log
```

The script plays/releases notes, changes pitch/amplitude and invokes panic. It
ends released. Inspect max render/preparation/combined times, budget violations,
write/partial failures, numerical faults, stack margin and internal heap. Do not
mistake DMA callback queue overflow for a complete underrun measure. Listening,
external recording/latency measurements and a 30-minute declared-workload stress
run remain release gates, separate from this short test.

The final recorded run used `tests/final-controls.json` for 30 seconds, including
same-boundary tap/retrigger cancellation. Summarize that exact run with
`python3 host/summarize_runtime.py evidence/realtime-final.log`. It reported
zero output/numerical failures but one 70% budget-margin violation at 1,020 µs;
see `STATUS.md` before adding UI work. The loaded normal firmware boots silent
and starts with codec 100, amplitude 0.5 and software master 0.8.

Display/touch initialization and its interaction with audio belong to M3 after
M2 audio is established. Optional vendor quickstart is available at the pinned
board repository; the two included diagnostic snapshots do not initialize a UI.
