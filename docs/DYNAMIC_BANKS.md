# DynKlank and DynKlang

Both SuperCollider classes work through the FM1 compiler/uploader and firmware.
They are language-level composites, not new serialized UGen types:

| Class | Compiled bank | Tested outputs |
| --- | --- | --- |
| DynKlank | One Ringz per mode, level multipliers and a sum | ar, kr |
| DynKlang | One SinOsc per mode, level multipliers and a sum | ar, kr |

The native engine still has 154 types. Source retains the DynKlank/DynKlang call;
the graph inspector shows its underlying Ringz/SinOsc and arithmetic nodes.

Unlike the fixed Klang/Klank banks, dynamic-bank parameters can change while the
sound runs. Tests cover changing frequencies, levels, frequency scale/offset,
ring times/decay scale, oscillator phases, nil defaults and mixed-rate inputs.
The sound-block compiler converts control-rate returns to audio with K2A.

## Rate behaviour

The loader now accepts audio-rate parameter buffers for Ringz and the mixed-rate
SinOsc inputs used by these composites. Ringz reads frequency and ring time at
the start of each calculation block and interpolates its coefficients, matching
SuperCollider. An audio-rate parameter buffer does not make those coefficients
update at audio rate. Ringz's excitation must still fit its output rate; other
filters retain their existing validation. SinOsc retains its existing input-rate
calculation paths. No DSP equations, precision, sample rate or block size changed.

Use control-rate LFOs for slow modulation. DynKlang.ar also accepts audio-rate
frequency/phase modulation. A bank costs one oscillator/filter per mode plus
mixing and modulation; use the display's audio-CPU measurement for the full patch.

## Examples

- [dynklank.scd](../examples/dynklank.scd): five resonators, fresh initial Rand
  values and continuously changing frequency, level and ring-time scales.
- [dynklang.scd](../examples/dynklang.scd): five sine oscillators with continuously
  changing tuning, level and phases.

Open either file in Studio, compile, then choose a writable destination. Both are
autonomous sound blocks. Each example constructs one mono bank and copies its
output to left/right with `! 2`. No saved slot was replaced during verification.

## Verification

`python3 host/test_dynamic_banks.py` compiles 12 deterministic cases, checks FM1
admission and renders 4,096 blocks per case at 44.1 kHz. All 3,145,728 stereo
frames were compared with SuperCollider 3.14.1 NRT output. Maximum absolute
difference was 1.28858e-5, below the 2e-4 peak / 3e-5 RMS limits. Bounds,
undefined-behaviour and float-conversion checks pass. Two negative cases ensure
audio excitation into control-rate Ringz and audio coefficients into Resonz remain
rejected. The 31 Studio tests include source compilation of dynamic banks.

Four muted board traces span 11.89 seconds each, covering the two bank types and
their mixed-rate cases. Forty windows per trace match native C with maximum
sample difference 1.24216e-7. Whole-trace fault/nonfinite/canary checks pass.
The previous sound, volume, saved library and master selection were restored.
The refreshed running uploader also admits and renders both example files.

Evidence: `evidence/dynamic-banks-host.json`, `dynamic-banks-device.json`,
`dynamic-banks-uploader.json` and `dynamic-banks-build.json`. The before report
records the earlier Ringz parameter rejection. These checks establish numerical
support for the tested graphs, not a worst-case CPU qualification for every bank.

Primary references: [DynKlank](https://doc.sccode.org/Classes/DynKlank.html),
[DynKlang](https://doc.sccode.org/Classes/DynKlang.html), and SuperCollider 3.14.1
FSinOsc.sc / FilterUGens.cpp / OscUGens.cpp. The vendored engine remains unchanged;
the audited target generator applies the narrow admission extension.
