# Touch control buses

The code-first interface reads hardware-style control buses with standard
SuperCollider `In.kr`. There are 32 read-only float32 channels, numbered 0–31.
Control-bus numbering is separate from the existing stereo audio input bus.

| Bus | Source | Values |
| --- | --- | --- |
| 0 | Touch X | Left 0, right 1 |
| 1 | Touch Y | Bottom 0, top 1 |
| 2 | Touch gate | Finger down 1, release 0 |
| 3–31 | Reserved | Currently zero |

The playing region is screen (0,48) through (319,367). X/Y retain their last
values on release. Opening Controls, becoming busy and Panic release the touch.
The right/bottom scroll strips send neither note events nor bus changes.
Press ownership is locked until release, even when crossing between regions.

The audio owner applies input updates before rendering each 64-frame block.
The bus array is stable throughout that render; the physical touch controller
has its own sampling cadence. Rendering performs no GPIO/I2C reads. This does
not promise sample-accurate physical input timing or an atomic XY sensor pair.

## SynthDef

[touch-buses.scd](../examples/touch-buses.scd) is the complete original source.
Its compiled graph is [TouchBuses.scsyndef](../examples/TouchBuses.scsyndef).
The input can be read as a contiguous bank:

```supercollider
var touch = In.kr(\hwBus.kr(0), 3);
var x = touch[0];
var y = touch[1];
var gate = touch[2];
```

Use Lag or another supported smoothing UGen where appropriate. The SynthDef
chooses the X/Y mappings and its own envelope; no custom hardware UGen or SC
extension is required.

The FM1 firmware accepts bus-driven graphs without requiring the legacy
freq/amp/gate/knob arguments. Browser/legacy bus-driven packages start at load with touch gate low
and continue running between touches, preserving oscillator, delay and other
state. SC-managed definitions still require explicit creation (`ESP32.play` or
`.playESP32`); saving alone does not start them. The SynthDef should use the gate
if sound must stop on finger-up.
Its doneAction remains effective. Panic stops it; the next touch starts it
again. A same-block release/retrigger is separated by a low-gate block so the
next rising edge is observable. Early release cancels deferred construction.

Existing saved voices retain their prior note lifecycle, normalized X/Y to
knob1/knob2 mapping, attack/release defaults and persistent master delay.

## On the computer

After booting SC and loading the same definition, allocate a control bank and
pass its base address to the SynthDef:

```supercollider
~touch = Bus.control(s, 3);
~touch.setn([0.5, 0.5, 0]);
~voice = Synth(\TouchBuses, [\hwBus, ~touch.index]);
~touch.setn([0.2, 0.8, 1]); // Touch/move
~touch.setAt(2, 0);         // Release
```

On the ESP32 the hardware bank starts at 0. On the host the allocated index can
be different; the graph/source is otherwise unchanged. Bus allocation and
initialization precede starting the host synth.

## Engine scope and checks

The target profile adds bounded, multichannel In.kr support to a generated
copy of the pinned engine. Vendored sources are unchanged. Invalid literal
bus ranges, channel counts and rates are rejected; invalid dynamic addresses
or nonfinite values fault safely. Unbound channels read zero. The caller binds
a persistent snapshot after fm_start with fm_bind_control_buses. This is not
a general SC server: Out.kr, arbitrary audio routing and a synth node tree
are not added. Compact policy uploads retain their existing admission rules;
the device bus example uses the FM1 firmware.

```sh
python3 host/export_touch_buses.py
python3 host/test_control_buses.py
python3 host/preview_ui.py
python3 host/test.py
python3 host/test_patches.py
```

The bus test checks bounds and lifecycle under undefined/bounds sanitizers and
compares 28,672 stereo frames against SuperCollider NRT with live X/Y/gate
changes. No computer audio device is opened. See control-buses-host.json.
The native UI test exercises real LVGL input dispatch, both scroll strips,
cross-boundary ownership, slot list scroll/load, busy/Panic and 64 KiB documents.

The board diagnostic u parks/mutes audio and captures four windows from the
same 448-block bus schedule for comparison with native C. The code/slots device
test preserves existing slots, optionally installs the example into an empty
slot, verifies package readback and captures both screens. See
evidence/code-slots-device.json and host/test_device_code_slots.py. Physical
finger and power-cycle checks are recorded separately.
