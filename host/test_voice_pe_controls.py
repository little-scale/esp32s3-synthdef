#!/usr/bin/env python3
"""Computer-only reserved control-output and physical input lifecycle tests."""
import json,subprocess
from engine_profile import ROOT,generate
from synthdef_binary import encode
build=ROOT/'build/host/voice-pe-controls';engine=generate(build/'engine','fm1',qualified_kernels=True)
port=ROOT/'ports/voice_pe/main';inst=ROOT/'firmware/components/instrument'
paths=[]
def fixture(name,constants,nodes,controls=None,names=None):
    g=dict(name=name,constants=constants,controls=controls or [],names=names or [],nodes=nodes)
    p=build/(name+'.scsyndef');p.write_bytes(encode(g));paths.append(p)
fixture('writers',[0,3,39,.25,.1,.2,.3],[
    ('In',1,[(-1,0)],[1],0),('BinaryOpUGen',1,[(0,0),(-1,1)],[1],0),
    ('Out',1,[(-1,1),(-1,3)],[],0),('Out',1,[(1,0),(-1,3)],[],0),
    ('Out',1,[(-1,2),(-1,4),(-1,5),(-1,6)],[],0)])
fixture('inputs',[0,3],[('In',1,[(-1,0)],[1,1,1],0),('K2A',2,[(0,0)],[2],0),
    ('K2A',2,[(0,1)],[2],0),('Out',1,[(-1,1),(0,2)],[],0),('Out',2,[(-1,0),(1,0),(2,0)],[],0)])
for name,bus,channels in [('below',2,1),('past',42,1),('fractional',3.5,1),('spanning',41,2),('many',3,40)]:
    fixture(name,[bus,.1],[('Out',1,[(-1,0)]+[(-1,1)]*channels,[],0)])
fixture('audio-input',[3,440,0],[('SinOsc',2,[(-1,1),(-1,2)],[2],0),('Out',1,[(-1,0),(0,0)],[],0)])
exe=build/'test'
subprocess.run(['cc','-std=c99','-O1','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off',
    '-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all',
    *['-I'+str(p) for p in (engine,inst/'include',port)],
    *[str(p) for p in (engine/'fm_load.c',engine/'fm_render.c',inst/'instrument.c',port/'voice_pe_controls.c',ROOT/'tests/voice_pe_control_test.c')],
    '-lm','-o',str(exe)],check=True)
run=subprocess.run([str(exe),*map(str,paths)],capture_output=True,text=True)
print(run.stdout,end='');print(run.stderr,end='');run.check_returncode()
(build/'report.json').write_text(json.dumps(dict(passed=True,hardware_access=False,rates=[16000,44100,48000],output=run.stdout),indent=2)+'\n')
