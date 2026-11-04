# DSP hardware qualification plan

Prepared **4 November 2026**. The [first selected-case session](DSP_HARDWARE_RESULTS.md)
has now run on XIAO; broader stages remain planned. No board was connected,
queried or written while initially preparing this plan. Production candidate switches
remain off. This plan covers the shared AMOLED/XIAO engine, with separate checks
for their mono speaker and stereo I²S adapters.

## Start with one 30-minute session

The first session uses **one board and two firmware variants**, not nine.
Build and audit both images, compile the musical patches, prepare reference
digests and sort out the test runner **before the board is available**.
Prefer the XIAO with the known PCM5102A wiring for the first numerical/audio
session. An available AMOLED V2 can be used first instead, provided its diagnostic
capture supports the required raw floats; its mono speaker alone is not enough.

| Time budget | Action | Useful result |
| --- | --- | --- |
| 0–3 min | Q0: identify the exact module, save Main/FX/settings and confirm recovery files | A reversible session tied to one physical module |
| 3–8 min | Baseline image: run the 50-case muted pack and three short timing trials per selected workload | Same-board reference output/state and CPU figures |
| 8–10 min | Install the all-candidates image and verify its build/configuration identity | Candidate measurement tied to an actual image |
| 10–15 min | Repeat the identical muted pack and timing workloads | Exactness comparison and aggregate speed/regression |
| 15–23 min | Main/FX/tail tests, volume/panic, short SC pattern and listening comparison | Real instrument behavior, not just an isolated kernel result |
| 23–26 min | Investigate one discrepancy if needed; otherwise repeat the noisiest timing pair | A focused follow-up instead of a full sweep |
| 26–30 min | Restore original packages/settings/instance state; save the report | Explicit restoration result and next-session checkpoint |

These are time budgets, not measured test durations. USB recovery can consume
the reserve. Stop starting new cases at minute 26 and finish restoration/reporting.
Do not rush restoration to finish the test list. If only 15 minutes are available,
run the muted A/B pack and one representative workload, then restore; defer the
listening and network checks. No skipped test is recorded as passed.

The initial session is a **selected-case qualification**, not proof that every
UGen/input combination works or that every candidate improves performance.
The machine plan records the full backlog without requiring it all in one visit.

## Prepared inventory and fixtures

Run these **computer-only** commands to regenerate/check the package:

```sh
python3 host/plan_dsp_hardware.py
python3 host/plan_dsp_hardware.py --check
```

The checked-in [machine plan](dsp_hardware_plan.json) maps all **154 native
types, 33 unary and 40 binary selectors** to fixture hashes and candidate families.
It includes:

- **50 first-session raw fixtures**: 24 tiny signed-zero compositions and 26
  representative smoothing, noise, routing, chaos, oscillator/bank and input-binding
  probes. Representatives exercise all seven candidate families and all ten
  changed input-binding entry points; this is not all 72 input-binding UGen types.
- A **324-graph structural coverage set** covering every inventory UGen/rate and
  operator/rate. This is an extended sweep, not the first-session checklist.
- **1,444 pinned graphs**, one supporting project graph, and **896 generated
  edge graphs**: **2,341 distinct fixture IDs** for optional deeper regression.
- Thirteen musical/integration source cases, including the corrected five-voice
  Comb Cloud AR and KR variants, eight-Saw/Resonz/MiVerb, dynamic banks, Rings,
  triggered harmonics, note/touch controls and separate FX processors.

Generated raw binaries go under `build/host/dsp-hardware-plan/fixtures/`.
They are **muted diagnostic inputs**, not an autoplay playlist: some contain DC,
extreme parameters, signed zeros or deliberate fault-domain tests. The generator
does not execute `.play`, compile/flash firmware, open serial ports or send Wi-Fi.
Source-only musical cases are marked uncompiled in this plan. The inventory
contains no hardware results, and creating a fixture does not qualify it.

