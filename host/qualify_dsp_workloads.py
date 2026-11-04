#!/usr/bin/env python3
"""Muted, guarded four-workload timing for the DSP hardware session."""
import argparse
from pathlib import Path
import qualify_dsp_kernels as timing
from patches import ROOT

timing.FIXTURES={name:(ROOT/('examples/'+file+'.scd')).read_text() for name,file in (
    ('eight_saw','module-audio-check'),('comb_kr','comb-cloud-kr'),('triggered_harmonics','triggered-harmonics'))}
timing.FIXTURES['filters']=r'{var x=SinOsc.ar(220,0,0.01),f=SinOsc.kr(0.2).range(200,2400); Mix([Resonz.ar(x,f,0.1),Ringz.ar(x,f,0.2),LPF.ar(x,f),HPF.ar(x,f),RLPF.ar(x,f,0.2),RHPF.ar(x,f,0.2),BPF.ar(x,f,0.1),BRF.ar(x,f,0.1)])*0.01!2}'

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--device-id',required=True)
    p.add_argument('--phase',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--runs',type=int,default=3,choices=range(1,6));a=p.parse_args()
    timing.run(a.device_id,a.phase,a.runs,a.output)
