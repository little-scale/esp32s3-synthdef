# Current DSP sweep and mixer experiment — 13 November 2026

The XIAO-3eeb84 (`esp32-1c29043eeb84`) completed the broader regression sweep
on firmware `b06188c54dbe`, followed by fixed-seed hotspot profiling and a separate
controlled mixer experiment. All diagnostics were muted. Original Main/FX
packages, saved generations and live controls were restored; final saved volume
is **5%**, with Studio connected and the original continuous sound playing.

## Long-trace results

The 332 distinct graphs combine the historical main and edge plans, excluding
six duplicate graph hashes. Fresh sanitized native references use the same
qualified DSP source as the tested XIAO. Each graph renders 8,192 blocks at
44.1 kHz / 64 frames, with 40 captured stereo float windows across startup,
parameter changes and tails. Full-duration peak/RMS, faults, nonfinite values and
delay-arena canaries are checked separately.

| Result | Graphs |
| --- | ---: |
| Within the declared waveform limits | 309 |
| Statistical agreement only | 22 |
| Strict float-tolerance failure, retained | 1 (`Klang`) |

The sweep covers **154 inherited native types**, the **258 original inventory
type/rate pairs**, and two additional initial-rate diagnostic-plumbing pairs
(`Control` and `MulAdd`). Six banks exercise every **33 unary / 40 binary selector
at initial, control and audio rate**. The separate TDelay implementation retains
its [six previously captured XIAO timing cases](../evidence/tdelay-xiao-3eeb84.json);
it is not counted as newly swept here.

There are **zero reported renderer faults, nonfinite outputs or arena-guard
failures** over 174,063,616 rendered frames. Captured windows contain 1,699,840
float samples. Statistical grades do not establish identical chaotic trajectories;
sparse windows and aggregate guards are not a full-sample identity proof.

Klang repeats the historical maximum float error of approximately **1.068e-5**
and RMS error **3.431e-6**. Independent float32 mono/stereo gain and nearest-even
S16 conversion checks differ by at most **one PCM step**, including at 5% gain.
The raw reports deliberately remain `passed: false` under their stricter float
criterion; the bounded PCM result does not relabel that failure.

[Summary](../evidence/current-inventory-summary-20261113.json),
[plan and native references](../evidence/current-inventory-plan-20261113.json),
[full initial run](../evidence/current-inventory-xiao-20261113.json),
[completed profiling follow-up](../evidence/current-inventory-profiles-resumed-xiao-20261113.json),
[Klang precision check](../evidence/klang-current-drift-20261113.json).

## What profiling found

Three fixed-seed trials per sustained graph use seed 12345, 128 warm-up blocks
and 1,024 measured blocks at the reported 240 MHz CPU clock. Normal-renderer
timing is separate from the instrumented pass used for node attribution.

| Representative graph | Median normal DSP µs/block |
| --- | ---: |
| All unary selectors at audio rate | 2,369.01 |
| Rings 6, forced | 1,140.80 |
| Rings 6, live | 1,104.15 |
| Rings 2, forced | 1,046.11 |
| Rings 5, forced | 1,044.90 |
| Rings 2, live | 1,009.53 |
| Rings 5, live | 1,008.25 |
| MiVerb saturation fixture | 492.13 |

The unary mega-bank exceeds the 1,451 µs audio block budget. Its largest
attributed selectors are `midicps`, `octcps`, `midiratio` and `dbamp`; those costs
come from repeated audio-rate exponential math. Support does not make this dense
bank a real-time-safe patch. Rings 2/5/6 remain heavier individual algorithms.
The original eight-saw/Resonz/MiVerb graph measures about 1,162 µs/block; Saw and
MiVerb dominate its instrumented attribution.

The finite `m5_addy` fixture passes its long trace but its `Line` doneAction=2
ends the voice before the profiler finishes. Its first profiling attempt is
retained as unavailable; the follow-up selects sustained graphs instead.
These are parked renderer timings, excluding PCM/I²S, UI and network load.

