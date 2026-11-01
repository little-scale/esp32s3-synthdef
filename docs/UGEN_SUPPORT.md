# UGen and operator support — 1 November 2026

All **154 UGen types, 33 unary operators and 40 binary operators** in the pinned
FM1 engine now have successful computer-side execution coverage. They are no
longer merely inferred from compiled source. The renderer already contained this
set; the new optional ESP32 profile expands upload admission, graph capacities
and synth memory to make it usable.

The initial full-set validation used silent local tests. The user subsequently
authorized flashing and hardware tests, including playback. The FM1 profile is
now installed. Extended captures cover all 154 UGen types, all 258 observed
fixture type/rate pairs, and every unary/binary selector at initial, control and
audio rate. A Gendy3 closing-segment fault was found and fixed. The ledger labels
statistical-only and float-drift results explicitly; numerical support does not
guarantee real-time CPU suitability. See [EXTENDED_TESTS.md](EXTENDED_TESTS.md).
Native execution of C on the computer is not cycle-accurate Xtensa emulation.

## Meaning of the results

- **Software tested:** every row passed finite-output rendering with undefined-
  behaviour, bounds and float-cast sanitizers. The 1,444 pinned fixtures also
  passed SuperCollider 3.14.1 offline comparisons. Some stochastic/chaotic cases
  use the pinned statistical/timing criteria rather than exact waveforms;
  independent state and arithmetic oracles passed separately.
- **In:** absent from those 1,444 fixtures; covered by the embedded master-delay
  graph and three additional 12-second SuperCollider input-bus comparisons.
- **Heard:** occurs at the stated rates in graphs previously played successfully
  on this board. This covers those graph configurations, not every input domain.
- **Captured:** muted numerical captures, including all 73 audio-rate operator
  selectors on the FM1 compatibility image and earlier/current delay evidence.
  The operator graphs cycle through every selector and vary inputs over 280
  cases each; all 107,520 mono samples matched the computer exactly. This does
  not establish all domains/rates or arbitrary graph performance.
- **Long:** 11.89-second guarded hardware traces, including parameter events.
  Statistical cases and Klang drift are labelled; they are not exact waveform
  claims. CPU timing is separate from numerical agreement.
- **Untested:** no board evidence for that particular combination.

`ir` = initial/scalar, `kr` = control, `ar` = audio rate. Rates shown below are
observed in the rendered fixtures/probes, not a promise of every possible rate or
input combination. The pinned loader remains authoritative for valid layouts,
literal parameters, selectors and domains.

## Dynamic bank composites

DynKlank and DynKlang are supported and verified at audio/control rate, including
live parameter changes and mixed-rate inputs. SuperCollider expands them to
Ringz/SinOsc plus mixing; they do not add new native opcode names to the 154-type
count. Twelve SC NRT comparisons and four muted board traces pass. See
[DYNAMIC_BANKS.md](DYNAMIC_BANKS.md) for examples, rate semantics and evidence.

## UGen list

