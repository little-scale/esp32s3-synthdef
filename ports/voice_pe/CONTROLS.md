# Voice PE control buses

This layout applies to both the standard **48 kHz** shared application and the
matched [native 16 kHz build](NATIVE_16K.md).
Waveshare/XIAO touch and pin mappings retain their existing assignments.

| Bus | Direction | Meaning |
| --- | --- | --- |
| 0 | `In.kr` | Centre button: released 0, pressed 1; approximately 20–30 ms debounce |
| 1 | `In.kr` | Dial: normalised 0–1, starts at 0.5, clamps at either end; 0.0125 per quadrature edge (about 20 four-edge detents for the full range) |
| 2 | `In.kr` | Physical microphone-mute switch sense: low 0, high 1 |
| 3–38 | `Out.kr` | Twelve LEDs, RGB triplets; LED `n` starts at `3 + (3 * n)` |
| 39 | `Out.kr` | Shared red value for all twelve LEDs |
| 40 | `Out.kr` | Shared green value for all twelve LEDs |
| 41 | `Out.kr` | Shared blue value for all twelve LEDs |
| 42 | `In.kr` | DLight normalised illuminance: 0–1 over 0–1,000 lux, clamped |
| 43 | `In.kr` | DLight illuminance in lux, retaining values above 1,000 lux |
| 44 onward | Reserved | Further Grove inputs |

The [M5Stack DLight driver](GROVE_DLIGHT.md) updates 42/43 only after successful
new sensor readings. Values hold between samples and on read failure; sensor
availability and age are separate status fields. Main and FX share these inputs.

The mute switch is **input data**, not a software speaker-mute instruction. It
continues to physically control the microphone hardware. Dial polarity and the
mute switch's physical-end labels need a user check on this port.

Each RGB value is 0–1. For example, `Out.kr(39, [0, 0.2, 0])` gives the ring a green
background; `Out.kr(3, [0.5, 0, 0])` makes LED 0 red. Individual channels override
that graph's shared colour. On any channel written by FX, FX takes priority over
Main; a shared FX colour also takes priority over Main's individual channels.
Multiple `Out.kr` writers to the same address within a graph **add**, following
Out semantics. Values are clamped only when resolving physical LED colours.
An explicit zero write counts as a write and can override a background colour.
Unwritten channels are black.

The ring uses the official logical order: LED 0 maps to physical LED 7, then
wraps after physical 11. The driver packs GRB internally; patches always use RGB.
The initial firmware caps physical brightness at **20%** for USB-powered testing.
There is no gamma correction. Synth controls are calculated once per 64-frame
block; a bounded mailbox publishes at 50 Hz and the control task refreshes the
ring at up to 40 Hz. RMT transmission never runs on the audio task. If the audio
publisher stops for 200 ms while the control task is running, the ring goes dark.
Boot leaves ring power off. Panic/no remaining writers clears the ring. A stopped
Main does not extinguish an independently running FX graph's authored LEDs.

The Main and FX graphs read the same physical input snapshot. It is kept
separate from internal touch/note-gate state, so note starts and Panic cannot
change the mute-switch input. `In.kr(3, 39)` can read the resolved LED control
snapshot from the **previous audio block**; this is requested colour data,
not electrical/optical feedback. It excludes the physical brightness cap.

## SuperCollider example

Recompile the SC class library after updating the linked ESP32 extension. The
Studio compiler also accepts these control outputs inside a sound Function.
Return the audio signal as the Function's last expression.

If SC still reports `Return audio from the Function; use a literal SynthDef for
authored Out.ar routing` for an `Out.kr` block, choose **Language → Recompile
Class Library** in the SC IDE. The linked extension is read when that library
compiles; changing the files does not update an already-running SC interpreter.
Restart any SC patterns afterward. The current wrapper permits `Out.kr` while
retaining the authored-audio-routing check for `Out.ar`.

A sound Function must finally return mono or stereo audio. For example,
`(0..size)` with `size = 4` creates **five** oscillator frequencies; use
`(0..(size - 1))` for four. Use `Splay.ar(sig)` for a stereo mix or
`Mix.ar(sig) ! 2` for a dual-mono mix when `sig` contains multiple voices.
These audio channel rules do not prevent writing multiple LED control channels.

```supercollider
(
{
    var button = In.kr(0);
    var dial = In.kr(1);
    var hz = dial.linexp(0, 1, 110, 880);

    Out.kr(39, [0, 0.1, 0]);       // all LEDs: dim green
    Out.kr(3, [button * 0.4, 0, dial * 0.4]); // LED 0

    SinOsc.ar(hz, 0, 0.5) * Lag.kr(button, 0.01) ! 2
}.playESP32("VoicePE-0697d4");
)
```

A literal SynthDef may contain both `Out.kr(...)` and its authored `Out.ar(0,...)`.
Control-rate physical output writes are limited to buses **3–41**; writes to
button/dial/mute, Grove inputs or future Grove addresses are rejected. Dynamic bus addresses
are checked again during rendering. A nonfinite signal or invalid dynamic range
faults the graph and clears its physical output bank. Old firmware or a board
without the Voice PE output adapter is rejected by Studio before transfer.

The [installed complete example](../../examples/voice-pe-controls.scd) moves a
blue highlight around the ring as the dial changes, rather than only changing
one segment's brightness. It uses a unit-amplitude source before the global
volume. The current shared firmware uses **0 dB codec gain**, with its first
upgrade starting at no more than **5%** software volume. The original quiet
commissioning firmware used −24 dB.
A forced-button version of the earlier example passed digital PCM capture.
The user confirmed the faster dial, audible button-triggered sound, release
and normal operation after a physical power cycle at saved **25%** volume. Digital capture
alone is not analog proof; the separate listening confirmation is recorded in
the shared-app evidence. The earlier automated tests used 5%.

## Following audio loudness

`Amplitude.kr(audio, attackTime, releaseTime)` follows audio-rate magnitude and
returns a smoothed control-rate envelope. For mono or stereo audio, this makes
one shared ring colour without cancellation between audio channels:

```supercollider
level = Amplitude.kr(sig, 0.01, 0.2).asArray.mean;
level = (level * 5).clip(0, 1);
Out.kr(39, [level * 0.5, 0, level]);
```

Declare `level` with the Function's other variables and return `sig` afterward.
The multiplier sets visual sensitivity; it does not change audio volume. This
tracks the authored signal before the module's global volume slider. For one
LED per voice, measure the audio array before `Splay` and interleave each
envelope into RGB triplets, as in the [complete example](../../examples/voice-pe-audio-leds.scd).
Use at most twelve such triplets. A longer release makes LED trails smoother;
the physical LED driver retains its own refresh and brightness limits.

## Computer verification

```sh
python3 host/test_voice_pe_controls.py
python3 host/test_voice_pe_rates.py
python3 -m unittest discover -s host -p test_signal_limits.py
```

Tests cover first/last output channels, additive writes, dynamic address faults,
nonfinite data, prepare/restart, physical-input isolation from note lifecycle,
broadcast and per-channel priority, RGB/GRB ordering, default darkness and both
16/44.1/48 kHz engine rates. DLight now occupies 42/43; the historical Grove
16–31 prototype draft must not be bound into this Voice PE layout.