## Q0 — identity, preparation and restoration

Before touching slots, record physical module ID, board revision, image hash/build
ID, all candidate flags, toolchain/SDK configuration, 44,100 Hz and 64-frame
blocks. Record the configured/observed CPU frequency; use cycle counts directly
if the frequency cannot be verified. Do not assume 350 MHz. The current profiler's
`*_at_240mhz` convenience conversion is valid only for a confirmed 240 MHz run.

Save original Main and stored FX packages, their graph/source hashes, active
instance states, FX bypass and volume. Use private recovery files and the existing
ownership guards; do not restore over an unrelated patch uploaded by another
writer. Keep Wi-Fi credentials/pairing intact; an application-only firmware change
must not erase NVS or the patch filesystem. Firmware recovery and package
restoration are separate: retain the known-good image as well as patch backups.

After the session, verify package hashes, bypass, volume and active/inactive
states. Recreated oscillators restart and old reverb tails are lost; do not claim
phase/tail restoration. On an interrupted test, record the last complete case and
restore or explicitly report incomplete restoration before starting more tests.

## Q1 — establish an identical comparison

The two initial variants are:

1. **Baseline**: current production optimisations enabled; all seven new candidate
   switches false. This checks recent enabled filters, Lag/LagUD/LeakDC, unary
   cache paths, sine/Dust/Decay/Saw/Pulse and MiVerb as part of the baseline too.
2. **All candidates**: exactly the same configuration with the seven new switches
   true. The packed MiVerb experiment stays false. Graph limits, buffer reuse,
   float32, block size and sample rate stay identical.

Use the same physical board, graph bytes, seeds, input samples and parameter
schedule for A/B. Compile each graph once and reuse its bytes. Fixed-seed replay
is needed for noise, Gendy, triggered random UGens and chaotic initialization;
normal sound-block uploads intentionally randomize instances and cannot serve
as an exactness oracle without this diagnostic override.

Verify the generated profile flags in each **linked image**. An unchanged image
on the board is not a test of disabled candidates. CMake candidate selection and
the target build audit now record these flags. The follow-up
[fixed-seed profiler](DSP_SEEDED_PROFILING.md) adds deterministic workload timing;
the original live-snapshot timing must not be treated as seed-locked across images.

## Q2 — compact numerical/state pack

Run the 24 signed-zero graphs for **32 blocks** each and the other 26 compact
probes for **256 blocks** each at 44.1 kHz. This is 7,424 blocks, or about
**10.8 seconds of synthesized block time per variant**, before diagnostic,
transfer and installation overhead. The pack is intended for one batched RAM
diagnostic session, not 50 filesystem uploads and flash writes.

| Focus | High-value cases and expected behavior |
| --- | --- |
| Binary signed zero | All 24 selector/swapped-operand compositions, including downstream `atan2`. Preserve `-0.0` versus `+0.0`; post-mix/16-bit PCM alone can conceal this bug. |
| Smooth/history | Lag3 held-time changes and OneZero audio input; unchanged, changing and zero parameters. Constructor histories and output order match. Expand to all six smooth UGens only if this family needs attribution. |
| RNG | Interleaved White/Pink/LFNoise/Dust/GrayNoise and RandSeed. Compare RNG words and output, not just statistical similarity. A seed trigger must neither skip nor consume an extra random word. |
| Routing/initial rate | DC.ir and Select.ir retain their initial values; RandSeed edge/repeat behavior stays exact. Alternating Main/FX must not overwrite cached initial-rate values. |
| Chaos | HenonN and LatoocarfianL changing frequency through zero, low rates and cycle boundaries; recurrence and interpolation state match. |
| Core caches | Line/XLine endpoint/done-action edges; five-partial Klang/Klank; dynamic SinOscFB, Blip, Formant, Gendy3, BPeakEQ, Amplitude and Formlet. Change each cached parameter independently and after a held run. |
| Bound inputs | Above probes plus CombC, MiVerb, MiRings1, Pluck, FreqShift, Latch and XFade2 cover all ten modified entry points. Check constructor scratch, multi-output routes and per-sample input indexing. |

