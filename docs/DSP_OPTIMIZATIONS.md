# Exact DSP block kernels and upload transitions

The [optimisation register](OPTIMIZATION_REGISTER.md) is the complete per-UGen
and operator checklist, including inherited paths and disabled experiments.
Its editable JSON and generation/check command keep coverage explicit as the
supported inventory changes. This page describes the latest implementation.

The AMOLED and headless XIAO builds use the same generated DSP implementation.
`host/engine_profile.py` applies audited transformations to the pinned engine;
the vendored upstream files remain unchanged. These changes retain float32
arithmetic, 64-frame blocks, UGen execution order and the SynthDef file format.

The [hardware qualification plan](DSP_HARDWARE_TEST_PLAN.md) prioritizes a
30-minute, two-image session before optional family attribution and broader
coverage. Its prepared fixtures are not hardware results.
The [first XIAO hardware session](DSP_HARDWARE_RESULTS.md) subsequently matched
the 50-case pack for full and narrowed candidates. Target timing was mixed;
no new candidate is enabled by default.
The later [fixed-seed follow-up](DSP_SEEDED_PROFILING.md) records 28 target graphs
and 240 paired runs, with substantial smoothing/bank/delay gains alongside
regressions. The register now includes those hardware timing tables.

## Proposed selective board defaults

The [selective update](QUALIFIED_DSP_UPDATE.md) reuses the measured smoothing,
partial-bank and delay/reverb binding bodies without enabling unrelated core
caches. Both board builds now select these paths through
`SYNTHDEF_QUALIFIED_KERNELS`; the standalone Python generator keeps its legacy
reference unless explicitly requested. The new combined image is prepared and
cross-built, with hardware timing still pending. All broad experimental flags
remain off, and the connected board has not been changed.

The review below is the pre-selection baseline audit. Its unchanged-source and
historical timing claims retain that original scope.

## Complete computer-only review — 4 November 2026

All **154 native UGen types, 33 unary and 40 binary selectors** now have a
recorded review. The [register](OPTIMIZATION_REGISTER.md) links every enabled
implementation, existing FM1 path and host-only experiment to source and evidence.
Its per-fixture tables retain both faster and slower results. Desktop graph
measurements are not isolated node timings or ESP32 predictions.

The existing production paths cover 26 project-tuned and 24 inherited/reviewed
native types. New candidates cover all 104 types without an enabled individual
optimisation, plus some already-tuned types. Several candidates regress on the
desktop or show negligible gains. They remain experiments; no claim is made
that all 154 types became faster.

| Opt-in switch | Work and recorded outcome |
| --- | --- |
| `candidate_smooth` | Lag2/Lag3 coefficient reuse; OnePole/OneZero/LPZ1/HPZ1 bound block loops. Exact history, coefficients and constructor behavior retained. |
| `candidate_binary` | All 40 unchanged scalar selectors share one evaluation path. Four existing arithmetic audio loops plus 36 candidate audio loops move dispatch outside the sample loop. Changing controls retain pinned interpolation. |
| `candidate_noise` | WhiteNoise/PinkNoise/LFNoise0–2 keep exact local RNG state; hoist decoding/type dispatch. LFNoise reuses the exact length within a block; PinkNoise's guarded trailing-zero operation passes 200,000 private probes. |
| `candidate_binding` | Ten entry points serving 72 types bind graph references/rates once. Each type has a selected whole-graph native measurement, including slowdowns; extra pointer slots and stack use are recorded. |
| `candidate_routing` | A2K/K2A/DC, Delay1/2, Select, Clip, DegreeToKey and RandSeed use dedicated loops; held selectors/keys/seeds resolve once. Legal initial-rate DC/Select, signed-zero interpolation and seed ordering are covered. |
| `candidate_chaos` | Fourteen chaos models cache exact held-frequency period/slope outside the overlaid chaotic state. Recurrences/reset/interpolation remain unchanged; the offline object is 1,353 bytes smaller in the isolated comparison. |
| `candidate_core` | LFSaw/LFTri/LFPulse and Klang/Klank block loops; exact Line span/XLine ratio caches; Formant integer increments; independent Gendy constants; SinOscFB steps/feedback; Blip effective-frequency/harmonic scales. Three-sample coefficient groups are reused in BPeakEQ/BLowShelf/BHiShelf/Formlet, and Amplitude caches attack/release coefficients independently. Results vary by fixture; Klang is slightly slower in the final native run, while Line/XLine and Amplitude show larger gains. |

