# DSP optimisation register

Last reviewed: **2026-11-12**. Applies to the shared AMOLED/XIAO DSP
source. This is an implementation ledger, separate from the
[support and hardware-test ledger](UGEN_SUPPORT.md).

The editable source is [dsp_optimizations.json](dsp_optimizations.json).
Regenerate with `python3 host/document_optimizations.py`; validate coverage and
the checked-in page with `python3 host/document_optimizations.py --check`.
The command checks every native type and supported operator selector against the
pinned inventory plus explicit project additions, compiled capabilities,
status/group consistency and linked file existence. It does
not rerun DSP tests or certify that a source implementation is still enabled.

## Status meanings

- **Project optimisation enabled:** a recorded project-specific change is in
  the production defaults. It does not mean every rate/input uses a faster path.
- **Inherited FM1 fast path:** an existing specialised block implementation,
  rather than a newly claimed project algorithm optimisation.
- **No enabled individual optimisation:** production retains its existing
  implementation. A reviewed computer-only candidate is linked separately;
  this does not claim that the original was slow or untuned upstream.
- **Disabled experiment:** excluded from production defaults, even if host
  numerical checks passed.
- **Experimental candidate:** an opt-in implementation with computer evidence
  and, where linked, scoped ESP32 tests. The checklist status still describes the
  production path; a candidate link does not mark it enabled.

Shared buffer reuse, code/cache placement and float32 arithmetic can benefit
many rows. They do not mark every UGen as individually optimised. Hardware
records retain their original board/build/fixture scope; an older measurement
does not automatically qualify the current image. The latest targeted tests ran
on XIAO; a complete sweep of the latest image and its physical AMOLED check
remain outstanding. See [current status](../STATUS.md).

## Coverage summary

| Category | Project optimisation enabled | Inherited FM1 fast path | No enabled individual optimisation | Experimental candidate available |
| --- | ---: | ---: | ---: | ---: |
| Native UGen types | 43 | 24 | 88 | 112 |
| Unary selectors | 33 | 0 | 0 | 0 |
| Binary selectors | 0 | 40 | 0 | 40 |

Selector totals are separate views of UnaryOpUGen/BinaryOpUGen, not additional native types. Candidate counts overlap production statuses.

Every supported native type and selector now has a recorded implementation
review: an existing enabled/inherited path, an experimental candidate, or both.
New project additions are recorded separately without claiming a speed-up.
No supported entry remains unreviewed. This does **not** mean every candidate
is faster: negative timing differences are retained below and all new candidate
switches remain off. Constructor/state/arena and raw-scratch combined checks are
in [the final offline report](../evidence/dsp-all-host.json).

## Recorded implementations

### sine-cache

**SinOsc phase-step cache — Project optimisation enabled**

Cache the exact integer phase step for unchanged initial/control-rate frequency. Audio-rate frequency retains sample-by-sample calculation.

Implementation: [host/engine_profile.py](../host/engine_profile.py)

Host verification: [evidence/comb-kernel-equivalence.json](../evidence/comb-kernel-equivalence.json)

Hardware evidence: [evidence/comb-ugen-profile-after.json](../evidence/comb-ugen-profile-after.json), [evidence/dsp-kernels-xiao-final.json](../evidence/dsp-kernels-xiao-final.json)

Qualification: Kernel equivalence is measured separately from whole-patch timings; no isolated universal SinOsc speed-up is claimed.

### bandlimited-crossfade

**Saw/Pulse crossfade fraction — Project optimisation enabled**

Replace per-sample division by the power-of-two block size with exact reciprocal multiplication; preserve the bandlimited oscillator.

Implementation: [host/engine_profile.py](../host/engine_profile.py)

Host verification: [evidence/saw-crossfade-host.json](../evidence/saw-crossfade-host.json)

Hardware evidence: [evidence/saw-crossfade-device.json](../evidence/saw-crossfade-device.json)

Qualification: The historical target timing isolates Saw in a two-Saw patch. Pulse shares the changed routine and has host coverage; no separate Pulse speed-up measurement is claimed. Blip was a regression case, not a changed loop.

### dust-rng

**Dust/Dust2 random-state locality — Project optimisation enabled**

Keep Taus88 state words local during each block, then commit once; preserve random word order.

Implementation: [host/engine_profile.py](../host/engine_profile.py)

Host verification: [evidence/comb-kernel-equivalence.json](../evidence/comb-kernel-equivalence.json)

Hardware evidence: [evidence/comb-ugen-profile-after.json](../evidence/comb-ugen-profile-after.json)

Qualification: Hardware evidence is the recorded Comb Cloud workload; not separate timing certification of every Dust2/rate combination.

### decay-coefficients

**Decay/Decay2 interpolation and coefficient reuse — Project optimisation enabled**

Use exact power-of-two block interpolation; independently cache Decay2 attack and decay coefficients. Retain compensated recurrences.

Implementation: [host/engine_profile.py](../host/engine_profile.py)

Host verification: [evidence/comb-kernel-equivalence.json](../evidence/comb-kernel-equivalence.json), [evidence/comb-kr-kernel-check.json](../evidence/comb-kr-kernel-check.json)

Hardware evidence: [evidence/comb-ugen-profile-after.json](../evidence/comb-ugen-profile-after.json), [evidence/comb-kr-live.json](../evidence/comb-kr-live.json)

Qualification: Hardware measurements cover recorded cloud patches, including the KR variant, not an isolated speed-up for every Decay layout.

### filter-blocks

**Eight filter block kernels — Project optimisation enabled**

Resonz, Ringz, LPF, HPF, RLPF, RHPF, BPF and BRF bind inputs once per block and share each existing three-sample group coefficient calculation. Preserve constructor/control rules and arithmetic order.

Implementation: [host/dsp_kernels.py](../host/dsp_kernels.py), [host/engine_profile.py](../host/engine_profile.py)

Host verification: [evidence/dsp-kernels-host.json](../evidence/dsp-kernels-host.json), [evidence/dsp-kernels-inventory.json](../evidence/dsp-kernels-inventory.json)

Hardware evidence: [evidence/dsp-kernels-xiao-final.json](../evidence/dsp-kernels-xiao-final.json), [evidence/dsp-kernels-summary.json](../evidence/dsp-kernels-summary.json)

Qualification: Latest XIAO filter fixture contains all eight types. Its aggregate saving is not the saving for each individual type or all rates.

### lag-blocks

**Lag/LagUD/LeakDC block kernels — Project optimisation enabled**

Bind inputs once. Lag/LagUD cache unchanged smoothing-time coefficients independently; LeakDC uses the streamlined recurrence loop without that exponential time cache.

Implementation: [host/dsp_kernels.py](../host/dsp_kernels.py), [host/engine_profile.py](../host/engine_profile.py)

Host verification: [evidence/dsp-kernels-host.json](../evidence/dsp-kernels-host.json), [evidence/dsp-kernels-inventory.json](../evidence/dsp-kernels-inventory.json)

Hardware evidence: [evidence/dsp-kernels-xiao-final.json](../evidence/dsp-kernels-xiao-final.json), [evidence/dsp-kernels-summary.json](../evidence/dsp-kernels-summary.json)

Qualification: Latest physical Lag fixture contains Lag and LagUD. LeakDC has historical broad-sweep hardware evidence and current host equivalence, but no dedicated current-build hardware timing in this fixture.

### miverb-clamp

**MiVerb ordered delay-write clamp — Project optimisation enabled**

Replace fminf/fmaxf calls after the finite-value guard with ordered comparisons; retain Q1.15 delay storage, saturation, quantisation and float processing. The proposed qualified-kernel board default also binds MiVerb graph inputs once per block; its arithmetic is unchanged.

Implementation: [host/engine_profile.py](../host/engine_profile.py), [host/qualified_kernels.py](../host/qualified_kernels.py)

Host verification: [evidence/miverb-clamp-host.json](../evidence/miverb-clamp-host.json), [evidence/qualified-kernels-review.json](../evidence/qualified-kernels-review.json)

Hardware evidence: [evidence/miverb-clamp-device.json](../evidence/miverb-clamp-device.json), [evidence/dsp-kernels-xiao-final.json](../evidence/dsp-kernels-xiao-final.json)

Qualification: Historical isolated-node and whole-patch timings are retained. Latest full-patch measurements include MiVerb but do not isolate a new clamp change. The new combined default still awaits target validation; the measured input-binding variant is recorded separately.

### rings-placement

**MiRings1–6 memory placement and startup — Project optimisation enabled**

Keep selected hot Rings functions in instruction RAM and remove duplicate arena clearing at initialisation. Production retains the selected PSRAM arena; internal-arena experiments are not claimed enabled.

Implementation: [host/engine_profile.py](../host/engine_profile.py), [firmware/components/synthdef_engine/hot_data.lf](../firmware/components/synthdef_engine/hot_data.lf)

