# Deterministic target profiling

The 4 November follow-up removes a limitation of the first DSP timing session:
the old `j` profiler copied the live voice, so separate images could start with
different random values, oscillator phases and effect histories.

## Fixed mode

The explicit uppercase `J` diagnostic reconstructs the admitted Main graph from
its saved graph defaults at seed **12345**. It binds zero-valued control buses,
clears the graph's delay memory and scratch, and runs the constructor twice to
check the normal idempotent preparation path. Both renderer passes start again
from that state, run 128 warm-up blocks and time 1,024 blocks at 44.1 kHz / 64 frames.
There are no external inputs or timed control changes in these four workloads.

Warm-up and measured audio receive separate SHA-256 digests. The normal and
instrumented passes must also agree on voice state, raw scratch and delay-memory
digests. The host checks identical graph bytes, setup, both audio digests and final
RNG words across trials and images. This complements the earlier 50-case state/
arena replay; audio hashes alone do not establish every internal-state property.

Cycle and wall-clock readings enclose rendering only. Clearing the output,
hashing, reporting, allocation, restoration and deliberate scheduler yields are
outside those intervals. Per-node attribution comes from a separate instrumented
renderer and includes its probe overhead; use the normal-renderer total for
whole-graph comparisons. SDK CPU frequency is reported, and cycles/wall time
provide an independent consistency check, not an external clock measurement.

All borrowed Main voice, scratch and affected arena bytes are restored before
returning. The command parks/resumes audio through the existing maintenance path;
it is a muted diagnostic, not a transparent live performance control. Constructor
and allocation failures are reported as incomplete results, not successful tests.

## Connection ownership

`POST /api/diagnostics/ugen-profile` runs under Studio's device lock and borrows
the existing USB connection. It requires the exact module ID, USB transport and
a confirmed zero output volume. The idle log reader cannot consume profiler
records while that lock is held. This avoids repeated serial close/open cycles;
it does not guarantee recovery from an already stalled USB device.

The endpoint uses the existing authenticated loopback API and has no automatic
polling or UI button. Profiling pauses synthesis. New firmware with `J` support
is required; normal resource-panel polling and CPU peak reset remain cached-only.

## Reproduction

To reproduce the historical image comparisons on newer checkouts, set
`SYNTHDEF_QUALIFIED_KERNELS=OFF` in every compared build. The proposed combined
image has a separate validation plan.

Prepare graph bytes once, silently on the computer:

```sh
python3 host/qualify_seeded_dsp.py --prepare build/host/seeded-dsp-plan
PYTHONPATH=host python3 -m unittest test_profile_ugens
python3 host/test_seeded_profile.py
```

Native diagnostic tests use real generated renderers, a CommonCrypto SHA adapter
and mocked target clocks/allocator on macOS. They cover RNG, delay and bus graphs,
repeatability, live-state restoration, allocation failures and arena canaries
under undefined-behavior/bounds/float-conversion sanitizers. They are not target
performance measurements.

After backing up the exact module and deliberately installing a test image,
run the guarded, muted workload helper:

```sh
python3 host/qualify_seeded_dsp.py \
  --plan build/host/seeded-dsp-plan/plan.json \
  --device-id esp32-288485ba1e48 --phase fixed-baseline \
  --runs 3 --output evidence/dsp-seeded-xiao-baseline.json
```

For later images, pass `--compare evidence/dsp-seeded-xiao-baseline.json` and a
different output path. The helper saves/restores packages and runtime settings
around each workload session. Firmware installation and any persistent test mute
are separate session operations: preserve the original application and saved
volume and restore them explicitly. It will not overwrite an unrelated graph.

## Completed results — 4 November 2026

XIAO-ba1e48 completed **28 unique pinned graphs**, **14 timing records**, and
**240 normal/instrumented pairs** at 44.1 kHz / 64 frames. Each pair rendered
1,024 measured blocks after 128 warm-up blocks. The measured streams contain
62,914,560 float values across both renderers; warm-up output is checked separately.
Normal/instrumented audio, voice, scratch and arena checks passed. Cross-image
warm/measured audio SHA-256 digests and final RNG words matched for every comparison.
These cross-image checks do not compare normalized whole-voice state; the earlier
50-case replay provides its separate state/arena evidence.

