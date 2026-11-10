# XIAO ESP32-S3 headless instrument

The XIAO target uses the same FM1-compatible DSP engine, Main/FX definitions,
instance lifecycle, named controls and module volume as the AMOLED instrument.
It excludes the Waveshare BSP, display, touch controller and ES8311 codec.
The initial physical target has 8 MB flash and 8 MB octal PSRAM.

## What is working

The standard commissioning Main is the autonomous
[module audio check](../examples/module-audio-check.scd), at 20% output volume
with the separate FX slot bypassed. It plays without BOOT, touch or host input
and starts again on reboot. The older **Standalone BOOT** example is an optional
GPIO demonstration, not the standard headless listening setup. Firmware-only
updates preserve the saved Main; commissioning explicitly installs this block.

- USB upload with saved graph/source readback; Main and FX survive restart.
- SuperCollider Function/SynthDef deployment, aliases, sets and scheduled notes
  through Studio's existing USB connection. Wi-Fi pairing is not required for USB.
- Stereo, 44.1 kHz, signed 16-bit Philips I²S, with six 128-frame DMA buffers.
- Separate left/right output, final volume ramp, FX routing and bypass.
- Studio's **Output volume** slider controls this module over USB or Wi-Fi;
  releasing it saves the level for reboot, without replacing Main or FX.
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

On 3 November 2026, with the supplied antenna attached, the expanded signal-reuse
build [successfully scanned 10 nearby networks](../evidence/signal-reuse-xiao-wifi-scan.json).
No Wi-Fi credentials were configured and no association or network upload was
tested. After the scan, internal free RAM was 99,115 bytes, with a 63,488-byte
largest free block; all audio fault counters remained zero while the restored
BOOT patch was idle. This is radio startup/scan evidence, not loaded-network DSP
qualification.

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

## Checking SuperCollider control

Target the XIAO's own ID, name or alias; AMOLED IDs in an older example still
target those AMOLED modules. For the tested XIAO:

```supercollider
ESP32.set("esp32-288485ba1e48", \freq, 440);
ESP32.info("XIAO-ba1e48").onDone(_.postln);
```

Use `\esp32Set` patterns for an already running autonomous sound with no `gate`
control. `\esp32Note` requires a writable control-rate `gate` and handles the
note's gate-on/release, including creating an inactive saved definition. For an
ADSR definition saved with `.sendESP32`, explicit
`ESP32.play("XIAO-ba1e48", [\freq, 440, \gate, 1])` creates and opens the gate;
`ESP32.set("XIAO-ba1e48", \gate, 0)` releases it. A parameter update alone does
not create an inactive definition. Saved definitions boot inactive by design.

Check **Bypass FX** when Main already contains an expensive reverb. Separate FX
can add enough load to overrun audio even though uploads and control messages
still succeed. On this XIAO, the eight-saw/MiVerb Main plus a second master FX
reached about 135% audio load and accumulated DMA overruns; bypassing the master
reduced the observed Main load to about 92%. These are workload observations,
not a general headless/AMOLED performance comparison.

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

### NS4168 I2S DAC and speaker amplifier

On 11 November 2026, the user confirmed hardware testing with a Seeed XIAO
ESP32-S3 and the NS4168 I²S DAC/amp breakout. The amplifier plays one channel of
the XIAO's existing 44.1 kHz, 16-bit Philips I²S stream. For a listening test,
send the same signal to both I²S channels.

| Breakout label | XIAO connection |
| --- | --- |
| `G` | `GND` |
| `V` | `3V3` |
| `BCL` | `D8` / GPIO7 |
| `LRC` | `D9` / GPIO8 |
| `DIN` | `D10` / GPIO9 |

Connect a passive 4 Ω speaker across the amplifier's `+` and `−` terminals and
keep both leads isolated from ground. Powering the amp at 3.3 V keeps its I²S
input thresholds within the XIAO's logic range. Begin at low output volume
when sharing the XIAO's regulated supply. [NS4168 datasheet](https://pdf.data.kynix.com/r/datasheets/04aba3168248e67c38dd0a24fbd44cbd.pdf)

### Temporary PCM5102A test DAC

Project decision, 3 November 2026: the temporary PCM5102A breakout is now wired
and has passed a basic stereo listening test. The final I²S solution will change.
The user confirmed clean left-only 440 Hz, right-only 660 Hz and simultaneous
stereo tones. Internal PCM matched both pitches and channel separation, with
zero audio fault-counter increases; Panic produced silent PCM. The test used
25% module volume and a 0.1-amplitude sine per enabled channel. Original saved
Main and settings were restored. See [the listening record](../evidence/xiao-pcm5102a-listening.json).
Analogue level, noise/distortion and clock accuracy remain unmeasured; this is
user listening confirmation, not instrumented DAC qualification.

