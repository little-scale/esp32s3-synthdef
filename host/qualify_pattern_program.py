#!/usr/bin/env python3
"""Muted XIAO standalone-pattern checks; preserves saved Main/FX generations.

Requires a private backup from qualify_current_inventory.backup. Uses temporary
Main activation and removes only programs created by this run. No firmware flash.
"""
import argparse
import base64
import contextlib
import hashlib
import json
from pathlib import Path
import time
from control_client import schema
from patches import Device,ROOT
from pattern_program import compile_pattern
from probe_usb_lifecycle import find_port
from program_transport import upload_program
from qualify_dsp_transient import restore,volume
from studio import AudioTelemetry,Compiler
from studio_client import StudioClient

def op(name,*args):return dict(op=name,args=list(args))
def wait_end(d,timeout=8):
 deadline=time.monotonic()+timeout
 while time.monotonic()<deadline:
  info=d.request('PINFO')
  if info['faulted']:raise RuntimeError(bytes.fromhex(info['error_hex']).decode())
  if info['ended']:return info
  time.sleep(.04)
 raise TimeoutError('Standalone program did not finish')

def reset_device(device,target,telemetry):
 import esptool
 device.close();d=None;port=find_port(target)
 log=ROOT/'build/host/private/pattern-reset.log'
 with log.open('a') as stream,contextlib.redirect_stdout(stream),contextlib.redirect_stderr(stream):
  with esptool.detect_chip(port=port,connect_attempts=3) as chip:
   assert chip.CHIP_NAME=='ESP32-S3' and bytes(chip.read_mac()).hex()==target[6:]
   esptool.main(['--chip','esp32s3','--port',port,'--after','watchdog_reset','read_mac'],esp=chip)
 deadline=time.monotonic()+40
 while time.monotonic()<deadline:
  try:
   if d is None:d=Device(find_port(target),log=telemetry)
   hello=d.request('HELLO',timeout=1,retries=0)
   assert hello['device_id']==target
   return d
  except (OSError,TimeoutError,RuntimeError):
   if d:d.close();d=None
   time.sleep(.25)
 if d:d.close()
 raise TimeoutError('Reconnect the XIAO to finish restoration')

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--device-id',required=True)
 parser.add_argument('--backup',type=Path,required=True)
 parser.add_argument('--output',type=Path,required=True)
 parser.add_argument('--reboot',action='store_true',help='Also reset the chip to check autostart and persistent deletion')
 parser.add_argument('--remove-owned-program-sha',help='Only remove this exact prior qualification program before testing')
 args=parser.parse_args();b=json.loads(args.backup.read_text());client=StudioClient();d=None
 report=dict(passed=False,device_id=args.device_id,muted=True,tests={})
 hashes=set();graphs={b['state']['status']['graph_sha256']};changes_allowed=False
 telemetry=AudioTelemetry()
 try:
  state=client.http('refresh',{})
  assert state['hello']['device_id']==args.device_id and state['hello']['pattern_programs']==1
  report['firmware_build']=state['hello']['build']
  assert state['status']['graph_sha256'] in graphs and state['slots']==b['state']['slots']
  client.http('disconnect',{});d=Device(find_port(args.device_id),log=telemetry)
  existing=d.request('PINFO')
  if existing['loaded'] and args.remove_owned_program_sha==existing['sha256']:
   d.request('PDELETE');existing=d.request('PINFO')
  assert not existing['loaded'],'Back up an existing standalone program before testing'
  changes_allowed=True
  volume(d,0)
  source=r'''ESP32Program({arg freq=440,amp=0.02,gate=1;
   SinOsc.ar(freq)*EnvGen.kr(Env.asr(0.005,1,0.03),gate)*amp!2},
   Pbind(\degree,Pseq([0,Pseq([2,4],1),7],inf),
    \dur,Pbjorklund2(3,8,2)/8),tempo:4,seed:123)'''
  graph,original,info=Compiler(Path('/Applications/SuperCollider.app/Contents/MacOS/sclang')).compile(dict(source=source))
  assert info['admitted'];graphs.add(info['graph_sha256'])
  d.upload(graph,original,'Pattern QA',mapping=0,definition=True)
  raw=base64.b64decode(info['program']['data']);hashes.add(info['program']['pattern_sha256'])
  before=d.request('RCINFO',b'\0\0')
  upload_program(d,raw,save=False)
  ended=wait_end(d);after=d.request('RCINFO',b'\0\0')
  assert ended['events']==6 and after['applied']-before['applied']==6
  assert after['rejected']==before['rejected'] and after['late']==before['late']
  report['tests']['nested_euclidean_notes']=ended
  # A graph authored with gate=1 must still begin with a zero gate. A leading
  # rest leaves ample time to inspect the instance before its first note.
  tree=op('Pbind','freq',440,'type',op('Pseq',['rest','note'],1),'dur',.5)
  raw,meta=compile_pattern(tree,info['graph_sha256'],tempo=2,seed=123)
  hashes.add(meta['pattern_sha256']);upload_program(d,raw,save=False)
  gate=next(c for c in schema(d,0)['controls'] if c['name']=='gate')
  assert gate['values']==[0]
  rested=wait_end(d);assert rested['rests']==1 and rested['events']==1
  report['tests']['initial_gate_and_leading_rest']=rested
  tree=op('Pbind','type','set','freq',op('Pbrown',220,880,10,8),
          'amp',op('Pexprand',.01,.1,8),'dur',.03125)
  raw,meta=compile_pattern(tree,info['graph_sha256'],tempo=2,seed=123)
  hashes.add(meta['pattern_sha256']);upload_program(d,raw,save=False)
  random_info=wait_end(d);time.sleep(.1);first=schema(d,0)
  values={c['name']:c['values'] for c in first['controls']}
  assert random_info['events']==8 and 220<=values['freq'][0]<=880
  assert int(values['freq'][0])==values['freq'][0] and .01<=values['amp'][0]<=.1
  d.request('PPLAY');wait_end(d);time.sleep(.1);again=schema(d,0)
  assert {c['name']:c['values'] for c in again['controls']}==values
  report['tests']['seeded_random_controls']=dict(random_info,repeatable=True)
  # A near-limit nested event stream must not exhaust the control task stack.
  tree=op('Pbind','freq',440,'dur',.0625)
  tree=op('Pfin',1,tree)
  for _ in range(18):tree=op('Pn',tree,1)
  raw,meta=compile_pattern(tree,info['graph_sha256'],tempo=2,seed=123)
  hashes.add(meta['pattern_sha256']);upload_program(d,raw,save=False)
  ended=wait_end(d);assert ended['events']==1
  report['tests']['deep_nesting']=ended
  deadline=time.monotonic()+2.5
  while time.monotonic()<deadline:
   d.request('PINFO');time.sleep(.1)
  observed=telemetry.snapshot()
  report['diagnostics_after_deep']={k:observed[k] for k in
   ('controls_stack_free_bytes','stack_free_bytes','faults','nonfinite','overflow','write_fail','dma_event_overflow') if k in observed}
  if 'controls_stack_free_bytes' in observed:assert observed['controls_stack_free_bytes']>=1024
  d.request('PPLAY');d.request('PANIC');time.sleep(.15)
  stopped=d.request('PINFO');assert not stopped['running'] and stopped['faulted']
  report['tests']['panic_cancels_ownership']=stopped
  # Save a set program bound to the already-saved user Main. No test Main
  # package is ever persisted, so Main/FX generations remain unchanged.
  restore(d,b,0)
  controls=schema(d,0)['controls'];name=next(c['name'] for c in controls if c['writable'] and not c['name'].startswith('__esp32_'))
  value=next(c['values'][0] for c in controls if c['name']==name)
  tree=op('Pbind','type','esp32Set',name,op('Pseq',[value,value],op('Infinity')),'dur',.25)
  raw,meta=compile_pattern(tree,b['state']['status']['graph_sha256'],tempo=2,seed=321,autostart=True)
  hashes.add(meta['pattern_sha256']);upload_program(d,raw,save=True)
  time.sleep(.35);saved=d.request('PINFO');assert saved['events']>=2 and saved['running']
  report['tests']['saved_set_program']=saved
  d.request('PSTOP');assert not d.request('PINFO')['running']
  d.request('PPLAY');time.sleep(.15);assert d.request('PINFO')['running']
  report['tests']['stop_restart']=True
  report['autostart_program_sha256']=meta['pattern_sha256']
  if args.reboot:
   old=d;d=None;d=reset_device(old,args.device_id,telemetry)
   deadline=time.monotonic()+5
   while time.monotonic()<deadline:
    booted=d.request('PINFO')
    if booted['running'] and booted['events']>=2:break
    time.sleep(.1)
   assert booted['running'] and booted['bound'] and booted['sha256']==meta['pattern_sha256']
   assert d.request('VOLUME')['percent']==0
   report['tests']['reboot_autostart']=booted
  report['passed']=True
 except BaseException as error:
  report['passed']=False;report['error']=str(error) or type(error).__name__;raise
 finally:
  try:
   if d:
    try:
     if changes_allowed:
      current=d.request('PINFO');status=d.request('STATUS')
      assert status['graph_sha256'] in graphs,'Main changed outside qualification'
      if current['loaded']:
       assert current['sha256'] in hashes,'Program changed outside qualification'
       d.request('PDELETE')
      if args.reboot:
       old=d;d=None;d=reset_device(old,args.device_id,telemetry)
       assert not d.request('PINFO')['loaded'],'Deleted program returned after reboot'
       report['tests']['deletion_survives_reboot']=True
      report['restoration']=restore(d,b,b['state']['volume_percent'],save=True)
      assert not d.request('PINFO')['loaded']
    finally:
     if d:d.close()
  except BaseException as error:
   report['passed']=False;report['restoration_error']=str(error) or type(error).__name__;raise
  finally:
   try:
    state=client.http('connect',dict(port=find_port(args.device_id)))
    report['studio_connected']=state['hello']['device_id']==args.device_id
   except Exception as error:
    report['studio_error']=str(error);report['passed']=False
   finally:
    client.close();report['passed']=report['passed'] and 'restoration' in report
    args.output.write_text(json.dumps(report,indent=2)+'\n')
 print('PASS: muted device pattern checks; original Main/FX, controls, generations and volume restored')

if __name__=='__main__':main()