| UGen | Software-tested rates | Graphs | Board evidence |
| --- | --- | ---: | --- |
| A2K | kr | 1 | Long: kr |
| AllpassC | kr, ar | 11 | Long: kr, ar |
| AllpassL | kr, ar | 11 | Long: kr, ar |
| AllpassN | kr, ar | 11 | Long: kr, ar |
| Amplitude | kr, ar | 9 | Long: kr, ar |
| BHiShelf | ar | 9 | Long: ar |
| BLowShelf | ar | 9 | Long: ar |
| BPF | kr, ar | 6 | Long: kr, ar |
| BPeakEQ | ar | 9 | Long: ar |
| BRF | kr, ar | 6 | Long: kr, ar |
| Balance2 | kr, ar | 6 | Long: kr, ar |
| BinaryOpUGen | ir, kr, ar | 1198 | Long: ir, kr, ar |
| Blip | kr, ar | 12 | Long: kr, ar |
| BlockSize | ir | 1 | Long: ir |
| BrownNoise | kr, ar | 2 | Long: kr, ar |
| Clip | kr, ar | 4 | Long: kr, ar |
| ClipNoise | kr, ar | 2 | Long: kr, ar |
| CoinGate | kr, ar | 6 | Long: kr, ar |
| CombC | kr, ar | 11 | Long: kr, ar |
| CombL | kr, ar | 12 | Long: kr, ar |
| CombN | kr, ar | 11 | Long: kr, ar |
| Control | ir, kr | 807 | Long: ir, kr |
| ControlDur | ir | 1 | Long: ir |
| ControlRate | ir | 1 | Long: ir |
| Crackle | kr, ar | 6 | Long: kr, ar |
| CuspL | ar | 3 | Long: ar |
| CuspN | ar | 3 | Long: ar |
| DC | kr, ar | 141 | Long: kr, ar |
| Decay | kr, ar | 10 | Long: kr, ar |
| Decay2 | kr, ar | 18 | Long: kr, ar |
| DegreeToKey | kr, ar | 11 | Long: kr, ar |
| Delay1 | kr, ar | 4 | Long: kr, ar |
| Delay2 | kr, ar | 4 | Long: kr, ar |
| DelayC | kr, ar | 11 | Long: kr, ar |
| DelayL | kr, ar | 11 | Long: kr, ar |
| DelayN | kr, ar | 11 | Long: kr, ar |
| Dust | kr, ar | 12 | Long: kr, ar |
| Dust2 | kr, ar | 12 | Long: kr, ar |
| EnvGen | kr, ar | 40 | Long: kr, ar |
| ExpRand | ir | 7 | Long: ir |
| FBSineC | ar | 3 | Long: ar |
| FBSineL | ar | 3 | Long: ar |
| FBSineN | ar | 3 | Long: ar |
| Fold | kr, ar | 6 | Long: kr, ar |
| Formant | ar | 15 | Long: ar |
| Formlet | kr, ar | 80 | Long: kr, ar |
| FreeVerb | ar | 11 | Long: ar |
| FreeVerb2 | ar | 11 | Long: ar |
| FreqShift | ar | 6 | Long: ar |
| Gate | kr, ar | 9 | Long: kr, ar |
| Gendy1 | kr, ar | 27 | Long: kr, ar; some statistical |
| Gendy2 | kr, ar | 27 | Long: kr, ar; some statistical |
| Gendy3 | kr, ar | 27 | Long: kr, ar; some statistical |
| GrayNoise | kr, ar | 6 | Long: kr, ar |
| HPF | kr, ar | 6 | Long: kr, ar |
| HPZ1 | kr, ar | 6 | Long: kr, ar |
| Hasher | kr, ar | 6 | Long: kr, ar |
| HenonC | ar | 3 | Long: ar |
| HenonL | ar | 3 | Long: ar |
| HenonN | ar | 3 | Long: ar |
| Impulse | kr, ar | 150 | Long: kr, ar |
| In | ar, kr | 1 | Long: ar; control-bus extension: kr, see TOUCH_BUSES.md |
| K2A | ar | 605 | Long: ar |
| Klang | ar | 1 | Long: ar; float drift, PCM ≤1 step |
| Klank | ar | 1 | Long: ar |
| LFClipNoise | kr, ar | 6 | Long: kr, ar |
| LFCub | kr, ar | 8 | Long: kr, ar |
| LFDClipNoise | kr, ar | 7 | Long: kr, ar |
| LFDNoise0 | kr, ar | 10 | Long: kr, ar |
| LFDNoise1 | kr, ar | 10 | Long: kr, ar |
| LFDNoise3 | kr, ar | 10 | Long: kr, ar |
| LFNoise0 | kr, ar | 8 | Long: kr, ar |
| LFNoise1 | kr, ar | 9 | Long: kr, ar |
| LFNoise2 | kr, ar | 8 | Long: kr, ar |
| LFPar | kr, ar | 8 | Long: kr, ar |
| LFPulse | kr, ar | 118 | Long: kr, ar |
| LFSaw | kr, ar | 6 | Long: kr, ar |
| LFTri | kr, ar | 5 | Long: kr, ar |
| LPF | kr, ar | 6 | Long: kr, ar |
| LPZ1 | kr, ar | 6 | Long: kr, ar |
| Lag | kr, ar | 5 | Long: kr, ar |
| Lag2 | kr, ar | 4 | Long: kr, ar |
| Lag3 | kr, ar | 4 | Long: kr, ar |
| LagControl | kr | 2 | Long: kr |
| LagUD | kr, ar | 4 | Long: kr, ar |
| Latch | kr, ar | 9 | Long: kr, ar |
| LatoocarfianC | ar | 3 | Long: ar; some statistical |
| LatoocarfianL | ar | 3 | Long: ar; some statistical |
| LatoocarfianN | ar | 3 | Long: ar; some statistical |
| LeakDC | kr, ar | 4 | Long: kr, ar |
| Limiter | ar | 5 | Long: ar |
| LinExp | kr, ar | 4 | Long: kr, ar |
| LinXFade2 | kr, ar | 6 | Long: kr, ar |
| Line | kr, ar | 7 | Long: kr, ar |
| LocalBuf | ir | 11 | Long: ir |
| Logistic | kr, ar | 4 | Long: kr, ar |
| LorenzL | ar | 3 | Long: ar |
| MaxLocalBufs | ir | 11 | Long: ir |
| MiMu | ar | 8 | Long: ar |
| MiRings1 | ar | 7 | Long: ar |
| MiRings2 | ar | 7 | Long: ar |
| MiRings3 | ar | 7 | Long: ar |
| MiRings4 | ar | 7 | Long: ar |
| MiRings5 | ar | 7 | Long: ar |
| MiRings6 | ar | 7 | Long: ar |
| MiVerb | ar | 15 | Long: ar |
| MoogFF | kr, ar | 8 | Long: kr, ar |
| MulAdd | ir, kr, ar | 387 | Long: ir, kr, ar |
| OnePole | kr, ar | 8 | Long: kr, ar |
| OneZero | kr, ar | 8 | Long: kr, ar |
| Out | ar | 1445 | Long: ar |
| Pan2 | ar | 314 | Long: ar |
| Phasor | kr, ar | 10 | Long: kr, ar |
| PinkNoise | kr, ar | 4 | Long: kr, ar |
| Pluck | ar | 6 | Long: ar |
| Pulse | kr, ar | 13 | Long: kr, ar |
| PulseCount | kr, ar | 8 | Long: kr, ar |
| PulseDivider | kr, ar | 6 | Long: kr, ar |
| RHPF | kr, ar | 6 | Long: kr, ar |
| RLPF | kr, ar | 7 | Long: kr, ar |
| RadiansPerSample | ir | 1 | Long: ir |
| Rand | ir | 7 | Long: ir |
| RandSeed | ir, kr, ar | 370 | Long: ir, kr, ar |
| Resonz | kr, ar | 8 | Long: kr, ar |
| Ringz | kr, ar | 9 | Long: kr, ar |
| SampleDur | ir | 1 | Long: ir |
| SampleRate | ir | 1 | Long: ir |
| Saw | kr, ar | 9 | Long: kr, ar |
| Select | kr, ar | 5 | Long: kr, ar |
| SetBuf | ir | 11 | Long: ir |
| SetResetFF | kr, ar | 8 | Long: kr, ar |
| SinOsc | kr, ar | 639 | Long: kr, ar |
| SinOscFB | kr, ar | 12 | Long: kr, ar |
| Slew | kr, ar | 6 | Long: kr, ar |
| StandardL | ar | 3 | Long: ar; some statistical |
| StandardN | ar | 3 | Long: ar; some statistical |
| Stepper | kr, ar | 8 | Long: kr, ar |
| Sum3 | ar | 2 | Long: ar |
| Sum4 | ir, ar | 2 | Long: ir, ar |
| SyncSaw | kr, ar | 8 | Long: kr, ar |
| TExpRand | kr, ar | 11 | Long: kr, ar |
| TIRand | kr, ar | 6 | Long: kr, ar |
| TRand | kr, ar | 11 | Long: kr, ar |
| TWindex | kr, ar | 6 | Long: kr, ar |
| ToggleFF | kr, ar | 6 | Long: kr, ar |
| Trig | kr, ar | 6 | Long: kr, ar |
| Trig1 | kr, ar | 6 | Long: kr, ar |
| TrigControl | kr | 1 | Long: kr |
| UnaryOpUGen | ir, kr, ar | 78 | Long: ir, kr, ar |
| VarSaw | kr, ar | 8 | Long: kr, ar |
| WhiteNoise | kr, ar | 45 | Long: kr, ar |
| Wrap | kr, ar | 6 | Long: kr, ar |
| XFade2 | kr, ar | 8 | Long: kr, ar |
| XLine | kr, ar | 2 | Long: kr, ar |

