#!/usr/bin/env python3
"""Prepare a hardware test inventory locally; never opens a device or plays audio.

This is a plan/fixture generator, NOT a hardware runner or firmware installer.
Prepared raw graphs require the muted diagnostic harness described in the plan.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from engine_profile import ROOT
from synthdef_binary import decode, encode
from core_fixtures import fixtures as core_fixtures
from routing_fixtures import fixtures as routing_fixtures
import test_dsp_candidates as candidates
from dsp_chaos_cache import TYPES as CHAOS_TYPES

OUTPUT = ROOT/'docs/dsp_hardware_plan.json'
BUILD = ROOT/'build/host/dsp-hardware-plan'
FLAGS = {
    'candidate-smoothing':'candidate_smooth', 'candidate-binary':'candidate_binary',
    'candidate-noise':'candidate_noise', 'candidate-binding':'candidate_binding',
    'candidate-routing':'candidate_routing', 'candidate-chaos':'candidate_chaos',
    'candidate-core':'candidate_core',
}
MUSIC = {
    'eight-saw':'module-audio-check', 'comb-ar':'comb-cloud-efficient', 'comb-kr':'comb-cloud-kr',
    'klank':'klank-cloud-fixed', 'dynklank':'dynklank', 'dynklang':'dynklang',
    'triggered-harmonics':'triggered-harmonics', 'rings':'mirings1-try',
    'touch':'touch-buses', 'notes':'gated-sine', 'fx-bypass':'master-bypass',
    'fx-delay':'master-delay', 'fx-reverb':'hardware-qualification/master-reverb',
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def tokens(graph):
    result=set()
    for typ,rate,refs,rates,selector in graph['nodes']:
        result.add(('type',typ,rate))
        if typ in ('UnaryOpUGen','BinaryOpUGen'):
            result.add((typ,str(selector),rate))
    return result


def required_tokens(register, inventory):
    result={('type',typ,rate) for typ in register['ugens'] for rate in inventory['types'][typ]['rates']}
    for kind,key in (('UnaryOpUGen','unary'),('BinaryOpUGen','binary')):
        result.update((kind,op,rate) for op in register[key] for rate in inventory['operators'][kind][op]['rates'])
    return result


def select_cover(graphs, required):
    """Deterministic small baseline sweep; the full pinned set remains required later."""
    pending=set(required); chosen=[]
    while pending:
        name=min(graphs,key=lambda name:(-len(graphs[name][1]&pending),name))
        hit=graphs[name][1]&pending
        if not hit:raise ValueError('No fixture covers '+repr(sorted(pending)))
        chosen.append(name);pending-=hit
    return chosen


def build_plan():
    register=json.loads((ROOT/'docs/dsp_optimizations.json').read_text())
    inventory=json.loads((ROOT/'evidence/fm1-fixed-inventory.json').read_text())
    required=required_tokens(register,inventory)
    graphs={}
    base=ROOT/'upstream/fm1-synthdef/synthdef-engine/fixtures'
    for p in sorted(base.glob('*.scsyndef')):
        data=p.read_bytes();graphs['pinned/'+p.stem]=(data,tokens(decode(data)))
    # The inventory also records this project's In.ar and control-rate sqrt path.
    data=(ROOT/'examples/master-delay.scsyndef').read_bytes()
    graphs['reference/master-delay']=(data,tokens(decode(data)))
    smoke=select_cover(graphs,required)
    pinned=[name for name in graphs if name.startswith('pinned/')]
    supporting=[name for name in graphs if name.startswith('reference/')]
    with tempfile.TemporaryDirectory(prefix='dsp-hardware-plan-') as temp:
        folder=Path(temp)
        old=candidates.BUILD
        try:
            candidates.BUILD=folder
            paths=candidates.fixtures()+routing_fixtures(folder)+core_fixtures(folder)
        finally:candidates.BUILD=old
        for p in paths:
            data=p.read_bytes();graphs['edges/'+p.stem]=(data,tokens(decode(data)))
        for typ in CHAOS_TYPES:
            p=base/(inventory['types'][typ]['fixtures'][0]+'.scsyndef')
            g=decode(p.read_bytes());nodes=[]
            for name,rate,refs,rates,special in g['nodes']:
                shifted=[(n+1 if n>=0 else n,o) for n,o in refs]
                if name==typ:shifted[0]=(0,0)
                nodes.append((name,rate,shifted,rates,special))
            try:zero=g['constants'].index(0)
            except ValueError:zero=len(g['constants']);g['constants'].append(0)
            g['nodes']=[('In',1,[(-1,zero)],[1],0)]+nodes
            data=encode(g);graphs['edges/chaos_dynamic_'+typ]=(data,tokens(g))
    prepared={}
    for name,(data,coverage) in sorted(graphs.items()):
        relative='build/host/dsp-hardware-plan/fixtures/'+name+'.scsyndef'
        path=ROOT/relative;path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists() or path.read_bytes()!=data:path.write_bytes(data)
        graph=decode(data)
        prepared[name]=dict(path=relative,sha256=digest(data),bytes=len(data),nodes=len(graph['nodes']),
                            coverage=[list(token) for token in sorted(coverage)],
                            execution='muted-diagnostic-only',hardware_status='planned')
    variants={'baseline':dict.fromkeys(FLAGS.values(),False)}
    for name,flag in FLAGS.items():variants[name]=dict(variants['baseline'],**{flag:True})
    variants['all-candidates']=dict.fromkeys(FLAGS.values(),True)
    # Bounded first session: composed sign witnesses plus one representative of
    # every candidate family. This intentionally does not qualify all 154 types.
    first_session=sorted(name for name in graphs if name.startswith('edges/Binary_signed_zero_'))
    first_session += ['edges/'+name for name in (
        'Lag3_2_1_normal','OneZero_2_2_normal','Noise_interleaved_seed',
        'Routing_DC_0_0','Routing_Select_0_0','Routing_RandSeed_2_1',
        'chaos_dynamic_HenonN','chaos_dynamic_LatoocarfianL',
        'core_Line_2_0.001_0','core_XLine_2_0.001_0','core_Klang_5','core_Klank_5',
        'core_dynamic_SinOscFB','core_dynamic_Blip','core_dynamic_Formant',
        'core_dynamic_Gendy3','core_dynamic_BPeakEQ','core_dynamic_Amplitude','core_dynamic_Formlet')]
    for typ in ('CombC','MiVerb','MiRings1','Pluck','FreqShift','Latch','XFade2'):
        options=[name for name in pinned if ('type',typ,2) in graphs[name][1]]
        if not options:raise ValueError('No first-session audio fixture for '+typ)
        first_session.append(min(options))
    first_session=list(dict.fromkeys(first_session))
    assert all(name in prepared for name in first_session)
    coverage={}
    for typ,row in sorted(register['ugens'].items()):
        membership=[c['id'] for c in register['candidates'] if typ in c['ugens']]
        coverage[typ]=dict(production_status=row['status'],existing_group=row['group'],
            candidate_groups=membership,rates=inventory['types'][typ]['rates'],
            smoke_fixtures=[name for name in smoke if any(t[:2]==('type',typ) for t in graphs[name][1])],
            required_phases=['Q1','Q2','Q3','Q4'] if membership else ['Q1','Q2'],hardware_status='planned')
    operators={}
    for kind,key in (('UnaryOpUGen','unary'),('BinaryOpUGen','binary')):
        operators[key]={}
        for op,row in sorted(register[key].items(),key=lambda item:int(item[0])):
            operators[key][op]=dict(name=row['name'],rates=inventory['operators'][kind][op]['rates'],
                smoke_fixtures=[name for name in smoke if any(t[:2]==(kind,op) for t in graphs[name][1])],
                candidate_groups=[c['id'] for c in register['candidates'] if op in c[key]],hardware_status='planned')
    groups={c['id']:dict(flag=FLAGS[c['id']],types=c['ugens'],binary=c['binary'],unary=c['unary'],
                        desktop_report=c['metrics_record'],hardware_status='planned') for c in register['candidates']}
    plan=dict(schema_version=1,prepared='2026-11-04',status='planned-not-executed',hardware_tested=False,
        device_access=False,firmware_written=False,production_defaults_changed=False,
        plan_document='docs/DSP_HARDWARE_TEST_PLAN.md',
        scope='Inventory and raw fixtures only. Build wiring, block-exact target replay and the new hardware runner are not implemented by this generator.',
        source_sha256={name:digest((ROOT/name).read_bytes()) for name in (
            'docs/dsp_optimizations.json','evidence/fm1-fixed-inventory.json','host/plan_dsp_hardware.py',
            'docs/DSP_HARDWARE_TEST_PLAN.md','host/engine_profile.py','host/dsp_candidates.py',
            'host/dsp_binding.py','host/dsp_routing.py','host/dsp_chaos_cache.py','host/dsp_core.py',
            'host/core_fixtures.py','host/routing_fixtures.py','host/test_dsp_candidates.py','tests/dsp_kernels_test.c')},
        boards=['xiao-esp32s3-pcm5102a','waveshare-touch-amoled-1.8-v2'],
        audio_config=dict(rate=44100,block_frames=64,block_budget_us=64/44100*1e6),
        firmware_variants=variants,candidate_groups=groups,ugen_coverage=coverage,operator_coverage=operators,
        fixture_sets=dict(first_session=first_session,extended_structural_cover=smoke,full_pinned=pinned,supporting_reference=supporting,
                          generated_edges=[name for name in prepared if name.startswith('edges/')]),
        fixture_counts=dict(first_session=len(first_session),extended_cover=len(smoke),pinned=len(pinned),supporting_reference=len(supporting),
                            edges=len(prepared)-len(pinned)-len(supporting),total=len(prepared)),
        fixtures=prepared,
        musical_cases={name:dict(source='examples/'+stem+'.scd',sha256=digest((ROOT/'examples'/ (stem+'.scd')).read_bytes()),
                                compiled=False,hardware_status='planned') for name,stem in MUSIC.items()},
        phases=['Q0','Q1','Q2','Q3','Q4','Q5','Q6','Q7','Q8'],
        timeboxed_sessions=dict(
            first=dict(minutes=30,boards=1,variants=['baseline','all-candidates'],
                raw_fixture_set='first_session',raw_blocks=256,signed_zero_blocks=32,
                musical_cases=['eight-saw','comb-kr','triggered-harmonics','fx-reverb'],
                timing_trials=3,timing_seconds_per_trial=2,
                result_scope='Selected-case check and aggregate timing only; no full per-type or per-family promotion.',
                on_failure='Keep remaining diagnostics saved; attribute with only the relevant isolated flag, or defer if time expires.'),
            second_board=dict(minutes=15,boards=1,variants=['all-candidates'],
                result_scope='Board-specific integration/listening on the already numerically checked build; add same-board baseline before claiming speed-up.'),
            extended=dict(optional=True,fixture_set='extended_structural_cover',
                note='Run remaining coverage and isolated attribution in resumable batches; never required to finish in the first session.')),
        replay_contract=dict(status='specified-not-implemented',reference='tests/dsp_kernels_test.c',
            rate=44100,seed_formula='12345 + zero-based block number at each restart',
            restart_every_blocks=128,prepare_calls_per_restart=2,
            first_session_blocks=256,edge_blocks=512,
            note='Port all existing block-specific control/input schedules exactly; source/hash plus constants alone do not define the output.'),
        hardware_results=[])
    # Structural coverage is not evidence that any of these graphs ran on a board.
    assert set(coverage)==set(register['ugens'])
    assert all(row['smoke_fixtures'] for row in coverage.values())
    assert all(row['smoke_fixtures'] for rows in operators.values() for row in rows.values())
    assert not any(variants['baseline'].values()) and len(variants)==9
    assert sum(bool(row['candidate_groups']) for row in coverage.values())==112
    return plan


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true',help='Rebuild local fixtures and check the checked-in plan is current')
    args=parser.parse_args()
    plan=build_plan();text=json.dumps(plan,indent=2)+'\n'
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text()!=text:parser.exit(1,'Hardware plan is out of date; run python3 host/plan_dsp_hardware.py\n')
    else:OUTPUT.write_text(text)
    print(json.dumps(dict(status=plan['status'],ugens=len(plan['ugen_coverage']),
        unary=len(plan['operator_coverage']['unary']),binary=len(plan['operator_coverage']['binary']),
        variants=len(plan['firmware_variants']),fixtures=plan['fixture_counts'],
        hardware_tested=False,manifest=str(OUTPUT.relative_to(ROOT))),indent=2))


if __name__=='__main__':main()
