# SynthDefs for ESP32-S3 Touch AMOLED 1.8

Native C99 SynthDef runtime for the **Waveshare ESP32-S3-Touch-AMOLED-1.8 V2**.
SuperCollider compiles patches on the computer; synthesis runs on the ESP32.
The project uses one voice, 64-frame blocks and a mono ES8311 output. The optimized
audio core has passed its short hardware timing comparison. The four-control
touch screen is running on the V2 board and has passed initial display, touch,
target numerical and audio-under-redraw checks. Extended release testing remains.

See [STATUS.md](STATUS.md) for completed checks and outstanding hardware gates, and
[handover.md](handover.md) for the full specification. See [docs/UI.md](docs/UI.md)
for the touchscreen variant. USB patch transfer and the saved library are described
in [docs/PATCHES.md](docs/PATCHES.md). Effects and sequencing remain later milestones.
Phase FM, additive and filtered examples are included as exact tested one-voice
catalog entries; the generic sine family remains supported.
The reproducible interaction-timing fix and its checks are in
[docs/PERFORMANCE.md](docs/PERFORMANCE.md).

## Reproduce the software checks

```sh
python3 host/prepare.py
python3 host/test.py
python3 host/test_touch.py
python3 host/test_patches.py
python3 host/test_catalog.py
make -C upstream/fm1-synthdef/synthdef-engine test
FM_REFERENCE_FILTER=fm1_voice make -C upstream/fm1-synthdef/synthdef-engine reference-test
```

The reference check requires SuperCollider 3.14.1 installed at its normal macOS
location, or `SCSYNTH` pointing to that version. It checks one pinned sine fixture
against SuperCollider, then runs the scale catalog check. `make test` runs the
full upstream host API/oracle suite. FM1 device-math oracles are host tests, not
ESP32 hardware tests. The adapter checks use undefined-behavior, bounds and
float-conversion sanitizers. AddressSanitizer initialization currently deadlocks
on this Mac and is not counted as passing coverage.

After ESP-IDF has resolved the managed components, `python3 host/preview_ui.py`
exercises the actual LVGL widgets with simulated input and renders host previews.
These checks cannot validate physical panel power, transfer or touch behavior.

## Build and flash

Pinned application dependencies: ESP-IDF **5.5.0**, Waveshare BSP **2.0.3**,
LVGL **8.4.0**. The generated `firmware/dependencies.lock` pins transitive versions.
The current touchscreen/library configuration is retained as
`evidence/sdkconfig.catalog.esp32s3`; earlier audio-only configurations remain
separately recorded.
The current build uses Xtensa GCC 14.2.0 and the normal ESP maths library.

```sh
git clone https://github.com/little-scale/synthdefs-for-esp32-s3-touch-amoled-1.8.git
cd synthdefs-for-esp32-s3-touch-amoled-1.8
python3 host/prepare.py
SYNTHDEF_BUILD_DIR=build-ui host/idf.sh -D IDF_TARGET=esp32s3 \
  -D "SDKCONFIG=$PWD/firmware/build-ui/sdkconfig" \
  -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;$PWD/docs/ui.defaults;$PWD/docs/timing.defaults" build
python3 host/record_build.py --build-dir build-ui --output esp32-ui-build.json
# After board/codec bring-up, using the observed device port:
SYNTHDEF_BUILD_DIR=build-ui host/idf.sh -p /dev/cu.usbmodem101 flash
SYNTHDEF_BUILD_DIR=build-ui host/idf.sh -p /dev/cu.usbmodem101 monitor
```

`host/idf.sh` activates the existing `$HOME/esp/esp-idf` installation and an
existing IDF 5.5 Python environment. Override `IDF_PATH` and
`IDF_PYTHON_ENV_PATH` for another installation. Build outputs are in
`firmware/build-ui/` with the command above, or `firmware/build-esp32s3/` by default.
The port shown above was observed locally on 31 October
2026; check it again after reconnecting. Exit the IDF monitor with Ctrl-].

The firmware boots silent. In the monitor, single characters control it:

| Key | Action |
| --- | --- |
| `n` | Start/retrigger one note |
| `o` | Release the current note |
| `!` | Panic: immediate engine silence |
| `+` / `-` | Raise/lower pitch by one semitone |
| `]` / `[` | Raise/lower amplitude |

Codec output level starts at 100/100, synth amplitude at 0.5 and master gain at
0.8. Panic and release reach the sink after already-queued audio. Current DMA
capacity is six 128-frame descriptors, approximately 17.4 ms at 44.1 kHz before
codec/input delays. This is capacity, not measured end-to-end latency.

Boot/runtime logs include source identity, requested format, memory, preparation
and render maxima, budget overruns, write failures, partial writes and queue
statistics. A failed/partial write mutes and stops the audio task until reset.
DMA event queue overflow is logged separately and is not an underrun detector.

## Architecture and evidence

`firmware/components/instrument` owns portable note/control/DSP behavior.
`board_audio` owns I2S and codec configuration using BSP pins. The audio task
alone mutates the voice; console controls enter through a bounded queue. Panic
has an independent atomic latch. The touchscreen and patch service run on core 0.
Filesystem writes use explicit muted maintenance; radio remains off.
Admitted rendering kernels reside in internal instruction RAM to avoid the
reproduced interaction stalls. Their source and lookup values remain pinned.

`host/prepare.py` checks vendored source hashes, compares the enum with the
compiled loader, generates the target capability manifest and embeds the pinned
factory patch. Builds fail when this metadata is stale. All 154 types compile;
uploads use `catalog-voice-v2`: the narrower `simple-voice-v1` sine family plus
exact qualified example hashes. Broad hardware compatibility has not been established.

Recorded checks and build identities are in `evidence/`. See [docs/BOARD.md](docs/BOARD.md),
[docs/BRINGUP.md](docs/BRINGUP.md), [docs/MEMORY.md](docs/MEMORY.md) and
[THIRD_PARTY.md](THIRD_PARTY.md). The source follows GPL-3.0-or-later; original
third-party notices remain with the vendored material.
