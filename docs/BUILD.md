# Build, flash and development checks

The current instrument configuration is the FM1 compatibility/cache profile in
`host/fm1-cache.defaults`, on top of `firmware/sdkconfig.defaults`. It enables the
AMOLED UI, the full pinned 154-type engine profile, internal rendering/Rings code,
32 KiB instruction and 64 KiB data caches, PSRAM arenas and Wi-Fi memory settings.
The older compact/catalog builds remain useful historical configurations; they
are not the configuration used by the README quickstart.

The shared [DSP block kernels and replacement fades](DSP_OPTIMIZATIONS.md) apply
to both board profiles. Hardware-specific timing and listening records remain
separate; cross-building the AMOLED image is not a physical panel/speaker test.

## Toolchain

The physical V2 board is the Waveshare ESP32-S3-Touch-AMOLED-1.8 with 16 MB flash
and 8 MB octal PSRAM. Current evidence uses ESP-IDF 5.5, Xtensa GCC 14.2.0,
Waveshare BSP 2.0.3 and LVGL 8.4.0. Managed components are pinned by
`firmware/dependencies.lock`. Host source compilation uses SuperCollider 3.14.1;
MiVerb and other non-stock classes need their host-side SC class packages.

Install ESP-IDF using its normal ESP32-S3 setup and export its environment.
`host/idf.sh` can activate an existing installation at `$HOME/esp/esp-idf` and
an existing `$HOME/.espressif/python_env/idf5.5*_env`. Select other locations with
`IDF_PATH` and `IDF_PYTHON_ENV_PATH`. The examples below use a POSIX shell; the
physical/GUI workflow has been exercised on macOS.

For Studio, use Python 3.11+ and a C compiler:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r host/requirements.txt
```

`host/studio.sh` chooses a Python with pyserial, including an existing IDF Python
environment. Tests which compile SC use its normal macOS application location;
reference tools also accept `SCSYNTH` where documented. Font regeneration needs Pillow; install it separately for that developer tool.
The UI preview PNG writer uses the Python standard library.
The generated code font is checked in, so a firmware build does not regenerate it.

## Build the current instrument

From the repository root:

```sh
python3 host/prepare.py
SYNTHDEF_BUILD_DIR=build-instrument host/idf.sh -D IDF_TARGET=esp32s3 \
  -D "SDKCONFIG=$PWD/firmware/build-instrument/sdkconfig" \
  -D "SDKCONFIG_DEFAULTS=$PWD/firmware/sdkconfig.defaults;$PWD/host/fm1-cache.defaults" build
python3 host/record_build.py --build-dir build-instrument --output instrument-build.json
```

Use an empty build directory when selecting defaults for the first time. An
existing sdkconfig takes precedence over defaults. Outputs are under
`firmware/build-instrument/`. `record_build.py` checks profile contents, strict
floating-point options, instruction placement and pinned sine-table bytes; its
JSON records the image/configuration hashes and target structure sizes.

`prepare.py` checks the vendored snapshot against `upstream/SOURCES.json`,
generates engine/profile/catalog metadata, and pairs factory source with its
compiled graph. Build identity depends on the firmware sources and generated
capabilities. Source changes invalidate prior workload qualification; they do
not retroactively change the scope of old hardware measurements.

## Flash without erasing saved packages

For every newly installed module, follow the
[standard post-flash listening check](COMMISSIONING.md): the saved eight-saw
sound block starts independently of touch, with separate master FX bypassed.

Close Studio's USB connection and any serial monitor. Stop ESP32 patterns before
restarting firmware. Identify the actual port (`/dev/cu.usbmodem...` on macOS,
`/dev/ttyACM...` on Linux, or the appropriate COM port). Do not copy a previously
recorded port blindly.

In the **ESP-IDF Python environment**, flash the generated manifest:

```sh
cd firmware/build-instrument
python -m esptool --chip esp32s3 --port YOUR_PORT \
  --before default_reset --after watchdog_reset write_flash @flash_args
