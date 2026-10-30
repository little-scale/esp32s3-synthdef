#!/usr/bin/env python3
"""Compare the UI patch, including live changes, with SuperCollider 3.14.1."""
import array
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
from prepare import ROOT, ENGINE, FLAGS

build = ROOT/'build/host'
build.mkdir(parents=True,exist_ok=True)
renderer = build/'render-touch'
subprocess.run(['cc',*FLAGS,'-I'+str(ENGINE/'src'),str(ENGINE/'src/fm_load.c'),
                str(ENGINE/'src/fm_render.c'),str(ROOT/'tests/render_touch.c'),
                '-lm','-o',str(renderer)],check=True)
raw = build/'touch-sine.f32'
subprocess.run([str(renderer),str(ROOT/'examples/touch-sine.scsyndef'),str(raw)],check=True)
sc = Path('/Applications/SuperCollider.app/Contents/Resources/scsynth')
version = subprocess.check_output([str(sc),'-v'],text=True).strip()
assert '3.14.1' in version
wav = build/'touch-sine-reference.wav'
run = subprocess.run([str(sc),'-U',str(sc.parent/'plugins'),'-N',str(ROOT/'examples/touch-sine.osc'),'_',str(wav),
                      '44100','WAV','float','-o','2','-i','0','-z','64'],capture_output=True,text=True,timeout=30)
assert run.returncode == 0 and 'ERROR' not in run.stdout+run.stderr, run.stdout+run.stderr
data=wav.read_bytes(); pos=12
while pos+8 <= len(data):
    tag,size=struct.unpack_from('<4sI',data,pos); pos+=8
    if tag==b'data': reference=data[pos:pos+size]; break
    pos+=size+(size%2)
else: raise RuntimeError('Missing reference samples')
actual=array.array('f'); actual.frombytes(raw.read_bytes())
expected=array.array('f'); expected.frombytes(reference)
assert len(expected)>=len(actual)>0
expected=expected[:len(actual)]
assert all(math.isfinite(x) for x in actual)
peak=max(abs(a-b) for a,b in zip(actual,expected))
rms=math.sqrt(sum((a-b)**2 for a,b in zip(actual,expected))/len(actual))
passed=peak<=1e-4 and rms<=3e-5
report={'test':'touch sine vs SuperCollider, live pitch/level and gate release',
        'passed':passed,'peak_error':peak,'rms_error':rms,'peak_limit':1e-4,'rms_limit':3e-5,
        'frames':len(actual)//2,'sample_rate':44100,'reference_version':version,
        'graph_sha256':hashlib.sha256((ROOT/'examples/touch-sine.scsyndef').read_bytes()).hexdigest(),
        'events':[[68,'knob1',0.75],[137,'knob2',0.3],[172,'gate',0]]}
(ROOT/'evidence/touch-reference.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
if not passed:raise SystemExit(1)