Host verification: [evidence/rings-clear-identity.json](../evidence/rings-clear-identity.json), [evidence/rings-target-oracle.json](../evidence/rings-target-oracle.json)

Hardware evidence: [evidence/rings-optimization.json](../evidence/rings-optimization.json), [evidence/rings-regression-device.json](../evidence/rings-regression-device.json)

Qualification: Placement/startup optimisation, not a changed resonator algorithm. Model and moving-control costs differ; historical overruns remain documented.

### unary-blocks

**UnaryOpUGen cache and block dispatch — Project optimisation enabled**

All 33 supported selectors cache bitwise-unchanged scalar input/results, distinguishing signed zero. Twelve common audio selectors dispatch once per block; other audio selectors retain the original per-sample unary evaluator. No transcendental approximation.

Implementation: [host/dsp_kernels.py](../host/dsp_kernels.py), [host/engine_profile.py](../host/engine_profile.py)

Host verification: [evidence/dsp-kernels-host.json](../evidence/dsp-kernels-host.json), [evidence/dsp-kernels-inventory.json](../evidence/dsp-kernels-inventory.json)

Hardware evidence: [evidence/dsp-kernels-xiao-final.json](../evidence/dsp-kernels-xiao-final.json), [evidence/dsp-kernels-summary.json](../evidence/dsp-kernels-summary.json)

Qualification: Latest hardware unary fixture measures repeated control-rate pitch math, not every selector/path. All selectors/rates have older broad-sweep hardware evidence; current all-selector differential checks are host-side.

### inherited-envelope

**EnvGen block renderer — Inherited FM1 fast path**

Existing FM1 fast_envelope path with bound inputs and segment processing. No newly isolated project-specific envelope algorithm speed-up claimed.

Implementation: [upstream/fm1-synthdef/synthdef-engine/src/fm_render.c](../upstream/fm1-synthdef/synthdef-engine/src/fm_render.c)

Host verification: [evidence/fm1-fixed-reference.json](../evidence/fm1-fixed-reference.json)

Hardware evidence: [evidence/extended-validation.json](../evidence/extended-validation.json)

Qualification: Historical hardware tests include envelope/rate fixtures; not a current per-UGen before/after performance claim.

### inherited-pan

**Pan2 cached block gains — Inherited FM1 fast path**

Existing FM1 fast_pan path when position input is not audio rate; audio-rate position retains the general path.

Implementation: [upstream/fm1-synthdef/synthdef-engine/src/fm_fast.inc](../upstream/fm1-synthdef/synthdef-engine/src/fm_fast.inc), [upstream/fm1-synthdef/synthdef-engine/src/fm_render.c](../upstream/fm1-synthdef/synthdef-engine/src/fm_render.c)

Host verification: [evidence/fm1-fixed-reference.json](../evidence/fm1-fixed-reference.json)

Hardware evidence: [evidence/extended-validation.json](../evidence/extended-validation.json)

Qualification: Path depends on input rate. Latest eight-Saw fixture also uses Pan2; no new isolated panner speed-up is claimed.

### inherited-arithmetic

**BinaryOpUGen/MulAdd/Sum3/Sum4 block arithmetic — Inherited FM1 fast path**

Existing FM1 bound-input arithmetic paths. Addition, subtraction, multiplication and floating division have direct common-rate loops; other binary selectors preserve the original evaluator and control-ramp semantics.

Implementation: [upstream/fm1-synthdef/synthdef-engine/src/fm_fast.inc](../upstream/fm1-synthdef/synthdef-engine/src/fm_fast.inc), [upstream/fm1-synthdef/synthdef-engine/src/fm_render.c](../upstream/fm1-synthdef/synthdef-engine/src/fm_render.c)

Host verification: [evidence/fm1-fixed-reference.json](../evidence/fm1-fixed-reference.json)

Hardware evidence: [evidence/extended-validation.json](../evidence/extended-validation.json)

Qualification: All 40 binary selectors have historical initial/control/audio hardware captures. This records an inherited block framework, not a dedicated new optimisation of every selector.

### inherited-initial-cache

**Existing initial-rate result caching — Inherited FM1 fast path**

SampleRate, SampleDur, ControlRate, ControlDur, BlockSize, RadiansPerSample, Rand, ExpRand, MaxLocalBufs, LocalBuf and SetBuf use initial-rate construction and per-voice cached result restoration. Their math/RNG/declaration handling does not run per audio sample. No new arithmetic optimisation or measured speed-up is claimed; removing construction or reseeding would change semantics.

Implementation: [upstream/fm1-synthdef/synthdef-engine/src/fm_render.c](../upstream/fm1-synthdef/synthdef-engine/src/fm_render.c), [upstream/fm1-synthdef/synthdef-engine/src/fm_load.c](../upstream/fm1-synthdef/synthdef-engine/src/fm_load.c)

Host verification: [evidence/fm1-fixed-reference.json](../evidence/fm1-fixed-reference.json), [evidence/dsp-binding-host.json](../evidence/dsp-binding-host.json)

Hardware evidence: [evidence/extended-validation.json](../evidence/extended-validation.json)

Qualification: Reviewed on 4 November 2026. Metadata/table setup and per-instance random generation remain necessary. Historical hardware coverage is separate from this computer-only review.

### inherited-control-bank

**Existing batched control and trigger banks — Inherited FM1 fast path**

Control, TrigControl and LagControl have the existing one-pass output-bank renderer. LagControl computes its coefficient at initialisation and retains smoothing state; TrigControl clears triggers per control calculation. No new project speed-up is claimed.

Implementation: [upstream/fm1-synthdef/synthdef-engine/src/fm_render.c](../upstream/fm1-synthdef/synthdef-engine/src/fm_render.c)

Host verification: [evidence/fm1-fixed-reference.json](../evidence/fm1-fixed-reference.json), [evidence/dsp-binding-host.json](../evidence/dsp-binding-host.json)

Hardware evidence: [evidence/extended-validation.json](../evidence/extended-validation.json)

Qualification: Reviewed on 4 November 2026. Preserve trigger clearing, per-channel smoothing and initial/control-rate behavior. These paths are already batched outside the generic sample switch.

### inherited-bus-blocks

**Existing bounded audio/control bus block loops — Inherited FM1 fast path**

In.ar and Out.ar already validate the bus once per node and copy/deinterleave or accumulate complete channel blocks using stable pointers. In.kr is the project control-snapshot extension and reads once per control calculation. Required sample checks, interleaving and ordered mixing remain unchanged; no new performance change is claimed.

Implementation: [upstream/fm1-synthdef/synthdef-engine/src/fm_render.c](../upstream/fm1-synthdef/synthdef-engine/src/fm_render.c), [host/engine_profile.py](../host/engine_profile.py)

Host verification: [evidence/control-buses-host.json](../evidence/control-buses-host.json), [evidence/dsp-binding-host.json](../evidence/dsp-binding-host.json)

Hardware evidence: [evidence/extended-validation.json](../evidence/extended-validation.json)

Qualification: Reviewed on 4 November 2026. The ledger records the existing batched paths, not an additional measured speed-up; general audio-bus expansion or dropping finite checks would change the supported contract.

### inherited-freeverb

**Existing generated FreeVerb block kernels — Inherited FM1 fast path**

FreeVerb/FreeVerb2 already bind audio pointers and block-held mix/room/damping once, keep recurrence state local across the block and use generated unrolled comb/allpass loops. Their sample loop does not repeatedly decode graph inputs. No new algorithm or timing saving is claimed.

Implementation: [upstream/fm1-synthdef/synthdef-engine/src/fm_freeverb.inc](../upstream/fm1-synthdef/synthdef-engine/src/fm_freeverb.inc), [upstream/fm1-synthdef/synthdef-engine/src/fm_reverb.inc](../upstream/fm1-synthdef/synthdef-engine/src/fm_reverb.inc)

Host verification: [evidence/fm1-fixed-reference.json](../evidence/fm1-fixed-reference.json), [evidence/dsp-binding-host.json](../evidence/dsp-binding-host.json)

Hardware evidence: [evidence/extended-validation.json](../evidence/extended-validation.json)

Qualification: Reviewed on 4 November 2026. A further redesign would need dependency/cache profiling and memory-layout analysis; the existing efficient block implementation is retained in this computer-only pass.

### qualified-smoothing

**Six additional smoothing block kernels — Project optimisation enabled**

Reuse the measured Lag2/Lag3/OnePole/OneZero/LPZ1/HPZ1 arithmetic bodies. Bind excitation and held coefficients once; preserve constructor histories, coefficient interpolation, faults and cache ownership. Dispatch after existing fast exits.

Implementation: [host/qualified_kernels.py](../host/qualified_kernels.py), [host/engine_profile.py](../host/engine_profile.py)

Host verification: [evidence/qualified-kernels-host.json](../evidence/qualified-kernels-host.json), [evidence/qualified-kernels-review.json](../evidence/qualified-kernels-review.json)

