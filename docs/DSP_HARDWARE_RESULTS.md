# XIAO DSP candidate results — 4 November 2026

This page records the first session. The later [fixed-seed follow-up](DSP_SEEDED_PROFILING.md)
removes the stochastic-start limitation in the timing comparison and adds
individual smoothing, bank/oscillator/Gendy and delay test graphs.

The bounded hardware session ran on **XIAO-ba1e48**, permanent ID
`esp32-288485ba1e48`, with the connected PCM5102A. Configuration was 44.1 kHz,
64-frame float32 processing, fixed configured 240 MHz and stereo I²S. The clock
was not measured externally. No AMOLED was tested in this session.

**Decision:** keep all new candidates disabled in the standard firmware.
The trials passed the selected numerical checks, but performance was mixed.
The XIAO was left on standard headless source build **`7afd20139b45`**, application
size **1,337,728 bytes**, with the large replay pack disabled. Original Main/FX
packages, instance activity and settings were restored; output volume is 25% and
the separate FX slot is bypassed. The initial full-flash and package backups
remain private under the ignored build directory.
Restoration describes the end of qualification; subsequent user changes in
Studio are outside this report.

## Numerical replay

Three images ran the same 50-case pack: baseline, all seven candidates, and a
narrow selection containing only `delay_render` / `render_miverb` input binding.
Each image rendered **950,272 output float values**. Both candidate comparisons
matched baseline SHA-256 digests for output, normalized voice/partial/RNG state,
raw scratch and allocated delay memory, including constructor snapshots.

The checks cover **42 native types and 16 binary selectors** in their selected
layouts; they do not retest the 33 unary selectors or establish all-rate/parameter
coverage for those types. All seven new candidate families and all ten changed
binding entry points have a representative in the pack. The swapped-operand
integer-division signed-zero case intentionally faults for 32 blocks; baseline
and both candidates agree. This is separate from fault-free normal playback.

The replay is parked and muted; its hashing/cache conditions are not real-time
performance evidence. Paused-audio telemetry warnings during it are retained as
maintenance observations. Digests establish matching serialized data; this run
did not export a byte-by-byte first-mismatch dump because no mismatch occurred.

## Measured workload timing

Values are median **normal DSP microseconds per 64-frame block**, from three
1,024-block trials per image with 128 warm-up blocks. Per-node instrumented runs
were checked against the normal renderer separately. These are DSP timing
figures, excluding the full control/preparation/output workload shown by the
device's CPU display.

| Workload | Baseline | All candidates | Delay/reverb binding only | Narrow selection vs baseline |
| --- | ---: | ---: | ---: | ---: |
| Eight-Saw / Resonz / MiVerb | 1,177.39 µs | 1,173.31 µs | 1,161.30 µs | 1.37% less time |
| Corrected Comb Cloud KR | 393.88 µs | 383.31 µs | 364.98 µs | 7.34% less time |
| Triggered harmonics | 311.21 µs | 326.73 µs | 317.13 µs | 1.90% more time |
| Eight-filter bank | 277.73 µs | 279.94 µs | 277.69 µs | Essentially unchanged |

Graph hashes match across the three timing sets. The current profiler copies
the live voice before its normal/instrumented pair: those two paths share exact
initial state, but stochastic starting states are **not seed-locked across
firmware images**. Retain these as observations; smaller differences need a
fixed-seed, paired A/B measurement. The per-node figures suggested useful delay/
MiVerb binding savings and an expanded arithmetic-path cost, motivating the
narrow third image. They do not certify an isolated speed-up for every UGen.

No production flag was enabled from these measurements. The narrow variant
remains reproducible with:

```sh
host/xiao.sh -D SYNTHDEF_DSP_QA=ON \
  -D SYNTHDEF_DSP_CANDIDATES=binding \
  -D SYNTHDEF_BINDING_FAMILIES=delay_render,render_miverb build
```

This builds a test image only; it does not flash. Use separate build directories
or explicitly reset the cached options after experiments. The final standard
image was built with `SYNTHDEF_DSP_QA=OFF`, `SYNTHDEF_DSP_CANDIDATES=none` and an
empty `SYNTHDEF_BINDING_FAMILIES` value.

## Output, listening and restoration

At the saved **25%** volume, eight-Saw, Comb Cloud KR, triggered harmonics and a
separate MiVerb burst/tail were played on the narrow test image. The user
confirmed **“Clean, including the reverb tail.”** Digital capture also verified
non-clipped output, a tail after Main stopped, and exactly silent PCM after Panic.

After the standard firmware was installed, a separate final capture measured
**330 Hz left and 660 Hz right**, followed by zero PCM after gate release. The
saved Main and FX packages were checked against the initial package backup;
the temporary stereo definition was then replaced by the saved Main and instance
activity, bypass and volume were restored. Oscillator phase and old effect tails
cannot be recreated by that restoration.

## Evidence and remaining work

The checked summary is [dsp-qa-xiao-summary.json](../evidence/dsp-qa-xiao-summary.json).
It links the raw replay, workload, listening, build and final-smoke records.
Regenerate that summary **without hardware access** with:

```sh
python3 host/summarize_dsp_hardware.py
```

The explicit replay runner and workload/listening helpers are
`host/run_dsp_qa.py`, `host/qualify_dsp_workloads.py` and
`host/qualify_dsp_listening.py`. They access hardware when invoked; the plan and
summary generators do not. The replay command parks Main and is part of a
session with a private backup and restoration, not a general-purpose silent
inspection command.

Still outstanding: fixed-seed performance A/B, individual remaining types/rates/
selectors, the 324-graph coverage set, a long soak, current AMOLED qualification
and multi-module Wi-Fi tests. The [test plan](DSP_HARDWARE_TEST_PLAN.md) retains
those as optional later stages. This session is not a full 154-UGen/73-operator
hardware qualification.
