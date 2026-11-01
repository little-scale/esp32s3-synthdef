# Rendering timing and optimization

## Per-UGen kernel optimization and KR excitation — 1 November 2026

A separate instrumented renderer measures each node on the parked audio owner.
Normal rendering contains no per-node timing probes. Audio, voice-state and
arena digests agree between the normal and instrumented passes. Node shares
include probe overhead; the normal-renderer total is measured independently.
The diagnostic copy adds flash code only when diagnostics are enabled.

For the corrected AR Comb cloud, initial node shares were Decay2 39.1%, Dust
19.0%, CombC 13.6%, SinOsc 9.0%. The target generator now applies:

- Exact cached sine phase increments for unchanged frequency/sample rate.
- Exact binary-reciprocal Decay2 ramp scaling, eliminating per-sample division.
- Independent attack/decay coefficient caches.
- The identical Dust/Dust2 taus88 sequence held in registers for each block.

| Graph work, microseconds/block | Before | After |
| --- | ---: | ---: |
| Decay2 | 309.70 | 237.42 |
| Dust | 150.62 | 120.19 |
| SinOsc | 71.28 | 56.73 |
| CombC (unchanged) | 107.77 | 107.52 |
| Normal whole graph | 798.97 | 681.50 |

Under the same blank master, 30% volume and SLOTS view, five live one-second
windows measured 57.86% -> 49.76% average audio CPU (14.0% less work); highest
recent block peaks were 78.1% -> 66.9%. Slot 7's source/graph read back unchanged.
Twenty subsequent seconds reported zero new audio errors, clips or nonfinites.
Panic remained stopped through master reload; sound reload restarted without touch.

The user's slot-8 variant moves Dust and Decay2 to control rate. Six live windows
measured 29.02% average and 43.4% recent peak. Both versions retain 44.1 kHz audio,
64-frame blocks, float32 arithmetic, five oscillators and stereo cubic CombC.
The KR envelope/noise timing has 1.45 ms resolution; this is a source-level change,
not a bit-exact replacement for the AR graph. The user heard similar, clean sound.
Both still use 32 KiB of delay memory; voice/scratch sizes remain 35,752/49,152 bytes.

`host/test_comb_kernels.py` checks 14 graphs: targeted fixtures at 8/44.1/48/192 kHz,
and existing presets within their qualified 44.1 kHz range. The 46,137,344 output
samples, RNG sequences and delay buffers match the pre-optimization oracle exactly.
The complete KR graph adds 4,194,304 matching samples. Bounds/undefined-behaviour
checks pass. AddressSanitizer on this Mac deadlocks in initialization before main;
it is not recorded as a passing check. Kernel equivalence uses fixed seeds;
normal hardware sound starts now deliberately vary their seeds.

Evidence: comb-kernel-equivalence.json, comb-kr-kernel-check.json,
comb-ugen-profile-before/after.json, comb-live-before-kernels.json, comb-kr-live.json,
and comb-optimized-build.json under evidence/. These are measured workloads, not
worst-case qualification. Lifetime maxima include cold starts and maintenance.


## Comb cloud control-rate optimization — 1 November 2026

On firmware `931c9593efd1`, configured for 240 MHz with power management disabled,
changing only `SinOsc.ar(5)` to `SinOsc.kr(5)` for CombC delay time reduced the
measured average audio budget from **76.32% to 57.72%** (24.37% less processing).
The highest recent block peak in five one-second windows fell from 93.8% to
72.7%. Both versions used the same blank master FX route, 44.1 kHz / 64 samples,
float32 signals and cubic delay interpolation. Error, clipping and nonfinite
counters were zero. Lifetime maxima include prior runs and maintenance and are
not the recent-window peaks. These captures are workload evidence, not a
worst-case qualification. The user independently reported about 57%.

The audio-rate delay path recalculates its exponential feedback coefficient each
sample. Control-rate delay time computes it per block and ramps delay/feedback
between block targets. This cuts that work by roughly 64 for this part of the
graph; it does not reduce all graph work by 64. The 5 Hz modulation frequency and
49–50 ms range are retained, with different modulation sampling/interpolation.
Audio-rate modulation remains available when the sound requires it.

`examples/comb-cloud-efficient.scd` is the preferred version, verified in saved
slot 7. `examples/comb-cloud-audio-delay.scd` preserves the preceding version.
The original user expression remains in `examples/comb-cloud.scd`.
See `evidence/comb-cpu-optimization.json` for samples and graph identities.


The current [Rings optimization pass](RINGS_OPTIMIZATION.md) uses 32 KiB
instruction / 64 KiB data caches, internal Rings code and bounded preparation.
Models 2/5/6 use 27–28% less steady CPU time in the original muted fixtures.
The moving-control musical graphs still exceed the block deadline at some
settings. The existing voices reached 738/663/731 µs with display/master delay,
without new output-error events. Captured windows from all 24 long runs match native C
exactly. Startup allocation and LVGL task allocation failures are fixed; the
66 KiB optional arena stays off. Earlier measurements retain their identities.