All switches default to **false** in both compact and FM1 profiles. An audit
compares every existing generated C/header/include against commit `368d267`;
production DSP source is byte-identical. New provenance/profile metadata changes
future build identities; it is not an identical-firmware-binary claim.
No board connection, audio playback or firmware write was used.

Both default firmware variants were cross-built and audited on the computer:
AMOLED **1,680,384 bytes**, XIAO **1,337,728 bytes**, source build
`eaf9cd626f8a`. Their compile settings, current loader inventory, pinned sine
table and configured instruction placement pass the existing build audit.
The build logs retain warnings from the unchanged engine and managed UI code;
this is not a warning-free-build claim. These builds keep all candidates off
and do not qualify candidate firmware or change the installed board baseline.
See `evidence/dsp-review-{amoled,xiao}-default-build.json`.

The final comparison enables all seven switches together against production:

- **2,451 graphs**, 64 blocks each at 44.1 kHz: **20,078,592 output samples**.
- **896 generated edge graphs**, 512 blocks at 8 / 44.1 / 48 / 192 kHz:
  **234,881,024 output samples**.
- All **254,959,616** compared stereo float samples match bit-for-bit, alongside
  recursive voice/partial state, RNG, fault flags and delay arenas. Raw scratch
  is compared after construction and rendering. Only documented new,
  otherwise-unused per-node cache fields and caller-owned pointers are normalized.
- Undefined-behavior, bounds and float-to-integer sanitizers pass. Deliberately
  invalid domains must match faults; that is separate from fault-free playback.
- Offline Xtensa compilation/stack reports cover independent and combined
  contexts. All candidates together grow the unlinked object's text from
  **174,711 to 185,746 bytes** (**11,035 bytes**). Public graph/voice/scratch
  structures remain unchanged. This is not final firmware flash/IRAM usage or
  a whole-call-stack guarantee.

The composition checks found a real signed-zero edge. The pinned discontinuous
binary path adds positive zero to held inputs between samples; held `-0.0` may
become `+0.0` after the first sample. A naive scalar fill loses that behavior,
which is audible through a subsequent `atan2` with a negative second argument.
The final candidate falls back to the pinned path in those cases. Twenty-four
composed selector/operand regressions and full scratch comparisons pass. The
before/after witness is in `evidence/dsp-signed-zero-regression.json`.
Initial operator prototype reports predate this fix and are historical; use
`dsp-operators-final-host.json` and `dsp-all-host.json` for the corrected scope.

An optional AddressSanitizer pass could not start: even an empty instrumented C
program stalls before main. Sampling the two-block probe showed recursive ASan
initialisation through dyld/malloc and a spin lock. The stalled probe was stopped;
no DSP executed in that attempt. `dsp-address-runtime.json` records this as
**unavailable**, not passed. The successful three-sanitizer comparisons above
remain separate. The initial chaos timing harness also rejected its new cache
fields before its normalization was corrected; that initial unavailable timing
record is retained as `dsp-chaos-initial-benchmark-rejected.json`.

Per-type/selector desktop timings and source hashes are in the register and
`evidence/dsp-{operators-final,binding,routing,chaos,core}-host.json`. The summary
and unchanged-default-source audit are in `evidence/dsp-review-summary.json`.
Broader suites include current local example/kernel fixtures when present, so a fresh workspace may report a different graph count; the pinned set and generated edge cases remain required. Native timing tables describe their own fixtures/source revisions; later combined
correctness does not make them hardware qualifications. Hardware measurement,
IRAM placement, call-stack margins and listening tests remain a later phase.