Port the **actual replay schedule** in `tests/dsp_kernels_test.c` rather than
sending approximate wall-clock SC messages. The constructor/control changes
occur at exact block indices, with input buffers recreated identically. Preserve
fixture IDs: the current reference schedule dispatches some dynamic profiles by
fixture-name substring. Seed `12345 + block_index` on each restart, restart every
128 blocks, prepare twice, and poison scratch exactly as the host suite does.
Pin the schedule source hash with the graph hashes in each report.

Use raw stereo float bits **before output mixing/gain/PCM** as appropriate for
the check, plus constructor/render scratch, recursive voice/partial state, RNG,
active/fault flags and every allocated delay-arena byte. Compare after preparation
and after every block. Normalize only the exact documented otherwise-unused
candidate cache fields and pointer addresses; never normalize recursive state or
ignore an output just because it is inaudible.

To keep RAM/IRAM layout representative, prefer **sequential baseline/candidate
replay images** with block digests and first-mismatch snapshots, rather than
linking both complete renderers into one real-time firmware image. Use per-block
streaming SHA-256 digests with separate output/state/scratch/arena components;
hashing/protocol overhead is excluded from performance trials. Re-run a mismatch
with a bounded detailed dump. Digest checks alone do not provide a byte offset.

**Pass:** baseline and candidate on the same target give identical float/state
bits after approved normalization. Deliberately invalid domains must give the
same fault behavior and terminate cleanly; they are not fault-free playback cases.
Host-versus-Xtensa library-math differences must first be characterized on the
baseline; do not relax a target-to-target mismatch into an RMS tolerance.

## Q3 — short, useful performance trials

Time the normal renderer, without per-node probes or state hashing. Keep
volume, UI/Wi-Fi state, placement, arenas and clocks the same. Muting by scaling
PCM must not bypass Main/FX rendering. Use these four workloads in the first visit:

| Workload | Why it earns time |
| --- | --- |
| Eight-Saw/Resonz/MiVerb | The user's real heavy graph; oscillator, noise, smoothing, filter and reverb work together. Separate FX slot bypassed. |
| Corrected five-voice Comb Cloud KR | Operators, noise/triggers, cached coefficients, panning and delay binding; compare to its own baseline, not the AR patch's CPU. |
| Triggered harmonics | Fast repeated random updates, normalized amplitudes and control-rate decays. |
| Triggered harmonics → separate MiVerb FX | Input binding and Main/FX shared workspace, with a live tail. |

Use a short warm-up, then **three two-second measurement windows per workload
per image**. Record normal DSP cycles/block, average and window-peak combined
audio microseconds, fault/DMA/write/queue counters and free/minimum RAM/largest
block/stack headroom. A two-second window is a minimum; discard incomplete or
stale telemetry rather than substituting zero. Do not infer p99 from window
maxima: a per-block histogram would be additional instrumentation.

At 44.1 kHz, 64 frames give **1,451.25 µs per block**. Use
`100 × combined_us / 1451.25` for audio deadline usage. CPU here is not total
dual-core utilization. Per-node profiler shares include their probe overhead;
they explain a bottleneck but do not replace the uninstrumented A/B result.

Compare medians and run-to-run spread, retaining all raw windows. If the apparent
gain is smaller than the measured spread, label it **inconclusive**. Repeat only
that workload, preferably baseline → candidate → baseline, before spending time
on other graphs. Five paired runs are reserved for confirming a promotion,
not required for every initial case. Old desktop percentages are prioritization
information, not target acceptance thresholds.

