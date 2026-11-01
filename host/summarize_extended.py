#!/usr/bin/env python3
"""Summarize completed extended tests without converting drift into exact agreement."""
import collections,json
from pathlib import Path
from engine_profile import ROOT
def read(name):return json.loads((ROOT/'evidence'/f'{name}.json').read_text())
base=read('fm1-extended-device');fixed=read('fm1-fixed-edges-device');cost=read('fm1-cost-profile')
regression=read('gendy-boundary-regression');reference=read('fm1-fixed-reference');fuzz=read('fm1-fixed-fuzz');drift=read('klang-long-drift')
assert base['status']==fixed['status']==cost['status']=='complete'
assert fixed['passed'] and regression['passed'] and reference['passed'] and fuzz['passed'] and drift['pcm_check_passed']
assert all(r['packages_unchanged'] and r['library_unchanged'] for r in (base,fixed))
stats={name:read(name) for name in ('long-trace-chaotic-statistics','long-trace-device-statistics','long-trace-edges-statistics','long-trace-edges-device-statistics')}
assert all(r['passed'] for r in stats.values())
captures=base['captures']+fixed['captures'];exercises=base['exercises']+fixed['exercises']
assert len(captures)==338 and all(int(r['device'][k])==0 for r in captures for k in ('faults','nonfinite','guards','initial_accepts'))
assert all(r['reported_output_checks_passed'] and r['timing_budget_passed'] for r in exercises)
assert cost['passed'] and cost['library_unchanged']
pairs={tuple(p) for r in captures for p in r['type_rates']};types={p[0] for p in pairs}
assert len(types)==154
grades=collections.Counter(r['comparison']['comparison'] for r in captures)
exceptions=[r['id'] for r in captures if not r['comparison']['passed']];assert exceptions==['klang']
summary={'completed':True,'functional_and_memory_checks_passed':True,'all_strict_float_comparisons_passed':False,
    'type_count':len(types),'observed_fixture_type_rate_pairs':258,'captured_type_rate_pairs_including_probes':len(pairs),'long_graph_runs':len(captures),
    'long_graph_capture_grades':dict(grades),'capture_duration_seconds':8192*64/44100,'virtual_stereo_frames_checked':len(captures)*8192*64,
    'operators':{'unary':33,'binary':40,'rates':['initial','control','audio'],'initial_value_changes_rejected_after_prepare':30,'restart_changes_accepted':6},
    'bug_fixed':'Gendy3 incorrectly rejected the allocated closing segment after discarding sub-sample breakpoints. Audio-rate and slow control-rate regressions now pass on ESP32.',
    'current_build':fixed['hello']['build'],'old_sweep_build':base['hello']['build'],'soak_rounds':sum(r['rounds'] for r in exercises),
    'soak_seconds':sum(r['rounds']*30 for r in exercises),'patch_activations':base['patch_churn']['patch_activations']+fixed['patch_churn']['patch_activations'],
    'fixed_image_soak_maximum_us':{r['patch']:r['maximum']['combined_max_us'] for r in fixed['exercises']},
    'precision_exceptions':{'klang':drift,'stochastic':'Statistical-only grades remain distinct from waveform agreement; independent SC long-record statistics also pass.'},
    'reference_fixtures_passed':len(reference['results']),'fuzz_inputs':fuzz['mutated_or_truncated_inputs'],
    'library_packages_unchanged':True,'final_slot':cost['final_status']['slot'],'final_state':'Mac Sine restored, original effect settings restored, Panic requested',
    'limits':['Only representative fixture/rate combinations and selected parameter edges, not exhaustive domains','Some Rings graphs and dense operator banks exceed real-time budgets','Klang fails the stricter long float threshold but remains within one S16 output step','Statistical comparisons do not establish waveform or identical-state hardware equivalence','No external clock, latency, physical continuity or thermal measurement']}