The latest extended run and isolated constructor/live timing measurements are in
[EXTENDED_TESTS.md](EXTENDED_TESTS.md). The fixed image reached 939/918/952 µs for
the three example voices over repeated UI exercises. Rings models 2/5/6 and dense
operator banks exceed practical budgets in the measured configurations; they
remain experimental. Older measurements below retain their recorded identities.

The optional FM1 compatibility profile is documented in
[UGEN_SUPPORT.md](UGEN_SUPPORT.md). It has software tests and cross-compiler
checks plus one 30-second board exercise per richer example (956/832/932 µs,
zero 70%-margin violations). General graph timing remains unqualified. See
`evidence/fm1-device-smoke.json`. The sections below preserve earlier
compact-profile board measurements; function sizes and free-heap observations
belong to those recorded images. Current target sizes are in
`evidence/fm1-compact-build.json` and `fm1-compat-build.json`. Generated source now
also includes a precleared binding helper; DSP equations and tables are preserved.

## Persistent five-second delay and bounded note preparation

The selected capacity profile uses 24 nodes, 32 signals and 256 input references,
with a 262,144-float memory limit per instance. The embedded `master-delay` graph
uses one 1 MiB PSRAM ring, renders once after the synth and retains its state
between note events. Its output is converted to PCM only after the effect.

The earlier immediate-note path reached **1,129 µs** with margin violations when
both synth and delay controls moved. Output counters were zero, but this failed
the unchanged 70% gate. The reports remain in `delay-before-prestart-*`.

The target now reserves the note-on block for constructor/preparation work and
starts the note waveform in the following block. The master still processes that
first block, preserving old echoes. This adds exactly 64 samples (about 1.45 ms)
to the logical onset; it spreads work across deadlines rather than reducing total
CPU work. A release received before the first sample cancels the pending note.
Raw graph/reference callers keep their existing immediate-render behavior.

The new qualification exercise moves four synth controls and three delay controls
at a requested 25 Hz. Delay spans 20 ms to 5 seconds, feedback 0–0.8 and wet 0–1.
It also performs seven pitch positions, attack/release extremes and five note
starts per second. All selected combinations passed with zero margin violations,
output errors, clipping or nonfinite samples:

| Patch | Requested exercise | Combined maximum | Fraction of block |
| --- | ---: | ---: | ---: |
| filtered | 90 s | 914 µs | 62.98% |
| phase-fm | 90 s | 857 µs | 59.05% |
| additive | 90 s | 910 µs | 62.70% |
| mac-sine | 30 s | 706 µs | 48.65% |

The sparse target probe captures first/second echo windows at 20 ms, 350 ms,
1 second and 5 seconds, plus post-panic zeros. The host reference covers full
12-second traces, feedback and changing parameters against SC 3.14.1. Its terminal
Out is wrapped as ReplaceOut for isolated bus semantics. Persistent reference
nodes are explicitly freed before server teardown. Unit tests also check bounded
sustained feedback, arena canaries, bypass PCM, pending-note cancellation and
old-tail preservation during retrigger.

Panic suppresses the effect at the next audio boundary. The owner then drains
silence, stops DMA, clears/reprepares the ring and only then acknowledges resume.
Full clears take roughly 46 ms outside rendering. Save/load clears the effect in
the same maintenance state. Neither note start nor note release clears the ring.

The sine table remains in flash and standard math routines remain unchanged.
The longer soak, external audio recording, actual clocks and total input/output
latency remain release checks. The figures here describe this measured workload;
CPU averages and arbitrary effect graphs are not established by these maxima.

## 31 October: bounded control work and adapter placement

The audio adapter resolves `freq`, `amp`, `gate` and the four knob indices once
when activating an immutable graph. Note starts and live events write validated
indices directly, retaining finite/range checks and rejecting initial-rate aliases.
The name-lookup and cached versions produced **bit-identical PCM across 1,400
cases / 268,800 mono samples**; see `evidence/control-cache-equivalence.json`.

`instrument_apply`, `instrument_apply_batch`, `instrument_render` and
`instrument_pcm` now use internal instruction RAM. Their retained bodies use
**1,470 bytes**, plus literals/alignment. Build recording checks actual addresses.
Engine source, math flags, sine table bytes and PCM rounding remain unchanged.

With cached indices but the adapter in flash, the filter exercise reached
**1,019 µs** with one block above the 70% margin. After adapter placement, three
rounds reached **813 µs**, with zero margin violations or reported output/numerical
errors. The failure remains in `filtered-exercise-before-adapter-iram.*`. This is
a workload comparison, not a universal speedup or average CPU-utilization figure.

The expanded muted matrix covers **280 cases per patch**: base frequencies 20,
110, 440, 1,760 and 20,000 Hz; seven pitch positions; and both extremes of timbre,
attack and release. First-note, live pitch/timbre change and release blocks give
53,760 mono samples per patch. This does not cover every continuous value or the
full duration of long releases. The audible UI exercise uses each patch's compiled
base-frequency default (330 Hz for the three new examples); the extreme-frequency
muted matrix is not a realtime guarantee under simultaneous screen activity.

