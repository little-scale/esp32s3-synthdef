# Touchscreen instrument

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

The default screen is the original SynthDef source, on white with line numbers,
a fixed-width font and SuperCollider colours. Startup restores the last selected
Main patch. There are two screens:

- **Code/play:** touch the code to play and move X/Y. The 48-pixel strip on the
  right scrolls vertically; the 40-pixel strip below the code scrolls horizontally.
- **Controls:** CONTROLS opens a black page with white UI, output volume,
  one Main row to restart the saved patch, and FX / Bypass choices. CODE returns
  without loading. Loading Main returns to code. The footer retains its light
  CODE/CPU/PANIC area. Legacy numbered slots are hidden and inaccessible.

Playback depends on the saved package type:

- **Autonomous `{ ... }.play` blocks:** start on load/reboot. Touch updates X/Y
  but does not restart or stop their audio. The subtitle says **PLAYS AUTOMATICALLY**.
- **Managed SynthDefs:** upload and boot without constructing a voice. Touching
  code starts an inactive instance or triggers the existing one through its
  exposed `gate` argument, if present. Release lowers that gate; the SynthDef's
  envelope/doneAction or natural resonator tail determines when sound ends.
  Without a gate or self-ending envelope, the authored sound may keep running.
  The subtitle says **TOUCH CODE TO PLAY**. SC instance and note commands remain
  available, sharing the same monophonic instance.

The managed-touch fix preserves an active voice's state and controls across
presses, delivers a low block for retriggering, and rejects stale touch releases.
Taking the gate with touch clears the preceding remote note's pending release;
a later SC note or explicit gate set takes ownership back. An old finger release
cannot end that newer remote note. Rapid same-block taps on autonomous blocks
are ignored without silencing them. CPU usage indicates DSP activity; a gated
Rings voice can consume CPU while its trigger is zero and its tail is silent.

The managed-touch update was [physically confirmed on the AMOLED](../evidence/managed-touch-amoled-physical.json):
four press/release pairs changed MiRings1's gate and produced a strike on each
press according to the user, with no new audio fault counters. The autonomous
standard listening block was restored afterward with separate master FX bypassed.

The title is the active patch on Code, and the module name on Controls. Controls
shows the permanent module ID beneath the name. A small green circle directly
above the Wi-Fi symbol lights for 140 ms after a valid upload/control frame (USB or Wi-Fi);
background queries stay dark. Wi-Fi RSSI is shown in dBm beneath the battery,
updated once per second; disconnected nodes show Wi-Fi off. Sampling and bounded
display updates run outside the audio task. The receive cue acknowledges traffic,
not successful sound playback.

Battery remains top right; PANIC remains bottom right and acts on press, even
while loading. Starting in a scroll strip stays a scroll gesture until release,
including when crossing over the code. Starting over the code stays a playing
gesture when crossing into a strip; X/Y clamp at the edges. Scrolling never
posts notes or changes the touch buses. Flick-to-change is removed.

The top title starts 28 pixels from the left and the battery ends 20 pixels
from the right. Subtitle positions are unchanged.

The code playing area is 320 × 320 pixels at screen (0,48). X is 0 at the left
and 1 at the right; Y is 0 at the bottom and 1 at the top. Its coordinates do
not depend on the document's scroll position. The gate is 1 while held and
0 on release, page changes, busy transitions or Panic. See
[TOUCH_BUSES.md](TOUCH_BUSES.md) for In.kr and host testing.

Existing saved patches retain the old touch mapping through knob1/knob2.
The Main graph and saved FX determine its envelope/effect behaviour. Four
sliders, the separate pad, on-screen SAVE and the DELAY page are no longer part
of this interface. USB patch save and FX commands remain available.

Battery uses read-only AXP2101 telemetry every five seconds. It shows the gauge
percentage and charging symbol; USB/empty means no battery detected and ? means
unavailable. The
[pinned vendor reference](https://github.com/waveshareteam/ESP32-S3-Touch-AMOLED-1.8/blob/78e13f852929c2ab4f9d5e0ad1c50ea378dbf2b4/examples/arduino/libraries/XPowersLib/src/XPowersAXP2101.tpp)
defines the registers; this firmware changes no charger/rail configuration.

The footer on both screens shows **CPU** above READY/PLAYING. It is the average
audio processing time as a percentage of the available block duration, refreshed
about once per second. Controls, synthesis, master delay and PCM conversion are
included; waiting for I2S is excluded. This measures the audio budget, not total
utilisation across both cores. The text turns amber if a block in the latest
window uses at least 70% of its budget, or red at 100%. Values can exceed 100%.
Before the first reading, or when telemetry stops, it shows `CPU --`.

## Build and placement

Use the current FM1/cache recipe in [BUILD.md](BUILD.md). Earlier compact/audio-only
build recipes describe historical configurations, not the README quickstart.

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

Native USB recovery and port identification are covered in [BUILD.md](BUILD.md).

## Output volume in CONTROLS

A fixed VOLUME row sits above Main and FX controls. The white slider and numeric
percentage use the existing black background; the code screen and footer remain
unchanged. The list starts at y=114 and is 294 pixels tall. Its scrolling cannot
move the volume row. Dragging volume never sends notes, X/Y or library actions.

The range is 0–100%, default 20% on a module without a saved volume. Existing
saved levels are retained across firmware updates. This is a scale on the existing final output,
after master FX and before PCM quantization. It does not change synth arguments,
feedback levels or the codec setting. Zero keeps the DSP running silently.
A 20 ms linear gain ramp avoids abrupt changes; stable 100% is bit-exact with the
previous PCM conversion. Release saves the value in NVS through a short muted
maintenance operation preserving source and FX state. Patch changes and reboot
retain it. The user confirmed smooth operation; 30% survived a firmware update.

Native LVGL tests exercise drag, busy-state rejection and note/load isolation.
The fixed 64 KiB widget heap retains 33,960 bytes free in the checked fixture.


## Main / FX simplification

There is one writable Main package and one writable FX package, with protected
transparent bypass. The three control rows fit without scrolling. Main is always
restored on ordinary startup when its saved package is valid; FX/bypass and volume
restore independently. Older numbered slot files remain archived in storage.
The host LVGL check retains 44,408 bytes free in the fixed 64 KiB widget heap.


SuperCollider can set the same live output scale with
`ESP32.module(target, \volume, 0.5)` (50%), including `\all`. This updates the
slider without loading a patch. Remote changes are not saved to flash; physical
slider release saves as described above. See [SUPERCOLLIDER.md](SUPERCOLLIDER.md).
