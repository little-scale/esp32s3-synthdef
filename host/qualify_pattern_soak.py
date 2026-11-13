#!/usr/bin/env python3
"""Time-bounded muted pattern soak; temporary Main only, no saved test packages."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import secrets
import struct
import time
from control_client import schema
from patches import Device
from pattern_program import compile_pattern
from probe_usb_lifecycle import find_port
from program_transport import upload_program
from qualify_dsp_transient import restore,volume
from qualify_pattern_program import op
from studio import AudioTelemetry,Compiler
from studio_client import StudioClient

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--device-id',required=True);p.add_argument('--backup',type=Path,required=True)
 p.add_argument('--output',type=Path,required=True);p.add_argument('--seconds',type=int,default=60)
 args=p.parse_args();assert 10<=args.seconds<=120
 b=json.loads(args.backup.read_text());c=StudioClient();d=None;changed=False
 telemetry=AudioTelemetry();hashes=set();graphs={b['state']['status']['graph_sha256']}
 report=dict(passed=False,device_id=args.device_id,muted=True,tests={},observations=[])
 def info():return d.request('PINFO')
 def rc():return d.request('RCINFO',b'\0\0')
 def compile_tree(tree,graph_hash,seed=123):
  raw,meta=compile_pattern(tree,graph_hash,tempo=1,seed=seed)
  hashes.add(meta['pattern_sha256']);return raw
 def install(tree,graph_hash):return upload_program(d,compile_tree(tree,graph_hash),save=False)
 def finite(hz,seconds,soak=False):
  count=round(hz*seconds)
  tree=op('Pbind','freq',op('Pbrown',220,880,5,count),'amp',op('Pwhite',.01,.02,count),
          'levels',op('Pseq',[[.1,.2],[.2,.1]],op('Infinity')),'dur',1/hz)
  before=rc();install(tree,main_hash);started=rc();deadline=time.monotonic()+seconds+4
  samples=[];next_sample=0
  while time.monotonic()<deadline:
   state=info()
   if state['faulted']:raise AssertionError(bytes.fromhex(state['error_hex']).decode())
   if time.monotonic()>=next_sample:
    now=rc();sample=dict(program=state,remote=now,
      diagnostics={k:v for k,v in telemetry.snapshot().items() if k in AudioTelemetry.fields})
    samples.append(sample);next_sample=time.monotonic()+1
    if soak and len(samples)%15==0:print('Soak:',state['events'],'events generated',flush=True)
   if state['ended']:break
   time.sleep(.1 if seconds<5 else .2)
  else:raise TimeoutError('Finite pattern deadline')
  time.sleep(.12);after=rc()
  assert state['events']==count and after['applied']-before['applied']==count
  assert after['late']==before['late'] and after['rejected']==before['rejected']
  assert not after['queued']
  duration=(after['now_us']-started['now_us'])/1e6
  assert seconds-.1<=duration<=seconds+1
  return dict(hz=hz,count=count,device_elapsed_seconds=duration,pattern=state,samples=samples)
 def rejected(raw,kind):
  previous=info()['sha256'];tx=secrets.randbits(32) or 1
  digest=hashlib.sha256(raw).digest()
  if kind=='digest':digest=bytes([digest[0]^1])+digest[1:]
  d.request('PBEGIN',struct.pack('<II',tx,len(raw))+digest)
  try:
   for at in range(0,len(raw),256):d.request('PDATA',struct.pack('<II',tx,at)+raw[at:at+256])
   try:d.request('PCOMMIT',struct.pack('<I',tx))
   except RuntimeError:pass
   else:raise AssertionError('Invalid program was accepted: '+kind)
  finally:d.request('PABORT')
  assert info()['sha256']==previous and d.request('VOLUME')['percent']==0
 try:
  state=c.http('refresh',{});assert state['hello']['device_id']==args.device_id
  assert state['slots']==b['state']['slots'] and state['status']['graph_sha256'] in graphs
  report['build_id']=state['hello']['build']
  c.http('disconnect',{});d=Device(find_port(args.device_id),log=telemetry)
  assert not info()['loaded'];changed=True;volume(d,0)
  source=r'''ESP32Program({arg freq=440,amp=0.02,gate=0,levels=#[0.1,0.2];
   SinOsc.ar(freq)*EnvGen.kr(Env.asr(0.001,1,0.01),gate)*amp*levels},
   Pbind(\freq,440,\dur,0.02),seed:123)'''
  graph,source,layout=Compiler(Path('/Applications/SuperCollider.app/Contents/MacOS/sclang')).compile(dict(source=source))
  assert layout['admitted'];main_hash=layout['graph_sha256'];graphs.add(main_hash)
  d.upload(graph,source,'Pattern soak',mapping=0,definition=True)
  report['tests']['soak_50hz']=finite(50,args.seconds,True)
  print('PASS: one-minute 50 Hz note/array-control soak',flush=True)
  for hz in (100,200):
   report['tests']['rate_'+str(hz)]=finite(hz,3)
   print('PASS:',hz,'events/second',flush=True)
  valid=compile_tree(op('Pbind','freq',440,'dur',.1),main_hash)
  for kind in ('digest','magic','graph','control'):
   raw=valid
   if kind=='magic':raw=b'bad!'+raw[4:]
   if kind=='graph':raw=raw[:28]+bytes([raw[28]^1])+raw[29:]
   if kind=='control':raw=compile_tree(op('Pbind','notAControl',440,'dur',.1),main_hash)
   rejected(raw,kind)
  report['tests']['invalid_uploads_preserve_program']=4
  # Incomplete/out-of-order transfers must recover without replacing Main.
  tx=123;d.request('PBEGIN',struct.pack('<II',tx,len(valid))+hashlib.sha256(valid).digest())
  try:
   try:d.request('PDATA',struct.pack('<II',tx,12)+valid[:10])
   except RuntimeError:pass
   else:raise AssertionError('Out-of-order chunk accepted')
   try:d.request('PCOMMIT',struct.pack('<I',tx))
   except RuntimeError:pass
   else:raise AssertionError('Incomplete program accepted')
  finally:d.request('PABORT')
  report['tests']['incomplete_transfer_recovery']=True
  # Empty infinite streams must fault promptly and leave the device responsive.
  install(op('Pn',op('Pfin',0,op('Pbind','freq',440)),op('Infinity')),main_hash)
  time.sleep(.2);bounded=info();assert bounded['faulted'] and not bounded['running']
  assert 'budget' in bytes.fromhex(bounded['error_hex']).decode()
  report['tests']['work_budget_stops_infinite_empty']=bounded
  install(op('Pbind','freq',440,'dur',.1),main_hash)
  cycles=[]
  for i in range(48):
   try:
    d.request('PPLAY');time.sleep(.06);current=info()
    assert current['running'] and not current['faulted'],bytes.fromhex(current['error_hex']).decode()
    d.request('PSTOP');assert not info()['running'];cycles.append(dict(cycle=i+1,passed=True))
   except Exception as error:
    cycles.append(dict(cycle=i+1,passed=False,error=str(error)));break
  report['tests']['restart_cycles']=cycles
  if not all(x['passed'] for x in cycles):raise AssertionError('Restart cycle failed: '+str(cycles[-1]))
  report['passed']=True
 except BaseException as error:
  report['error']=str(error) or type(error).__name__;raise
 finally:
  try:
   if d:
    try:
     if changed:
      assert d.request('STATUS')['graph_sha256'] in graphs,'Unrelated Main replacement'
      current=info()
      if current['loaded']:
       assert current['sha256'] in hashes,'Unrelated program replacement'
       d.request('PDELETE')
      report['restoration']=restore(d,b,b['state']['volume_percent'],save=True)
    finally:d.close()
  except Exception as error:
   report['restoration_error']=str(error);report['passed']=False;raise
  finally:
   try:
    connected=c.http('connect',dict(port=find_port(args.device_id)))
    report['studio_connected']=connected['hello']['device_id']==args.device_id
   except Exception as error:report['studio_error']=str(error);report['passed']=False
   c.close();report['passed']=report['passed'] and 'restoration' in report
   args.output.write_text(json.dumps(report,indent=2)+'\n')
 print('PASS: unattended pattern soak; original package and settings restored')

if __name__=='__main__':main()
