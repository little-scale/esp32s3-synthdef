# XIAO ESP32-S3 headless instrument

The XIAO target uses the same FM1-compatible DSP engine, Main/FX definitions,
instance lifecycle, named controls and module volume as the AMOLED instrument.
It excludes the Waveshare BSP, display, touch controller and ES8311 codec.
The initial physical target has 8 MB flash and 8 MB octal PSRAM.

## What is working

- USB upload with saved graph/source readback; Main and FX survive restart.
- SuperCollider Function/SynthDef deployment, aliases, sets and scheduled notes
  through Studio's existing USB connection. Wi-Fi pairing is not required for USB.
- Stereo, 44.1 kHz, signed 16-bit Philips I²S, with six 128-frame DMA buffers.
- Separate left/right output, final volume ramp, FX routing and bypass.
- Up to one second of actual post-volume PCM capture, downloadable as stereo WAV.
- Onboard activity LED on GPIO21, active low; queries do not flash it.
- BOOT button on control bus 10, debounced outside the audio task.
- CPU, queue, memory and fault reporting through USB telemetry.

See [USB/PCM checks](../evidence/xiao-usb-check.json) and
[physical button/capture checks](../evidence/xiao-button-check.json).
The [one-minute MiRings1 stress test](../evidence/xiao-rings-stress.json) delivered
eight parameter-changing notes per second with no reported write, DMA, clipping
or nonfinite faults. Maximum sampled average audio load was 52.8%, with a 59.9%
peak; this measures the audio task with Wi-Fi unconfigured, not whole-chip load.
These verify rendering and the buffers copied to the I²S driver. No external DAC,
logic analyser or physical audio output was connected. Wi-Fi firmware support is
included, but real-network operation on this XIAO has not yet been tested.

## DSP qualification without external audio hardware

The [five-minute qualification](../evidence/xiao-dsp-qualification.json) exercised
Comb Cloud KR through a separate MiVerb master. All 2,400 control updates applied;
seven concurrent PCM captures contained sound without clipping. Reported write,
DMA, queue, DSP and nonfinite fault counters did not increase. Sampled maximum
average audio load was 67.9%; sampled peak load reached 80.7%. These figures apply
to this fixture, with Wi-Fi unconfigured, rather than every supported patch.

| Resource during the combined workload | Observed value |
| --- | --- |
| Free internal RAM | 164,867 bytes; constant across sampled readings |
| Largest internal free block | 90,112 bytes |
| Free PSRAM | 5,261,472 bytes; constant across sampled readings |
| Audio task stack remaining | 12,680 bytes of 16,384 |
| Control task stack remaining | 2,836 bytes of 8,192 |
| Reserved delay arena per stage | 1 MiB Main + 1 MiB FX |

Free PSRAM does not automatically expand the fixed per-stage admission budgets.
The test also verified independent stereo CombN echoes at 4,410 and 6,615 frames,
their feedback decay, and a four-second mono delay using all 262,144 Main arena
samples. An oversized stereo delay was rejected before upload. MiVerb continued
ringing after Main stopped; Panic cleared both stages to silent PCM. A stale
control stream could not alter a replacement patch, and a new stream recovered.

To repeat the checks, connect the exact module by USB in Studio, select Main,
and ensure both Main and FX slot 1 contain a saved package:

```sh
python3 host/qualify_headless.py \
  --device-id esp32-288485ba1e48 --seconds 300 \
  --report build/host/headless-qualification.json
```

Use your own permanent module ID. This takes over both stages during testing.
The tool saves a private recovery backup under `build/host/private/`, then restores
graph bytes, source, names, labels, mappings, definition flags, module volume,
FX selection and instance activity. Storage generations advance as with normal
uploads; oscillator phases and effect tails restart. It refuses to overwrite an
unrelated patch introduced by another session. Backups remain available if the
USB connection is interrupted. Control metadata is prepared after each upload,
as it is when starting a new SuperCollider pattern.

## I²S wiring

| Signal | XIAO label | ESP32 GPIO |
| --- | --- | --- |
| BCLK | D8 | 7 |
| WS / LRCLK | D9 | 8 |
| Data out | D10 | 9 |
| Ground | GND | Ground |