Reproduce the computer-only review without opening a device:

```sh
python3 host/test_dsp_candidates.py --benchmark --inventory --variants \
  --all-operator-benchmarks --build-dir build/host/dsp-operators-final \
  --output evidence/dsp-operators-final-host.json
python3 host/test_dsp_binding.py --benchmark
python3 host/test_dsp_binding.py --routing --benchmark
python3 host/test_dsp_binding.py --chaos --benchmark
python3 host/test_dsp_binding.py --core --benchmark
python3 host/test_dsp_binding.py --all
python3 host/document_optimizations.py --check
python3 host/summarize_dsp_review.py
```

The optional `python3 host/test_dsp_binding.py --all --address` first probes the
local ASan runtime and exits with an unavailable record if it cannot initialize.
None of these commands use USB, Wi-Fi, a DAC or a sound server.

## Filters

`Resonz`, `Ringz`, `LPF`, `HPF`, `RLPF`, `RHPF`, `BPF` and `BRF` have dedicated
block loops. Inputs bind once, and filter type dispatch occurs outside the
sample loop. The existing coefficient cache still updates when frequency or
the second parameter changes.

The old renderer recalculated the same interpolated coefficients for each of
three adjacent samples. The new loop calculates that group once, then applies
the unchanged recurrence to each sample in order. The last sample of a 64-frame
block is its own group. The division by 21 is retained: replacing it with a
reciprocal would change rounding. One-sample constructor/control calculations
retain their original rules, including the Resonz constructor's zero output
and Ringz's offset-zero sampling of audio-rate coefficient inputs.

## Lag and unary operators

`Lag` and `LagUD` cache independently unchanged up/down time coefficients.
`LeakDC` uses the same bound-input block path. Recurrences and interpolation
order remain unchanged; division by the power-of-two block size is an exact
reciprocal multiplication.

Pure unary operators evaluate a scalar input once per block and retain a
bitwise input/result cache across blocks. Signed zero is distinguished. Audio
inputs still evaluate each sample; common unary selectors dispatch once per
block. No lookup approximation replaces exponential, pitch, log or trig math.

Caches reuse fields otherwise unused by those node types. Graph, voice and
scratch allocations do not grow. Reconstruction clears the caches with the
voice. They belong to the voice, not recycled scratch or a global singleton.

## Computer-only next batch — 3 November 2026

This section retains the initial six-UGen/twenty-operator prototype scope. The
complete review and signed-zero correction above supersede it for current use.

`host/dsp_candidates.py` contains two independently selectable candidates.
Both are **disabled in production defaults** and have **no hardware measurements**
for this revision. No board connection, flash, network request or playback was
used for this work.

| Candidate | Applicable path |
| --- | --- |
| Lag2, Lag3 | Bound input/block recurrence, unchanged-time coefficient cache, exact power-of-two interpolation scaling after the original product |
| OnePole, OneZero | Bound input and dedicated recurrence; preserve constructor history and OnePole's special constructor equation |
| LPZ1, HPZ1 | Bound input and dedicated two-point recurrence; preserve initial sample history |
| Binary selectors 6–13 | `==`, `!=`, `<`, `>`, `<=`, `>=`, `min`, `max` |
| Binary selectors 30–38 | `ring1`–`ring4`, `difsqr`, `sumsqr`, `sqrsum`, `sqrdif`, `absdif` |
| Binary selectors 40, 41, 46 | `amclip`, `scaleneg`, `firstArg` |

The twenty binary specialisations apply when neither input has a changing
control ramp. Dispatch is outside the sample loop; scalar/scalar expressions
run once per block. Changing-control paths, including discontinuous operators'
accumulated ramps, remain untouched. Min/max retain `fminf`/`fmaxf`; no approximate
math, reassociation or reduced precision is introduced. Lag2/3 use only an
otherwise-unused `freq` field for the time cache; structure sizes do not grow.

