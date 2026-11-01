#!/usr/bin/env python3
"""Keep numerical verification distinct from Rings real-time qualification."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read(name):return json.loads((ROOT/'evidence'/name).read_text())
baseline=read('fm1-cost-profile.json');hot=read('rings-hot-cost.json')
fast=read('rings-fast-cost.json');cache=read('rings-cache-cost.json')
live=read('rings-cache-live-device.json');long=read('rings-regression-device.json')
memory=read('rings-full-arena-device.json');build=read('rings-cache-build.json')
reference=read('rings-cache-reference-device.json')
assert cache['status']==live['status']==long['status']==memory['status']=='complete'
assert len(cache['results'])==12 and len(live['matrices'])==6 and len(live['exercises'])==9 and len(long['captures'])==24
assert reference['status']=='complete' and len(reference['matrices'])==7
assert all(r['hello']['build']==build['build_id'] for r in (cache,live,long,memory,reference))
lookup=lambda report:{row['id']:row['phase_maximum_us'] for row in report['results']}
costs=list(map(lookup,(baseline,hot,fast,cache)));rows=[]
for model in range(1,7):
    key=f'm13_MiRings{model}_live';values=[cost[key] for cost in costs]
    rows.append(dict(model=model,baseline=values[0],iram=values[1],internal_arena=values[2],larger_caches=values[3],
        live_reduction_percent=round(100*(1-values[3]['live']/values[0]['live']),2)))
budget=64/44100*1e6
exercises=[]
for entry in live['exercises']:
    exercises.append(dict(patch=entry['patch'],combined_max_us=entry['maximum']['combined_max_us'],
        within_block_deadline=entry['maximum']['combined_max_us']<=budget,
        within_70_percent_margin=entry['timing_budget_passed'],
        output_checks_passed=entry['reported_output_checks_passed'],output_counter_delta=entry['output_counter_delta']))
numeric=cache['passed'] and all(row['numerical']['passed'] for row in live['matrices']) and long['passed'] and memory['passed'] and reference['passed']
report=dict(validation_completed=True,all_workloads_realtime_qualified=all(e['within_70_percent_margin'] and e['output_checks_passed'] for e in exercises),
    numerical_and_memory_checks_passed=numeric,selected_build=build['build_id'],selected_cache=build['cache'],
    selected_internal_voice_arena_bytes=build['synth_fast_arena_internal_bytes'],
    selected_binary_sha256=next(value for name,value in build['sha256'].items() if name.endswith('/waveshare_synthdef.bin')),
    cost_comparison=rows,live_exercises=exercises,minimum=live['minimum'],
    matrix_graphs=26,matrix_cases=26*280,long_graphs=24,long_blocks_per_graph=8192,
    master_delay_echo_windows=reference['master_delay'],
    long_capture_grades=[row['comparison']['comparison'] for row in long['captures']],
    live_exercise_seconds=sum(row['rounds']*30 for row in live['exercises']),
    saved_packages_unchanged=live['packages_unchanged'] and long['packages_unchanged'],
    saved_library_unchanged=all(row['library_unchanged'] for row in (cache,live,long,memory,reference)),
    full_synth_arena_bytes=memory['arena_bytes'],
    fixes=['Bound Rings initialization avoids redundant whole-arena clearing; standalone oracle initializer retains its original contract',
        'Reserve large internal allocations and task stacks before display/NVS startup; optional arena can fall back to PSRAM',
        'LVGL task requests internal byte-addressable RAM including the reserved internal pool',
        'Exercise reports attribute cumulative error-counter increments to the patch that caused them'],
    limits=['Moving-control Rings workloads remain separately graded; no blanket real-time qualification',
        'Original raw-fixture timing excludes the master effect and normal UI exercise',
        'Digital timing/counter checks do not establish physical continuity, clock accuracy or audible quality',
        'Intermittent USB software-reset behavior is not claimed generally fixed'])
(ROOT/'evidence/rings-optimization.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({key:report[key] for key in ('validation_completed','numerical_and_memory_checks_passed','all_workloads_realtime_qualified','saved_packages_unchanged')},indent=2))
table='\n'.join(f'| {r["model"]} | {r["baseline"]["prepare"]:.0f} → {r["larger_caches"]["prepare"]:.0f} | {r["baseline"]["live"]:.0f} → {r["larger_caches"]["live"]:.0f} | {r["live_reduction_percent"]:.1f}% |' for r in rows)
ui='\n'.join(f'| {e["patch"]} | {e["combined_max_us"]:,} | {"Pass" if e["within_70_percent_margin"] else "Above target"} | {sum(e["output_counter_delta"].values())} |' for e in exercises)
text=f'''# Rings optimization — 31 October 2026

This optimization pass validated **{build['build_id'][:12]}**, using a 32 KiB instruction
cache, 64 KiB data cache and 64-byte data-cache lines. Rings processing code
remains in internal instruction RAM. The optional 66 KiB voice arena is disabled
by default; voices retain their full 1 MiB PSRAM arena and the persistent master
effect retains a separate 1 MiB arena. No sample-rate, float32 precision, lookup
table, string-capacity or DSP-equation reduction was made.

## Measured rendering costs

These maxima compare the original fixed image (`d816a0e97c8e`) with the selected
cache build, using the same muted 280-case diagnostic per original fixture.
Live time includes control application, rendering and PCM conversion, but
excludes the master effect and normal UI exercise. Added interface controls are
unused by those original fixtures, so the table does not qualify pitch extremes.

| Rings model | Preparation before → after, µs | Live before → after, µs | Live reduction |
| --- | ---: | ---: | ---: |
{table}

The bound-voice constructor avoids a second whole-buffer clear: binding or
bounded deferred clearing has already established zeroed, non-overlapping node
slices. The standalone initializer used by the independent reference retains
its original clear. Four existing Rings routines occupy 16,665 bytes of internal
instruction RAM before linker alignment/literals. Vendored sources remain
unchanged; the checked target copy is generated by `host/engine_profile.py`.

## Actual musical voices with display and master delay

Six new SuperCollider diagnostic voices connect pitch, structure, brightness,
damping, amplitude and gate. Each exercise runs for 30 seconds with four synth
controls and three master-delay controls changing at 25 Hz, plus five note
starts per second. The existing three voices were exercised on the same image.
Rings voices use a fixed 5 ms attack / 150 ms release.

The nominal 64-frame deadline at 44.1 kHz is **1,451 µs**; the project's 70%
target is **1,016 µs**. The measured combined time includes synth, master effect
and PCM conversion.

| Voice | Combined maximum, µs | 70% target | New output/error events |
| --- | ---: | --- | ---: |
{ui}

All nine selected-build exercises reported no new output faults, nonfinite
values, clipping, control-queue overflow or DMA event-queue overflow. **Rings
models 2, 5 and 6 nevertheless exceeded the block deadline at some settings.**
Only model 3's tested musical graph met the 70% target. The other Rings graphs
remain experimental; numerical support is not blanket real-time qualification.

The three existing voices improved from 954/916/951 µs in the dedicated-arena
comparison to 738/663/731 µs here (Filtered Tone / Phase FM / Harmonic Mix).
This is one 30-second round per voice on the selected image, separate from the
earlier extended soak recorded in `EXTENDED_TESTS.md`.

## Numerical, memory and saved-state checks

- **26 muted matrices / 7,280 cases** passed within one S16 step of native C.
  They cover original Rings fixtures, real-control voices, existing voices,
  unary/binary operators and the full synth arena.
- **24 long hardware captures** each rendered 8,192 blocks (11.89 seconds).
  Every captured stereo window matched native C exactly. Full-duration fault,
  finite-output and arena-guard checks passed; the new voices release to silence.
  These are 40 sparse windows per graph, not a continuous exported recording.
- Master-delay first/second echoes at 20 ms, 350 ms, 1 s and 5 s, plus post-Panic
  zeros, matched native C exactly.
- The full **1 MiB synth arena** passed its matrix, early-note cancellation and
  normal incremental start/play/release. Its bounded clearing and calculated
  full-arena startup interval remain as described in `MEMORY.md`.
- Earlier host checks on the unchanged DSP transformation pass 1,445 voice
  lifecycle graphs, 18 byte-identical pre/post native captures, 132 independent
  Rings waveform cases and 28 additional compact-capacity/domain cases. The
  domain cases are not claimed as waveform matches beyond compact pitch limits.
- The selected live run retained at least **{live['minimum']['internal_min']:,}
  internal bytes**, a **{live['minimum']['internal_largest']:,}-byte** largest
  free block, **{live['minimum']['stack_free_bytes']:,}** unused audio-stack bytes
  and **{live['minimum']['controls_stack_free_bytes']:,}** unused control-stack bytes.
- Saved graph/source/metadata packages and library generations read back
  unchanged. Helpers restore the selected saved patch and original effect
  controls and request Panic. No diagnostic voices were saved.

## Allocation problems found and fixed

The first 66 KiB arena trial (`7d463159450b`) could not create the USB task after
display startup. Reserving stacks first (`1bc71d838891`) recovered safely through
PSRAM fallback, but crowded out a voice-state allocation. Allocating largest
objects first, then reserving task stacks before display/NVS setup, retained the
arena (`859d15a810df`). Mandatory allocation failures release the optional arena.
The two static task-control blocks total 680 bytes; stack sizes remain 16 KiB.

The dedicated arena left only 26,459 internal bytes free and improved steady
Rings cost little beyond code placement. Its moving-control Rings 6 test
produced 849 DMA event-queue overflows. The selected cache layout preserves more
headroom and removed those events in the repeated tests, so the arena stays off.

The larger-cache trial also exposed an LVGL startup allocation failure:
`INTERNAL|DEFAULT` excluded IDF's reserved internal pool. The display task now
requests `INTERNAL|8BIT`, keeping its stack internal while permitting that pool.
Display startup, normal UI exercises and USB control now work on the selected
image. The compact UI configuration also cross-compiles with these fixes.

Exercise reporting now measures increments in cumulative error counters. This
attributes the 849 events to the failing Rings 6 run rather than later clean
patches; regression checks cover that attribution. Failed trial records remain
in the evidence folder and are not counted as successful qualification.

## Reproduction and evidence

Apply `host/fm1-cache.defaults` after `firmware/sdkconfig.defaults` to a fresh
SDKCONFIG with ESP-IDF 5.5. Defaults do not override an existing configuration.
From the repository root:

```sh
python3 host/prepare.py
project_dir="$PWD"
SYNTHDEF_BUILD_DIR=build-fm1-cache host/idf.sh \\
  -D SDKCONFIG="$project_dir/build/host/fm1-cache-sdkconfig" \\
  -D "SDKCONFIG_DEFAULTS=$project_dir/firmware/sdkconfig.defaults;$project_dir/host/fm1-cache.defaults" build
python3 host/export_rings.py
python3 host/prepare_rings_plan.py
```

After loading that FM1 build, replace PORT with the board port:

```sh
python3 host/profile_expensive_graphs.py --port PORT --output evidence/rings-cache-cost.json
python3 host/test_device_rings.py --port PORT --rounds 1 --arena-storage PSRAM --output evidence/rings-cache-live-device.json
python3 host/test_device_long.py --port PORT --plan evidence/rings-regression-plan.json --rounds 0 --churn 0 --output evidence/rings-regression-device.json
python3 host/test_device_synth_memory.py --port PORT --playback --output evidence/rings-full-arena-device.json
python3 host/test_device_fm1.py --port PORT --output evidence/rings-cache-reference-device.json
python3 host/summarize_rings.py
```

The matrices/long captures are muted; UI and full-arena playback use reduced
amplitude. `evidence/rings-optimization.json` separates numerical verification
from timing qualification. Detailed provenance and allocation measurements are
in `rings-cache-build.json`, `rings-cache-live-device.json` and the named device
reports. Source build IDs are shared by configuration variants; configuration
and binary hashes in build records distinguish them.

Physical continuity, clock accuracy, latency and thermal behavior have not been
measured externally. Intermittent USB software-reset behavior is not claimed
generally fixed. No Rings diagnostic graph has been promoted into the catalog.
'''
(ROOT/'docs/RINGS_OPTIMIZATION.md').write_text(text)
