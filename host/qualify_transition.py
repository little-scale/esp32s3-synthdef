#!/usr/bin/env python3
"""Capture a bounded Main polarity swap and restore the user's saved setup."""
import argparse
import array
import base64
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time
from patches import ROOT
from qualify_headless import Qualification
from studio_client import StudioClient


def run(target,output):
 c=StudioClient();q=Qualification(c,target,ROOT/'build/host/private'/f'transition-{time.time_ns()}.json')
 report=dict(passed=False,device_id=target,hardware=True,scope='Post-volume PCM during real Main upload; not analogue pop measurement')
 try:
  hello=q.save();report['build']=hello['build']
  positive=q.compile('{ DC.ar(0.1) ! 2 }.play',definition=False)
  negative=q.compile('{ DC.ar(-0.1) ! 2 }.play',definition=False)
  q.rpc('meta',args=['volume',.2]);q.rpc('bypass',bypassed=True)
  q.install(positive);time.sleep(.2)
  before=c.http('audio')
  with ThreadPoolExecutor(max_workers=1) as pool:
   future=pool.submit(c.http,'capture',dict(seconds=.8,device_id=target));time.sleep(.1)
   q.install(negative);capture=future.result(timeout=10)
  samples=array.array('h',base64.b64decode(capture['data']));left=samples[::2];right=samples[1::2]
  assert left==right,'Stereo ramp differs between channels'
  peak=max(left);bottom=min(left);assert peak>100 and bottom< -100,'Capture did not span both patches'
  start=next(i for i in range(1,len(left)) if left[i]<left[i-1] and left[i]>0)
  end=next(i for i in range(start,len(left)) if left[i]==0)
  rise=next(i for i in range(end,len(left)) if left[i]<0)
  settled=next(i for i in range(rise,len(left)) if left[i]<=bottom+1)
  jump=max(abs(b-a) for a,b in zip(left,left[1:]));report.update(positive_peak=peak,negative_peak=bottom,
    down_frames=end-start+1,zero_gap_frames=rise-end,up_frames=settled-rise+1,max_adjacent_step_s16=jump)
  assert 180<=report['down_frames']<=240,'Outgoing fade is not approximately 5 ms'
  assert report['zero_gap_frames']>=768,'Output did not remain silent through DMA drain'
  assert 160<=report['up_frames']<=240,'Incoming fade is not approximately 5 ms'
  assert jump<=max(16,peak//25),'Abrupt PCM discontinuity during patch replacement'
  # Explicit instance operations preserve FX state. A DC offset in the master
  # makes any full-level rebound during the drain unambiguous in captured PCM.
  q.install(positive)
  fx=q.compile('{ In.ar(0,2) + 0.04 }',target='master',definition=False)
  q.install(fx,'master');q.rpc('bypass',bypassed=False);time.sleep(.2)
  with ThreadPoolExecutor(max_workers=1) as pool:
   future=pool.submit(c.http,'capture',dict(seconds=.8,device_id=target));time.sleep(.1)
   q.rpc('play',stage='main');capture=future.result(timeout=10)
  values=array.array('h',base64.b64decode(capture['data']))[::2]
  first_zero=next(i for i,v in enumerate(values) if v==0)
  first_after=next(i for i in range(first_zero,len(values)) if values[i]!=0)
  jump=max(abs(b-a) for a,b in zip(values,values[1:]));gap=first_after-first_zero
  assert gap>=768 and jump<=max(16,max(values)//25),'Preserved FX rebounded during drain'
  report['preserved_fx_restart']=dict(zero_gap_frames=gap,max_adjacent_step_s16=jump)
  q.rpc('bypass',bypassed=True)
  definition=q.compile('{ DC.ar(0.1) ! 2 }',definition=True);q.install(definition);time.sleep(.1)
  quiet=c.http('capture',dict(seconds=.1,device_id=target));quiet_pcm=array.array('h',base64.b64decode(quiet['data']))
  assert max(abs(x) for x in quiet_pcm)==0 and not q.info()['active'],'Definition-only upload started sound'
  report['definition_only_remains_inactive']=True
  after=c.http('audio');keys=('write_fail','partial','dma_event_overflow','faults','clips','nonfinite','overflow')
  report['diagnostic_deltas']={k:after.get(k,0)-before.get(k,0) for k in keys}
  assert not any(report['diagnostic_deltas'].values()),'Audio fault counters changed'
  report['passed']=True
 finally:
  try:report['restoration']=q.restore()
  except Exception as error:report['restoration_error']=str(error);report['passed']=False;raise
  finally:c.close();output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n')
 return report


if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--device-id',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 print(json.dumps(run(a.device_id,a.output),indent=2))