(ROOT/'evidence/extended-validation.json').write_text(json.dumps(summary,indent=2)+'\n')
text=f'''# Extended ESP32 testing — 31 October 2026

The extended pass completed **{len(captures)} long graph runs** spanning all
**154 UGen types**, the **258 type/rate pairs present in the fixture set**, and
all **33 unary / 40 binary operators at initial, control and audio rate**.
Each long run rendered 8,192 blocks (11.89 seconds), checked every output for
faults/nonfinite values, guarded both ends of the DSP arena, and captured 40
stereo blocks across startup, updates and tails. These are representative tests,
not exhaustive parameter-domain or arbitrary-graph performance certification.

## Result grades

| Hardware versus native C | Graph runs |
| --- | ---: |
| Within declared float waveform limits | {grades['waveform']} |
| Statistical consistency only | {grades['statistical-only']} |
| Stricter float mismatch, within one S16 output step (`Klang`) | {grades['failed']} |

No long hardware run reported a renderer fault, nonfinite output or damaged
arena guard. The main sweep contains the Klang float mismatch and therefore
retains `passed: false`; it has not been relabelled as a strict float pass.
The separate Klang output conversion check measures **one PCM step** maximum
across 2,560 captured mono samples (raw float peak difference approximately
1.07e-5). The statistical grades use the declared distribution/roughness
envelopes and remain separate from sample identity.

Independent SuperCollider 3.14.1 NRT comparisons cover the long recordings too:
208/224 main graphs and 92/114 edge graphs satisfy their waveform limits; the
remaining 16 and 22 precision-sensitive generator traces satisfy statistical
consistency checks. Long Gendy statistics are explicitly an extension beyond
the original short-fixture waveform criteria. The original **1,444-fixture
reference suite** also passes after the fix, using its pinned waveform/timing/
statistical criteria. The Gendy identical-state oracle passes 2,795,520 samples
and 707,707 distribution inputs on the host. This is not an identical-state
hardware oracle. A fresh 1,560,000-input sanitizer fuzz pass also succeeds.

The SC control-update timestamps are placed inside the intended control block
to avoid OSC timestamp rounding applying an update one block early. The input
bus test uses a reference-only ReplaceOut wrapper so the provider's dry signal
is not counted twice. Original pinned source/fixtures remain unchanged.

## Gendy3 bug found and fixed

The pinned engine rejected `index == active` after Gendy3 discarded a duration
shorter than one sample. That index denotes its allocated zero-valued closing
segment; rejecting it stopped an otherwise valid voice. The 64-point audio-rate
case failed after about eight seconds, and a 0.1 Hz control-rate case failed
after about ten seconds. The old half-second fixtures had not reached the fault.

The audited target generator now permits that closing segment, holds its next
amplitude at zero, and retains rejection for indices beyond it. No arithmetic
precision, random-number order or ordinary segment equation is reduced.
The vendored snapshot is untouched. Before/after regressions reproduce both
faults and pass after the fix; 60-second runs cover five sample rates and five
explicit RandSeed values. Both formerly failing cases pass on the ESP32 with
zero captured float difference. The edge sweep covers all 81 Gendy fixtures,
Rings forced/bypass cases, negative delay/comb/allpass cases, MiVerb freeze and
saturation, and the extra slow-control regression.

## Live stress and saved data

There were **24 thirty-second rounds / 12 minutes** of reduced-level playback
and UI stress, plus **60 patch activations**. The pre-fix image completed 18
rounds; the fixed image repeated six. Four synth controls and three delay
controls changed, including 20 ms–5 s delay, 0–0.8 feedback, 0–1 wet, pitch and
attack/release extremes and frequent retriggers. No reported write failures,
partial writes, DMA errors, numerical faults, clipping, queue overflow or
70%-margin violations occurred in those live exercises.

| Fixed-image voice | Worst combined block | 64/44.1 kHz block |
| --- | ---: | ---: |
'''
for r in fixed['exercises']:text+=f"| {r['patch']} | {r['maximum']['combined_max_us']} µs | 1,451 µs |\n"
minimum={k:min(r['minimum'][k] for r in fixed['exercises']) for k in ('internal_min','internal_largest','stack_free_bytes')}
text+=f'''
The fixed-image exercises retained at least {minimum['internal_min']:,} internal
bytes free, a {minimum['internal_largest']:,}-byte largest internal block and
{minimum['stack_free_bytes']:,} unused audio-stack bytes. The diagnostic uses a
temporary guarded arena while the owner is parked and the codec is muted; it
does not allocate in the live renderer. Telemetry-gap messages during this
maintenance state do not indicate a DMA failure.

Saved graph/source/metadata packages read back unchanged. No patch SAVE was
issued. Mac Sine and the original delay settings were restored, with Panic
requested at the end. The intermittent USB reset issue is not claimed fixed.

## Actual CPU limitations

The additional muted matrix separates synchronous memory reset, constructor,
first-audio and live-block cost. These graphs use the fixture's original default
parameters; the added seven-control interface is test plumbing, not a musical
patch converter. The measurements exclude the persistent effect and normal UI
exercise, so they are not complete instrument timing qualifications.

| Diagnostic graph | Constructor maximum | First audio maximum | Live block incl. PCM |
| --- | ---: | ---: | ---: |
'''
for r in cost['results']:
    m=r['phase_maximum_us'];text+=f"| {r['id']} | {m['prepare']:.0f} µs | {m['dsp']:.0f} µs | {m['live']:.0f} µs |\n"