The offline differential suite covers **610 graphs**, four sample rates and
**159,907,840 bit-identical output samples** per variant. The combined candidate,
smooth-only and binary-only variants each pass. It compares recursive voice/RNG
state, constructor scratch and fault behavior, including signed zeros,
subnormals, legal lower-rate audio inputs, negative coefficients, endpoints,
changing times, repeated prepare, reconstruction and poisoned shared scratch.
Only caller-owned control-bank pointers and the new otherwise-unused Lag2/3
time-cache field are normalized. Deliberately invalid domains must produce the
same faults; matching fault counts are not claims of fault-free valid playback.
Undefined-behavior, bounds and float-to-integer sanitizers are enabled.

A broader **1,555-graph** pass compares another **6,369,280 samples**, full
recursive state and delay arenas at 44.1 kHz, 32 blocks per graph. This covers
all pinned fixtures plus the current local example/kernel fixture set. It is
short regression coverage, not a long-soak test.

Desktop bank throughput trials favor these candidates, but are not predictions
for the ESP32. Offline Xtensa compilation succeeds with strict floating-point
flags and no double-arithmetic helper references. The candidate smoothing
function has no direct software-division helper references. The combined
renderer object text grows from **174,711 to 179,141 bytes**: **4,430 bytes** extra,
including roughly 3.1 KiB in the existing hot arithmetic function. This is an
unlinked object comparison, not final firmware flash/IRAM usage. Actual target
cycles, cache/IRAM fit and normal whole-patch timing must justify promotion.

The default compact and FM1 profiles' compiled DSP source files remain
byte-identical to commit `368d267` with both switches off. Profile/provenance
metadata records the new candidate source and disabled flags; this does not
promise an identical future firmware build ID. Historical device records remain
unchanged. See `evidence/dsp-candidates-host.json` and
`evidence/dsp-candidates-defaults.json`.

Reproduce silently:

```sh
python3 host/test_dsp_candidates.py --benchmark --inventory --variants
python3 host/document_optimizations.py --check
```

To generate an opt-in comparison source tree, without building/flashing firmware:

```sh
python3 host/engine_profile.py --profile fm1 \
  --output build/host/candidate-source/src --candidate-smooth --candidate-binary
```