## Unary operators

| Selector | Operation | Software-tested rates | Board evidence |
| ---: | --- | --- | --- |
| 0 | neg | kr, ar | Long: ir, kr, ar |
| 5 | abs | ar | Long: ir, kr, ar |
| 8 | ceil | ar | Long: ir, kr, ar |
| 9 | floor | ar | Long: ir, kr, ar |
| 10 | frac | ar | Long: ir, kr, ar |
| 11 | sign | ar | Long: ir, kr, ar |
| 12 | squared | ar | Long: ir, kr, ar |
| 13 | cubed | ar | Long: ir, kr, ar |
| 14 | sqrt | ar | Long: ir, kr, ar |
| 15 | exp | ar | Long: ir, kr, ar |
| 16 | reciprocal | ir, ar | Long: ir, kr, ar |
| 17 | midicps | ar | Long: ir, kr, ar |
| 18 | cpsmidi | kr, ar | Long: ir, kr, ar |
| 19 | midiratio | kr, ar | Long: ir, kr, ar |
| 20 | ratiomidi | kr, ar | Long: ir, kr, ar |
| 21 | dbamp | kr, ar | Long: ir, kr, ar |
| 22 | ampdb | kr, ar | Long: ir, kr, ar |
| 23 | octcps | kr, ar | Long: ir, kr, ar |
| 24 | cpsoct | kr, ar | Long: ir, kr, ar |
| 25 | log | kr, ar | Long: ir, kr, ar |
| 26 | log2 | ar | Long: ir, kr, ar |
| 27 | log10 | ar | Long: ir, kr, ar |
| 28 | sin | ar | Long: ir, kr, ar |
| 29 | cos | ar | Long: ir, kr, ar |
| 30 | tan | ar | Long: ir, kr, ar |
| 31 | asin | ar | Long: ir, kr, ar |
| 32 | acos | kr, ar | Long: ir, kr, ar |
| 33 | atan | kr, ar | Long: ir, kr, ar |
| 34 | sinh | kr, ar | Long: ir, kr, ar |
| 35 | cosh | kr, ar | Long: ir, kr, ar |
| 36 | tanh | kr, ar | Long: ir, kr, ar |
| 42 | distort | ar | Long: ir, kr, ar |
| 43 | softclip | ar | Long: ir, kr, ar |

