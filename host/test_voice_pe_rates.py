#!/usr/bin/env python3
"""Computer-only multi-rate admission, timing and shared FX control-bus checks."""
import json
import subprocess
from pathlib import Path
from engine_profile import ROOT,generate
from synthdef_binary import encode
from studio import Compiler,admission_for_device,Problem
build=ROOT/'build/host/voice-pe-rates';build.mkdir(parents=True,exist_ok=True)
engine=generate(build/'engine','fm1',qualified_kernels=True)
component=ROOT/'firmware/components/instrument';patches=ROOT/'firmware/components/patches'
delay=dict(name='Rate boundary',constants=[0,2.9,.1],controls=[],names=[],nodes=[
    ('In',2,[(-1,0)],[2,2],0),
    ('DelayC',2,[(0,0),(-1,1),(-1,2)],[2],0),
    ('DelayC',2,[(0,1),(-1,1),(-1,2)],[2],0),
    ('Out',2,[(-1,0),(1,0),(2,0)],[],0)])
bus=dict(name='FX bus gain',constants=[0,8],controls=[],names=[],nodes=[
    ('In',2,[(-1,0)],[2,2],0),('In',1,[(-1,1)],[1],0),
    ('BinaryOpUGen',2,[(0,0),(1,0)],[2],2),
    ('BinaryOpUGen',2,[(0,1),(1,0)],[2],2),
    ('Out',2,[(-1,0),(2,0),(3,0)],[],0)])
paths=[]
for name,g in [('delay',delay),('bus',bus)]:
    p=build/(name+'.scsyndef');p.write_bytes(encode(g));paths.append(p)
exe=build/'test'
subprocess.run(['cc','-std=c99','-O1','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off',
    '-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all','-DPATCH_FM1_COMPAT=1',
    *['-I'+str(p) for p in (engine,component/'include',patches/'include')],
    *[str(p) for p in (engine/'fm_load.c',engine/'fm_render.c',component/'master_delay.c',patches/'patch_format.c',ROOT/'tests/voice_pe_rate_test.c')],
    '-lm','-o',str(exe)],check=True)
run=subprocess.run([str(exe),*map(str,paths),str(ROOT/'examples/miRings1.scsyndef')],capture_output=True,text=True,check=True)
inspector=Compiler(Path('/unused')).validator()
info=json.loads(subprocess.check_output([str(inspector),str(paths[0]),'1'],text=True))
assert info['rate']==44100 and info['fm1_admitted'] and info['master_admitted']
for r,expected in [('16000',True),('44100',True),('48000',False)]:
    row=admission_for_device(info,{'rate':int(r)})
    assert row['fm1_admitted'] is expected and row['master_admitted'] is expected
# Selecting recipients does not mutate a shared broadcast artifact.
assert info['fm1_admitted'] and info['rate']==44100
assert admission_for_device({'fm1_admitted':True},{})['fm1_admitted']
for hello in ({'rate':48000},{'rate':32000},{'rate':True}):
    try:admission_for_device({'fm1_admitted':True},hello)
    except Problem:pass
    else:raise AssertionError(hello)
report={'passed':True,'hardware_access':False,'rates':[16000,44100,48000],'output':run.stdout,
        'boundary_admissions':info['admission_rates']}
(build/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(run.stdout,end='');print('PASS: Studio inspector exposes all three rate budgets; recipient selection is immutable')