**Pass for the initial session:** report correctness and aggregate timing
separately; no new runtime faults, DMA/write failures or unexplained audio dropouts
in normal workloads. An already-heavy workload may exceed a deadline; preserve
that result and compare its incidence rather than hiding peaks or stopping an
otherwise useful diagnostic. It cannot establish comfortable real-time headroom.

## Q4 — isolate only what needs attention

Seven one-family variants are listed in the manifest for **conditional** use.
They are not seven extra mandatory flashes. If the combined build fails:

- Re-run the first failing fixture with detailed state and block/control data.
- For a family-specific fixture, enable just that family against baseline.
  If overlap makes attribution unclear, bisect the relevant flag set rather
  than exhaustively trying all 128 flag combinations.
- If output is exact but a musical workload slows down, use the existing muted
  per-node profiler to choose the suspected family, then measure normal rendering
  with that flag isolated. Profile one representative expensive graph first.
- Keep a slower/inconclusive flag off. Formant, Klang, feedback oscillators,
  delay loops and binding stack costs deserve measurement despite desktop results.

For an individual family to be enabled by default, require target exactness,
repeatable improvement on a useful target workload, acceptable linked IRAM/flash
and stack costs, and no material regressions in its intended workloads. A mixed
family can be split into smaller switches later; do not promote 18 core types
just because Line became faster. Enabling the combined image during a test is
not a production promotion. Run the final selected flag subset once too.

## Q5 — real instrument behavior and listening

Once muted comparisons pass, listen at the existing 20% output setting, adjusting
to a useful listening level. Use the same Main/FX and volume in each A/B pair.
Begin with recognizable, bounded sounds rather than raw edge fixtures.

1. Play eight-Saw/Resonz/MiVerb and Comb Cloud KR for approximately 20 seconds
   each. Confirm pitch/control motion and clean transitions. AR Cloud is the
   first optional follow-up, not a required extra first-session benchmark.
2. Feed a short burst into separate MiVerb; then a 350 ms CombC/Delay path.
   Stop excitation and observe/listen for the complete tail. Allow up to 60 seconds
   for the long-tail case; compare identical windows and do not declare an effect
   silent just because a one-second capture missed its first echo.
3. Run a short gated pattern at 4–8 notes/second. Check attack/release/retrigger,
   stop and restart, exposed Main and FX arguments and pattern cancellation.
4. Change Main while FX is active. Check the existing approximately 5 ms fades,
   zero hold through replacement and preserved FX behavior. Check bypass,
   smoothed volume/mute and Panic. The retained transition test supplies objective
   PCM checks separately from a listening opinion.

Capture on XIAO is post-volume stereo PCM and checks the digital sink path;
listen through the PCM5102A separately. AMOLED requires mono adapter/speaker
listening. A raw engine match does not establish either analogue output path.
Record each listening answer as **pass / concern / not assessed**, never infer
that it passed from a clean numerical capture.

## Q6 — second board, about 15 minutes

After the reference board's exactness checks, use the same selected candidate
flags on the other board. Confirm firmware identity, startup and no new faults;
run a few representative muted cases, the heavy patch, one long-tail effect,
Main/FX routing and restoration. On AMOLED also check touch press/release, drag,
scroll strips, Controls, volume and UI activity during sound. On XIAO check left,
right and stereo PCM5102A routing. In Studio check CPU values are live and attached
to the correct module, and stale data disappears.

This second-board visit qualifies its integration only. A numerical or speed
claim about that board requires its own corresponding checks and, for a speed
comparison, a same-board baseline. XIAO headroom does not qualify AMOLED's UI/
codec/Wi-Fi memory or scheduling.

## Q7 — deferred, resumable coverage and stress

Only if more time is available:

- Run missing cases from the 324-graph structural set in batches, then the
  generated 512-block edge suite and full pinned set as needed. Report per-type,
  selector, output rate and input layout coverage; a combined all-selector sound
  graph alone is not individual numerical certification.