The [register](OPTIMIZATION_REGISTER.md#host-only-candidates) keeps these as
host-only candidates separately from enabled production optimisations.

## MiVerb packed memory

**Experimental and disabled by default.** It matched samples/state on the host
but regressed on the XIAO: the measured MiVerb node cost increased from about
462 to 687 µs per block. The full patch rose from 1,181 to 1,405 µs. Production
retains the existing byte-wise access and ordered clamp optimization.

In the opt-in comparison variant, packed Q1.15 delay data is unchanged. Little-endian targets transfer a
16-bit word through `memcpy` rather than two byte operations. Float arena slices
are aligned and every byte offset is even. The alignment hint enables native
halfword instructions without violating C's aliasing rules. Other byte orders
retain explicit byte assembly. Quantisation, saturation, freeze, random state
and float processing remain unchanged.

The generator has independent comparison switches for filters, Lag, unary and
packed MiVerb. Production defaults must be justified by both differential
checks and ESP32 measurements; desktop timing alone is not target evidence.

## Main replacement fade

All maintenance transitions now use a separate 5 ms stereo output gate after
master FX and before user volume/PCM conversion. At 44.1 kHz the ramp contains
221 frames with exact endpoints. It has no sample-processing cost at steady
unity. The old Main remains rendered throughout fade-out, then output stays
zero through twelve 64-frame blocks to drain six 128-frame DMA buffers before
the audio owner acknowledges parking. Loading/reconstruction occurs while
parked. The next actual Main render or audible FX output starts fade-in.

The gate also suppresses preserved FX during the drain. Previously the final
PCM was faded for two blocks, but a preserved master could then reappear at full
level before DMA stopped. Existing maintenance rules still decide whether FX
state is retained or reset; this change does not add a second Main instance or
a crossfade. Loading/storage can produce a longer silent gap between ramps.

User volume is unchanged, and definition-only uploads remain uninstantiated.
Panic still stops Main/FX directly; it does not wait for a transition ramp.
Normal per-note envelopes and the existing short instance-onset fade are retained.
The gate operates on float stereo before either the AMOLED mono sink or XIAO
stereo sink, so both board targets receive the same transition behavior.

## Validation

`host/test_dsp_kernels.py` compares the optimized implementation with the original
general loops and byte-wise MiVerb memory: 100 graphs, four sample rates and
26,214,400 bit-identical samples, including changing coefficients, independent
lag times, legal scalar excitation of audio kernels, all supported unary selectors, signed zeros, constructors, repeated
prepare and voice reconstruction. Mathematical fault cases must match too.
Whole recursive voice state, RNG and delay memory are compared; only the
documented new, otherwise-unused cache fields are normalized.

The wider differential run covers 1,500 previously accepted graphs at 44.1 kHz
for 32 blocks each, including 6,144,000 additional samples. The MiVerb-specific
test covers 8,388,608 samples and 400,000 private quantiser/readback probes, with
complete voice/arena identity. Undefined-behavior, bounds and float-to-integer
sanitizers are enabled. See `evidence/dsp-kernels-host.json`,
`dsp-kernels-inventory.json` and `miverb-packed-host.json`.

`host/test_audio_transition.py` tests endpoints, monotonic ramps, stereo pairing,
interrupted fades, zero hold and bit-identical steady unity at four rates.
`host/qualify_transition.py` captures actual post-volume PCM while Main is
replaced, checks preserved-FX restarts and definition-only silence, and restores
the user's Main/FX packages, instance state, bypass and volume. This verifies
digital behavior; analogue DAC/codec clicks still require listening.

Physical timing uses `host/qualify_dsp_kernels.py`: three runs of the same graph
per fixture, 128 warm-up blocks and 1,024 timed blocks per run. The diagnostic
compares instrumented and normal renderer hashes/state, while the normal render
time excludes per-node probes. Tests are muted, run on the audio owner, and
restore saved packages/settings. These are rendering-cost measurements, not
whole-chip or worst-case real-time guarantees under arbitrary RF/display load.

The final XIAO build `cd9fc38336ae` measured:

| Fixture | Before, µs/block | After, µs/block | Less time |
| --- | ---: | ---: | ---: |
| Eight filter types | 672.88 | 277.64 | 58.7% |
| Lag/LagUD bank | 1,311.85 | 527.27 | 59.8% |
| Repeated unchanged control-rate pitch math | 364.63 | 132.99 | 63.5% |
| Eight-saw/Resonz/MiVerb block | 1,287.98 | 1,150.18 | 10.7% |

The fixtures' graph hashes match between runs. Rendering times are cycle counts
converted at the configured 240 MHz. Stochastic/oscillator state may differ
between installations. `evidence/dsp-kernels-summary.json` gives the comparison;
the before/final/packed records retain all three timing trials and per-node
results. The packed experiment is excluded from the final default.

On the final firmware, actual Main replacement capture measured a 220-frame
fall, 1,898-frame zero interval and 215-frame rise, with at most five PCM counts
between adjacent samples at the test level. Preserved-FX restart held zero for
805 frames, with a maximum seven-count step. Definition-only upload remained
inactive and silent. No audio diagnostic counters increased. These low-level
test signals and output settings are restored afterwards; they do not measure
the analogue DAC transient. An interrupted USB timing attempt required a
physical reconnect; the original package was recovered and the final run
repeated successfully. See `dsp-kernels-xiao-final-interrupted.json` and
`dsp-kernels-usb-recovery.json` for that scope.

After the final firmware was installed, the user confirmed that switching sounds
cleaner. This is listening confirmation of improvement, not a measured analogue
noise floor or a claim that every DAC/codec transition is artifact-free.