Hardware evidence: [evidence/dsp-seeded-xiao-smooth.json](../evidence/dsp-seeded-xiao-smooth.json), [evidence/dsp-combined-xiao-3eeb84-summary.json](../evidence/dsp-combined-xiao-3eeb84-summary.json), [evidence/dsp-combined-xiao-3eeb84-final.json](../evidence/dsp-combined-xiao-3eeb84-final.json)

Qualification: Enabled in the proposed board-build defaults through SYNTHDEF_QUALIFIED_KERNELS. Individual candidate measurements exist; the new combined image has native equality and cross-build checks but still needs a same-board hardware check. Existing deployed firmware was not changed. Combined-image follow-up on XIAO-3eeb84 (12 November): 28 fixed-seed graphs/three trials match output and RNG; selected timing gains and unchanged isolated oscillator slowdowns retained. A 30-second Main/FX control/capture check passes. Physical AMOLED and broad coverage remain pending.

### qualified-banks

**Klang/Klank partial-bank block loops — Project optimisation enabled**

Separate the fixed-bank sample loops and bind Klank excitation once. Preserve partial order, initial parameters and constructor reset behavior; insert dispatch at the old bank fallback.

Implementation: [host/qualified_kernels.py](../host/qualified_kernels.py), [host/engine_profile.py](../host/engine_profile.py)

Host verification: [evidence/qualified-kernels-host.json](../evidence/qualified-kernels-host.json), [evidence/qualified-kernels-review.json](../evidence/qualified-kernels-review.json)

Hardware evidence: [evidence/dsp-seeded-xiao-core.json](../evidence/dsp-seeded-xiao-core.json), [evidence/dsp-combined-xiao-3eeb84-summary.json](../evidence/dsp-combined-xiao-3eeb84-summary.json), [evidence/dsp-combined-xiao-3eeb84-final.json](../evidence/dsp-combined-xiao-3eeb84-final.json)

Qualification: Enabled in the proposed board-build defaults through SYNTHDEF_QUALIFIED_KERNELS. Individual candidate measurements exist; the new combined image has native equality and cross-build checks but still needs a same-board hardware check. Existing deployed firmware was not changed. Combined-image follow-up on XIAO-3eeb84 (12 November): 28 fixed-seed graphs/three trials match output and RNG; selected timing gains and unchanged isolated oscillator slowdowns retained. A 30-second Main/FX control/capture check passes. Physical AMOLED and broad coverage remain pending.

### qualified-delay-binding

**Delay and MiVerb input-reference binding — Project optimisation enabled**

Bind graph references once per block only in delay_render and render_miverb. Preserve all read indexing, interpolation, arithmetic and finite-value guards. MiVerb keeps its existing ordered-clamp primary entry too.

Implementation: [host/qualified_kernels.py](../host/qualified_kernels.py), [host/engine_profile.py](../host/engine_profile.py)

Host verification: [evidence/qualified-kernels-host.json](../evidence/qualified-kernels-host.json), [evidence/qualified-kernels-review.json](../evidence/qualified-kernels-review.json)

Hardware evidence: [evidence/dsp-seeded-xiao-binding-delay.json](../evidence/dsp-seeded-xiao-binding-delay.json), [evidence/dsp-seeded-xiao-binding.json](../evidence/dsp-seeded-xiao-binding.json), [evidence/dsp-combined-xiao-3eeb84-summary.json](../evidence/dsp-combined-xiao-3eeb84-summary.json), [evidence/dsp-combined-xiao-3eeb84-final.json](../evidence/dsp-combined-xiao-3eeb84-final.json)

Qualification: Enabled in the proposed board-build defaults through SYNTHDEF_QUALIFIED_KERNELS. Individual candidate measurements exist; the new combined image has native equality and cross-build checks but still needs a same-board hardware check. Existing deployed firmware was not changed. Combined-image follow-up on XIAO-3eeb84 (12 November): 28 fixed-seed graphs/three trials match output and RNG; selected timing gains and unchanged isolated oscillator slowdowns retained. A 30-second Main/FX control/capture check passes. Physical AMOLED and broad coverage remain pending.

## Native UGen checklist