```

This writes the bootloader, partition table and application specified by the
build; it does not request a full-chip erase. The current partition map keeps
NVS and SPIFFS outside the 3 MiB application partition. Keep that layout to retain
pairings, network settings and saved Main/FX packages. Updating an existing
installation can instead write only `waveshare_synthdef.bin` at `0x10000`, after
checking that its existing bootloader/partition layout matches.

Managed definition packages boot inactive until `ESP32.play` or a first note.
Legacy browser sound blocks keep their previous automatic startup behaviour.
The fixed factory patch remains a recovery fallback. Reconnect the host, prepare
the intended stages, and restart patterns after a firmware update.

### Native USB recovery

This board can remain in ROM download mode after an ordinary RTS reset. A
watchdog reset is preferred. If it still reports `waiting for download`, the
following clears only the volatile ESP32-S3 forced-download bit and resets:

```sh
python -m esptool --chip esp32s3 --port YOUR_PORT \
  --before default_reset --after watchdog_reset write_mem 0x6000812c 0 1
```

This is a V2/ESP32-S3 recovery command, not an erase or credential reset. If USB
has disappeared entirely, unplug for five seconds and reconnect; hold BOOT while
connecting only when ROM download mode is needed for recovery. After recovery,
re-identify the port. No flash image containing network NVS is distributed.

## Software checks

These run on the computer and do not contact a board:

```sh
python3 host/prepare.py --check
python3 host/test.py
python3 host/test_touch.py
python3 host/test_patches.py
python3 host/test_catalog.py
python3 host/test_source.py
python3 host/test_control_buses.py
python3 host/test_master_delay.py
python3 host/test_remote_control.py
python3 host/test_comb_kernels.py
python3 host/test_miverb.py
python3 host/test_saw.py
python3 host/test_dynamic_banks.py
```

The adapter/remote tests use undefined-behaviour, bounds and float-conversion
sanitizers. `test_remote_control.py` covers lifecycle, queue/cancel ownership,
300 rendered EnvGen retriggers, and bit-identical full/delta audio under
interleaved future events. AddressSanitizer did not initialize successfully on
the development Mac; an ASan pass is not claimed.

Run the browser, paired-network, SC bridge and parameter-encoding suite:

```sh
cd host
python3 -m unittest test_studio test_network test_control_client test_ide_bridge
```

These include real native `sclang` clients and loopback HTTP device simulators,
not physical ESP32 or RF tests. Browser interaction tests use Node.js and a DOM
adapter. Native bridge tests require the SC classes under `supercollider/` and
keep their private descriptors under temporary/build directories.

After ESP-IDF resolves managed components, `python3 host/preview_ui.py` compiles
real LVGL/widgets with simulated touch and renders images in `evidence/`. It
checks source scrolling, touch ownership, controls, identity and activity pixels;
it cannot verify panel power or physical touch quality.

For deeper DSP coverage:

```sh
make -C upstream/fm1-synthdef/synthdef-engine test
python3 host/test_fm1_parity.py --reference
python3 host/test_fm1_voice.py
python3 host/test_fm1_rejections.py
```

The parity suite uses the pinned fixtures and SC reference server without
opening an audio device. Keep waveform, statistical/drift, timing and listening
claims separate; see [UGEN_SUPPORT.md](UGEN_SUPPORT.md).

## Hardware checks and publication

`host/test_device_*.py` and `host/probe_touch.py` are explicit hardware tools.
Some load patches, mute/restart audio or request physical interaction. Read their
help/source, preserve the current packages/settings and identify the board before
running them. They are not part of the host-only regression command above.

The public repository contains source, examples, tests, summary reports and
selected UI previews. Raw trace/screenshot-transfer logs and local browser/setup
screenshots remain local. Build products, Python environments, complete flash
backups, Wi-Fi credentials, pairing keys and session descriptors are ignored.
See [the evidence index](../evidence/README.md) for current reports and history.