MCLK is not generated. Select a DAC compatible with the configured I²S format
and clocks. These pins may remain unconnected for DSP, DMA and capture tests.
Power wiring and analogue output still depend on the eventual DAC board.
GPIO assignments are build settings: `SYNTHDEF_I2S_BCLK`, `SYNTHDEF_I2S_WS`,
`SYNTHDEF_I2S_DOUT`. USB GPIO19/20 are left available for native USB.
Pin aliases follow the [Espressif XIAO variant definition](https://github.com/espressif/arduino-esp32/blob/master/variants/XIAO_ESP32S3/pins_arduino.h).

## Build and flash

Use ESP-IDF 5.5 and the existing toolchain described in [BUILD.md](BUILD.md):

```sh
python3 host/prepare.py
host/xiao.sh build
python3 host/record_build.py --build-dir build-xiao --output xiao-build.json
```

`host/xiao.sh` selects the separate `build-xiao` directory, XIAO sdkconfig,
8 MB partition table and headless component dependencies. It disables the
component manager for this build because no third-party BSP components are
needed. Keep using the normal build command for the AMOLED target.

In the ESP-IDF Python environment, from `firmware/build-xiao`:

```sh
python -m esptool --chip esp32s3 --port YOUR_XIAO_PORT \
  --before default_reset --after watchdog_reset write_flash @flash_args
```

The XIAO and AMOLED use different flash layouts and audio hardware adapters.
Choose the image for the connected board. Avoid holding BOOT during normal
power-up; holding it selects ROM download mode.

## SuperCollider over USB

1. Start `sh host/studio.sh` and open its local session link.
2. Choose USB, select the XIAO port, and Connect. Keep Studio running.
3. In SC, evaluate `ESP32.connect;` and use the XIAO's permanent module ID.

The tested unit is `esp32-288485ba1e48`; every board gets its own MAC-derived ID.
`ESP32.scan.onDone(_.postln);` lists the USB connection alongside discovered
paired Wi-Fi modules. A connected USB endpoint takes precedence when the same
module is also paired over Wi-Fi; `\all` includes it once. Browser Wi-Fi omni
upload retains its existing Wi-Fi-only recipient selection.

```supercollider
ESP32.alias(\xiao, "esp32-288485ba1e48");
```

See [the ready-to-use SC examples](../examples/xiao-headless.scd). No new SC class
or UGen is required for USB routing or GPIO buses. Existing named definitions
remain silent when deployed and boot inactive until explicitly started or first
used by a note pattern. Browser-uploaded autonomous sound blocks retain their
automatic loading/reboot behaviour, allowing standalone operation without a host.

## Capturing sound without a DAC

Start the intended sound or pattern first. Studio shares USB between capture and
live controls one transaction at a time; DSP and I²S keep running. Three full
captures were downloaded during a [one-minute, eight-note-per-second MiRings1
pattern](../evidence/xiao-live-capture.json), with zero late/rejected events or
reported audio faults. With the [faster capture firmware](../evidence/xiao-fast-capture.json),
a one-second snapshot takes about 4.9 seconds to record and download while the
pattern plays, versus about 11 seconds with the original 256-byte reads.
Capture reads negotiate up to 1,024 bytes; patch-upload chunks remain 256 bytes.

Studio permits one capture at a time and checks that the selected device has not
changed before each transaction. A disconnect or device replacement aborts the
capture. Updated hosts bind every read to an opaque recording ID, and firmware
rejects an ID mismatch, so another controller replacing the capture cannot
silently mix different recordings. Legacy hosts or firmware can still use
untagged reads; coordinate captures between hosts when using that fallback.

With Studio connected to the XIAO:

```sh
python3 host/capture.py --studio --seconds 1 --output build/host/xiao.wav
```

Use the IDF Python or another environment with pyserial for direct USB:

```sh
python host/capture.py --port YOUR_XIAO_PORT --output build/host/xiao.wav
```

Close Studio's USB connection before direct access. A paired Wi-Fi endpoint can
instead be selected with `--module PERMANENT_ID`. Audio is captured from the
stereo S16 buffer after master FX, volume, gain and saturation, using the exact
buffer successfully copied to the I²S driver. Capture does not create or restart a synth. Files are written locally;
there is no automatic computer playback.

For developer checks of reply bounds, recording IDs and byte-identical readout
at different chunk sizes, close Studio's USB connection and run:

```sh
python host/check_capture_protocol.py --port YOUR_XIAO_PORT --benchmark
```

This replaces the temporary capture buffer without changing saved patches. The
[physical protocol check](../evidence/xiao-capture-protocol.json) records the
validated bounds, legacy compatibility and measured readout times.

## Physical inputs as control buses

| Bus | Input | Default |
| --- | --- | --- |
| 8 | D0 / GPIO1 / ADC1 channel 0 | Disabled; 0 |
| 9 | D1 / GPIO2 / ADC1 channel 1 | Disabled; 0 |
| 10 | BOOT / GPIO0 | Released = 0, pressed = 1 |

These are ordinary `In.kr` buses. On a desktop SC server, host `c_set` messages
can simulate the same input values. Touch buses 0–2 retain their existing meaning
for code shared with the AMOLED target.

Enable `CONFIG_SYNTHDEF_ANALOG_INPUTS=y` only after connecting suitable 0–3.3 V
controls. ADC inputs are sampled outside the audio task at up to 100 Hz, smoothed,
and normalized from raw 12-bit counts; this is not calibrated voltage measurement.
The optional ADC path has not yet been verified with externally driven voltages.
It has been cross-compiled with the ADC option enabled.
The button uses roughly 20 ms debounce. Values cross into the audio task through
atomic scalars; ADC reads and GPIO configuration never occur in the audio loop.

The low-level `INPUTS` query reports mapping and current values. From SC:

```supercollider
ESP32.request(\inputs, (target: "esp32-288485ba1e48")).onDone(_.postln);
```

The tested unit is left with [this standalone BOOT-controlled sound block](../examples/xiao-standalone-button.scd)
in Main, with the test FX bypassed. It starts automatically on reboot and is
silent until BOOT is pressed. The [restart check](../evidence/xiao-restart-check.json)
verifies its saved graph and automatic startup; no network or host play command
is needed for that block. Sending a new definition replaces this demo normally.
