#!/usr/bin/env python3
"""Summarise the computer-only review and audit unchanged production DSP source."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
from engine_profile import ROOT,generate
from document_optimizations import render


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',default='368d267',help='Qualified pre-candidate commit to compare')
    args=parser.parse_args()
    register=json.loads((ROOT/'docs/dsp_optimizations.json').read_text())
    assert render(register)==(ROOT/'docs/OPTIMIZATION_REGISTER.md').read_text()
    covered={name for entry in register['candidates'] for name in entry['ugens']}
    existing={name for name,entry in register['ugens'].items() if entry['status']!='not_recorded'}
    unreviewed=sorted(set(register['ugens'])-covered-existing);assert not unreviewed
    full=json.loads((ROOT/'evidence/dsp-all-host.json').read_text())
    assert full['passed'] and not full['hardware'] and not full['device_access']
    address=json.loads((ROOT/'evidence/dsp-address-runtime.json').read_text())
    result=full['reports']['all-vs-production'];edges=result['four_rate_edges']
    assert result['passed'] and edges['passed']
    old_source=subprocess.check_output(['git','show',args.baseline+':host/engine_profile.py'],cwd=ROOT,text=True)
    namespace={'__file__':str(ROOT/'host/engine_profile.py'),'__name__':'baseline_profile'}
    exec(compile(old_source,'baseline_engine_profile.py','exec'),namespace)
    baseline_commit=subprocess.check_output(['git','rev-parse',args.baseline],cwd=ROOT,text=True).strip()
    audit={}
    for profile in ('compact','fm1'):
        before=namespace['generate'](ROOT/f'build/host/dsp-review-audit/baseline/{profile}/src',profile)
        after=generate(ROOT/f'build/host/dsp-review-audit/default/{profile}/src',profile)
        hashes={}
        for path in sorted(before.iterdir()):
            if path.suffix not in ('.c','.h','.inc'):continue
            assert path.read_bytes()==(after/path.name).read_bytes(),(profile,path.name)
            hashes[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
        flags=json.loads((after.parent/'profile.json').read_text())['candidate_kernels'];assert not any(flags.values())
        audit[profile]={'compiled_sources_identical':True,'source_sha256':hashes,'candidate_flags':flags}
    outcomes={}
    for entry in register['candidates']:
        record=json.loads((ROOT/entry['metrics_record']).read_text())
        table=record['native_per_type']['measurements'] if entry.get('metrics_kind')=='per-type' else record['native_throughput']['fixtures']
        outcomes[entry['id']]={}
        for key in entry['metrics_fixtures']:
            row=table[key]
            if row.get('timing_unavailable'):outcomes[entry['id']][key]={'timing_unavailable':True};continue
            before=row['median_reference_seconds'];after=row['median_candidate_seconds']
            outcomes[entry['id']][key]={'less_native_time_percent':(1-after/before)*100,'trials':len(row['trials']),
                                       'source_report':entry['metrics_record'],'scope':'Desktop whole-graph measurement; not isolated node cost or ESP32 performance.'}
    objects=full['xtensa_objects']['all-vs-production']
    builds={}
    for board in ('amoled','xiao'):
        name=f'evidence/dsp-review-{board}-default-build.json'
        record=json.loads((ROOT/name).read_text())
        assert not any(record['engine_profile']['candidate_kernels'].values())
        assert record['compiled_loader_types_checked_in_target_object']==len(register['ugens'])
        builds[board]={'record':name,'status':record['status'],'build_id':record['build_id'],
                       'app_bytes':record['app_bytes'],'candidate_flags':record['engine_profile']['candidate_kernels'],
                       'target_structure_sizes':record['target_structure_sizes']}
    report=dict(passed=True,reviewed='2026-11-04',hardware=False,device_access=False,audio_playback=False,
                production_candidates_enabled=False,baseline_commit=baseline_commit,
                native_ugen_count=len(register['ugens']),unary_count=len(register['unary']),binary_count=len(register['binary']),
                native_baseline_statuses=dict(Counter(e['status'] for e in register['ugens'].values())),
                native_types_with_candidates=len(covered),unreviewed_native_types=unreviewed,
                combined_comparison={'graphs':result['graphs'],'samples':result['samples'],
                                     'four_rate_edge_graphs':edges['graphs'],'four_rate_edge_samples':edges['samples'],
                                     'total_output_samples':result['samples']+edges['samples'],'sanitizers':full.get('sanitizers',['undefined','bounds','float-cast-overflow']),
                                     'scope':full['comparison'],'record':'evidence/dsp-all-host.json'},
                optional_address_sanitizer=address,
                production_source_audit=audit,
                default_firmware_cross_builds=builds,
                unlinked_xtensa_text_bytes={'before':objects['reference']['text_bytes'],'all_candidates':objects['target']['text_bytes'],
                                           'increase':objects['target']['text_bytes']-objects['reference']['text_bytes']},
                native_results=outcomes,
                cautions=['Some native fixtures regress; all candidates remain off by default.',
                          'Cached-field normalization excludes only documented previously-unused fields; recursive state, RNG, arena and raw scratch remain checked.',
                          'Earlier prototype operator reports predate the signed-zero fix; final full comparisons and corrected operator measurements supersede them.',
                          'Old measurements retain their own source/build scope; current combined correctness does not turn desktop timings into hardware evidence.',
                          'Firmware flash/IRAM placement, whole-call-stack headroom and board timing are future hardware qualification work, excluded from this goal.'])
    (ROOT/'evidence/dsp-review-summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('native_results','production_source_audit')},indent=2))


if __name__=='__main__':main()
