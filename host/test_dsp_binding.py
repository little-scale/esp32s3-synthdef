#!/usr/bin/env python3
"""Offline exact input-binding regression; no device/network/audio operations."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import statistics
import time
import test_dsp_candidates as suite
from engine_profile import ROOT, generate
from dsp_binding import TYPE_FAMILIES
from dsp_routing import TYPES as ROUTING_TYPES
from dsp_chaos_cache import TYPES as CHAOS_TYPES
from dsp_core import TYPES as CORE_TYPES
from core_fixtures import fixtures as core_fixtures
from routing_fixtures import fixtures as routing_fixtures
from synthdef_binary import decode,encode

BUILD=ROOT/'build/host/dsp-binding'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--benchmark',action='store_true',help='Measure each affected type using a representative native fixture')
    parser.add_argument('--routing',action='store_true',help='Test routing candidate instead of input binding')
    parser.add_argument('--chaos',action='store_true',help='Test cycle-period cache instead of input binding')
    parser.add_argument('--core',action='store_true',help='Test oscillator/bank/ramp/Gendy candidates')
    parser.add_argument('--all',action='store_true',help='Compare all candidates together against production defaults')
    parser.add_argument('--address',action='store_true',help='Also enable AddressSanitizer; results stored separately')
    args=parser.parse_args()
    global BUILD
    assert sum((args.routing,args.chaos,args.core,args.all))<=1
    assert not(args.all and args.benchmark),'Use the per-family benchmarks for attribution'
    mode='all' if args.all else 'core' if args.core else 'chaos' if args.chaos else 'routing' if args.routing else 'binding'
    if args.routing:BUILD=ROOT/'build/host/dsp-routing'
    if args.chaos:BUILD=ROOT/'build/host/dsp-chaos-cache'
    if args.core:BUILD=ROOT/'build/host/dsp-core'
    if args.all:BUILD=ROOT/'build/host/dsp-all-candidates'
    if args.address:BUILD=BUILD.with_name(BUILD.name+'-address')
    families={'candidate_core':CORE_TYPES} if args.core else {'candidate_chaos':CHAOS_TYPES} if args.chaos else {'candidate_routing':ROUTING_TYPES} if args.routing else TYPE_FAMILIES
    BUILD.mkdir(parents=True,exist_ok=True)
    if args.address:
        probe=BUILD/'asan-preflight.c';probe.write_text('int main(void){return 0;}\n')
        binary=BUILD/'asan-preflight'
        suite.run(['cc','-fsanitize=address',probe,'-o',binary])
        started=time.monotonic()
        try:
            trial=subprocess.run([str(binary)],capture_output=True,text=True,timeout=5)
            available=trial.returncode==0;detail=trial.stderr[-2000:]
        except subprocess.TimeoutExpired:
            available=False;detail='Even an empty C program times out before main under this AddressSanitizer runtime.'
        runtime=dict(available=available,hardware=False,device_access=False,dsp_tests_executed=False,
                     compiler=suite.run(['cc','--version']).splitlines()[0],elapsed_seconds=time.monotonic()-started,
                     detail=detail,scope='Optional local memory-checker startup probe; not a DSP failure or a passing sanitizer run.')
        (ROOT/'evidence/dsp-address-runtime.json').write_text(json.dumps(runtime,indent=2)+'\n')
        if not available:parser.exit(2,'AddressSanitizer runtime unavailable before main; recorded in evidence/dsp-address-runtime.json.\n')
    suite.BUILD=BUILD
    paths=suite.fixtures()
    if args.routing or args.all:paths+=routing_fixtures(BUILD)
    if args.core or args.all:paths+=core_fixtures(BUILD)
    dynamic=[]
    if args.chaos or args.all:
        inventory=json.loads((ROOT/'evidence/fm1-fixed-inventory.json').read_text())
        for typ in CHAOS_TYPES:
            path=ROOT/'upstream/fm1-synthdef/synthdef-engine/fixtures'/(inventory['types'][typ]['fixtures'][0]+'.scsyndef')
            g=decode(path.read_bytes());nodes=[]
            for name,rate,refs,rates,special in g['nodes']:
                shifted=[(n+1 if n>=0 else n,o) for n,o in refs]
                if name==typ:shifted[0]=(0,0)
                nodes.append((name,rate,shifted,rates,special))
            try:zero=g['constants'].index(0)
            except ValueError:zero=len(g['constants']);g['constants'].append(0)
            g['nodes']=[('In',1,[(-1,zero)],[1],0)]+nodes
            p=BUILD/f'chaos_dynamic_{typ}.scsyndef';p.write_bytes(encode(g));dynamic.append(p)
        paths+=dynamic
    edge_paths=list(paths)
    paths+=sorted((ROOT/'upstream/fm1-synthdef/synthdef-engine/fixtures').glob('*.scsyndef'))
    paths+=sorted((ROOT/'examples').glob('*.scsyndef'))
    paths+=sorted((ROOT/'build/host/dsp-kernels').glob('*.scsyndef'))
    reports={}
    contexts=[('all-vs-production',False)] if args.all else [(mode+'-only',False),('combined',True)]
    for name,other in contexts:
        flags=dict(candidate_smooth=other,candidate_binary=other,candidate_noise=other)
        if args.routing:flags['candidate_binding']=other
        if args.chaos:flags.update(candidate_binding=other,candidate_routing=other)
        if args.core:flags.update(candidate_binding=other,candidate_routing=other,candidate_chaos=other)
        reference=generate(BUILD/name/'reference/src','fm1',**flags)
        if args.all:
            target=generate(BUILD/name/'target/src','fm1',**dict.fromkeys(('candidate_smooth','candidate_binary','candidate_noise','candidate_binding','candidate_routing','candidate_chaos','candidate_core'),True))
        else:target=generate(BUILD/name/'target/src','fm1',**{'candidate_'+mode:True},**flags)
        define='DSP_ALL_CANDIDATES' if args.all else 'DSP_CORE_COMPARISON' if args.core else 'DSP_CHAOS_COMPARISON' if args.chaos else 'DSP_BINDING_COMPARISON'
        binary=suite.executable(reference,target,True,inventory=True,defines=(define,),address=args.address)
        result=json.loads(suite.run([binary,*paths],env={**os.environ,'DSP_TEST_BLOCKS':'64','DSP_TEST_RATE':'44100'}))
        result['profile']=json.loads((target.parent/'profile.json').read_text())['candidate_binding_sites']
        reports[name]=result
        if args.all:
            reports[name]['four_rate_edges']=json.loads(suite.run([binary,*edge_paths],env={**os.environ,'DSP_TEST_BLOCKS':'512'}))
        if args.chaos:
            reports[name]['four_rate_dynamic']=json.loads(suite.run([binary,*dynamic],env={**os.environ,'DSP_TEST_BLOCKS':'512'}))
        if args.core:
            probes=[p for p in paths if p.stem.startswith('core_')]
            reports[name]['four_rate_edges']=json.loads(suite.run([binary,*probes],env={**os.environ,'DSP_TEST_BLOCKS':'512'}))
    # This test performs no hardware timing. Compile actual Xtensa renderer
    # objects and retain size/stack information for each independent context.
    roots=sorted((Path.home()/'.espressif/tools/xtensa-esp-elf').glob('*/xtensa-esp-elf/bin'))
    target_objects={}
    if roots:
        prefix=str(roots[-1]/'xtensa-esp32s3-elf-')
        for name in reports:
            target_objects[name]={}
            for variant in ('reference','target'):
                src=BUILD/name/variant/'src';obj=BUILD/name/(variant+'.o')
                flags=['-std=gnu99','-Os','-mlongcalls','-mtext-section-literals','-ffunction-sections','-fdata-sections','-fno-jump-tables','-fno-tree-switch-conversion','-fno-fast-math','-ffp-contract=off','-fstack-usage']
                suite.run([prefix+'gcc',*flags,'-I'+str(src),'-c',src/'fm_render.c','-o',obj])
                size=suite.run([prefix+'size',obj]);stack=obj.with_suffix('.su').read_text()
                target_objects[name][variant]={'text_bytes':int(size.splitlines()[-1].split()[0]),'stack_usage':stack.splitlines()}
    report=dict(passed=True,hardware=False,device_access=False,audio_playback=False,production_enabled=False,
                sanitizers=['undefined','bounds','float-cast-overflow']+(['address'] if args.address else []),
                comparison='Bit-identical output and recursive voice/RNG/flags/arena fields; only caller-owned pointers and '+('documented otherwise-unused candidate cache fields normalized; constructor scratch compared too.' if args.all else 'documented new core invariant-cache fields normalized.' if args.core else 'new chaos freq/b1/b2 fields outside chaos_state normalized.' if args.chaos else 'no DSP cache fields normalized.'),
                reports=reports,xtensa_objects=target_objects,
                source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ('host/dsp_binding.py','host/dsp_routing.py','host/dsp_chaos_cache.py','host/dsp_core.py','host/core_fixtures.py','host/routing_fixtures.py','host/engine_profile.py','host/test_dsp_binding.py','host/test_dsp_candidates.py','tests/dsp_kernels_test.c')})
    if args.benchmark:
        suite.BUILD=BUILD/'timing';suite.BUILD.mkdir(exist_ok=True)
        reference=BUILD/(mode+'-only')/'reference/src';target=BUILD/(mode+'-only')/'target/src'
        binary=suite.executable(reference,target,False,defines=('DSP_CORE_COMPARISON',) if args.core else ('DSP_CHAOS_COMPARISON',) if args.chaos else ())
        inventory=json.loads((ROOT/'evidence/fm1-fixed-inventory.json').read_text())
        measurements={}
        for typ in sorted({t for types in families.values() for t in types}):
            candidates=[]
            for stem in inventory['types'][typ]['fixtures']:
                options=[ROOT/'upstream/fm1-synthdef/synthdef-engine/fixtures'/(stem+'.scsyndef'),ROOT/'examples'/(stem+'.scsyndef')]
                path=next((p for p in options if p.is_file()),None)
                assert path,stem
                candidates.append(path)
            candidates.sort(key=lambda p:(len(decode(p.read_bytes())['nodes']),p.name))
            if args.core and typ in ('Line','XLine'):
                candidates=[BUILD/f'core_{typ}_2_1000_0.scsyndef']+candidates
            failures=[]
            for path in candidates[:6]:
                try:
                    trials=[json.loads(suite.run([binary,'--benchmark',path])) for _ in range(3)]
                except RuntimeError as error:
                    failures.append({'fixture':path.name,'error':str(error)[-1500:]});continue
                before=statistics.median(row['reference_seconds'] for row in trials)
                after=statistics.median(row['candidate_seconds'] for row in trials)
                measurements[typ]={'fixture':str(path.relative_to(ROOT)),'graph_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                                   'graph_nodes':len(decode(path.read_bytes())['nodes']),'trials':trials,
                                   'median_reference_seconds':before,'median_candidate_seconds':after,
                                   'less_native_time_percent':(1-after/before)*100,'prior_failed_attempts':failures}
                break
            else:
                measurements[typ]={'timing_unavailable':True,'failed_attempts':failures}
        report['native_per_type']={'scope':'Three native steady-state whole-graph trials per type; results are representative-graph costs, not isolated node costs or ESP32 predictions. Both final voice/RNG/arena state and final audio block must match after 1,024 warm and 16,384 timed blocks.',
                                   'measurements':measurements}
        report['source_sha256']['tests/dsp_candidates_test.c']=hashlib.sha256((ROOT/'tests/dsp_candidates_test.c').read_bytes()).hexdigest()
    suffix='-address' if args.address else ''
    output=ROOT/f'evidence/dsp-{mode}{suffix}-host.json'
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':True,'reports':{k:{'graphs':v['graphs'],'samples':v['samples']} for k,v in reports.items()},
                      'timed_types':sum(not v.get('timing_unavailable') for v in report.get('native_per_type',{}).get('measurements',{}).values()),
                      'timing_unavailable':[k for k,v in report.get('native_per_type',{}).get('measurements',{}).items() if v.get('timing_unavailable')],
                      'hardware':False,'report':str(output.relative_to(ROOT))},indent=2))


if __name__=='__main__':main()