| UGen | Status | Work |
| --- | --- | --- |
| A2K | No enabled individual optimisation | —; [experimental candidate](#candidate-routing) |
| AllpassC | Project optimisation enabled | [qualified-delay-binding](#qualified-delay-binding); [experimental candidate](#candidate-binding) |
| AllpassL | Project optimisation enabled | [qualified-delay-binding](#qualified-delay-binding); [experimental candidate](#candidate-binding) |
| AllpassN | Project optimisation enabled | [qualified-delay-binding](#qualified-delay-binding); [experimental candidate](#candidate-binding) |
| Amplitude | No enabled individual optimisation | —; [experimental candidate](#candidate-binding), [experimental candidate](#candidate-core) |
| BHiShelf | No enabled individual optimisation | —; [experimental candidate](#candidate-binding), [experimental candidate](#candidate-core) |
| BLowShelf | No enabled individual optimisation | —; [experimental candidate](#candidate-binding), [experimental candidate](#candidate-core) |
| BPF | Project optimisation enabled | [filter-blocks](#filter-blocks) |
| BPeakEQ | No enabled individual optimisation | —; [experimental candidate](#candidate-binding), [experimental candidate](#candidate-core) |
| BRF | Project optimisation enabled | [filter-blocks](#filter-blocks) |
| Balance2 | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| BinaryOpUGen | Inherited FM1 fast path | [inherited-arithmetic](#inherited-arithmetic); [experimental candidate](#candidate-binary) |
| Blip | No enabled individual optimisation | —; [experimental candidate](#candidate-binding), [experimental candidate](#candidate-core) |
| BlockSize | Inherited FM1 fast path | [inherited-initial-cache](#inherited-initial-cache) |
| BrownNoise | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| Clip | No enabled individual optimisation | —; [experimental candidate](#candidate-routing) |
| ClipNoise | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| CoinGate | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| CombC | Project optimisation enabled | [qualified-delay-binding](#qualified-delay-binding); [experimental candidate](#candidate-binding) |
| CombL | Project optimisation enabled | [qualified-delay-binding](#qualified-delay-binding); [experimental candidate](#candidate-binding) |
| CombN | Project optimisation enabled | [qualified-delay-binding](#qualified-delay-binding); [experimental candidate](#candidate-binding) |
| Control | Inherited FM1 fast path | [inherited-control-bank](#inherited-control-bank) |
| ControlDur | Inherited FM1 fast path | [inherited-initial-cache](#inherited-initial-cache) |
| ControlRate | Inherited FM1 fast path | [inherited-initial-cache](#inherited-initial-cache) |
| Crackle | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| CuspL | No enabled individual optimisation | —; [experimental candidate](#candidate-chaos) |
| CuspN | No enabled individual optimisation | —; [experimental candidate](#candidate-chaos) |
| DC | No enabled individual optimisation | —; [experimental candidate](#candidate-routing) |
| Decay | Project optimisation enabled | [decay-coefficients](#decay-coefficients) |
| Decay2 | Project optimisation enabled | [decay-coefficients](#decay-coefficients) |
| DegreeToKey | No enabled individual optimisation | —; [experimental candidate](#candidate-routing) |
| Delay1 | No enabled individual optimisation | —; [experimental candidate](#candidate-routing) |
| Delay2 | No enabled individual optimisation | —; [experimental candidate](#candidate-routing) |
| DelayC | Project optimisation enabled | [qualified-delay-binding](#qualified-delay-binding); [experimental candidate](#candidate-binding) |
| DelayL | Project optimisation enabled | [qualified-delay-binding](#qualified-delay-binding); [experimental candidate](#candidate-binding) |
| DelayN | Project optimisation enabled | [qualified-delay-binding](#qualified-delay-binding); [experimental candidate](#candidate-binding) |
| Dust | Project optimisation enabled | [dust-rng](#dust-rng) |
| Dust2 | Project optimisation enabled | [dust-rng](#dust-rng) |
| EnvGen | Inherited FM1 fast path | [inherited-envelope](#inherited-envelope) |
| ExpRand | Inherited FM1 fast path | [inherited-initial-cache](#inherited-initial-cache) |
| FBSineC | No enabled individual optimisation | —; [experimental candidate](#candidate-chaos) |
| FBSineL | No enabled individual optimisation | —; [experimental candidate](#candidate-chaos) |
| FBSineN | No enabled individual optimisation | —; [experimental candidate](#candidate-chaos) |
| Fold | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| Formant | No enabled individual optimisation | —; [experimental candidate](#candidate-core) |
| Formlet | No enabled individual optimisation | —; [experimental candidate](#candidate-binding), [experimental candidate](#candidate-core) |
| FreeVerb | Inherited FM1 fast path | [inherited-freeverb](#inherited-freeverb) |
| FreeVerb2 | Inherited FM1 fast path | [inherited-freeverb](#inherited-freeverb) |
| FreqShift | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| Gate | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| Gendy1 | No enabled individual optimisation | —; [experimental candidate](#candidate-core) |
| Gendy2 | No enabled individual optimisation | —; [experimental candidate](#candidate-core) |
| Gendy3 | No enabled individual optimisation | —; [experimental candidate](#candidate-core) |
| GrayNoise | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| HPF | Project optimisation enabled | [filter-blocks](#filter-blocks) |
| HPZ1 | Project optimisation enabled | [qualified-smoothing](#qualified-smoothing); [experimental candidate](#candidate-smoothing), [experimental candidate](#candidate-binding) |
| Hasher | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| HenonC | No enabled individual optimisation | —; [experimental candidate](#candidate-chaos) |
| HenonL | No enabled individual optimisation | —; [experimental candidate](#candidate-chaos) |
| HenonN | No enabled individual optimisation | —; [experimental candidate](#candidate-chaos) |
| Impulse | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| In | Inherited FM1 fast path | [inherited-bus-blocks](#inherited-bus-blocks) |
| K2A | No enabled individual optimisation | —; [experimental candidate](#candidate-routing) |
| Klang | Project optimisation enabled | [qualified-banks](#qualified-banks); [experimental candidate](#candidate-core) |
| Klank | Project optimisation enabled | [qualified-banks](#qualified-banks); [experimental candidate](#candidate-core) |
| LFClipNoise | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| LFCub | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| LFDClipNoise | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| LFDNoise0 | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| LFDNoise1 | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| LFDNoise3 | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| LFNoise0 | No enabled individual optimisation | —; [experimental candidate](#candidate-noise) |
| LFNoise1 | No enabled individual optimisation | —; [experimental candidate](#candidate-noise) |
| LFNoise2 | No enabled individual optimisation | —; [experimental candidate](#candidate-noise) |
| LFPar | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| LFPulse | No enabled individual optimisation | —; [experimental candidate](#candidate-core) |
| LFSaw | No enabled individual optimisation | —; [experimental candidate](#candidate-core) |
| LFTri | No enabled individual optimisation | —; [experimental candidate](#candidate-core) |
| LPF | Project optimisation enabled | [filter-blocks](#filter-blocks) |
| LPZ1 | Project optimisation enabled | [qualified-smoothing](#qualified-smoothing); [experimental candidate](#candidate-smoothing), [experimental candidate](#candidate-binding) |
| Lag | Project optimisation enabled | [lag-blocks](#lag-blocks) |
| Lag2 | Project optimisation enabled | [qualified-smoothing](#qualified-smoothing); [experimental candidate](#candidate-smoothing), [experimental candidate](#candidate-binding) |
| Lag3 | Project optimisation enabled | [qualified-smoothing](#qualified-smoothing); [experimental candidate](#candidate-smoothing), [experimental candidate](#candidate-binding) |
| LagControl | Inherited FM1 fast path | [inherited-control-bank](#inherited-control-bank) |
| LagUD | Project optimisation enabled | [lag-blocks](#lag-blocks) |
| Latch | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| LatoocarfianC | No enabled individual optimisation | —; [experimental candidate](#candidate-chaos) |
| LatoocarfianL | No enabled individual optimisation | —; [experimental candidate](#candidate-chaos) |
| LatoocarfianN | No enabled individual optimisation | —; [experimental candidate](#candidate-chaos) |
| LeakDC | Project optimisation enabled | [lag-blocks](#lag-blocks) |
| Limiter | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| LinExp | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| LinXFade2 | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| Line | No enabled individual optimisation | —; [experimental candidate](#candidate-core) |
| LocalBuf | Inherited FM1 fast path | [inherited-initial-cache](#inherited-initial-cache) |
| Logistic | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| LorenzL | No enabled individual optimisation | —; [experimental candidate](#candidate-chaos) |
| MaxLocalBufs | Inherited FM1 fast path | [inherited-initial-cache](#inherited-initial-cache) |
| MiMu | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| MiRings1 | Project optimisation enabled | [rings-placement](#rings-placement); [experimental candidate](#candidate-binding) |
| MiRings2 | Project optimisation enabled | [rings-placement](#rings-placement); [experimental candidate](#candidate-binding) |
| MiRings3 | Project optimisation enabled | [rings-placement](#rings-placement); [experimental candidate](#candidate-binding) |
| MiRings4 | Project optimisation enabled | [rings-placement](#rings-placement); [experimental candidate](#candidate-binding) |
| MiRings5 | Project optimisation enabled | [rings-placement](#rings-placement); [experimental candidate](#candidate-binding) |
| MiRings6 | Project optimisation enabled | [rings-placement](#rings-placement); [experimental candidate](#candidate-binding) |
| MiVerb | Project optimisation enabled | [miverb-clamp](#miverb-clamp); [experimental candidate](#candidate-binding) |
| MoogFF | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| MulAdd | Inherited FM1 fast path | [inherited-arithmetic](#inherited-arithmetic) |
| OnePole | Project optimisation enabled | [qualified-smoothing](#qualified-smoothing); [experimental candidate](#candidate-smoothing), [experimental candidate](#candidate-binding) |
| OneZero | Project optimisation enabled | [qualified-smoothing](#qualified-smoothing); [experimental candidate](#candidate-smoothing), [experimental candidate](#candidate-binding) |
| Out | Inherited FM1 fast path | [inherited-bus-blocks](#inherited-bus-blocks) |
| Pan2 | Inherited FM1 fast path | [inherited-pan](#inherited-pan) |
| Phasor | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| PinkNoise | No enabled individual optimisation | —; [experimental candidate](#candidate-noise) |
| Pluck | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| Pulse | Project optimisation enabled | [bandlimited-crossfade](#bandlimited-crossfade) |
| PulseCount | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| PulseDivider | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| RHPF | Project optimisation enabled | [filter-blocks](#filter-blocks) |
| RLPF | Project optimisation enabled | [filter-blocks](#filter-blocks) |
| RadiansPerSample | Inherited FM1 fast path | [inherited-initial-cache](#inherited-initial-cache) |
| Rand | Inherited FM1 fast path | [inherited-initial-cache](#inherited-initial-cache) |
| RandSeed | No enabled individual optimisation | —; [experimental candidate](#candidate-routing) |
| Resonz | Project optimisation enabled | [filter-blocks](#filter-blocks) |
| Ringz | Project optimisation enabled | [filter-blocks](#filter-blocks) |
| SampleDur | Inherited FM1 fast path | [inherited-initial-cache](#inherited-initial-cache) |
| SampleRate | Inherited FM1 fast path | [inherited-initial-cache](#inherited-initial-cache) |
| Saw | Project optimisation enabled | [bandlimited-crossfade](#bandlimited-crossfade) |
| Select | No enabled individual optimisation | —; [experimental candidate](#candidate-routing) |
| SetBuf | Inherited FM1 fast path | [inherited-initial-cache](#inherited-initial-cache) |
| SetResetFF | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| SinOsc | Project optimisation enabled | [sine-cache](#sine-cache) |
| SinOscFB | No enabled individual optimisation | —; [experimental candidate](#candidate-binding), [experimental candidate](#candidate-core) |
| Slew | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| StandardL | No enabled individual optimisation | —; [experimental candidate](#candidate-chaos) |
| StandardN | No enabled individual optimisation | —; [experimental candidate](#candidate-chaos) |
| Stepper | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| Sum3 | Inherited FM1 fast path | [inherited-arithmetic](#inherited-arithmetic) |
| Sum4 | Inherited FM1 fast path | [inherited-arithmetic](#inherited-arithmetic) |
| SyncSaw | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| TDelay | No enabled individual optimisation | New implementation; see project additions below |
| TExpRand | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| TIRand | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| TRand | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| TWindex | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| ToggleFF | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| Trig | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| Trig1 | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| TrigControl | Inherited FM1 fast path | [inherited-control-bank](#inherited-control-bank) |
| UnaryOpUGen | Project optimisation enabled | [unary-blocks](#unary-blocks) |
| VarSaw | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| WhiteNoise | No enabled individual optimisation | —; [experimental candidate](#candidate-noise) |
| Wrap | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| XFade2 | No enabled individual optimisation | —; [experimental candidate](#candidate-binding) |
| XLine | No enabled individual optimisation | —; [experimental candidate](#candidate-core) |

## Project additions

**TDelay: new implementation; no individual speed-up claimed.** Audio/control-rate trigger delay. Reuses per-node countdown and previous-trigger state; no delay arena or dynamic allocation. Exact SC pulse timing tested in legacy/qualified/dedicated-buffer modes. Six selected XIAO PCM timing cases pass (100,588 checked frames); physical AMOLED and isolated performance measurements remain pending.

Implementation: [host/engine_profile.py](../host/engine_profile.py)

Host verification: [evidence/tdelay-host.json](../evidence/tdelay-host.json)

Hardware evidence: [evidence/tdelay-xiao-3eeb84.json](../evidence/tdelay-xiao-3eeb84.json)

## Unary operator checklist

| Selector | Operation | Status | Applicable path |
| ---: | --- | --- | --- |
| 0 | `neg` | Project optimisation enabled | Scalar cache; dedicated audio block loop |
| 5 | `abs` | Project optimisation enabled | Scalar cache; dedicated audio block loop |
| 8 | `ceil` | Project optimisation enabled | Scalar cache; dedicated audio block loop |
| 9 | `floor` | Project optimisation enabled | Scalar cache; dedicated audio block loop |
| 10 | `frac` | Project optimisation enabled | Scalar cache; dedicated audio block loop |
| 11 | `sign` | Project optimisation enabled | Scalar cache; dedicated audio block loop |
| 12 | `squared` | Project optimisation enabled | Scalar cache; dedicated audio block loop |
| 13 | `cubed` | Project optimisation enabled | Scalar cache; dedicated audio block loop |
| 14 | `sqrt` | Project optimisation enabled | Scalar cache; dedicated audio block loop |
| 15 | `exp` | Project optimisation enabled | Scalar cache; original audio evaluator |
| 16 | `reciprocal` | Project optimisation enabled | Scalar cache; dedicated audio block loop |
| 17 | `midicps` | Project optimisation enabled | Scalar cache; original audio evaluator |
| 18 | `cpsmidi` | Project optimisation enabled | Scalar cache; original audio evaluator |
| 19 | `midiratio` | Project optimisation enabled | Scalar cache; original audio evaluator |
| 20 | `ratiomidi` | Project optimisation enabled | Scalar cache; original audio evaluator |
| 21 | `dbamp` | Project optimisation enabled | Scalar cache; original audio evaluator |
| 22 | `ampdb` | Project optimisation enabled | Scalar cache; original audio evaluator |
| 23 | `octcps` | Project optimisation enabled | Scalar cache; original audio evaluator |
| 24 | `cpsoct` | Project optimisation enabled | Scalar cache; original audio evaluator |
| 25 | `log` | Project optimisation enabled | Scalar cache; original audio evaluator |
| 26 | `log2` | Project optimisation enabled | Scalar cache; original audio evaluator |
| 27 | `log10` | Project optimisation enabled | Scalar cache; original audio evaluator |
| 28 | `sin` | Project optimisation enabled | Scalar cache; original audio evaluator |
| 29 | `cos` | Project optimisation enabled | Scalar cache; original audio evaluator |
| 30 | `tan` | Project optimisation enabled | Scalar cache; original audio evaluator |
| 31 | `asin` | Project optimisation enabled | Scalar cache; original audio evaluator |
| 32 | `acos` | Project optimisation enabled | Scalar cache; original audio evaluator |
| 33 | `atan` | Project optimisation enabled | Scalar cache; original audio evaluator |
| 34 | `sinh` | Project optimisation enabled | Scalar cache; original audio evaluator |
| 35 | `cosh` | Project optimisation enabled | Scalar cache; original audio evaluator |
| 36 | `tanh` | Project optimisation enabled | Scalar cache; original audio evaluator |
| 42 | `distort` | Project optimisation enabled | Scalar cache; dedicated audio block loop |
| 43 | `softclip` | Project optimisation enabled | Scalar cache; dedicated audio block loop |

## Binary operator checklist

| Selector | Operation | Status | Applicable path |
| ---: | --- | --- | --- |
| 0 | `+` | Inherited FM1 fast path | Direct common-rate arithmetic path when applicable; preserve ramps; [experimental candidate](#candidate-binary) |
| 1 | `-` | Inherited FM1 fast path | Direct common-rate arithmetic path when applicable; preserve ramps; [experimental candidate](#candidate-binary) |
| 2 | `*` | Inherited FM1 fast path | Direct common-rate arithmetic path when applicable; preserve ramps; [experimental candidate](#candidate-binary) |
| 3 | `div (floor integer division)` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 4 | `/` | Inherited FM1 fast path | Direct common-rate arithmetic path when applicable; preserve ramps; [experimental candidate](#candidate-binary) |
| 5 | `mod` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 6 | `==` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 7 | `!=` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 8 | `<` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 9 | `>` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 10 | `<=` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 11 | `>=` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 12 | `min` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 13 | `max` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 17 | `lcm` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 18 | `gcd` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 19 | `round` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 20 | `roundUp` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 21 | `trunc (floor quantization)` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 22 | `atan2` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 23 | `hypot` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 24 | `hypotApx` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 25 | `pow (signed)` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 30 | `ring1` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 31 | `ring2` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 32 | `ring3` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 33 | `ring4` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 34 | `difsqr` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 35 | `sumsqr` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 36 | `sqrsum` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 37 | `sqrdif` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 38 | `absdif` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 39 | `thresh` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 40 | `amclip` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 41 | `scaleneg` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 42 | `clip2` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 43 | `excess` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 44 | `fold2` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 45 | `wrap2` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |
| 46 | `firstArg` | Inherited FM1 fast path | Inherited bound-input framework; original selector evaluator; [experimental candidate](#candidate-binary) |

<a id="host-only-candidates"></a>

## Experimental candidates

### candidate-smoothing

**Lag2/Lag3/OnePole/OneZero/LPZ1/HPZ1 block loops (experimental; disabled by default).** Bind inputs and choose the recurrence once per block. Lag2/3 cache the time coefficient in otherwise-unused freq state and retain multiply-then-scale interpolation order. Preserve OnePole constructor behavior, OneZero/LPZ1/HPZ1 initial history and coefficient-domain faults. Opt in with candidate_smooth=True; selected-layout hardware evidence is linked below. Selected bodies are now reused by the separate SYNTHDEF_QUALIFIED_KERNELS board-build option; this broad experimental flag remains off.

Implementation: [host/dsp_candidates.py](../host/dsp_candidates.py), [host/engine_profile.py](../host/engine_profile.py)

Host verification: [evidence/dsp-operators-final-host.json](../evidence/dsp-operators-final-host.json), [evidence/dsp-all-host.json](../evidence/dsp-all-host.json)

Hardware evidence: [evidence/dsp-qa-xiao-summary.json](../evidence/dsp-qa-xiao-summary.json), [evidence/dsp-seeded-xiao-summary.json](../evidence/dsp-seeded-xiao-summary.json)

Hardware qualification: Selected-layout 50-case replay plus fixed-seed XIAO profiling where applicable; normal/instrumented state checks and cross-image audio/RNG equality. Hardware timings are scoped whole-graph results, not full-rate/type qualification or a production promotion. Native types observed: HPZ1, LPZ1, Lag2, Lag3, OnePole, OneZero. Binary selectors observed: none.

XIAO fixed-seed measurements, 44.1 kHz / 64 frames, three trials per whole test graph. Each graph contains eight copies of the named smoothing UGen plus shared excitation/mixing. Negative percentages indicate a slowdown.

| Test graph | Baseline, µs/block | Candidate, µs/block | Less target DSP time |
| --- | ---: | ---: | ---: |
| Lag2 | 509.10 | 186.23 | 63.42% |
| Lag3 | 549.65 | 211.86 | 61.46% |
| OnePole | 443.95 | 179.33 | 59.61% |
| OneZero | 443.89 | 166.01 | 62.60% |
| LPZ1 | 270.07 | 127.55 | 52.77% |
| HPZ1 | 269.83 | 127.39 | 52.79% |

Desktop-only 32-node bank measurements (whole graph; trial counts in evidence). These are not isolated node costs or ESP32 predictions.

Negative percentages mean the candidate was slower in that fixture.

| Bank | Before, µs/block | Candidate, µs/block | Less native time |
| --- | ---: | ---: | ---: |
| Lag2 | 13.501 | 12.424 | 8.0% |
| Lag3 | 13.495 | 12.397 | 8.1% |
| OnePole | 4.510 | 3.308 | 26.7% |
| OneZero | 4.543 | 1.889 | 58.4% |
| LPZ1 | 2.833 | 1.635 | 42.3% |
| HPZ1 | 3.030 | 1.625 | 46.4% |

### candidate-binary

**Forty binary selectors: shared scalar path and complete audio specialisation coverage (experimental; disabled by default).** All 40 selectors use one shared scalar/scalar evaluation per block when applicable. The four inherited arithmetic audio loops plus 36 candidate loops move dispatch out of the sample loop. Changing-control ramps retain their pinned path. Held negative-zero inputs in discontinuous selectors deliberately fall back to preserve the -0 to +0 transient observed by downstream atan2. Exact composed regression and whole raw-scratch checks pass. Selected musical hardware timing is linked below.

Implementation: [host/dsp_candidates.py](../host/dsp_candidates.py), [host/engine_profile.py](../host/engine_profile.py)

Host verification: [evidence/dsp-operators-final-host.json](../evidence/dsp-operators-final-host.json), [evidence/dsp-all-host.json](../evidence/dsp-all-host.json), [evidence/dsp-signed-zero-regression.json](../evidence/dsp-signed-zero-regression.json)

Hardware evidence: [evidence/dsp-qa-xiao-summary.json](../evidence/dsp-qa-xiao-summary.json), [evidence/dsp-seeded-xiao-summary.json](../evidence/dsp-seeded-xiao-summary.json)

Hardware qualification: Selected-layout 50-case replay plus fixed-seed XIAO profiling where applicable; normal/instrumented state checks and cross-image audio/RNG equality. Hardware timings are scoped whole-graph results, not full-rate/type qualification or a production promotion. Native types observed: BinaryOpUGen. Binary selectors observed: 0, 1, 2, 3, 4, 5, 17, 18, 19, 20, 21, 22, 39, 42, 43, 44, 45.

XIAO fixed-seed measurements, 44.1 kHz / 64 frames, three trials per whole test graph. These are musical regressions exercising selectors 0, 2 and 4, not isolated measurements of all 40 selectors. Negative percentages indicate a slowdown.

| Test graph | Baseline, µs/block | Candidate, µs/block | Less target DSP time |
| --- | ---: | ---: | ---: |
| eight_saw | 1180.00 | 1180.74 | -0.06% |
| comb_kr | 410.78 | 409.48 | 0.32% |
| triggered_harmonics | 311.73 | 310.96 | 0.25% |
| filters | 277.74 | 279.04 | -0.47% |

Desktop-only 32-node bank measurements (whole graph; trial counts in evidence). These are not isolated node costs or ESP32 predictions.

Negative percentages mean the candidate was slower in that fixture.

| Bank | Before, µs/block | Candidate, µs/block | Less native time |
| --- | ---: | ---: | ---: |
| `div (floor integer division)` (selector 3) | 2.915 | 1.781 | 38.9% |
| `mod` (selector 5) | 3.171 | 2.066 | 34.8% |
| `==` (selector 6) | 3.649 | 1.734 | 52.5% |
| `!=` (selector 7) | 3.382 | 1.717 | 49.2% |
| `<` (selector 8) | 3.356 | 1.717 | 48.8% |
| `>` (selector 9) | 3.529 | 1.734 | 50.9% |
| `<=` (selector 10) | 3.279 | 1.741 | 46.9% |
| `>=` (selector 11) | 3.558 | 1.731 | 51.4% |
| `min` (selector 12) | 3.340 | 1.736 | 48.0% |
| `max` (selector 13) | 3.241 | 1.710 | 47.3% |
| `lcm` (selector 17) | 11.909 | 11.285 | 5.2% |
| `gcd` (selector 18) | 10.634 | 9.952 | 6.4% |
| `round` (selector 19) | 3.606 | 1.998 | 44.6% |
| `roundUp` (selector 20) | 3.324 | 1.997 | 39.9% |
| `trunc (floor quantization)` (selector 21) | 3.587 | 2.024 | 43.6% |
| `atan2` (selector 22) | 5.297 | 4.193 | 20.9% |
| `hypot` (selector 23) | 3.950 | 3.065 | 22.4% |
| `hypotApx` (selector 24) | 3.904 | 2.001 | 48.8% |
| `pow (signed)` (selector 25) | 7.942 | 5.623 | 29.2% |
| `ring1` (selector 30) | 3.579 | 1.783 | 50.2% |
| `ring2` (selector 31) | 3.317 | 1.836 | 44.7% |
| `ring3` (selector 32) | 3.388 | 1.749 | 48.4% |
| `ring4` (selector 33) | 3.457 | 1.964 | 43.2% |
| `difsqr` (selector 34) | 3.262 | 1.838 | 43.7% |
| `sumsqr` (selector 35) | 3.285 | 1.822 | 44.5% |
| `sqrsum` (selector 36) | 3.312 | 1.771 | 46.5% |
| `sqrdif` (selector 37) | 3.827 | 1.757 | 54.1% |
| `absdif` (selector 38) | 3.819 | 1.712 | 55.2% |
| `thresh` (selector 39) | 3.279 | 1.864 | 43.2% |
| `amclip` (selector 40) | 3.425 | 1.950 | 43.1% |
| `scaleneg` (selector 41) | 3.578 | 1.783 | 50.2% |
| `clip2` (selector 42) | 3.355 | 1.793 | 46.6% |
| `excess` (selector 43) | 3.409 | 1.926 | 43.5% |
| `fold2` (selector 44) | 3.836 | 2.911 | 24.1% |
| `wrap2` (selector 45) | 3.388 | 2.165 | 36.1% |
| `firstArg` (selector 46) | 3.447 | 1.560 | 54.7% |

### candidate-noise

**WhiteNoise/PinkNoise/LFNoise0–2 block rendering (experimental; disabled by default).** Keep the same Taus88 state local throughout each node and commit before its successor. Hoist type dispatch and frequency decoding. LFNoise reuses exact segment length within each block; PinkNoise uses guarded ctz with the original zero-word mapping. Shared-sequence, interleaved RandSeed, constructor/history and 200,000 private index probes pass. Desktop bank timings and offline Xtensa object cost are recorded; opt in with candidate_noise=True.

Implementation: [host/dsp_candidates.py](../host/dsp_candidates.py), [host/engine_profile.py](../host/engine_profile.py)

Host verification: [evidence/dsp-operators-final-host.json](../evidence/dsp-operators-final-host.json), [evidence/dsp-all-host.json](../evidence/dsp-all-host.json)

Hardware evidence: [evidence/dsp-qa-xiao-summary.json](../evidence/dsp-qa-xiao-summary.json), [evidence/dsp-seeded-xiao-summary.json](../evidence/dsp-seeded-xiao-summary.json)

Hardware qualification: Selected-layout 50-case replay plus fixed-seed XIAO profiling where applicable; normal/instrumented state checks and cross-image audio/RNG equality. Hardware timings are scoped whole-graph results, not full-rate/type qualification or a production promotion. Native types observed: LFNoise0, LFNoise1, LFNoise2, PinkNoise, WhiteNoise. Binary selectors observed: none.

Desktop-only 32-node bank measurements (whole graph; trial counts in evidence). These are not isolated node costs or ESP32 predictions.

Negative percentages mean the candidate was slower in that fixture.

| Bank | Before, µs/block | Candidate, µs/block | Less native time |
| --- | ---: | ---: | ---: |
| WhiteNoise | 6.304 | 4.265 | 32.3% |
| PinkNoise | 22.446 | 17.680 | 21.2% |
| LFNoise0 | 6.265 | 1.902 | 69.6% |
| LFNoise1 | 6.680 | 2.399 | 64.1% |
| LFNoise2 | 6.773 | 3.420 | 49.5% |

### candidate-binding

**Block-bound input references across ten renderer entry points (experimental; disabled by default).** Hoist graph-reference decoding and input-rate lookup into per-call local pointers, without changing sample indices, parameters, equations or state. Seventy-two types share the touched renderers; not all benefit. All timing rows below are retained, including native regressions. Binding-only and combined variants each pass 2,176 graphs with complete state and arena identity. Target code/stack cost is recorded; selected-layout target timing, including regressions, is linked below. Opt in with candidate_binding=True. Selected bodies are now reused by the separate SYNTHDEF_QUALIFIED_KERNELS board-build option; this broad experimental flag remains off.

Implementation: [host/dsp_binding.py](../host/dsp_binding.py), [host/engine_profile.py](../host/engine_profile.py)

Host verification: [evidence/dsp-binding-host.json](../evidence/dsp-binding-host.json)

Hardware evidence: [evidence/dsp-qa-xiao-summary.json](../evidence/dsp-qa-xiao-summary.json), [evidence/dsp-seeded-xiao-summary.json](../evidence/dsp-seeded-xiao-summary.json)

Hardware qualification: Selected-layout 50-case replay plus fixed-seed XIAO profiling where applicable; normal/instrumented state checks and cross-image audio/RNG equality. Hardware timings are scoped whole-graph results, not full-rate/type qualification or a production promotion. Native types observed: AllpassC, AllpassL, AllpassN, Amplitude, BPeakEQ, Blip, CombC, CombL, CombN, DelayC, DelayL, DelayN, Formlet, FreqShift, GrayNoise, Impulse, Lag3, Latch, MiRings1, MiVerb, OneZero, Pluck, SinOscFB, TExpRand, TIRand, TRand, XFade2. Binary selectors observed: none.

XIAO fixed-seed measurements, 44.1 kHz / 64 frames, three trials per whole test graph. Narrowed to delay_render and render_miverb; these graphs exercise modulated delay time or reverb parameters. Negative percentages indicate a slowdown.

| Test graph | Baseline, µs/block | Candidate, µs/block | Less target DSP time |
| --- | ---: | ---: | ---: |
| DelayN | 145.78 | 133.32 | 8.54% |
| DelayL | 146.14 | 134.07 | 8.26% |
| DelayC | 158.12 | 146.13 | 7.59% |
| CombN | 148.25 | 135.65 | 8.50% |
| CombL | 148.51 | 136.29 | 8.23% |
| CombC | 160.63 | 148.31 | 7.67% |
| AllpassN | 150.32 | 137.09 | 8.80% |
| AllpassL | 150.60 | 138.14 | 8.27% |
| AllpassC | 163.78 | 150.67 | 8.00% |
| MiVerb_modulated | 555.40 | 536.80 | 3.35% |

Desktop-only selected fixture measurements (whole graph, three trials). These are not isolated node costs or ESP32 predictions.

Negative percentages mean the candidate was slower in that fixture.

| Bank | Before, µs/block | Candidate, µs/block | Less native time |
| --- | ---: | ---: | ---: |
| AllpassC | 0.336 | 0.347 | -3.4% |
| AllpassL | 0.319 | 0.288 | 9.7% |
| AllpassN | 0.284 | 0.281 | 1.1% |
| Amplitude | 0.719 | 0.715 | 0.7% |
| BHiShelf | 0.671 | 0.677 | -0.9% |
| BLowShelf | 0.682 | 0.673 | 1.3% |
| BPeakEQ | 0.686 | 0.680 | 0.8% |
| Balance2 | 0.307 | 0.258 | 16.0% |
| Blip | 0.172 | 0.168 | 2.3% |
| BrownNoise | 0.204 | 0.207 | -1.1% |
| ClipNoise | 0.174 | 0.169 | 2.9% |
| CoinGate | 0.646 | 0.612 | 5.4% |
| CombC | 0.312 | 0.315 | -1.0% |
| CombL | 0.281 | 0.280 | 0.6% |
| CombN | 0.287 | 0.284 | 1.0% |
| Crackle | 0.359 | 0.359 | -0.1% |
| DelayC | 0.305 | 0.320 | -5.0% |
| DelayL | 0.294 | 0.287 | 2.5% |
| DelayN | 0.304 | 0.289 | 4.8% |
| Fold | 0.219 | 0.199 | 9.2% |
| Formlet | 1.144 | 1.142 | 0.2% |
| FreqShift | 1.054 | 1.037 | 1.6% |
| Gate | 0.180 | 0.151 | 16.1% |
| GrayNoise | 0.179 | 0.185 | -3.0% |
| HPZ1 | 0.222 | 0.199 | 10.5% |
| Hasher | 0.250 | 0.241 | 3.6% |
| Impulse | 0.560 | 0.540 | 3.5% |
| LFClipNoise | 0.138 | 0.126 | 9.0% |
| LFCub | 0.563 | 0.567 | -0.6% |
| LFDClipNoise | 0.160 | 0.154 | 4.3% |
| LFDNoise0 | 0.167 | 0.141 | 15.9% |
| LFDNoise1 | 0.175 | 0.164 | 6.4% |
| LFDNoise3 | 0.200 | 0.192 | 4.0% |
| LFPar | 0.571 | 0.562 | 1.6% |
| LPZ1 | 0.220 | 0.201 | 8.7% |
| Lag2 | 1.021 | 1.001 | 1.9% |
| Lag3 | 1.005 | 0.999 | 0.6% |
| Latch | 0.182 | 0.152 | 16.5% |
| Limiter | 0.914 | 0.906 | 0.9% |
| LinExp | 0.343 | 0.321 | 6.4% |
| LinXFade2 | 0.308 | 0.266 | 13.6% |
| Logistic | 0.152 | 0.145 | 5.0% |
| MiMu | 0.361 | 0.337 | 6.6% |
| MiRings1 | 5.259 | 5.185 | 1.4% |
| MiRings2 | 4.487 | 4.499 | -0.3% |
| MiRings3 | 2.525 | 2.539 | -0.5% |
| MiRings4 | 1.536 | 1.517 | 1.2% |
| MiRings5 | 4.253 | 4.252 | 0.0% |
| MiRings6 | 3.210 | 3.214 | -0.1% |
| MiVerb | 1.372 | 1.352 | 1.4% |
| MoogFF | 0.904 | 0.924 | -2.2% |
| OnePole | 0.253 | 0.252 | 0.5% |
| OneZero | 0.254 | 0.254 | -0.2% |
| Phasor | 0.489 | 0.488 | 0.2% |
| Pluck | 0.519 | 0.510 | 1.7% |
| PulseCount | 0.677 | 0.625 | 7.7% |
| PulseDivider | 0.243 | 0.214 | 11.9% |
| SetResetFF | 0.658 | 0.610 | 7.4% |
| SinOscFB | 0.497 | 0.546 | -9.9% |
| Slew | 0.694 | 0.698 | -0.5% |
| Stepper | 0.681 | 0.630 | 7.5% |
| SyncSaw | 0.511 | 0.507 | 0.8% |
| TExpRand | 0.602 | 0.575 | 4.5% |
| TIRand | 0.667 | 0.631 | 5.3% |
| TRand | 0.617 | 0.603 | 2.2% |
| TWindex | 0.663 | 0.645 | 2.8% |
| ToggleFF | 0.254 | 0.239 | 5.7% |
| Trig | 0.248 | 0.228 | 8.3% |
| Trig1 | 0.260 | 0.234 | 9.7% |
| VarSaw | 0.561 | 0.551 | 1.9% |
| Wrap | 0.216 | 0.201 | 6.8% |
| XFade2 | 0.280 | 0.240 | 14.2% |

### candidate-routing

**Converters, short delays, selectors and seed control (experimental; disabled by default).** Dedicated A2K/K2A/DC, Delay1/2, Select, Clip, DegreeToKey and RandSeed loops retain exact constructor history, legal initial-rate result caching, interpolation order, sign behavior, trigger/seed ordering and faults. A held Select selector resolves the chosen source once per block; a held DegreeToKey input computes its key once. No new persistent fields. Opt in with candidate_routing=True.

Implementation: [host/dsp_routing.py](../host/dsp_routing.py), [host/engine_profile.py](../host/engine_profile.py)

Host verification: [evidence/dsp-routing-host.json](../evidence/dsp-routing-host.json), [evidence/dsp-all-host.json](../evidence/dsp-all-host.json)

Hardware evidence: [evidence/dsp-qa-xiao-summary.json](../evidence/dsp-qa-xiao-summary.json), [evidence/dsp-seeded-xiao-summary.json](../evidence/dsp-seeded-xiao-summary.json)

Hardware qualification: Selected-layout 50-case replay plus fixed-seed XIAO profiling where applicable; normal/instrumented state checks and cross-image audio/RNG equality. Hardware timings are scoped whole-graph results, not full-rate/type qualification or a production promotion. Native types observed: DC, K2A, RandSeed, Select. Binary selectors observed: none.

Desktop-only selected fixture measurements (whole graph, three trials). These are not isolated node costs or ESP32 predictions.

Negative percentages mean the candidate was slower in that fixture.

| Bank | Before, µs/block | Candidate, µs/block | Less native time |
| --- | ---: | ---: | ---: |
| A2K | 0.282 | 0.149 | 47.4% |
| Clip | 0.315 | 0.183 | 41.9% |
| DC | 0.168 | 0.082 | 51.3% |
| DegreeToKey | 0.177 | 0.072 | 59.3% |
| Delay1 | 0.241 | 0.173 | 28.3% |
| Delay2 | 0.242 | 0.237 | 2.2% |
| K2A | 0.194 | 0.097 | 49.8% |
| RandSeed | 0.492 | 0.488 | 0.8% |
| Select | 0.278 | 0.169 | 39.1% |

### candidate-chaos

**Fourteen exact chaos cycle-period caches (experimental; disabled by default).** Cache the unchanged held frequency period and, for interpolating variants, the original reciprocal slope. A compile-time check puts freq/b1/b2 cache fields beyond the complete overlaid chaos_state. No recurrence, interpolation, reset or nonlinear math changes. Code shrinks in the measured Xtensa object; native effects vary by model. All four-rate dynamic frequency probes and full state comparisons pass. The initially rejected timing harness and its corrected cache normalization are retained separately. Opt in with candidate_chaos=True.

Implementation: [host/dsp_chaos_cache.py](../host/dsp_chaos_cache.py), [host/engine_profile.py](../host/engine_profile.py)

Host verification: [evidence/dsp-chaos-host.json](../evidence/dsp-chaos-host.json), [evidence/dsp-all-host.json](../evidence/dsp-all-host.json)

Hardware evidence: [evidence/dsp-qa-xiao-summary.json](../evidence/dsp-qa-xiao-summary.json), [evidence/dsp-seeded-xiao-summary.json](../evidence/dsp-seeded-xiao-summary.json)

Hardware qualification: Selected-layout 50-case replay plus fixed-seed XIAO profiling where applicable; normal/instrumented state checks and cross-image audio/RNG equality. Hardware timings are scoped whole-graph results, not full-rate/type qualification or a production promotion. Native types observed: HenonN, LatoocarfianL. Binary selectors observed: none.

Desktop-only selected fixture measurements (whole graph, three trials). These are not isolated node costs or ESP32 predictions.

Negative percentages mean the candidate was slower in that fixture.

| Bank | Before, µs/block | Candidate, µs/block | Less native time |
| --- | ---: | ---: | ---: |
| CuspL | 0.258 | 0.189 | 26.6% |
| CuspN | 0.146 | 0.143 | 1.4% |
| FBSineC | 0.225 | 0.185 | 17.7% |
| FBSineL | 0.187 | 0.143 | 23.5% |
| FBSineN | 0.129 | 0.127 | 1.6% |
| HenonC | 0.116 | 0.114 | 1.9% |
| HenonL | 0.127 | 0.128 | -0.2% |
| HenonN | 0.105 | 0.106 | -0.5% |
| LatoocarfianC | 0.202 | 0.190 | 5.6% |
| LatoocarfianL | 0.189 | 0.164 | 13.5% |
| LatoocarfianN | 0.162 | 0.165 | -1.4% |
| LorenzL | 0.165 | 0.154 | 6.9% |
| StandardL | 0.220 | 0.178 | 19.1% |
| StandardN | 0.170 | 0.172 | -0.8% |

### candidate-core

**Oscillator, ramp, partial-bank and Gendy candidates (experimental; disabled by default).** Dedicated LFSaw/LFTri/LFPulse and Klang/Klank loops retain compensated phase, partial order and constructor resets. Line caches only invariant compensated span terms; XLine caches its held ratio, retaining per-sample pow and precise timing. Formant caches integer increments/width. Gendy1–3 cache independent distribution constants. SinOscFB caches exact phase steps and bit-keyed feedback targets; Blip caches effective crossfade frequency and harmonic scales, including the descending-frequency transition. Only documented otherwise-unused cache fields are normalized in comparisons. Native regressions and negligible gains are retained; timings vary between runs and fixtures, so no universal speed claim is made. Opt in with candidate_core=True. BPeakEQ/BLowShelf/BHiShelf and Formlet calculate each unchanged three-sample coefficient group once, retaining the exact division and final one-sample group. Amplitude caches attack/release coefficients independently and preserves audio-input/control-output stepping. Selected bodies are now reused by the separate SYNTHDEF_QUALIFIED_KERNELS board-build option; this broad experimental flag remains off.

Implementation: [host/dsp_core.py](../host/dsp_core.py), [host/engine_profile.py](../host/engine_profile.py)

Host verification: [evidence/dsp-core-host.json](../evidence/dsp-core-host.json), [evidence/dsp-all-host.json](../evidence/dsp-all-host.json)

Hardware evidence: [evidence/dsp-qa-xiao-summary.json](../evidence/dsp-qa-xiao-summary.json), [evidence/dsp-seeded-xiao-summary.json](../evidence/dsp-seeded-xiao-summary.json)

Hardware qualification: Selected-layout 50-case replay plus fixed-seed XIAO profiling where applicable; normal/instrumented state checks and cross-image audio/RNG equality. Hardware timings are scoped whole-graph results, not full-rate/type qualification or a production promotion. Native types observed: Amplitude, BPeakEQ, Blip, Formant, Formlet, Gendy1, Gendy2, Gendy3, Klang, Klank, LFPulse, Line, SinOscFB, XLine. Binary selectors observed: none.

XIAO fixed-seed measurements, 44.1 kHz / 64 frames, three trials per whole test graph. Klang/Klank graphs contain 16 partials; other rows are individual named UGens with their supporting nodes. Negative percentages indicate a slowdown.

| Test graph | Baseline, µs/block | Candidate, µs/block | Less target DSP time |
| --- | ---: | ---: | ---: |
| Klang | 147.86 | 104.05 | 29.63% |
| Klank | 197.92 | 146.87 | 25.80% |
| SinOscFB | 31.38 | 31.70 | -1.05% |
| Blip | 59.10 | 58.51 | 1.00% |
| Formant | 36.12 | 37.74 | -4.50% |
| Gendy1 | 89.95 | 88.48 | 1.64% |
| Gendy2 | 101.41 | 100.02 | 1.37% |
| Gendy3 | 91.27 | 90.13 | 1.26% |

Desktop-only selected fixture measurements (whole graph, three trials). These are not isolated node costs or ESP32 predictions.

Negative percentages mean the candidate was slower in that fixture.

| Bank | Before, µs/block | Candidate, µs/block | Less native time |
| --- | ---: | ---: | ---: |
| Amplitude | 0.865 | 0.767 | 11.3% |
| BHiShelf | 0.658 | 0.627 | 4.6% |
| BLowShelf | 0.641 | 0.630 | 1.8% |
| BPeakEQ | 0.643 | 0.629 | 2.2% |
| Blip | 0.155 | 0.145 | 6.4% |
| Formant | 0.110 | 0.101 | 8.0% |
| Formlet | 1.047 | 1.029 | 1.7% |
| Gendy1 | 0.491 | 0.482 | 1.9% |
| Gendy2 | 0.495 | 0.481 | 2.7% |
| Gendy3 | 0.503 | 0.495 | 1.7% |
| Klang | 0.331 | 0.334 | -0.9% |
| Klank | 0.417 | 0.405 | 3.0% |
| LFPulse | 0.516 | 0.495 | 4.0% |
| LFSaw | 0.523 | 0.494 | 5.7% |
| LFTri | 0.526 | 0.500 | 4.9% |
| Line | 0.270 | 0.197 | 27.1% |
| SinOscFB | 0.490 | 0.492 | -0.3% |
| XLine | 0.301 | 0.203 | 32.4% |

## Shared engine improvements

**Loader-planned signal-buffer reuse (enabled).** Independent scalar storage and conservative audio-buffer lifetime reuse improve graph memory/capacity. This is not a per-UGen algorithm speed-up.

Implementation: [host/signal_buffers.py](../host/signal_buffers.py)

Host verification: [evidence/signal-reuse.json](../evidence/signal-reuse.json), [evidence/dsp-kernels-reuse.json](../evidence/dsp-kernels-reuse.json)

Hardware evidence: [evidence/signal-reuse-xiao-capacity.json](../evidence/signal-reuse-xiao-capacity.json), [evidence/signal-reuse-amoled-install.json](../evidence/signal-reuse-amoled-install.json)

**Hot kernel/code and cache placement (enabled in production board profiles).** Selected shared rendering, arithmetic, envelope, panning, filter, Lag, unary and delay routines use internal instruction RAM; lookup/cache configuration is profile-specific. Do not classify all consumers as individually rewritten.

Implementation: [firmware/components/synthdef_engine/hot_data.lf](../firmware/components/synthdef_engine/hot_data.lf), [docs/timing.defaults](../docs/timing.defaults)

Host verification: [evidence/dsp-kernels-amoled-build.json](../evidence/dsp-kernels-amoled-build.json), [evidence/dsp-kernels-xiao-build.json](../evidence/dsp-kernels-xiao-build.json)

Hardware evidence: [evidence/timing-summary.json](../evidence/timing-summary.json), [evidence/dsp-kernels-xiao-final.json](../evidence/dsp-kernels-xiao-final.json)

## Disabled experiments

**MiVerb packed halfword delay access (disabled by default).** Host output/state checks passed, but measured XIAO rendering regressed. Production uses the ordered-clamp optimisation with existing byte-wise memory access.

Implementation: [host/dsp_kernels.py](../host/dsp_kernels.py), [host/engine_profile.py](../host/engine_profile.py)

Host verification: [evidence/miverb-packed-host.json](../evidence/miverb-packed-host.json)

Hardware evidence: [evidence/dsp-kernels-xiao-packed.json](../evidence/dsp-kernels-xiao-packed.json), [evidence/dsp-kernels-summary.json](../evidence/dsp-kernels-summary.json)

## Maintaining the register

For each new optimisation, update the JSON group and affected UGen/selector rows.
Record the applicable rates/input conditions, implementation paths, host
equivalence evidence and hardware board/build/fixture measurements separately.
Keep a host-only candidate out of the enabled category until it is actually a
production default; list it under host-only candidates. Keep rejected candidates
in the disabled experiment list.
Do not infer a per-UGen speed-up from a whole-patch measurement. Preserve old
evidence and add new records when requalifying a changed build.

DynKlank/DynKlang, Splay and Mix are host composites: track their generated native
UGens rather than adding them to the native count. Replacing audio-rate code
with control-rate code in a patch is a patch change, not an engine optimisation.
Main replacement fades improve transitions and are not a UGen speed optimisation.