## Binary operators

| Selector | Operation | Software-tested rates | Board evidence |
| ---: | --- | --- | --- |
| 0 | + | ir, kr, ar | Long: ir, kr, ar |
| 1 | - | ir, kr, ar | Long: ir, kr, ar |
| 2 | * | ir, kr, ar | Long: ir, kr, ar |
| 3 | div (floor integer division) | kr, ar | Long: ir, kr, ar |
| 4 | / | kr, ar | Long: ir, kr, ar |
| 5 | mod | kr, ar | Long: ir, kr, ar |
| 6 | == | ar | Long: ir, kr, ar |
| 7 | != | ar | Long: ir, kr, ar |
| 8 | < | kr, ar | Long: ir, kr, ar |
| 9 | > | ar | Long: ir, kr, ar |
| 10 | <= | ar | Long: ir, kr, ar |
| 11 | >= | kr, ar | Long: ir, kr, ar |
| 12 | min | ar | Long: ir, kr, ar |
| 13 | max | ar | Long: ir, kr, ar |
| 17 | lcm | kr, ar | Long: ir, kr, ar |
| 18 | gcd | kr, ar | Long: ir, kr, ar |
| 19 | round | kr, ar | Long: ir, kr, ar |
| 20 | roundUp | kr, ar | Long: ir, kr, ar |
| 21 | trunc (floor quantization) | kr, ar | Long: ir, kr, ar |
| 22 | atan2 | kr, ar | Long: ir, kr, ar |
| 23 | hypot | kr, ar | Long: ir, kr, ar |
| 24 | hypotApx | kr, ar | Long: ir, kr, ar |
| 25 | pow (signed) | kr, ar | Long: ir, kr, ar |
| 30 | ring1 | kr, ar | Long: ir, kr, ar |
| 31 | ring2 | kr, ar | Long: ir, kr, ar |
| 32 | ring3 | kr, ar | Long: ir, kr, ar |
| 33 | ring4 | kr, ar | Long: ir, kr, ar |
| 34 | difsqr | kr, ar | Long: ir, kr, ar |
| 35 | sumsqr | kr, ar | Long: ir, kr, ar |
| 36 | sqrsum | kr, ar | Long: ir, kr, ar |
| 37 | sqrdif | kr, ar | Long: ir, kr, ar |
| 38 | absdif | kr, ar | Long: ir, kr, ar |
| 39 | thresh | kr, ar | Long: ir, kr, ar |
| 40 | amclip | kr, ar | Long: ir, kr, ar |
| 41 | scaleneg | kr, ar | Long: ir, kr, ar |
| 42 | clip2 | kr, ar | Long: ir, kr, ar |
| 43 | excess | kr, ar | Long: ir, kr, ar |
| 44 | fold2 | kr, ar | Long: ir, kr, ar |
| 45 | wrap2 | kr, ar | Long: ir, kr, ar |
| 46 | firstArg | kr, ar | Long: ir, kr, ar |

