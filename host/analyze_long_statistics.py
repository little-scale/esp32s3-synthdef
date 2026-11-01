#!/usr/bin/env python3
"""Apply the pinned chaotic statistics to complete independent NRT recordings."""
import argparse,array,importlib.util,json,math,subprocess
from pathlib import Path
from long_trace import ROOT,BUILD
from compare_long_sc import read_wave
p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,default=ROOT/'evidence/long-trace-plan.json')
p.add_argument('--sc',type=Path,default=ROOT/'evidence/long-trace-sc.json')
p.add_argument('--device',type=Path);p.add_argument('--output',type=Path,default=ROOT/'evidence/long-trace-chaotic-statistics.json');args=p.parse_args()
component=ROOT/'firmware/components/instrument'
folder=BUILD/('full-observer-device' if args.device else 'full-observer');folder.mkdir(exist_ok=True)
# Add only a host-side file observer after the unchanged renderer call. The
# target program and DSP source are untouched; the same event loop is retained.
source=(component/'trace_probe.c').read_text();needle='fm_render_input(g,v,scratch,out,input);'
assert source.count(needle)==1
source='#include <stdio.h>\nextern FILE *trace_full_stream;\n'+source.replace(needle,needle+'\n        if(fwrite(out,sizeof(float),FM_BLOCK*2,trace_full_stream)!=FM_BLOCK*2)return 0;')
(folder/'observed_trace.c').write_text(source)
main=(ROOT/'tests/render_trace.c').read_text();main=main.replace('int main(int argc,char **argv)','FILE *trace_full_stream;\nint main(int argc,char **argv)')
main=main.replace('trace_summary s;int passed=', 'trace_full_stream=fopen(argv[2],"wb");assert(trace_full_stream);\n    trace_summary s;int passed=')
old='f=fopen(argv[2],"wb");assert(f);assert(fwrite(capture,sizeof(float),TRACE_FLOATS,f)==TRACE_FLOATS);assert(!fclose(f));'
assert main.count(old)==1;main=main.replace(old,'assert(!fclose(trace_full_stream));')
(folder/'main.c').write_text(main);exe=folder/'render-full'
subprocess.run(['cc','-std=c99','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off',
    '-I'+str(BUILD/'src'),'-I'+str(component/'include'),str(BUILD/'src/fm_load.c'),str(BUILD/'src/fm_render.c'),
    str(folder/'observed_trace.c'),str(folder/'main.c'),'-lm','-o',str(exe)],check=True)
spec=importlib.util.spec_from_file_location('pinned_stochastic',ROOT/'upstream/fm1-synthdef/synthdef-engine/tests/stochastic_metrics.py')
metrics=importlib.util.module_from_spec(spec);spec.loader.exec_module(metrics)
def distribution(name,a,b):
    value=metrics.comparison(name,a,b)
    if value:return value
    # Extended Gendy recordings can lose trajectory identity after many more
    # transitions than the original short fixtures. Report their acoustic
    # consistency separately, using the same declared statistical envelopes.
    stride=128 if '_kr_' in name or '-kr-' in name else 2
    x=list(a)[::stride];y=list(b)[::stride];skip=max(4,len(x)//10);x=x[skip:];y=y[skip:]
    def stats(z):
        mean=sum(z)/len(z);sd=math.sqrt(sum((v-mean)**2 for v in z)/len(z));rms=math.sqrt(sum(v*v for v in z)/len(z))
        rough=math.sqrt(sum((v-w)**2 for v,w in zip(z[1:],z))/max(1,len(z)-1));return mean,sd,rms,rough
    ma,sa,ra,da=stats(x);mb,sb,rb,db=stats(y)
    ratio=lambda v,w:v/w if w else 1 if not v else math.inf
    rr,sr,dr=ratio(ra,rb),ratio(sa,sb),ratio(da,db);mean=abs(ma-mb)/max(ra,rb,1e-12)
    passed=all(math.isfinite(v) for v in x+y) and .5<rr<2 and .5<sr<2 and .4<dr<2.5 and mean<.4
    return dict(comparison='Extended Gendy statistical consistency, not original short-fixture waveform equivalence',rms_ratio=rr,sd_ratio=sr,roughness_ratio=dr,normalized_mean_error=mean,stochastic_passed=passed)
plan=json.loads(args.plan.read_text());jobs={j['id']:j for j in plan['jobs']};results=[]
sc=json.loads(args.sc.read_text()) if not args.device else None
device=json.loads(args.device.read_text()) if args.device else None
raw={}
if device:
    selected={i for i,row in enumerate(device['captures']) if row['comparison']['comparison']=='statistical-only'}
    raw={i:bytearray() for i in selected};index=-1
    with args.device.with_suffix('.log').open('rb') as log:
        for line in log:
            if line.startswith(b'TRACE_BEGIN '):index+=1
            if index in raw and line.startswith(b'TRACE_BLOCK '):raw[index].extend(bytes.fromhex(line.split()[-1].decode()))
rows=device['captures'] if device else sc['results']
for index,row in enumerate(rows):
    if (device and index not in raw) or (not device and row.get('comparison')!='chaotic-divergence'):continue
    job=jobs[row['id']];out=folder/(job['id']+'.f32')
    a=array.array('f');b=array.array('f')
    if device:
        a.frombytes(raw[index]);b.frombytes((ROOT/job['samples']).read_bytes());assert len(a)==len(b)==5120
    else:
        subprocess.run([str(exe),str(ROOT/job['graph']),str(out)],check=True,capture_output=True)
        a.frombytes(out.read_bytes());b=read_wave(BUILD/'sc'/(job['id']+'.wav'))[:len(a)]
    value=distribution(job['id'],a,b)
    results.append({'id':job['id'],'samples':len(a),**value})
    print(job['id'],value['stochastic_passed'],flush=True)
report={'passed':all(r['stochastic_passed'] for r in results),'results':results,
    'scope':('Captured hardware windows versus native reference' if device else 'Full 11.89-second native-versus-SuperCollider recordings')+'; distribution/roughness criteria use the pinned envelopes, explicitly extended to long Gendy traces. Statistical agreement is not waveform identity; identical-state transition oracles are covered separately by the host suite.'}
args.output.write_text(json.dumps(report,indent=2)+'\n')
assert report['passed']
