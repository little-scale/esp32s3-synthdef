#!/usr/bin/env python3
"""Compare long persistent delay output against SuperCollider 3.14.1."""
import array,hashlib,json,math,struct,subprocess
from pathlib import Path
from prepare import ROOT,ENGINE,FLAGS
build=ROOT/'build/host';frames=(12*44100//64)*64
samples=array.array('f',[0])*(frames*2)
for index,left,right in [(0,.25,.25)]:
    samples[2*index]=left;samples[2*index+1]=right
raw=samples.tobytes();(build/'delay-input.f32').write_bytes(raw)
fmt=struct.pack('<HHIIHH',3,2,44100,44100*8,8,32)
wav=b'WAVE'+b'fmt '+struct.pack('<I',len(fmt))+fmt+b'data'+struct.pack('<I',len(raw))+raw
(build/'delay-input.wav').write_bytes(b'RIFF'+struct.pack('<I',len(wav))+wav)
sclang=Path('/Applications/SuperCollider.app/Contents/MacOS/sclang');sc=sclang.parent.parent/'Resources/scsynth'
version=subprocess.check_output([str(sc),'-v'],text=True).strip();assert '3.14.1' in version
export=subprocess.run([str(sclang),'-D',str(ROOT/'host/export-delay-reference.scd')],capture_output=True,text=True,timeout=60)
assert export.returncode==0,export.stdout+export.stderr
exe=build/'render-delay'
subprocess.run(['cc',*FLAGS,'-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all','-I'+str(ENGINE/'src'),'-I'+str(ROOT/'firmware/components/instrument/include'),str(ENGINE/'src/fm_load.c'),str(ENGINE/'src/fm_render.c'),str(ROOT/'firmware/components/instrument/master_delay.c'),str(ROOT/'tests/render_delay.c'),'-lm','-o',str(exe)],check=True)
reports=[]
for mode in range(3):
    actual=build/f'delay-{mode}.f32';reference=build/f'delay-{mode}-sc.wav'
    subprocess.run([str(exe),str(ROOT/'examples/master-delay.scsyndef'),str(build/'delay-input.f32'),str(actual),str(mode)],check=True)
    result=subprocess.run([str(sc),'-U',str(sc.parent/'plugins'),'-N',str(build/f'delay-reference-{mode}.osc'),'_',str(reference),'44100','WAV','float','-o','2','-i','0','-z','64'],capture_output=True,text=True,timeout=60)
    assert result.returncode==0 and 'ERROR' not in result.stdout+result.stderr,result.stdout+result.stderr
    data=reference.read_bytes();pos=12
    while pos+8<=len(data):
        tag,size=struct.unpack_from('<4sI',data,pos);pos+=8
        if tag==b'data':expected_bytes=data[pos:pos+size];break
        pos+=size+(size%2)
    a=array.array('f');a.frombytes(actual.read_bytes());b=array.array('f');b.frombytes(expected_bytes)
    assert len(b)>=len(a)>0 and all(math.isfinite(x) for x in a)
    peak=max(abs(x-y) for x,y in zip(a,b));rms=math.sqrt(sum((x-y)**2 for x,y in zip(a,b))/len(a))
    reports.append({'mode':mode,'frames':len(a)//2,'peak_error':peak,'rms_error':rms,'peak_limit':1e-4,'rms_limit':3e-5,'passed':peak<=1e-4 and rms<=3e-5})
report={'passed':all(r['passed'] for r in reports),'reference':version+'; ReplaceOut wrapper supplies isolated bus output','graph_sha256':hashlib.sha256((ROOT/'examples/master-delay.scsyndef').read_bytes()).hexdigest(),'arena_bytes':1048576,'reports':reports}
(ROOT/'evidence/delay-host-reference.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
assert report['passed']