## What the firmware accepts

| Profile | Graph capacity | Synth arena | Upload policy | Qualification |
| --- | --- | --- | --- | --- |
| Compact (default) | 24 nodes, 32 signals, 256 references | None | Existing sine family and exact catalog graphs | Earlier graphs have board evidence; current changed source requires renewed qualification |
| FM1 compatibility (optional) | 160 nodes, 192 signals, 1,024 references | 262,144 floats / 1 MiB PSRAM | Entire pinned FM1 type/operator set, subject to loader validation | Long captures cover the full type/rate set; precision grades and CPU limitations are reported separately |

The compact loader accepted 1,443 of the 1,444 original fixtures; the large
`m5_addy` graph needs 125 nodes, 136 signals and 338 input references. Loader
acceptance alone does not grant upload admission. The optional profile restores
the FM1 graph capacities and admits all 1,444 after a test-only live-control
interface is added. Uploaded voices require live `freq`, `amp` and `gate` controls;
the four knobs are optional. The fixture wrapper does not automatically connect
those added controls to the fixture DSP and is not a musical patch converter.

The shared five-second master delay retains a separate 1 MiB arena. The optional
synth arena enables Delay/Comb/Allpass, Pluck, FreeVerb/FreeVerb2/MiVerb,
Gendy and Rings inside voices. Graphs share that voice arena and must fit its
total budget. Graphs and scratch move to PSRAM in this profile; voice state stays
internal. This affects performance. Extended hardware tests comprise 24 thirty-second rounds across the three
example voices, plus 60 patch activations. The fixed-image final maxima were
939 µs for Filtered Tone, 918 µs for Phase FM and 952 µs for Harmonic Mix, without
reported faults or 70%-margin violations. Some Rings and dense operator-bank
graphs exceed real-time budgets; see the separate constructor/live cost table
in [EXTENDED_TESTS.md](EXTENDED_TESTS.md).

Synth memory is cleared in chunks of at most 1,024 floats per block, with a
separate constructor block. A full 1 MiB clear therefore adds roughly 373 ms
before rendering starts, at the requested 44.1 kHz rate. Shorter arenas need
fewer blocks. Release/Panic cancels pending preparation. The tests compare
incremental initialization against ordinary initialization exactly, including
arena guards and the full 1 MiB case. This is a functional bound, not a measured
ESP32 execution-time guarantee.

