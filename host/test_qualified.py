#!/usr/bin/env python3
"""Check the candidate one-voice graphs against SuperCollider's NRT renderer."""
import array
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
from prepare import ROOT, ENGINE, FLAGS

build=ROOT/'build/host';build.mkdir(parents=True,exist_ok=True)
renderer=build/'render-qualified'
subprocess.run(['cc',*FLAGS,'-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all',
                '-I'+str(ENGINE/'src'),str(ENGINE/'src/fm_load.c'),str(ENGINE/'src/fm_render.c'),
                str(ROOT/'tests/render_qualified.c'),'-lm','-o',str(renderer)],check=True)
sc=Path('/Applications/SuperCollider.app/Contents/Resources/scsynth')
version=subprocess.check_output([str(sc),'-v'],text=True).strip();assert '3.14.1' in version
reports=[]
for name in ['phase-fm','additive','filtered']:
    graph=ROOT/f'examples/{name}.scsyndef';raw=build/f'{name}.f32';wav=build/f'{name}-sc.wav'
    run=subprocess.run([str(renderer),str(graph),str(raw)],capture_output=True,text=True,check=True)
    reference=subprocess.run([str(sc),'-U',str(sc.parent/'plugins'),'-N',str(ROOT/f'examples/{name}.osc'),
                              '_',str(wav),'44100','WAV','float','-o','2','-i','0','-z','64'],
                             capture_output=True,text=True,timeout=30)
    assert not reference.returncode and 'ERROR' not in reference.stdout+reference.stderr,reference.stdout+reference.stderr
    data=wav.read_bytes();pos=12
    while pos+8<=len(data):
        tag,size=struct.unpack_from('<4sI',data,pos);pos+=8
        if tag==b'data': expected_bytes=data[pos:pos+size];break
        pos+=size+(size%2)
    else:raise AssertionError('Missing reference samples')
    actual=array.array('f');actual.frombytes(raw.read_bytes())
    expected=array.array('f');expected.frombytes(expected_bytes)
    assert len(expected)>=len(actual)>0
    expected=expected[:len(actual)];assert all(math.isfinite(x) for x in actual)
    peak=max(abs(a-b) for a,b in zip(actual,expected));rms=math.sqrt(sum((a-b)**2 for a,b in zip(actual,expected))/len(actual))
    report={'patch':name,'passed':peak<=1e-4 and rms<=3e-5,'peak_error':peak,'rms_error':rms,
            'peak_limit':1e-4,'rms_limit':3e-5,'frames':len(actual)//2,'sample_rate':44100,
            'graph_sha256':hashlib.sha256(graph.read_bytes()).hexdigest(),'layout':run.stdout.strip()}
    reports.append(report);print(json.dumps(report,indent=2),flush=True)
(ROOT/'evidence/qualified-host-reference.json').write_text(json.dumps({'reference':version,'reports':reports},indent=2)+'\n')
assert all(r['passed'] for r in reports)
