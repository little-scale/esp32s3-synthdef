# Rendering timing and optimization

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
smaller node state would reduce note-start clearing. That changes the target ABI
and needs a separate audited build/profile comparison. No capacity reduction or
approximate math has been applied here.

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