- Prioritize remaining binding types and cache transitions: all 14 chaos models,
  three EQs, three Gendys, 1/5/32/64-partial banks and all legal ar/kr/ir paths.
  Add independent coefficient changes, equal/unequal time constants, below-zero/
  Nyquist boundaries, segment ends, seed replay/reseed and after-reload histories.
- Time the next family's representative cases only after the musical result
  indicates a useful opportunity. Avoid 154 isolated benchmarks on the first visit.
- Run a **10-minute soak** with notes, parameter changes, a long effect and UI/
  Wi-Fi activity. Rotate a fixed small set of patches in RAM where possible;
  use only a few persistent uploads for the actual storage path, not continuous
  flash writes. Track post-warm-up memory trend, largest free block, stack minima,
  faults, queue rejection, DMA/write errors and new resets. Separate expected
  allocation/layout changes from a progressive leak.
- Briefly repeat near the user's normal heavy load and with Wi-Fi busy. Treat
  poor RSSI/host timeouts separately from DSP corruption. Multi-module throughput
  and router capacity remain a different test programme.

Checkpoint by board ID, image/profile hash, fixture hash, schedule hash and seed.
Resume only missing cases whose comparison context is unchanged. Configuration
or source changes invalidate affected previous results rather than silently
carrying them into a newer build. The optional 8/48/192 kHz offline arithmetic
probes are not evidence that the 44.1 kHz codec firmware supports those I²S rates.

## Q8 — decision and report

For each actual case, retain variant/flags and exact graph/source/schedule hashes,
board/configuration/clock, sample rate/block size, seed/restarts, comparison mode,
complete counter deltas, raw timing windows, memory/stack minima and restoration.
An absent field or stale telemetry means **incomplete**, not zero consumption.

Use separate outcomes: **numerically exact**, **timing improved / unchanged /
regressed / inconclusive**, **real-time integration passed**, **listened**,
**not run**, **failed**, and **restored / restoration incomplete**. Overall pass
requires the mandatory cases of the selected session tier; it must not imply
that deferred tiers ran. Never overwrite old evidence or auto-enable flags from
a report. Update the optimisation register only with the measured scope.

## What exists and what must be ready before hardware time

| Item | Current state |
| --- | --- |
| Coverage inventory, two-build fast tier, conditional family variants, fixture hashes | Prepared by `host/plan_dsp_hardware.py`; no device I/O |
| Host exact replay, cache normalization and edge/input schedules | Existing `tests/dsp_kernels_test.c` and host candidate tests |
| Muted per-node profiling and guarded package restoration | Existing helpers in `host/profile_ugens.py`, `host/qualify_dsp_kernels.py`, `host/qualify_headless.py` |
| XIAO PCM capture, Main/FX, long delays and transitions | Existing qualification tools; adapt their scopes rather than assuming they test new flags |
| Candidate firmware selection/build audit | Implemented with explicit CMake options; none/all/family selections and optional binding-entry masks. Standard defaults remain off. |
| Batched in-RAM target float/state/scratch replay | Implemented for the 50-case pack. Constructor/block data feeds four whole-case SHA-256 streams. Per-block exports and first-mismatch byte dumps remain future work. |
| Runner, checkpoints and report merging | Explicit replay/workload/listening CLIs and phase reports implemented. Full deadline enforcement, per-case resume and broader pack selection remain future work. |
| Hardware results/listening | XIAO baseline/all/narrow comparisons and user-confirmed PCM5102A listening recorded; see the linked results. AMOLED and broader tiers remain pending. |

Do not run legacy `host/test_device_*.py` scripts indiscriminately: some assume
older slot layouts, use direct USB ownership or replace stored slots without the
new session guard. The current kernel timing helper also assumes headless by
default and covers four workloads, not the complete new candidate matrix.
Commands above prepare the plan only. The separate execution helpers described
in the results access hardware when invoked; there is no automatic all-stage
flash/qualification command.
