#!/usr/bin/env python3
"""Validate the complete optimisation register and render its Markdown view."""
import argparse
import json
from collections import Counter
from pathlib import Path
from dsp_candidates import BINARY_SCALAR_SELECTORS, SMOOTH_TYPES, NOISE_TYPES
from dsp_binding import TYPE_FAMILIES
from dsp_routing import TYPES as ROUTING_TYPES
from dsp_chaos_cache import TYPES as CHAOS_TYPES
from dsp_core import TYPES as CORE_TYPES

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / 'docs/dsp_optimizations.json'
OUTPUT = ROOT / 'docs/OPTIMIZATION_REGISTER.md'
STATUSES = {
    'project': 'Project optimisation enabled',
    'inherited': 'Inherited FM1 fast path',
    'not_recorded': 'No enabled individual optimisation',
}


def link(path):
    return f'[{path}](../{path})'


def render(data):
    inventory = json.loads((ROOT / 'evidence/fm1-fixed-inventory.json').read_text())
    assert data['schema_version'] == 1
    additions = data.get('project_additions', {})
    assert not set(additions).intersection(inventory['types'])
    assert set(data['ugens']) == set(inventory['types']) | set(additions), 'UGen inventory changed; update register'
    capabilities = json.loads((ROOT / 'docs/capabilities.json').read_text())
    assert set(data['ugens']) == set(capabilities['compiled_types']), 'Compiled UGen inventory changed; update register'
    for entry in additions.values():
        assert entry['status'] == 'new implementation; no individual speed-up claimed'
        for field in ('implementation', 'host_evidence', 'hardware_evidence'):
            for path in entry[field]: assert (ROOT/path).is_file(), path
    for section, typename in [('unary', 'UnaryOpUGen'), ('binary', 'BinaryOpUGen')]:
        assert set(data[section]) == set(inventory['operators'][typename]), f'{section} inventory changed'
    groups = data['groups']
    candidates = data.get('candidates', [])
    by_id = {entry['id']: entry for entry in candidates}
    assert set(by_id['candidate-smoothing']['ugens']) == set(SMOOTH_TYPES)
    assert set(by_id['candidate-binary']['binary']) == set(map(str, BINARY_SCALAR_SELECTORS))
    assert set(by_id['candidate-noise']['ugens']) == set(NOISE_TYPES)
    assert set(by_id['candidate-binding']['ugens']) == {t for types in TYPE_FAMILIES.values() for t in types}
    assert set(by_id['candidate-routing']['ugens']) == set(ROUTING_TYPES)
    assert set(by_id['candidate-chaos']['ugens']) == set(CHAOS_TYPES)
    assert set(by_id['candidate-core']['ugens']) == set(CORE_TYPES)
    assert set(by_id['candidate-mix']['ugens']) == {'Sum3','Sum4','Pan2'}
    candidate_anchors = {entry['id'] for entry in candidates}
    assert len(candidate_anchors) == len(candidates), 'Duplicate candidate ID'
    assert not candidate_anchors.intersection(groups), 'Candidate/group anchor collision'
    candidate_rows = {'ugens': {}, 'unary': {}, 'binary': {}}
    for candidate in candidates:
        assert candidate['status'] in ('host-only; disabled by default','experimental; disabled by default')
        for section in candidate_rows:
            for name in candidate[section]:
                assert name in data[section], (section, name)
                candidate_rows[section].setdefault(name, []).append(candidate['id'])
        if 'metrics_record' in candidate:
            metrics = json.loads((ROOT/candidate['metrics_record']).read_text())
            assert metrics['hardware'] is False
            measurements = metrics['native_per_type']['measurements'] if candidate.get('metrics_kind')=='per-type' else metrics['native_throughput']['fixtures']
            for key in candidate['metrics_fixtures']:
                assert key in measurements
    for section in ('ugens', 'unary', 'binary'):
        for key, entry in data[section].items():
            assert entry['status'] in STATUSES, (section, key)
            assert entry['group'] is None or entry['group'] in groups, (section, key)
            assert (entry['status'] == 'not_recorded') == (entry['group'] is None)
            if entry['group']:
                assert entry['status'] == groups[entry['group']]['status']
            if entry['status']=='not_recorded':
                assert key in candidate_rows[section] or (section=='ugens' and key in additions), f'Unreviewed {section}: {key}'
    for group in [*groups.values(), *data['shared'], *data['experiments'], *candidates]:
        for field in ('implementation', 'host_evidence', 'hardware_evidence'):
            for path in group[field]:
                assert (ROOT / path).is_file(), f'Missing {field}: {path}'

    text = f'''# DSP optimisation register

Last reviewed: **{data['reviewed']}**. Applies to the shared AMOLED/XIAO DSP
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
does not automatically qualify the current image. The 13 November XIAO sweep
completed 332 long traces on build `b06188c54dbe`: 309 waveform passes,
22 statistical passes and the retained Klang float-tolerance exception.
Physical AMOLED verification remains separate. See
[current sweep](CURRENT_DSP_SWEEP.md) and [current status](../STATUS.md).

## Coverage summary

| Category | Project optimisation enabled | Inherited FM1 fast path | No enabled individual optimisation | Experimental candidate available |
| --- | ---: | ---: | ---: | ---: |
'''
    for section, label in [('ugens', 'Native UGen types'), ('unary', 'Unary selectors'), ('binary', 'Binary selectors')]:
        counts = Counter(e['status'] for e in data[section].values())
        text += f"| {label} | {counts['project']} | {counts['inherited']} | {counts['not_recorded']} | {len(candidate_rows[section])} |\n"
    text += '\nSelector totals are separate views of UnaryOpUGen/BinaryOpUGen, not additional native types. Candidate counts overlap production statuses.\n'
    text += '''
Every supported native type and selector now has a recorded implementation
review: an existing enabled/inherited path, an experimental candidate, or both.
New project additions are recorded separately without claiming a speed-up.
No supported entry remains unreviewed. This does **not** mean every candidate
is faster: negative timing differences are retained below and all new candidate
switches remain off. Constructor/state/arena and raw-scratch combined checks are
in [the final offline report](../evidence/dsp-all-host.json).
'''
    text += '\n## Recorded implementations\n'
    for key, group in groups.items():
        text += f"\n### {key}\n\n**{group['title']} — {STATUSES[group['status']]}**\n\n{group['scope']}\n"
        for field, label in [('implementation', 'Implementation'), ('host_evidence', 'Host verification'), ('hardware_evidence', 'Hardware evidence')]:
            paths = group[field]
            text += f"\n{label}: " + (', '.join(link(p) for p in paths) if paths else 'No separate record linked.') + '\n'
        text += f"\nQualification: {group['qualification']}\n"
    text += '\n## Native UGen checklist\n\n| UGen | Status | Work |\n| --- | --- | --- |\n'
    for name, entry in sorted(data['ugens'].items()):
        group = entry['group']
        work = f'[{group}](#{group})' if group else '—'
        if name in candidate_rows['ugens']:
            work += '; '+', '.join(f"[experimental candidate](#{key})" for key in candidate_rows['ugens'][name])
        if name in additions:
            work = 'New implementation; see project additions below'
        text += f"| {name} | {STATUSES[entry['status']]} | {work} |\n"
    if additions:
        text += '\n## Project additions\n'
        for name, entry in sorted(additions.items()):
            text += f"\n**{name}: {entry['status']}.** {entry['scope']}\n"
            for field, label in [('implementation','Implementation'),('host_evidence','Host verification'),('hardware_evidence','Hardware evidence')]:
                text += f'\n{label}: '+(', '.join(link(p) for p in entry[field]) or 'Pending.')+'\n'
    for section, title in [('unary', 'Unary operator checklist'), ('binary', 'Binary operator checklist')]:
        text += f'\n## {title}\n\n| Selector | Operation | Status | Applicable path |\n| ---: | --- | --- | --- |\n'
        for selector, entry in sorted(data[section].items(), key=lambda item: int(item[0])):
            scope = entry['scope']
            if selector in candidate_rows[section]:
                scope += '; '+', '.join(f"[experimental candidate](#{key})" for key in candidate_rows[section][selector])
            text += f"| {selector} | `{entry['name']}` | {STATUSES[entry['status']]} | {scope} |\n"
    text += '\n<a id="host-only-candidates"></a>\n\n## Experimental candidates\n'
    for entry in candidates:
        text += f"\n### {entry['id']}\n\n**{entry['title']} ({entry['status']}).** {entry['scope']}\n"
        for field, label in [('implementation', 'Implementation'), ('host_evidence', 'Host verification'), ('hardware_evidence', 'Hardware evidence')]:
            text += f"\n{label}: " + (', '.join(link(p) for p in entry[field]) or 'None for this candidate revision.') + '\n'
        if entry.get('hardware_coverage'):
            scope=entry['hardware_coverage']
            text += '\nHardware qualification: '+scope['scope']+' Native types observed: '+(', '.join(scope['native_types']) or 'none')+'. Binary selectors observed: '+(', '.join(scope['binary_selectors']) or 'none')+'.\n'
        if entry.get('hardware_metrics_record'):
            target=json.loads((ROOT/entry['hardware_metrics_record']).read_text())
            assert target['passed'] and target['hardware'] and target['fixed_seed'] and target['comparison']['passed']
            text+='\nXIAO fixed-seed measurements, 44.1 kHz / 64 frames, three trials per whole test graph. '+entry['hardware_metrics_scope']+' Negative percentages indicate a slowdown.\n\n'
            text+='| Test graph | Baseline, µs/block | Candidate, µs/block | Less target DSP time |\n| --- | ---: | ---: | ---: |\n'
            for name,row in target['comparison']['fixtures'].items():
                text+=f"| {name} | {row['baseline_us']:.2f} | {row['candidate_us']:.2f} | {row['less_time_percent']:.2f}% |\n"
        if 'metrics_record' in entry:
            metrics=json.loads((ROOT/entry['metrics_record']).read_text())
            text+='\nDesktop-only selected fixture measurements (whole graph, three trials). ' if entry.get('metrics_kind')=='per-type' else '\nDesktop-only 32-node bank measurements (whole graph; trial counts in evidence). '
            text+='These are not isolated node costs or ESP32 predictions.\n\n'
            text+='Negative percentages mean the candidate was slower in that fixture.\n\n'
            text+='| Bank | Before, µs/block | Candidate, µs/block | Less native time |\n| --- | ---: | ---: | ---: |\n'
            for key in entry['metrics_fixtures']:
                row=(metrics['native_per_type']['measurements'] if entry.get('metrics_kind')=='per-type' else metrics['native_throughput']['fixtures'])[key]
                if row.get('timing_unavailable'):
                    text+=f'| {key} | Unavailable | See evidence | — |\n';continue
                count=row['trials'][0]['iterations']
                before=row['median_reference_seconds'];after=row['median_candidate_seconds']
                label=f"`{data['binary'][key.removeprefix('Binary_')]['name']}` (selector {key.removeprefix('Binary_')})" if key.startswith('Binary_') else key
                text+=f'| {label} | {before*1e6/count:.3f} | {after*1e6/count:.3f} | {(1-after/before)*100:.1f}% |\n'
    for section, title in [('shared', 'Shared engine improvements'), ('experiments', 'Disabled experiments')]:
        text += f'\n## {title}\n'
        for entry in data[section]:
            text += f"\n**{entry['title']} ({entry['status']}).** {entry['scope']}\n"
            for field, label in [('implementation', 'Implementation'), ('host_evidence', 'Host verification'), ('hardware_evidence', 'Hardware evidence')]:
                text += f"\n{label}: " + (', '.join(link(p) for p in entry[field]) or 'No separate record linked.') + '\n'
    text += '''
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
'''
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Validate without rewriting')
    args = parser.parse_args()
    text = render(json.loads(REGISTER.read_text()))
    if args.check:
        if OUTPUT.read_text() != text:
            parser.exit(1, 'Optimisation page is stale; run host/document_optimizations.py\n')
        data = json.loads(REGISTER.read_text())
        print(f"Optimisation register: {len(data['ugens'])} UGens, "
              f"{len(data['unary'])} unary and {len(data['binary'])} binary selectors; page is current.")
    else:
        OUTPUT.write_text(text)
        print(f'Updated {OUTPUT.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