A subsequent [Comb Cloud KR + separate MiVerb listening test](../evidence/xiao-pcm5102a-cloud.json)
also passed: eight seconds dry, then 24 seconds with MiVerb at 35% wet and six
frequency changes. The user confirmed clean sound including the effect tail
after Main stopped. Maximum sampled average audio load was 33.6% dry and 70.0%
with FX. The first second after starting FX included a 126.3% peak window; that
individual-block timing exceeds the nominal block period, even though buffering
allowed playback without reported DMA overruns or write failures. There were
no new clipping, nonfinite, queue-overflow or DSP fault counts, and sampled free
memory remained constant. Panic produced silent PCM; original Main/FX packages,
bypass, volume and instance activity were restored. Wi-Fi remained unconfigured.

The [initial attempt](../evidence/xiao-pcm5102a-cloud-startup-guard.json) stopped
on a conservative 95% CPU peak guard. At the user's request, the repeat logged
brief timing peaks without stopping on percentage alone, while still checking
actual audio faults. This qualifies the heard fixture, not arbitrary workloads
or strict per-block deadline compliance.

The existing XIAO adapter already sends 44.1 kHz stereo, 16-bit Philips I²S,
with 16-bit slots (32 BCLK cycles per stereo frame). Its nominal BCLK is
1.4112 MHz. The PCM5102A supports this format and BCLK-derived internal clock,
so no firmware format change or external MCLK is needed. See the
[TI datasheet](https://www.ti.com/lit/ds/symlink/pcm5102a.pdf), sections 7 and
9.3.5.3 / Table 11.

| XIAO connection | PCM5102A breakout signal |
| --- | --- |
| D8 / GPIO7 | BCK / BCLK |
| D9 / GPIO8 | RCK on this unit; also labelled LCK / LRCK / WS |
| D10 / GPIO9 | DIN |
| GND | GND |

For three-wire operation, verify the breakout holds SCK at ground. Select
I²S with FMT low, disable de-emphasis with DEMP low, and ensure XSMT (sometimes
labelled XMT) is high for playback. Check the board's existing straps before
adding connections. Confirm its exact power input from its documentation:
a breakout's VIN and regulator are board-specific, and must not be inferred
from the chip supply rating. Connect line outputs to an amplifier, mixer or
audio-interface line input; these are not speaker outputs.

The later bench check should start at low module and listening levels, confirm
left/right independently, then test volume, Panic, FX bypass and reboot/patch
changes for glitches. Compare recorded analogue output against USB PCM capture.
Keep the DAC-specific power, straps and any future mute/control support within
the board adapter. The DSP, SynthDef format and network API remain independent
of the chosen converter; GPIO settings already support changing its wiring.

The user's supplied purple GY module photo and `pcm5102a_dac_schematic.pdf`
(macsbug, 2021-02-19) identify the actual test breakout. Its schematic specifies
5 V VIN feeding separate onboard analogue/digital 3.3 V regulators. For this
module, with the XIAO powered by USB, connect XIAO 5V to DAC VIN, GND to GND,
D8/GPIO7 to BCK, D9/GPIO8 to RCK (LRCK), and D10/GPIO9 to DIN. Ground DAC SCK using
a short wire to DAC GND, or the component-side SCK-to-ground solder jumper
shown in the supplied PDF. No XIAO MCLK signal is needed. Leave A3V3 and the
FLT/DEMP/XSMT/FMT header pins unconnected when using the configuration jumpers.

Required electrical settings for the three-pad selectors:

| Selector | Position in user's photo | Bridge | Function |
| --- | --- | --- | --- |
| H1L | Upper left | Centre to verified ground outer pad | FLT low: normal-latency filter |
| H2L | Lower left | Centre to verified ground outer pad | DEMP low: de-emphasis off |
| H3L | Upper right | Centre to verified 3.3 V outer pad | XSMT high: unmuted |
| H4L | Lower right | Centre to verified ground outer pad | FMT low: Philips I²S |

Correction, 3 November 2026: previous top/bottom pad instructions were too
confident. With the digital header at the top in both images, the PDF example
shows upper/centre bridges for H1/H2/H4 and a lower/centre bridge for H3; its H/L
lettering is reversed relative to the user's actual board photo. Do not infer
this unit's rail assignments from the PDF's physical bridge positions or silk
alone. With all power disconnected and temporary configuration wires removed,
measure each outer pad to GND. The ground outer pad should read approximately
zero ohms; the other outer pad is the high selection in the documented selector
topology. If both or neither outer pad reads as ground, resolve the wiring before
soldering. Select ground for H1/H2/H4 and the 3.3 V side for H3.

The PDF lists those electrical states as purchase defaults, but the user reported
all selectors open before rework on this unit. Retain a correct existing bridge if present;
remove an opposite-side bridge before changing sides. Never bridge all three
pads, since that connects the supply to ground. Use the jack or LROUT/ROUT plus
AGND for line-level audio. A [first listening test](../evidence/xiao-pcm5102a-first-listening.json)
produced no audible output despite correct internal PCM. After the jumper-setting
discussion and reconnection, the repeat test produced clean sound on both
channels according to the user. The final physical solder/wire arrangement was
not independently inspected or measured.

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
