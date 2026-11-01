#!/usr/bin/env python3
"""Exercise full-profile admission, synth memory and note lifecycle silently."""
import json
import subprocess
from engine_profile import ROOT, SOURCE, generate
from synthdef_binary import encode, decode, voice_interface

build=ROOT/'build/host/fm1-voice';source=generate(build/'src','fm1')
paths=[]
for fixture in sorted((SOURCE.parent/'fixtures').glob('*.scsyndef')):
    raw=fixture.read_bytes();assert encode(decode(raw))==raw
    out=build/fixture.name;out.write_bytes(voice_interface(raw));paths.append(out)
# The FM1 fixtures use at most 25,522 arena samples. Exercise the full enlarged
# 262,144-sample arena separately, with a genuinely live voice interface.
g=dict(name='long-delay-voice',constants=[0,5,.35,1],controls=[440,.5,1],names=[('freq',0),('amp',1),('gate',2)],nodes=[
    ('Control',1,[],[1,1,1],0),('SinOsc',2,[(0,0),(-1,0)],[2],0),
    ('BinaryOpUGen',2,[(1,0),(0,1)],[2],2),('BinaryOpUGen',2,[(2,0),(0,2)],[2],2),
    ('CombL',2,[(3,0),(-1,1),(-1,2),(-1,3)],[2],0),('Out',2,[(-1,0),(4,0)],[],0)])
out=build/'long-delay-voice.scsyndef';out.write_bytes(encode(g));paths.append(out)
component=ROOT/'firmware/components';exe=build/'test-voices'
subprocess.run(['cc','-std=c99','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off',
    '-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all','-DPATCH_FM1_COMPAT=1',
    '-I'+str(source),'-I'+str(component/'instrument/include'),'-I'+str(component/'patches/include'),
    str(source/'fm_load.c'),str(source/'fm_render.c'),str(component/'instrument/instrument.c'),
    str(component/'patches/patch_format.c'),str(ROOT/'tests/fm1_voice_test.c'),'-lm','-o',str(exe)],check=True)
run=subprocess.run([str(exe)],input=''.join(str(p)+'\n' for p in paths),capture_output=True,text=True,check=True)
report=json.loads(run.stdout);report.update(hardware_tested=False,audio_playback=False,profile='fm1-compat-v1',
    assertions=['all pinned fixture graphs admitted after addition of test-only live controls',
        'incremental clearing versus ordinary binding: exact float output equality',
        'arena guards, full 1 MiB arena, pending release, Panic and undersized/null bindings'],
    wrapper_scope='Added controls are unused by fixture DSP; this is an admission test, not an automatic patch converter')
(ROOT/'evidence/fm1-voice.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
