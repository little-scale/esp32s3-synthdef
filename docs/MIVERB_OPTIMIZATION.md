# MiVerb optimisation analysis — 1 November 2026

The ordered delay-write clamp is now implemented in the generated target engine
and verified on the ESP32. The vendored engine remains unchanged. Other
prototypes remain isolated; their target cycle savings have not been measured.

## Baseline

The board's 24-UGen Saw / Resonz / MiVerb patch spends 65.12% of its profiled
node time in MiVerb, about 779 microseconds per 64-frame block at 240 MHz.
Normal whole-graph rendering takes 1,194.6 microseconds; a block at 44.1 kHz
has a 1,451.25-microsecond deadline. Per-node probes add overhead, so node times
are useful for attribution rather than exact subtraction from normal rendering.

MiVerb has eight all-pass stages, two modulated delay reads, damping and
high-pass state, wet/dry mixing and a rational output soft clip. Its delay buffer
already stores 32,768 signed 16-bit samples: 64 KiB in PSRAM. The arithmetic and
filter state are single-precision floats. No hidden double-precision loop was
found.

## Candidates, in recommended order

| Change | Verified finding | Constraint |
| --- | --- | --- |
| Replace the delay-write clamp with ordered comparisons | Ten writes per sample each call `fmaxf` and `fminf`: 882,000 calls/second at 44.1 kHz. The Xtensa object contains these calls. The candidate eliminates these per-sample calls. | Retain the existing finite-value check, fault flag and quantisation bounds. The unquantised accumulator must still be scaled exactly as before. |
| Use aligned halfword delay access | Current code assembles each sample from two byte reads and writes it with two byte stores. Explicit two-byte builtin copies with the arena's guaranteed alignment produce native 16-bit accesses. | Preserve the little-endian layout, signed conversion, saturation and 15-bit fractional scale. Do not cast the float arena to an incompatible typed pointer. |
| Bind input/output pointers per block | The original calls the generic graph-input decoder twice per sample. Valid MiVerb audio inputs are already required to be audio rate by the loader. | Keep the constructor path and mono-input duplication. |
| Inline the small delay helpers selectively | The current target emits separate `mi_ap` and `mi_write` functions. Inlining exposes constant offsets and accumulator lifetimes to the compiler. | The combined helper group's code/literal size grows from 2,304 to 3,138 bytes. Measure cache effects on the actual device. |
| Reorganise delay stages for block locality | A possible later improvement to PSRAM access and loop overhead. | Requires a new dependency analysis: the shared circular storage reuses locations across stages. Preserve feedback ordering and quantisation points. Not prototyped here. |

There are twelve delay reads and ten writes per sample. Halfword transfers can
reduce the buffer's load/store instruction count from 44 byte accesses to 22
halfword accesses per sample; this is not a promise to halve memory-bus time.
Cache-line behaviour and PSRAM latency still matter.

## What should stay unchanged

- The delay storage is already 16-bit. Reducing all DSP precision would be a
  separate algorithm change.
- Keep the output soft-clip curve and its floating-point divisions initially.
  Reciprocal approximations or arithmetic reassociation require separate error
  bounds and listening tests.
- Lower wet amount or reverb time does not reduce the current stage count.
  Even dry-only output must preserve the internal tail for later parameter changes.
- Moving the entire 64 KiB delay buffer into internal RAM does not fit the
  current Wi-Fi image's roughly 15 KiB free internal heap.
- Moving code into IRAM also spends scarce internal memory. It needs a measured
  benefit and a memory-budget check, rather than a blanket placement change.

## Silent checks

Five candidates were compared independently with the current generated engine:
clamps, halfword packing, block binding, inlining, and their combination.
Each passed 8,388,608 bit-for-bit output comparisons: **41,943,040 across all
five**. Full voice state, shared random state and every delay-buffer byte matched.

The matrix covered mono noise, stereo sine/Dust, silence and the user's saved
patch, at 8 / 44.1 / 48 / 192 kHz. Each case ran 4,096 blocks, with changing
time, wet amount, damping, high-pass, diffusion, freeze, level and frequency,
including values outside normal parameter limits. Undefined-behaviour, bounds
and float-to-integer conversion sanitizers passed. This does not establish
exhaustive equivalence for every possible floating-point input.

An isolated desktop throughput benchmark was also run five times per candidate.
It is not a forecast for the ESP32: in particular, desktop min/max operations
have a different cost from the actual Xtensa library calls. The assembly result
is stronger evidence for prioritising the clamp candidate than desktop timing.

## Remaining device experiments

The clamp result is measured below. Halfword access plus selective inlining and
block binding remain future experiments. Use the same saved graph and seed, with Wi-Fi and display enabled,
and compare normal audio-owner timing as well as the instrumented profile.
Recheck output/state/delay digests and steady DMA counters, and retain the
measured memory headroom. A 50% MiVerb speed-up would save roughly a third of
this graph's DSP time, but that is an illustrative upper-level calculation,
not a measured prediction.

Evidence: `evidence/miverb-optimization-analysis.json` and
`evidence/resonz-miverb-profile.json`. Isolated source, Xtensa assembly, native
comparison programs and timing data are under `build/host/miverb-analysis/`.

## Implemented: ordered delay-write clamp

`host/engine_profile.py` replaces the nested min/max expression only after the
existing finite-value guard. The Q1.15 bounds, quantisation, original accumulator
scaling, buffer layout, memory use and soft clip are retained. The target
`mi_write` assembly has no min/max calls.

Three muted audio-owner profiles per image used the same 24-UGen saved graph,
240 MHz clock, 44.1 kHz / 64-frame blocks, Wi-Fi and display enabled:

| Median metric | Before | After | Reduction |
| --- | ---: | ---: | ---: |
| MiVerb node | 777.58 µs | 454.40 µs | 41.56% |
| Normal whole-graph DSP | 1,174.42 µs | 864.14 µs | 26.42% |

Per-node probes add overhead, so normal whole-graph timing is the stronger
end-to-end measurement. Profiles preserve the live voice and delay state.

The production regression test (`python3 host/test_miverb.py`) compares against
the pinned clamp with every other engine adaptation held constant. It passes
8,388,608 bit-identical output samples and 400,000 direct quantiser probes,
including signed zeros, neighbouring saturation-boundary values, infinities,
NaNs, subnormals and random float bit patterns. Full voice/random state and
delay-buffer bytes match; undefined/bounds/float-cast sanitizers pass.

Fixed-seed board traces span 8,192 blocks (11.89 seconds) per image. All 5,120
sparsely captured float samples match bit-for-bit; full-duration peak and RMS
match, with no reported faults, nonfinite samples or canary failures. Thirty-one
Studio tests also pass. These results preserve the existing implementation;
they do not claim exhaustive equivalence for all inputs.

Implementation evidence: `miverb-clamp-host.json`, `miverb-clamp-device.json`,
`miverb-clamp-build.json` and `miverb-clamp-steady.json` under `evidence/`.

Normal playback with Wi-Fi/display enabled averaged **62.24%** audio budget
(63.0% maximum one-second mean, 101.7% recent individual-block peak). No DMA
event additions or new faults/write failures were observed across 20.03 measured
seconds. Minimum internal heap was 15,759 bytes; minimum free control stack
was 4,196 bytes. Occasional individual blocks can exceed their nominal period;
the observation does not establish a universal worst-case deadline guarantee.
