#!/usr/bin/env python3
"""Silent SC compilation and native-16k engine integration; never opens USB."""
import base64
import json
import subprocess
from pathlib import Path
from engine_profile import ROOT, generate
from studio import Compiler, admission_for_device

build=ROOT/'build/host/voice-pe-native16-tests'
engine=generate(build/'engine','fm1',qualified_kernels=True,candidate_saw=True,candidate_impulse=True)
plan=json.loads((ROOT/'evidence/dsp-oscillators-voice-pe-plan-20261115.json').read_text())
compiler=Compiler('/Applications/SuperCollider.app/Contents/MacOS/sclang')
sources={
    'comb_cloud':r'''{ var copies=5, trig=Dust.kr(1!5);
        var tones=SinOsc.ar(Array.fill(copies,{|i| 330*(i+1)*Rand(0.99,1.01)}));
        CombC.ar(Splay.ar(tones*Decay2.kr(trig,0.01,SinOsc.kr(0.1).range(0.1,2))),
            0.05,SinOsc.kr(5).range(0.049,0.05),5)*0.1 }''',
    'saw_resonz_miverb':r'''{ arg freq=440,dev=20;
        MiVerb.ar(Resonz.ar(Splay.ar(Saw.ar(freq+{Lag.kr(LFNoise2.kr(1,dev),1)}!8,0.1)),
            SinOsc.kr(0.1).range(55,880),0.1,3),0.9,0.7,0.1) }''',
    'master_miverb':r'''SynthDef(\nativeVerb,{Out.ar(0,MiVerb.ar(In.ar(0,2),0.85,0.5,0.1))})''',
}
for name,source in sources.items():
    graph,_,info=compiler.compile(dict(source=source,target='master' if name.startswith('master') else 'sound'))
    row=admission_for_device(info,dict(rate=16000))
    assert row['master_admitted' if name.startswith('master') else 'fm1_admitted'],row
    plan[name]=dict(graph=base64.b64encode(graph).decode(),source=source)
paths=[]
for name,row in plan.items():
    p=build/(name+'.scsyndef');p.write_bytes(base64.b64decode(row['graph'],validate=True));paths.append(p)
exe=build/'rate-smoke'
subprocess.run(['cc','-std=c99','-O1','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off',
    '-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all','-I'+str(engine),
    str(engine/'fm_load.c'),str(engine/'fm_render.c'),str(ROOT/'tests/voice_pe_native16_test.c'),'-lm','-o',str(exe)],check=True)
run=subprocess.run([str(exe),*map(str,paths)],check=True,text=True,capture_output=True,timeout=180)
report=dict(passed=True,hardware_access=False,rates=[16000,48000],graphs=len(paths),
            seconds_per_graph_per_rate=4,restarts=2,seed=12345,
            scope='finite/state/restart smoke checks, not spectral/tuning equivalence or CPU qualification',output=run.stdout)
import test_dsp_oscillators as oracle
oracle.BUILD=build/'oscillator-oracle';oracle.BUILD.mkdir(exist_ok=True)
reference=generate(oracle.BUILD/'reference','fm1',qualified_kernels=True)
edges=oracle.fixtures()
binary=oracle.executable(reference,engine,True,driver_defines=('OSC_TEST_NATIVE16',))
report['oscillator_reference_comparison_16000']=json.loads(oracle.run([binary,*edges]))
(build/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(run.stdout,end='')
print('16k oscillator oracle:',report['oscillator_reference_comparison_16000'])