text+='''
In these tests, Rings models 2/5/6 have both expensive startup and roughly
1.4–1.6 ms live blocks before the master effect. They need performance work
before live use at this configuration. Dense banks evaluating every operator
simultaneously are also too costly; an operator being supported does not mean
every combination fits a 64-frame deadline. Models 1/3/4 are lighter but still
need patch-specific timing with the effect and UI. No fast-math or precision
reduction was used to make these tests pass.

## Evidence and reproduction

- [Combined summary](../evidence/extended-validation.json)
- [Main sweep, patch changes and 18 live rounds](../evidence/fm1-extended-device.json)
- [Fixed-image edges and six live rounds](../evidence/fm1-fixed-edges-device.json)
- [Constructor versus live cost](../evidence/fm1-cost-profile.json)
- [Gendy3 before/after regression](../evidence/gendy-boundary-regression.json)
- [Klang float drift and S16 conversion](../evidence/klang-long-drift.json)
- [Fixed-image original reference suite](../evidence/fm1-fixed-reference.json)
- [Fixed-image fuzz results](../evidence/fm1-fixed-fuzz.json)
- [Current fixed target build](../evidence/fm1-gendy-fixed-build.json)
- [Per-UGen/operator ledger](UGEN_SUPPORT.md)

```sh
python3 host/test_gendy_boundary.py
python3 host/long_trace.py
python3 host/long_trace.py --edges --output evidence/long-trace-edges-plan.json
python3 host/compare_long_sc.py
python3 host/compare_long_sc.py --plan evidence/long-trace-edges-plan.json --output evidence/long-trace-edges-sc.json
# Hardware commands require the matching diagnostic image and observed port:
python3 host/test_device_long.py --port PORT --output evidence/fm1-extended-device.json --rounds 6 --churn 10
python3 host/test_device_long.py --port PORT --plan evidence/long-trace-edges-plan.json --output evidence/fm1-fixed-edges-device.json --rounds 2 --churn 5
python3 host/profile_expensive_graphs.py --port PORT --output evidence/fm1-cost-profile.json
python3 host/summarize_extended.py
```

The historical main sweep predates the Gendy fix. Re-running it now tests the
current image rather than recreating that older binary's identity. Preserve
prior evidence if comparing builds.
'''
(ROOT/'docs/EXTENDED_TESTS.md').write_text(text)
print('Documented extended coverage, the fixed Gendy fault, precision grades and CPU limits')
