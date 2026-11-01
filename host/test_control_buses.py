#!/usr/bin/env python3
"""Control-bus bounds/lifecycle checks and an independent SC NRT comparison."""
import array,hashlib,json,math,struct,subprocess
from pathlib import Path
from engine_profile import generate
from synthdef_binary import encode,decode
ROOT=Path(__file__).resolve().parents[1];BUILD=ROOT/'build/host/control-buses';BUILD.mkdir(parents=True,exist_ok=True)
ENGINE=generate(BUILD/'src','fm1')
flags=['-std=c99','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-fno-fast-math','-ffp-contract=off',
       '-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all']
probe=dict(name='BusProbe',constants=[0],controls=[0],names=[('hwBus',0)],nodes=[
 ('Control',1,[],[1],0),('In',1,[(0,0)],[1,1,1],0),('K2A',2,[(1,0)],[2],0),
 ('K2A',2,[(1,1)],[2],0),('Out',2,[(-1,0),(2,0),(3,0)],[],0)])
fixture=BUILD/'probe.scsyndef';fixture.write_bytes(encode(probe));invalid=[]
for name,bus,channels,rate in [('negative',-1,1,1),('fractional',.5,1,1),('past-end',32,1,1),('spanning',31,2,1),('too-many',0,33,1),('scalar',0,1,0),('audio-range',1,2,2),('audio-channels',0,3,2)]:
 g=decode(encode(probe));g['constants']=[bus];g['nodes'][1]=('In',rate,[(-1,0)],[rate]*channels,0)
 # The rejection must occur at In, before downstream references are inspected.
 f=BUILD/(name+'.scsyndef');f.write_bytes(encode(g));invalid.append(f)
exe=BUILD/'control-bus-test';raw=BUILD/'actual.f32';graph=ROOT/'examples/TouchBuses.scsyndef'
pair=json.loads((ROOT/'examples/touch-buses.source.json').read_text())
assert pair=={name:hashlib.sha256((ROOT/'examples'/name).read_bytes()).hexdigest() for name in ('touch-buses.scd','TouchBuses.scsyndef')},'Stale example source/graph pair; run host/export_touch_buses.py'
subprocess.run(['cc',*flags,'-DPATCH_FM1_COMPAT=1','-I'+str(ENGINE),'-I'+str(ROOT/'firmware/components/instrument/include'),
 '-I'+str(ROOT/'firmware/components/patches/include'),str(ENGINE/'fm_load.c'),str(ENGINE/'fm_render.c'),
 str(ROOT/'firmware/components/instrument/instrument.c'),str(ROOT/'firmware/components/patches/patch_format.c'),
 str(ROOT/'tests/control_bus_test.c'),'-lm','-o',str(exe)],check=True)
result=subprocess.run([str(exe),str(graph),str(fixture),str(raw),*map(str,invalid)],capture_output=True,text=True,check=True)
print(result.stdout,flush=True)
def string(s):
 b=s.encode()+b'\0';return b+b'\0'*((-len(b))%4)
def msg(address,*args):
 tags=',';data=b''
 for a in args:
  if isinstance(a,str):tags+='s';data+=string(a)
  elif isinstance(a,bytes):tags+='b';data+=struct.pack('>I',len(a))+a+b'\0'*((-len(a))%4)
  elif isinstance(a,int):tags+='i';data+=struct.pack('>i',a)
  else:tags+='f';data+=struct.pack('>f',a)
 return string(address)+string(tags)+data
events={0:[msg('/g_new',1,0,0),msg('/d_recv',graph.read_bytes()),msg('/c_setn',0,3,.25,.7,1.),msg('/s_new','TouchBuses',1000,1,1,'hwBus',0)]}
for b,values in [(64,[(0,.8)]),(128,[(1,.2)]),(192,[(2,0.)]),(256,[(0,.5),(1,.7),(2,1.)]),(320,[(2,0.)])]:
 events[b+.25]=[msg('/c_set',*[v for pair in values for v in pair])]
events[448.25]=[msg('/g_freeAll',0)];events[449]=[msg('/c_set',0,0)]
score=BUILD/'reference.osc';score.write_bytes(b''.join(
 struct.pack('>I',len(packet))+packet for when,messages in sorted(events.items())
 for packet in [b'#bundle\0'+struct.pack('>Q',round(when*64/44100*2**32))+b''.join(struct.pack('>I',len(m))+m for m in messages)]))
sc=Path('/Applications/SuperCollider.app/Contents/Resources/scsynth');wav=BUILD/'reference.wav'
r=subprocess.run([str(sc),'-U',str(sc.parent/'plugins'),'-N',str(score),'_',str(wav),'44100','WAV','float','-o','2','-i','0','-z','64'],capture_output=True,text=True,timeout=30)
assert r.returncode==0 and 'ERROR' not in r.stdout+r.stderr,r.stdout+r.stderr
data=wav.read_bytes();pos=12
while pos+8<=len(data):
 tag,n=struct.unpack_from('<4sI',data,pos);pos+=8
 if tag==b'data':expected=data[pos:pos+n];break
 pos+=n+(n%2)
else:raise AssertionError('Missing WAV data')
a=array.array('f');a.frombytes(raw.read_bytes());b=array.array('f');b.frombytes(expected);b=b[:len(a)]
assert len(a)==len(b) and all(math.isfinite(x) for x in a)
peak=max(abs(x-y) for x,y in zip(a,b));rms=math.sqrt(sum((x-y)**2 for x,y in zip(a,b))/len(a))
report={'passed':peak<=1e-4 and rms<=3e-5,'native_checks':result.stdout.strip(),'sc_reference':subprocess.check_output([str(sc),'-v'],text=True).strip(),
 'frames':len(a)//2,'peak_error':peak,'rms_error':rms,'peak_limit':1e-4,'rms_limit':3e-5,
 'graph_sha256':hashlib.sha256(graph.read_bytes()).hexdigest(),'source_sha256':hashlib.sha256((ROOT/'examples/touch-buses.scd').read_bytes()).hexdigest(),
 'audio_playback':False,'hardware':False}
(ROOT/'evidence/control-buses-host.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
assert report['passed']
