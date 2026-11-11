#!/usr/bin/env python3
"""Offline selective-path regression against the unmodified b7fd8ac renderer.

No device, Wi-Fi, flashing or sound-server calls. Preserve prior evidence files.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import test_dsp_candidates as suite
from engine_profile import ROOT,generate
from core_fixtures import fixtures as core_fixtures
from routing_fixtures import fixtures as routing_fixtures
from qualified_fixtures import fixtures as qualified_fixtures


def main():
    build=ROOT/'build/host/qualified-production';build.mkdir(parents=True,exist_ok=True)
    suite.BUILD=build
    reference=generate(build/'reference/src','fm1')
    target=generate(build/'target/src','fm1',qualified_kernels=True)
    legacy=subprocess.check_output(['git','show','b7fd8ac:host/engine_profile.py'],cwd=ROOT,text=True)
    namespace={'__file__':str(ROOT/'host/engine_profile.py'),'__name__':'qualified_legacy_reference'}
    exec(compile(legacy,'legacy_profile.py','exec'),namespace)
    pinned=namespace['generate'](build/'pinned/src','fm1')
    for p in pinned.iterdir():
        if p.suffix in ('.c','.h','.inc'):assert p.read_bytes()==(reference/p.name).read_bytes(),p.name
    edges=suite.fixtures()+core_fixtures(build)+routing_fixtures(build)+qualified_fixtures(build)
    all_paths=edges+sorted((ROOT/'upstream/fm1-synthdef/synthdef-engine/fixtures').glob('*.scsyndef'))+sorted((ROOT/'examples').glob('*.scsyndef'))
    binary=suite.executable(reference,target,True,inventory=True,defines=('DSP_QUALIFIED_COMPARISON',))
    report={'passed':False,'hardware':False,'device_access':False,'audio_playback':False,
        'baseline_commit':'b7fd8ac210a7a08ac4d94431104076907dbe5c78',
        'baseline_compiled_sources_identical':True,
        'sanitizers':['undefined','bounds','float-cast-overflow'],
        'comparison':'Exact audio, constructor/render scratch, recursive voice/RNG/flags/arena. Only caller pointers and previously-unused Lag2/Lag3 coefficient-cache freq fields normalized.',
        'target_profile':json.loads((target.parent/'profile.json').read_text()),
        'source_sha256':{s:hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in ('host/qualified_kernels.py','host/qualified_fixtures.py','host/test_qualified_kernels.py','host/engine_profile.py','host/dsp_binding.py','tests/dsp_kernels_test.c','tests/signal_reuse_test.c')}}
    output=ROOT/'evidence/qualified-kernels-host.json'
    try:
        report['inventory']=json.loads(suite.run([binary,*all_paths],env={**os.environ,'DSP_TEST_BLOCKS':'64','DSP_TEST_RATE':'44100'}))
        print('Inventory exact:',report['inventory']['graphs'],'graphs',flush=True)
        report['four_rate_edges']=json.loads(suite.run([binary,*edges],env={**os.environ,'DSP_TEST_BLOCKS':'512'}))
        report['experimental_composition']={}
        contexts={
            'disjoint-binding':dict(candidate_binding=True,binding_families=['extensions']),
            'core-override':dict(candidate_core=True),
            'noise':dict(candidate_noise=True),
        }
        for name,flags in contexts.items():
            suite.BUILD=build/name;suite.BUILD.mkdir(exist_ok=True)
            mixed=generate(suite.BUILD/'target/src','fm1',qualified_kernels=True,**flags)
            probe=suite.executable(reference,mixed,True,inventory=True,defines=('DSP_ALL_CANDIDATES',))
            result=json.loads(suite.run([probe,*all_paths],env={**os.environ,'DSP_TEST_BLOCKS':'64','DSP_TEST_RATE':'44100'}))
            report['experimental_composition'][name]=result
            print('Mixed exact:',name,result['graphs'],'graphs',flush=True)
        interleaved={};runners={}
        flags=['cc','-std=c99','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off',
               '-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all','-DFM_QUALIFIED_NORMALIZE']
        for name,source in [('reference',reference),('target',target)]:
            runner=build/('interleaved-'+name)
            suite.run([*flags,'-I'+str(source),source/'fm_load.c',source/'fm_render.c',ROOT/'tests/signal_reuse_test.c','-lm','-o',runner])
            runners[name]=runner
        probes=[p for p in edges if p.stem.startswith(('qualified_','core_Klang_','core_Klank_'))]
        for path in probes:
            a=subprocess.run([str(runners['reference']),str(path),'48'],capture_output=True,check=True)
            b=subprocess.run([str(runners['target']),str(path),'48'],capture_output=True,check=True)
            assert json.loads(a.stderr)['prepared'] and json.loads(b.stderr)['prepared']
            assert a.stdout==b.stdout,'Interleaved voice mismatch: '+path.name
            interleaved[path.stem]=hashlib.sha256(b.stdout).hexdigest()
        report['interleaved_shared_scratch']=dict(graphs=len(probes),blocks_per_voice=48,voices=2,
            output_samples=len(probes)*48*2*64*2,canaries=True,alternate_signal_mapping=True,
            restart_one_voice=True,digests=interleaved)
        print('Shared scratch exact:',len(probes),'graphs',flush=True)
        report['passed']=True
    except Exception as error:report['error']=str(error);raise
    finally:output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('passed','inventory','four_rate_edges')},indent=2))


if __name__=='__main__':main()
