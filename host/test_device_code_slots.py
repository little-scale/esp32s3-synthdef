#!/usr/bin/env python3
"""Verify the code/slots firmware, install a bus example in an empty slot and compare muted DSP."""
import argparse,hashlib,json,re,struct,subprocess,sys,time,zlib
from pathlib import Path
from patches import Device,ROOT
from exercise_timing import output_counter_delta
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',required=True);p.add_argument('--output',type=Path,required=True)
args=p.parse_args();args.output=args.output.resolve()
report={'passed':False,'physical_touch_tested':False,'existing_slots_overwritten':False}
def save():args.output.write_text(json.dumps(report,indent=2)+'\n')
save()
graph=(ROOT/'examples/TouchBuses.scsyndef').read_bytes();source=(ROOT/'examples/touch-buses.scd').read_bytes()
with args.output.with_suffix('.log').open('wb') as log:
 d=Device(args.port,log)
 def wait(seconds):
  end=time.monotonic()+seconds
  while time.monotonic()<end:list(d.lines())
 def package():
  g,s,info=d.download()
  return {'graph':hashlib.sha256(g).hexdigest(),'source':hashlib.sha256(s).hexdigest(),'metadata':info['manifest'][152:]}
 def snapshot(label):
  d.request('PANIC');d.link.write(b's');lines=[];end=time.monotonic()+40;done=False
  while time.monotonic()<end and not done:
   for line in d.lines():
    if line.startswith(b'SCREEN_'):lines.append(line.rstrip(b'\r')+b'\n')
    if line.rstrip(b'\r')==b'SCREEN_END':done=True;break
  assert done
  path=args.output.with_name('code-slots-'+label+'.log');path.write_bytes(b''.join(lines));png=path.with_suffix('.png')
  subprocess.run([sys.executable,str(ROOT/'host/decode_screen.py'),str(path),'--output',str(png)],check=True)
  report[label+'_snapshot']=str(png.relative_to(ROOT));save()
 try:
  hello=d.hello();report['hello']=hello
  assert hello['build']==re.search(r'#define BUILD_ID "(.*?)"',(ROOT/'firmware/main/generated.h').read_text())[1]
  d.link.write(b'x');d.request('PANIC');report['initial_status']=d.request('STATUS')
  before=d.request('LIST');fx=d.request('FX');report['initial_library']=before
  protected={}
  for entry in before:
   if entry['name']:
    d.request('LOAD',bytes([entry['slot']]));protected[str(entry['slot'])]=package()
  report['initial_packages']=protected;save()
  reused=next((e['slot'] for e in before if e['slot'] and e['name']=='Touch buses' and
               protected[str(e['slot'])]['graph']==hashlib.sha256(graph).hexdigest() and
               protected[str(e['slot'])]['source']==hashlib.sha256(source).hexdigest()),None)
  slot=reused if reused is not None else next(e['slot'] for e in before if e['slot'] and not e['name'])
  if reused is None:
   d.upload(graph,source,'Touch buses',labels=('X','Y','ATTACK','RELEASE'))
   d.request('SAVE',bytes([slot]))
  else:d.request('LOAD',bytes([slot]))
  report['example_slot']=slot;report['new_slot_written']=reused is None
  assert package()['graph']==hashlib.sha256(graph).hexdigest()
  assert package()['source']==hashlib.sha256(source).hexdigest()
  save()
  baseline=args.output.with_suffix('.log').read_text(errors='replace')
  d.link.write(b'u');lines=[];done=False;end=time.monotonic()+20
  while time.monotonic()<end and not done:
   for raw in d.lines():
    line=raw.decode(errors='replace').strip()
    if line.startswith('BUSES_'):lines.append(line)
    if line=='BUSES_END':done=True;break
  assert done and 'passed=1' in lines[0],lines
  native=(ROOT/'build/host/control-buses/actual.f32').read_bytes()
  checks=[]
  for line in lines[1:-1]:
   _,index,block,crc,data=line.split();raw=bytes.fromhex(data)
   assert zlib.crc32(raw)==int(crc,16)
   expected=native[int(block)*512:(int(block)+1)*512]
   a=struct.unpack('<128f',raw);b=struct.unpack('<128f',expected)
   peak=max(abs(x-y) for x,y in zip(a,b));rms=(sum((x-y)**2 for x,y in zip(a,b))/128)**.5
   assert peak<=1e-4 and rms<=3e-5,(block,peak,rms)
   checks.append({'block':int(block),'peak_error':peak,'rms_error':rms})
  assert len(checks)==4
  report['bus_comparison']={'passed':True,'header':lines[0],'windows':checks,'peak_limit':1e-4,'rms_limit':3e-5,'muted':True}
  d.link.write(b'c');wait(.2);snapshot('code')
  d.link.write(b'v');wait(.2);snapshot('slots')
  # Existing saved packages and generations must be untouched.
  for entry in before:
   if entry['name']:
    d.request('LOAD',bytes([entry['slot']]));assert package()==protected[str(entry['slot'])]
  after=d.request('LIST')
  for entry in before:
   if entry['name']:assert next(e for e in after if e['slot']==entry['slot'])==entry
  assert d.request('FX')==fx
  d.request('LOAD',bytes([slot]));d.request('PANIC');d.link.write(b'c');wait(.4)
  report['final_status']=d.request('STATUS');report['final_library']=after
  assert not report['final_status']['reset_required']
  wait(1)
  _,delta=output_counter_delta(args.output.with_suffix('.log').read_text(errors='replace'),baseline)
  report['new_output_errors']=delta;assert not any(delta.values())
  report['passed']=True;save()
 finally:d.close()
print(json.dumps({k:report[k] for k in ('passed','example_slot','new_slot_written','bus_comparison','new_output_errors','final_status')},indent=2))
