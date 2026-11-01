#!/usr/bin/env python3
"""Separate constructor, first-audio and live-block costs using the muted matrix."""
import argparse,json,re,struct
from pathlib import Path
from engine_profile import generate
from patches import ROOT,Device
import profile_timing as matrix
from long_trace import prepare_cost_graphs
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
selected=prepare_cost_graphs(ROOT/'build/host/expensive-profile/graphs')
matrix.ENGINE=generate(ROOT/'build/host/expensive-profile/src','fm1').parent;exe=matrix.compile_renderer()
report={'passed':False,'status':'incomplete','results':[],'scope':'Parked/muted 280-case diagnostic. Constructor and synchronous reset are separated from first/live rendering; no master effect or normal UI stress is included.'}
def save():args.output.write_text(json.dumps(report,indent=2)+'\n')
save()
with args.output.with_suffix('.log').open('wb') as log:
    d=Device(args.port,log);effect=None;slot=1;before=None
    try:
        hello=d.hello();report['hello']=hello;assert hello['policy']=='fm1-compat-v1'
        assert hello['build']==re.search(r'#define BUILD_ID "(.*?)"',(ROOT/'firmware/main/generated.h').read_text())[1]
        d.request('PANIC');slot=d.request('STATUS')['slot'];effect=d.request('FX');before=d.request('LIST')
        for job in selected:
            path=ROOT/job['graph'];active=d.upload(path.read_bytes(),b'// Temporary cost-profile diagnostic.\n',job['id'][:30])
            result=matrix.collect_matrix(d,active,path,'cost-'+job['id'],exe)
            result['id']=job['id'];result['phase_maximum_us']={key:max(c[key] for c in result['cases']) for key in ('reset','controls','prepare','dsp','pcm','total','live')}
            report['results'].append(result);save();print(job['id'],result['phase_maximum_us'],flush=True)
        report['status']='complete';report['passed']=True
    except Exception as error:report['error']=repr(error);raise
    finally:
        try:
            d.request('PANIC')
            if effect:d.request('FX',struct.pack('<fff',*[effect[k] for k in ('time','feedback','wet')]))
            d.request('LOAD',bytes([slot if slot>=0 else 1]));report['final_status']=d.request('STATUS')
            if before is not None:report['library_unchanged']=d.request('LIST')==before
        finally:d.link.write(b'!');d.close();save()