The full-arena synth subsequently passed its own 280-case board comparison
(within one PCM step), cancellation before construction completed, and normal
incremental start/play/release without reported faults. The calculated 373 ms
startup interval has not been measured with an external audio capture.

`In.ar` is meaningful in an effect role with an input bus; ordinary voices receive
a silent audio input bus. The ESP32 target now also supports bounded `In.kr`
reads from a 32-channel control snapshot, with X/Y/gate at 0/1/2. This is an
extension beyond the pinned FM1 engine, independently checked against SC and
on the board; see [TOUCH_BUSES.md](TOUCH_BUSES.md). Custom master-effect uploads and general audio-bus routing
are not added by this profile. LocalBuf/SetBuf remain immutable scale tables
(up to 16 tables, 128 entries each), not general sample recording/playback.
Other FM1 limits remain, including 64 controls, 64 partials, 32 envelope segments
and 64 Gendy points. This is parity with the pinned FM1 DSP subset, not all of
SuperCollider: demand UGens, arbitrary plugins, file/sample playback, unsupported
selectors and unsupported layouts/rates remain rejected.

## Reproduce silently

```sh
make -C upstream/fm1-synthdef/synthdef-engine test
python3 host/test_fm1_parity.py --reference
python3 host/test_fm1_parity.py --fuzz
python3 host/test_fm1_voice.py
python3 host/test_fm1_rejections.py
python3 host/test_master_delay.py
python3 host/test_delay_reference.py
python3 host/document_support.py
```

The comparison uses SuperCollider 3.14.1 non-real-time file rendering. Original
scores remain untouched; cleanup messages are appended after the compared
interval so persistent nodes are destroyed before macOS unloads plugin code.
Upstream commands containing `--device` compile FM1 maths shims on the computer;
they do not connect to a device.

Build the optional firmware without flashing:

```sh
python3 host/prepare.py
SYNTHDEF_BUILD_DIR=build-fm1-compat host/idf.sh -D IDF_TARGET=esp32s3 \
  -D "SDKCONFIG=$PWD/firmware/build-fm1-compat/sdkconfig" \
  -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;$PWD/docs/ui.defaults;$PWD/docs/timing.defaults;$PWD/docs/fm1.defaults" build
python3 host/record_build.py --build-dir build-fm1-compat --output fm1-compat-build.json
```

For an existing build, the SDKCONFIG must actually contain
`CONFIG_SYNTHDEF_FM1_COMPAT=y`; defaults do not override an existing selection.
The build record checks this against the generated profile and records target
structure sizes. Current catalog entries are marked candidates because source
changed; historical hardware qualifications remain in their original evidence.

## Evidence

- [Extended results, Gendy fix, precision grades and CPU costs](EXTENDED_TESTS.md)
- [Fixed-source reference suite](../evidence/fm1-fixed-reference.json)
- [Rings optimization, selected caches, current timing and limits](RINGS_OPTIMIZATION.md)
- [Selected cache target build](../evidence/rings-cache-build.json)
- [Earlier broad-sweep fixed target build](../evidence/fm1-gendy-fixed-build.json)
- [Coverage and all graph results](../evidence/fm1-inventory.json)
- [FM1 hardware matrices and playback/timing follow-up](../evidence/fm1-device-smoke.json)
- [Full synth-arena hardware follow-up](../evidence/fm1-device-synth-memory.json)
- [1,444 SuperCollider comparisons](../evidence/fm1-reference.json)
- [1,445 admission/initialization/lifecycle tests](../evidence/fm1-voice.json)
- [Positive and negative upload-policy checks](../evidence/fm1-admission.json)
- [1,560,000 malformed-input cases](../evidence/fm1-fuzz.json)
- [Original FM1 API and independent oracle output](../evidence/fm1-upstream-tests.log)
- [Three persistent input-bus/delay comparisons](../evidence/delay-host-reference.json)
- [Compact target build](../evidence/fm1-compact-build.json)
- [FM1 compatibility target build](../evidence/fm1-compat-build.json)
- [Pinned FM1 limits and semantics](../upstream/fm1-synthdef/synthdef-engine/README.md)
