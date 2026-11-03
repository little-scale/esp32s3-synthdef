#!/usr/bin/env python3
"""Muted physical kernel timing, restoring saved packages/settings afterwards."""
import argparse
import json
from pathlib import Path
import statistics
import time

from patches import ROOT,Device
from profile_ugens import collect
from qualify_headless import Qualification
from studio_client import StudioClient

FIXTURES={
 'filters':r'''{var x=SinOsc.ar(220,0,0.01),f=SinOsc.kr(0.2).range(200,2400);
 Mix([Resonz.ar(x,f,0.1),Ringz.ar(x,f,0.2),LPF.ar(x,f),HPF.ar(x,f),
 RLPF.ar(x,f,0.2),RHPF.ar(x,f,0.2),BPF.ar(x,f,0.1),BRF.ar(x,f,0.1)])*0.01!2}''',
 'lag':r'''{arg time=1;var x=SinOsc.ar(220,0,0.01);
 12.do({x=LagUD.ar(x,time,time*0.5)+Lag.ar(x,time)});x*0.001!2}''',
 'unary':r'''{arg note=60;var x=note;
 40.do({x=x.midicps.cpsmidi});SinOsc.ar(x.midicps,0,0.01)!2}''',
 'saw_resonz_miverb':(ROOT/'examples/module-audio-check.scd').read_text(),
}


def run(target,phase,runs,output):
 client=StudioClient();q=Qualification(client,target,ROOT/'build/host/private'/f'dsp-kernels-{phase}-{time.time_ns()}.json')
 report=dict(passed=False,hardware=True,phase=phase,runs=runs,fixtures={})
 try:
  state=client.http('config')
  if not state['connected']:
   from serial.tools import list_ports
   ports=[p for p in list_ports.comports() if (p.serial_number or '').replace(':','').lower()==target.removeprefix('esp32-')]
   if len(ports)!=1:raise RuntimeError('Exact requested USB module is not visible')
   client.http('connect',dict(port=ports[0].device))
  hello=q.save();report.update(device_id=target,build=hello['build'])
  q.rpc('meta',args=['volume',0]);q.rpc('bypass',bypassed=True)
  for name,source in FIXTURES.items():
   artifact=q.compile(source,definition=False);q.install(artifact)
   samples=[]
   state=client.http('refresh',{});port=state['port']
   if state['hello']['device_id']!=target:raise RuntimeError('Module changed during timing')
   client.http('disconnect',{})
   d=None
   try:
    d=Device(port)
    if d.hello()['device_id']!=target:raise RuntimeError('Direct USB identity mismatch')
    for trial in range(runs):
     result=collect(d)
     samples.append({k:result[k] for k in ('header','by_type','normal_average_us_at_240mhz')})
   finally:
    if d is not None:d.close()
    # Reattach even after a failed diagnostic so the outer restoration can
    # inspect the current graph before deciding whether it owns the slot.
    client.http('connect',dict(port=port))
   report['fixtures'][name]=dict(graph_sha256=artifact['graph_sha256'],nodes=artifact['nodes'],
      median_us=statistics.median(s['normal_average_us_at_240mhz'] for s in samples),runs=samples)
   print(name,report['fixtures'][name]['median_us'],'us/block',flush=True)
  report['passed']=True
 except Exception as error:
  report['error']=str(error);raise
 finally:
  try:report['restoration']=q.restore()
  except Exception as error:report['restoration_error']=str(error);report['passed']=False;raise
  finally:
   client.close();output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n')
 return report


if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--device-id',required=True)
 p.add_argument('--phase',required=True);p.add_argument('--runs',type=int,default=3)
 p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if not 1<=a.runs<=5:p.error('Use 1–5 timing runs')
 print(json.dumps(run(a.device_id,a.phase,a.runs,a.output),indent=2))
