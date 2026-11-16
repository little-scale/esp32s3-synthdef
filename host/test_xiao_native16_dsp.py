#!/usr/bin/env python3
"""Silent native-16k XIAO DSP smoke tests using production candidate-off kernels.

Never opens USB. The shared driver checks finite output, exact delay arena bounds
and fixed-seed restart determinism at 16/48k; this is not DAC qualification.
"""
import json
from pathlib import Path
import subprocess
from engine_profile import ROOT,generate
from studio import Compiler,admission_for_device

build=ROOT/'build/host/xiao-native16-dsp';build.mkdir(parents=True,exist_ok=True)
engine=generate(build/'engine','fm1',qualified_kernels=True)
compiler=Compiler('/Applications/SuperCollider.app/Contents/MacOS/sclang')
sources={
    'stereo_sine':r'{ [SinOsc.ar(330),SinOsc.ar(550)] * 0.05 }',
    'saw_resonz_miverb':r'''{ arg freq=440,dev=20,slide=1;
        MiVerb.ar(Resonz.ar(Splay.ar(Saw.ar(Lag.kr(freq,slide)
        +{Lag.kr(LFNoise2.kr(1/slide,dev),slide)}!8,0.1)),
        SinOsc.kr(0.1).range(55,880),0.1,5),0.99,1,0.01) }''',
    'comb_cloud_kr':r'''{ var copies=5,trig=Dust.kr(1!5);
        var tones=SinOsc.ar(Array.fill(copies,{|i| 330*(i+1)*Rand(0.99,1.01)}));
        CombC.ar(Splay.ar(tones*Decay2.kr(trig,0.01,SinOsc.kr(0.1).range(0.1,2))),
            0.05,SinOsc.kr(5).range(0.049,0.05),5)*0.1 }''',
    'triggered_harmonics':r'''{ var trig=Impulse.kr(4),size=5;
        var freq=TChoose.kr(trig,[60,67,72].midicps);
        var amps=Array.fill(size,{TExpRand.kr(1,1000,trig)}).normalizeSum;
        Splay.ar(SinOsc.ar(freq*(1..size),0,amps)*Decay.kr(trig,0.3))*0.2 }''',
    'physical_buses':r'''{ var button=In.kr(10),pot=In.kr(8).clip(0,1);
        SinOsc.ar(220+(pot*440),0,Lag.kr(button,0.01)*0.05)!2 }''',
    'delay_tail':r'{ CombN.ar(Decay2.ar(Impulse.ar(1),0.01,0.1)*SinOsc.ar(330)*0.05,0.375,0.375,3)!2 }',
    'master_bypass':r'SynthDef(\bypass,{Out.ar(0,In.ar(0,2))})',
    'master_miverb':r'SynthDef(\verb,{Out.ar(0,MiVerb.ar(In.ar(0,2),0.85,0.5,0.1))})',
}
paths=[]
for name,source in sources.items():
    graph,_,info=compiler.compile(dict(source=source,target='master' if name.startswith('master') else 'sound'))
    row=admission_for_device(info,dict(rate=16000))
    assert row['master_admitted' if name.startswith('master') else 'fm1_admitted'],row
    path=build/(name+'.scsyndef');path.write_bytes(graph);paths.append(path)
binary=build/'rate-smoke'
subprocess.run(['cc','-std=c99','-O1','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off',
    '-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all','-I'+str(engine),
    str(engine/'fm_load.c'),str(engine/'fm_render.c'),str(ROOT/'tests/voice_pe_native16_test.c'),'-lm','-o',str(binary)],check=True)
run=subprocess.run([str(binary),*map(str,paths)],check=True,text=True,capture_output=True,timeout=180)
report=dict(passed=True,hardware_access=False,graphs=list(sources),rates=[16000,48000],
    seconds_per_graph_per_rate=4,restarts=2,seed=12345,candidate_kernels=False,
    scope='finite/state/arena/restart smoke checks; not spectral or hardware CPU qualification',output=run.stdout)
(build/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(run.stdout,end='')
