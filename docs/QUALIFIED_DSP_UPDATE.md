# Selective DSP update — computer preparation

This update selects the measured winners from the XIAO qualification: six
smoothing UGens, Klang/Klank, and input binding for the nine delays and MiVerb.
It is prepared on `codex/qualified-dsp-defaults`; **the connected board has not
been accessed or flashed during this work**. The combined image still needs a
same-board hardware comparison. Published individual-candidate gains are not
claimed for this combined image.

## Implementation

`host/qualified_kernels.py` reuses the tested smoothing and partial-bank arithmetic
bodies. It adds no Formant/Gendy/SinOscFB caches, noise changes or expanded binary
operator dispatch. Smoothing dispatch follows the existing filter, arithmetic,
envelope and oscillator exits; bank dispatch sits at the old bank fallback.
That keeps the new tests out of those common fast exits. Delay/reverb binding is
restricted to `delay_render` and `render_miverb`.

The board CMake option `SYNTHDEF_QUALIFIED_KERNELS` defaults to `ON`. All seven
experimental candidate switches remain off. They are separate controls: selecting
an overlapping experiment uses that implementation once; disjoint experimental
bindings retain the selected production paths without declaring helpers twice.
The profile manifest records each effective path and is checked against linked
build inputs by `host/record_build.py`.
The generated build-mode header also tags `UGEN_SETUP` and `DSPQA_BEGIN` with
`qualified=0` or `qualified=1`. The replay collector rejects an unexpected mode;
use `host/run_dsp_qa.py --qualified` only for the selected image. Native profiler
tests cover both modes, including deterministic replay and allocation-failure
restoration of the live voice, shared scratch and delay arena.

The standalone Python generator retains its legacy reference by default. Pass
`qualified_kernels=True` to `generate`, or CLI `--qualified-kernels`, to generate
the selected paths. This distinction keeps historical test baselines reproducible.
Graph layout, admission limits, float32 arithmetic, sample rate and block size
are unchanged. Only previously-unused Lag2/Lag3 coefficient-cache fields differ
in the native state comparison.

## Offline validation

`host/test_qualified_kernels.py` first checks that its reference C/header/include
files match the renderer generated at commit `b7fd8ac`. It then compares:

- 2,545 graphs at 44.1 kHz for 64 blocks each.
- 1,091 edge graphs at 8, 44.1, 48 and 192 kHz for 512 blocks each.
- Three full 2,545-graph composition runs: disjoint experimental binding,
  the experimental core override, and experimental noise.

All **369,393,664 compared output samples** match, along with constructor/render
scratch, recursive state, RNG, flags and delay arenas. Only caller pointers and
documented Lag2/Lag3 cache fields are normalized in the primary comparison;
composition tests additionally use the documented experimental cache exclusions.
Undefined-behavior, bounds and float-conversion sanitizers pass. Deliberate invalid
domains must match faults; those cases are not labelled fault-free playback.

A further 217 graph cases alternate two voices through poisoned shared scratch
with reversed signal mappings, different initial random values, canaries and a
single-voice restart. Their 2,666,496 audio samples and final state/arenas match
byte-for-byte after the same documented cache normalization.

Additional cases exercise initial/control/audio excitation, changing smoothing
time/coefficient, negative or out-of-range parameters, variable delay time and
feedback sign, multiple banks sharing excitation, repeated constructors and
recycled signal buffers. Selection guards preserve unselected source files and
verify that enabling all experiments produces the same C code as before.

Both board images cross-built and passed the target audit. XIAO adds 3,664 bytes
of application flash; AMOLED adds 3,600. Graph/voice/scratch structure sizes are
unchanged. The renderer's internal-code symbol shrank from 18,652 to 17,842 bytes;
this is not a total IRAM accounting or a speed measurement. Compiler-reported
individual frames are 80 bytes for smoothing and 112 for the bank helper; the
record is not a complete runtime call-stack guarantee.
The new smoothing and bank helpers remain in flash, matching the individual
candidate placement. Moving those helpers into IRAM would be a separate timing
and memory-placement experiment.

Reproduce without hardware:

```sh
PYTHONPATH=host python3 -m unittest test_qualified_selection test_binding_selection
python3 host/test_qualified_kernels.py
python3 host/summarize_qualified_kernels.py
```

The summary audits native results and the recorded board builds; it does not build
or flash. Evidence is in `evidence/qualified-kernels-*.json`. Tests preserve the
older candidate evidence rather than rewriting it.

## Rollback and historical comparisons

Set `-D SYNTHDEF_QUALIFIED_KERNELS=OFF` and keep
`-D SYNTHDEF_DSP_CANDIDATES=none` for the legacy renderer. The XIAO rollback image
has been cross-built and audited. Hardware experiment reproductions of the older
baseline/all/narrowed measurements must explicitly set this option to `OFF`.

These prepared builds use separate `build-qualified-xiao` and
`build-qualified-amoled` directories and separate SDK configurations. Existing
standard image files and the running Studio service were not replaced.

## Short hardware check when the board is available

Use the existing pinned plans and shared-USB profiling endpoint. Before changing
firmware, identify the module and save its Main/FX packages, runtime controls,
instance modes, FX bypass and saved volume. Keep a verified standard application
for recovery. Do not depend on USB recovery while the board is physically
inaccessible.

1. Capture three fixed-seed baseline runs of the four musical graphs.
2. Install the audited combined image with output muted; verify the actual image
   and effective profile, not just the source-derived build ID.
3. Repeat the musical plan and the 24 smoothing/core/delay targeted graphs.
   Require matching warm/audio SHA-256 and final RNG, with no new unexpected faults.
4. Repeat the baseline if a timing difference is near the earlier 0.4% variation.
   Investigate a repeatable regression above 1% in a musical workload before
   accepting the combined image; do not infer additive savings from old tables.
5. Check normal playback, FX tails, note release, mute/Panic and counters. Restore
   exact packages, instance modes, bypass and saved volume, then confirm output.

The previous interrupted USB attempt and its successful recovery remain in the
[fixed-seed report](DSP_SEEDED_PROFILING.md). Broader 324-graph hardware coverage,
long soak and physical AMOLED checks remain separate work.
