#!/usr/bin/env python3
"""Bounded audible checks with PCM assertions; restore saved Main/FX afterwards."""
import argparse
import json
from pathlib import Path
import time
from patches import ROOT
from qualify_headless import Qualification,REVERB,BURST,levels,require
from studio_client import StudioClient


def run(target,output,volume=None):
    c=StudioClient();q=Qualification(c,target,ROOT/'build/host/private'/('dsp-listen-'+str(time.time_ns())+'.json'))
    report=dict(passed=False,hardware=True,device_id=target,listening='pending user assessment',tests={})
    try:
        hello=q.save();report['build']=hello['build'];report['volume']=q.backup['volume'] if volume is None else volume
        require(0<=report['volume']<=1,'Volume must be between zero and one')
        q.rpc('meta',args=['volume',report['volume']]);q.rpc('bypass',bypassed=True)
        for name,file,seconds in (('eight_saw','module-audio-check',10),('comb_kr','comb-cloud-kr',12),('triggered_harmonics','triggered-harmonics',12)):
            artifact=q.compile((ROOT/('examples/'+file+'.scd')).read_text(),definition=False)
            q.install(artifact);q.rpc('play',stage='main')
            print('PLAYING',name,flush=True);time.sleep(2)
            measured=levels(q.capture(.5));require(measured['peak']<32767,'PCM clipped in '+name)
            # Stochastic clouds can have a quiet half-second. Keep that sample
            # as an observation; the subsequent gated/tail tests assert signal.
            report['tests'][name]=dict(graph_sha256=artifact['graph_sha256'],pcm=measured)
            time.sleep(seconds-2)
        q.rpc('stop',stage='main');q.load(REVERB,'master');q.load(BURST)
        q.rpc('play',stage='fx');q.rpc('play',stage='main');print('PLAYING burst_and_reverb_tail',flush=True)
        time.sleep(.2);tail=levels(q.capture(1));require(min(tail['rms'])>.1,'Reverb tail missing')
        q.rpc('stop',stage='main');after=levels(q.capture(.5));require(min(after['rms'])>.02,'FX tail lost when Main stopped')
        time.sleep(3);q.rpc('panic');quiet=levels(q.capture(.2));require(quiet['peak']==0,'Panic did not silence output')
        report['tests']['reverb']=dict(tail=tail,after_main_stop=after,panic=quiet)
        print('PASS digital signal/tail/panic checks; listening assessment pending',flush=True)
        report['passed']=True
    except BaseException as error:
        report['error']=str(error);raise
    finally:
        try:report['restoration']=q.restore()
        except Exception as error:report['restoration_error']=str(error);report['passed']=False;raise
        finally:c.close();output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--device-id',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--volume',type=float)
    a=p.parse_args();run(a.device_id,a.output,a.volume)