## Narrow mixer candidate: measured, kept disabled

`candidate_mix=True` / `SYNTHDEF_DSP_CANDIDATES=mix` adds an all-audio Sum3/Sum4
loop and binds Pan2 output pointers once per block. Float32 addition order,
control ramps, faults, state and buffer lifetimes stay unchanged. The candidate
is **off by default** in both board profiles and is not a firmware precision or
block-size change.

Strict sanitized native comparisons pass **174 edge graphs at four sample
rates** and **1,628 inventory/example graphs**: 58,949,632 output samples,
constructor/render scratch, complete voice state apart from caller pointers,
RNG, fault flags and delay memory. No DSP cache fields are normalized.

Both XIAO variants use source build `814e14cdfc6c`; their audited application
hashes and runtime `mix=0/1` tags distinguish them. Each of nine pinned graphs
runs three times per image on the same physical board. Warm/measured audio
SHA-256 and final RNG match across all trials/images; normal/instrumented state,
scratch and arena checks also match within each image.

| Whole graph | Baseline µs | Candidate µs | Less DSP time |
| --- | ---: | ---: | ---: |
| 24 Sum3 nodes | 450.71 | 358.80 | 20.39% |
| 24 Sum4 nodes | 530.80 | 394.60 | 25.66% |
| 24 Pan2 nodes | 343.71 | 363.10 | **−5.64%** |
| Eight-saw sound | 1,161.25 | 1,145.83 | 1.33% |
| Comb Cloud KR | 385.93 | 374.72 | 2.90% |
| Triggered harmonics | 311.05 | 300.78 | 3.30% |
| Filter bank | 277.86 | 266.45 | 4.11% |

These are whole-graph results, not isolated per-node speed-ups. The normal-image
code-placement effect is not isolated. Despite promising Sum results, the Pan2
regression means the combined candidate is **not promoted**. The useful next
experiment is to separate Sum and Pan changes and repeat the controlled comparison.

The XIAO is restored to the **standard, candidate-off `814e14cdfc6c` application**.
Only the application partition was written; patch storage and Wi-Fi settings
were preserved. Standard XIAO and AMOLED images and the experimental XIAO image
pass build audits. Physical AMOLED verification remains pending. Candidate app
size grows by 1,280 bytes; graph, scratch and voice structures do not change.

[Host checks](../evidence/dsp-mix-host-20261113.json),
[hardware comparison](../evidence/mix-xiao-comparison-20261113.json),
[standard XIAO audit](../evidence/mix-xiao-default-build-20261113.json),
[candidate XIAO audit](../evidence/mix-xiao-candidate-build-20261113.json),
[AMOLED audit](../evidence/mix-amoled-default-build-20261113.json),
[final installation/restoration](../evidence/mix-xiao-final-default-install-20261113.json).

## Reproduction

Prepare native references without a board, then explicitly run on an identified,
backed-up USB XIAO with FX bypassed and volume at or below 5%:

```sh
python3 host/qualify_current_inventory.py --prepare build/host/current-inventory/plan.json
python3 host/qualify_current_inventory.py \
  --plan build/host/current-inventory/plan.json --device-id esp32-YOUR_MAC \
  --backup build/host/private/inventory-backup.json --output evidence/new-inventory-run.json --profile
python3 host/test_dsp_mix.py
python3 host/qualify_mix.py --prepare build/host/dsp-mix/hardware-plan.json
```

Use separately audited images and `qualify_mix.py --mix 0` / `--mix 1` with the
same plan, distinct private backups and output paths. Tests activate temporary
RAM packages and never SAVE/INSTALL test patches. Restoration verifies graph and
source bytes, saved lists/generations, instance states and controls. Oscillator
phase and old reverb tails restart. The pilot cleanup log-lifetime mistake was
corrected and regression-tested; its original evidence and independent recovery
remain recorded. A later USB disappearance was confirmed by the user as an unplug,
and profiling resumed after reconnecting.