Each explicit `t` command has a separate timing window. Lifetime timing, output
and numerical counters remain visible. Reports retain window and cumulative
maxima, preserving failures without attributing an earlier patch's peak to a later
patch. The threshold remains 70% of a 64-frame block at requested 44.1 kHz.

A useful next optimization is a smaller target memory profile. The engine reserves
160 node states and 192 signals; current admission needs at most 24 nodes and 32
signals. Reducing signal capacity alone would save 40,960 scratch bytes, and
smaller node state would reduce note-start clearing. The capacity change is now selected through an audited generated header, with
new target numerical and timing checks. The older size proposal and original
measurements remain historical evidence; approximate math is still disabled.

## 30 October: original kernel-placement investigation

The initial M4 interaction observation reached 1,617 µs for preparation plus
rendering/conversion, exceeding both the 70% margin and a 64-frame block at the
requested 44.1 kHz (1,451.25 µs). Ordinary playback at saved defaults had passed.
The failed observation remains in `evidence/patch-device-powercycle-initial.*`.

## Reproduction and selected change

A bounded on-device exercise drives the real UI controls through their normal
mailboxes/queues: four updates at a requested 25 Hz, seven pitch positions,
attack/release extremes, and five retriggers per second. It stops itself after
30 seconds. The host then panics and reloads slot 1, restoring compiled defaults.

| Placement | Worst combined time | Blocks above 70% | Output error counters |
| --- | ---: | ---: | --- |
| Engine instructions and sine table in flash | 1,818 µs (125.27%) | 120 | Zero |
| Sine table in internal data RAM; instructions in flash | 1,808 µs (124.58%) | 117 | Zero |
| Admitted rendering kernels in internal instruction RAM; table in flash | 749 µs (51.61%) | 0 | Zero |
| Final image, three consecutive rounds | 761 µs (52.44%) | 0 | Zero |

The first three rows are separate 30-second experimental runs; the final image
passed 90 seconds of requested exercise across three rounds. Exact source identities,
configuration files and telemetry are in `evidence/timing-*`. The selected change
is `CONFIG_SYNTHDEF_INTERNAL_KERNELS=y`, now the default. The table-only option
remains disabled. Moving the table used 32,772 bytes without resolving the issue.

The measurements implicate pressure on the shared flash instruction path during
UI updates. Linker placement of the admitted kernels resolved the reproduced
case. `firmware/components/synthdef_engine/hot_data.lf` maps their existing text
and literals to internal instruction RAM. The pinned engine, graph files, lookup
values, floating-point flags and quantization rules remain unchanged.

The retained function bodies occupy 29,794 bytes, plus literal pools/alignment.
Runtime measurements replace assumptions about free heap; the experiment retained
at least 75,915 bytes internal free and a 31,744-byte largest free block. This is
a memory tradeoff for the admitted one-voice workload, not admission for another
voice or arbitrary compiled UGens. Build recording verifies symbol placement.

## Numerical and functional verification

The muted benchmark runs on the parked audio owner using its existing voice and
scratch. It originally covered 84 combinations per patch: three base frequencies, seven pitch
positions and attack/release extremes. It measures reset, control setup,
preparation, DSP and PCM conversion separately. Captured first-note, live-change
and release blocks are CRC-checked against a portable host renderer.

The 30 October final-image comparison covers 32,256 mono samples across factory and Mac Sine.
Both match within one PCM quantization step. This complements the earlier longer
float capture and SuperCollider checks; it does not replace physical recording.
The final build also passes failed-upload retention, activation, repeated save,
factory recall and byte-identical source/graph readback checks.

`timing-matrix-final.json`, `patch-device-timing-regression.json` and
`timing-exercise-final.json` retain final-image results. Historical failures remain
separate. The 70% threshold has not been relaxed, and counters are not reset
between rounds within the repeated-exercise session.

## Reproduce

For a new diagnostic build directory:

```sh
python3 host/prepare.py
SYNTHDEF_BUILD_DIR=build-timing host/idf.sh -D IDF_TARGET=esp32s3 \
  -D "SDKCONFIG=$PWD/firmware/build-timing/sdkconfig" \
  -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;$PWD/docs/ui.defaults;$PWD/docs/timing.defaults" build
python3 host/record_build.py --build-dir build-timing --output timing-build.json
```

Flash using the observed port and the normal project partition map. Afterward,
use the installed IDF Python environment for these pyserial commands. The matrix
expects factory slot 0 and the included Mac Sine saved in slot 1.

```sh
python host/profile_timing.py --port /dev/cu.usbmodem101 --output evidence/matrix-repeat.json
python host/exercise_timing.py --port /dev/cu.usbmodem101 \
  --output evidence/exercise-repeat.json --rounds 3
```

Diagnostic builds expose explicit console commands: `b` runs the muted matrix;
`t` starts the bounded audible UI exercise; `x` stops it; `!` panics. These are
operator tools and never start automatically. Normal builds default to diagnostics
off; the currently tested board image has them enabled and returns to the normal
touch UI afterward. The display/voice stay under their established owners.

The longer interaction soak, external recording/latency, actual clock accuracy
and power-failure tests remain release gates. Driver counters alone do not prove
uninterrupted physical audio, and the native USB reset issue remains separate.