| Musical workload | Baseline µs/block | Binary only | Delay/reverb binding | All seven candidates |
| --- | ---: | ---: | ---: | ---: |
| Eight-Saw / Resonz / MiVerb | 1,180.00 | 1,180.74 | 1,159.60 | 1,172.83 |
| Comb Cloud KR | 410.78 | 409.48 | 385.73 | 391.29 |
| Triggered harmonics | 311.73 | 310.96 | 310.63 | 319.82 |
| Eight-filter bank | 277.74 | 279.04 | 277.66 | 280.01 |

A second baseline after these images stayed within 0.4% of the first. Binary-only
and full input-binding-only images did not reproduce the combined image's 2.6%
triggered-harmonics slowdown. The core-only image slowed that workload by about
1.1%; smoothing-only was within 0.2%. Additional dispatch/code-layout interactions
remain possible, but are not isolated by this session. Do not attribute the whole
combined regression to binary operators.

### Targeted graphs

Three further baselines and matching family images covered:

| Scope | Result: less normal DSP time |
| --- | ---: |
| Lag2, eight parallel copies | 63.42% |
| Lag3, eight parallel copies | 61.46% |
| OnePole, eight parallel copies | 59.61% |
| OneZero, eight parallel copies | 62.60% |
| LPZ1, eight parallel copies | 52.77% |
| HPZ1, eight parallel copies | 52.79% |
| Klang, 16 partials | 29.63% |
| Klank, 16 partials | 25.80% |
| SinOscFB | −1.05% |
| Blip with changing frequency | 1.00% |
| Formant | −4.50% |
| Gendy1 / Gendy2 / Gendy3 | 1.64% / 1.37% / 1.26% |
| DelayN/L/C, CombN/L/C, AllpassN/L/C | 7.59–8.80% |
| MiVerb with changing time | 3.35% |

These are whole-graph results, including supporting excitation, controls,
scaling/mixing and output nodes; they are not isolated universal UGen speedups.
All six smoothing cases and eight bank/cache cases used the corresponding
family-only candidate image. Delay/reverb testing bound only `delay_render` and
`render_miverb`. The [register](OPTIMIZATION_REGISTER.md) retains individual rows,
scopes and raw baseline/candidate values.

The fixed workload set observed 52 native types, binary selectors 0/2/4 and unary
selector 16. Together with the separate first-session 50-case pack, the two sets
observed 74 native types in selected layouts. This does not qualify every type,
rate, parameter path or all supported operators. The 324-graph sweep, long soak,
remaining layouts and current physical AMOLED qualification are still outstanding.

SDK frequency was 240 MHz. Normal-renderer cycle/wall ratios ranged from about
233.8 to 239.8 cycles/µs across all short and long graphs; the extra timer-boundary
cost matters more for small graphs. The four original baseline workloads were
239.3–239.8. This supports the scale of the CPU meter, without external clock
measurement. Per-node probe overhead is excluded from the normal-renderer totals.

### Recovery and final state

The first binary attempt lost USB while reopening serial and is retained as
`evidence/dsp-seeded-xiao-binary-interrupted.json`. After physical reconnection,
all subsequent profiling borrowed Studio's current USB connection and completed.
The interrupted attempt remains failed; it was not relabelled as a successful run.

The XIAO is on **standard build `d627eccb77a7`**, all candidate switches off and the
large QA pack excluded. Its application is byte-identical to the audited standard
baseline. Original Main/FX packages and instance controls were restored and
verified; FX is bypassed and **15% volume is saved**. Main is active/prepared and
post-volume PCM is nonzero and unclipped. Oscillator phases and old reverb tails
are not restored. No new user listening confirmation is claimed for this session.

A settled 20-second read-only check advanced 883,200 frames with no increases
in write failures, partial writes, DMA queue notifications, faults, clipping,
nonfinite output or command overflows. Two cumulative DMA queue notifications
were already present before that interval; their earlier timing was not isolated,
so this is not a claim of zero notifications throughout startup/maintenance.

Both standard profiles cross-built and passed the target audit: XIAO 1,338,816
bytes, AMOLED instrument 1,681,504 bytes. No AMOLED was flashed. The local XIAO
build cache is also back to standard options. No candidate was promoted; selective
production changes should preserve these scopes and retest their combined image.

The checked machine summary is `evidence/dsp-seeded-xiao-summary.json`. Audit the
recorded results without hardware access using:

```sh
python3 host/summarize_seeded_dsp.py
```

The summary links raw timing records, hashes, final restoration and audio checks.
Native profiler tests are in `evidence/dsp-seeded-host.json`. Prepare targeted
suites separately with `--suite smooth`, `--suite core` or `--suite delay` alongside
`--prepare`; timing always consumes the resulting pinned `--plan` file.
