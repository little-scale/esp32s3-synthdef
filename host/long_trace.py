"""Build and run bounded long DSP traces, with identical host/device events."""
import array,hashlib,json,math,re,struct,subprocess,time,zlib
from pathlib import Path
from engine_profile import ROOT,generate
from synthdef_binary import decode,encode
BLOCKS=8192
WINDOWS=[0,1,2,3,4,7,8,15,16,31,63,64,127,172,344,516,688,1023,1024,1722,2047,2048,2755,3444,3445,3446,4095,4096,4097,4098,4268,4440,5120,6143,6890,6891,7540,7541,7542,8191]
BUILD=ROOT/'build/host/long-trace'

def compile_renderer():
    src=generate(BUILD/'src','fm1');exe=BUILD/'render-trace';component=ROOT/'firmware/components/instrument'
    subprocess.run(['cc','-std=c99','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off',
        '-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all','-I'+str(src),'-I'+str(component/'include'),
        str(src/'fm_load.c'),str(src/'fm_render.c'),str(component/'trace_probe.c'),str(ROOT/'tests/render_trace.c'),'-lm','-o',str(exe)],check=True)
    return exe

def wrap_fixture(path):
    g=decode(path.read_bytes());index=len(g['controls']);g['controls'] += [440,.5,1,.5,.5,.5,.5]
    g['names']=[('src_'+name,i) for name,i in g['names']]+[(n,index+i) for i,n in enumerate(('freq','amp','gate','knob1','knob2','knob3','knob4'))]
    g['nodes']=[('Control',1,[],[1]*7,index)]+[(n,r,[(i+1 if i>=0 else i,o) for i,o in refs],rates,s) for n,r,refs,rates,s in g['nodes']]
    event_path=path.with_suffix('.events.json');events=json.loads(event_path.read_text()) if event_path.exists() else []
    if not event_path.exists() and (path.stem.startswith('env_') or path.stem in ('adsr','fm1_voice','forced','loop','retrigger','phase_control','pan_control')):
        fallback={'retrigger':[(.1,0),(.125,1),(.3,0)],'forced':[(.25,-1.05)],'phase_control':[(.25,1)],'pan_control':[(.25,.6)]}
        events=fallback.get(path.stem,[(.25,0)])
    if events:
        first=len(g['controls'])
        for when,value in events:
            block=int(when*44100)//64
            g['names'].append((f'trace_ev_{block:06d}',len(g['controls'])));g['controls'].append(value)
        g['nodes'].append(('Control',0,[],[0]*len(events),first))
    g['name']='trace-'+path.stem[:57]
    return encode(g),events

def rate_graph(kind,rate):
    inv=json.loads((ROOT/'evidence/fm1-inventory.json').read_text());typ='UnaryOpUGen' if kind=='unary' else 'BinaryOpUGen'
    selectors=sorted(map(int,inv['operators'][typ]))
    g=dict(name=f'rate-probe-{kind}-{rate}',constants=[],controls=[440,.5,1,.5,.5,.5,.5,.25,.25],
        names=[(n,i) for i,n in enumerate(('freq','amp','gate','knob1','knob2','knob3','knob4','probe_initial','probe_live'))],nodes=[])
    def c(value):
        if value not in g['constants']:g['constants'].append(value)
        return (-1,g['constants'].index(value))
    def n(name,refs,rate=2,outputs=None,special=0):
        i=len(g['nodes']);g['nodes'].append((name,rate,refs,[rate] if outputs is None else outputs,special));return (i,0)
    n('Control',[],rate=1,outputs=[1]*7)
    initial=n('Control',[],rate=0,special=7);live=n('Control',[],rate=1,special=8)
    x=initial if rate==0 else live
    if rate==2:x=n('K2A',[live])
    integer=n('MulAdd',[x,c(24),c(6)],rate=rate);values=[]
    for selector in selectors:
        refs=[x] if kind=='unary' else [integer,c(18)] if selector in (17,18) else [x,c(.5)]
        result=n(typ,refs,rate=rate,special=selector)
        if kind=='binary' and selector in (17,18):result=n('BinaryOpUGen',[result,c(1/128 if selector==17 else 1/4)],rate=rate,special=2)
        if rate!=2:result=n('K2A',[result])
        values.append(result)
    phase=n('Phasor',[c(0),c(1),c(0),c(len(values)),c(0)])
    out=n('Select',[phase,*values]);out=n('BinaryOpUGen',[out,c(.005 if kind=='unary' else .05)],special=2)
    out=n('Pan2',[out,c(0),c(1)],outputs=[2,2]);n('Out',[c(0),out,(out[0],1)],outputs=[])
    return encode(g),selectors

def prepare_plan(edges=False,output=None):
    BUILD.mkdir(parents=True,exist_ok=True);exe=compile_renderer()
    inv=json.loads((ROOT/'evidence/fm1-inventory.json').read_text());rows=inv['profiles']['fm1']
    if edges:
        def edge(row):
            name=Path(row['path']).stem
            return name.startswith('m10_Gendy') or (name.startswith('m13_MiRings') and any(t in name for t in ('forced','bypass'))) or (name.startswith('m4_') and 'negative' in name) or name in ('m7_MiVerb_freeze','m7_MiVerb_saturation')
        rows=[row for row in rows if edge(row)]
    remaining={(n['name'],n['rate']) for row in rows for n in row['ugens']};expected=sorted(remaining);selected=[]
    def score(row):
        name=Path(row['path']).stem
        quality=2*('_live' in name or '_step' in name)+('impulse' in name or 'noise' in name)-('zero' in name or 'bypass' in name)
        return (len({(n['name'],n['rate']) for n in row['ugens']}&remaining),quality,-row['nodes'],name)
    while remaining and not edges:
        row=max(rows,key=score);cover={(n['name'],n['rate']) for n in row['ugens']}&remaining;assert cover
        selected.append(row);remaining-=cover
    jobs=[]
    if edges:selected=rows
    for kind in (() if edges else ('unary','binary')):
        for rate in (0,1,2):
            raw,selectors=rate_graph(kind,rate);jobs.append(dict(id=f'operators-{kind}-{rate}',raw=raw,selectors=selectors,rate=rate,events=[]))
    for row in selected:
        path=Path(row['path']);raw,events=wrap_fixture(path)
        jobs.append(dict(id=path.stem,raw=raw,source=str(path.relative_to(ROOT)),events=events))
    if edges:
        path=ROOT/'upstream/fm1-synthdef/synthdef-engine/fixtures/m10_Gendy3_kr_cp64.scsyndef'
        raw,events=wrap_fixture(path);g=decode(raw)
        ref=next(n[2][4] for n in g['nodes'] if n[0]=='Gendy3');assert ref[0]==-1
        g['constants'][ref[1]]=.1;g['name']='trace-gendy3-kr-slow'
        jobs.append(dict(id='gendy3-kr-slow',raw=encode(g),source=str(path.relative_to(ROOT)),events=events,variant='Frequency 0.1 Hz to exercise the closing-segment gap at control rate'))
    results=[]
    for index,job in enumerate(jobs):
        raw=job.pop('raw');path=BUILD/(job['id']+'.scsyndef');path.write_bytes(raw);samples=path.with_suffix('.f32')
        run=subprocess.run([str(exe),str(path),str(samples)],capture_output=True,text=True,timeout=60)
        if run.returncode:raise RuntimeError(job['id']+': '+run.stdout+run.stderr)
        summary=json.loads(run.stdout);assert summary['passed'] and summary['rejected']==0,job['id']
        layout=decode(raw);job.update(graph=str(path.relative_to(ROOT)),samples=str(samples.relative_to(ROOT)),graph_sha256=hashlib.sha256(raw).hexdigest(),
            type_rates=sorted({(n,r) for n,r,refs,rates,s in layout['nodes']}),host=summary)
        results.append(job)
        if not index%20:print(f'Host preflight {index+1}/{len(jobs)}',flush=True)
    report={'passed':True,'blocks':BLOCKS,'seconds_per_graph':BLOCKS*64/44100,'windows':WINDOWS,'expected_type_rates':expected,'jobs':results}
    (output or ROOT/'evidence/long-trace-plan.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Prepared',len(results),'graphs for',len(expected),'observed UGen/rate pairs',flush=True)
    return report

def prepare_cost_graphs(output):
    """Reproduce the twelve cost probes without an existing long-trace build."""
    output.mkdir(parents=True,exist_ok=True);jobs=[]
    for kind in ('unary','binary'):
        for rate in (0,1,2):
            raw,_=rate_graph(kind,rate);jobs.append((f'operators-{kind}-{rate}',raw))
    for model in range(6,0,-1):
        name=f'm13_MiRings{model}_live'
        raw,_=wrap_fixture(ROOT/f'upstream/fm1-synthdef/synthdef-engine/fixtures/{name}.scsyndef')
        jobs.append((name,raw))
    result=[]
    for name,raw in jobs:
        path=output/(name+'.scsyndef');path.write_bytes(raw)
        result.append(dict(id=name,graph=str(path.relative_to(ROOT)),graph_sha256=hashlib.sha256(raw).hexdigest()))
    return result

def collect(d):
    d.link.write(b'g');lines=[];end=False;until=time.monotonic()+75
    while time.monotonic()<until and not end:
        for line in d.lines():
            line=line.rstrip(b'\r')
            if line.startswith(b'TRACE_'):lines.append(line.decode().rstrip('\r'))
            if line==b'TRACE_END':end=True;break
    if not end:raise TimeoutError('Long trace incomplete: '+str(lines[-1:]))
    header=dict(re.findall(r'(\w+)=([^ ]+)',lines[0]));data=bytearray();indices=[]
    for line in lines[1:-1]:
        _,index,block,checksum,raw=line.split();chunk=bytes.fromhex(raw)
        assert int(index)==len(indices) and len(chunk)==512 and zlib.crc32(chunk)==int(checksum,16)
        indices.append(int(block));data.extend(chunk)
    assert indices==WINDOWS and header['blocks']==str(BLOCKS) and header['passed']=='1',header
    return header,bytes(data)

def compare(header,actual,job):
    a=array.array('f');a.frombytes(actual);b=array.array('f');b.frombytes((ROOT/job['samples']).read_bytes());assert len(a)==len(b)==len(WINDOWS)*128
    assert all(math.isfinite(x) for x in a)
    peak=max(abs(x-y) for x,y in zip(a,b));rms=math.sqrt(sum((x-y)**2 for x,y in zip(a,b))/len(a))
    scale=max(job['host']['peak'],1e-6)
    strict=peak<=max(1e-5,scale*1e-4) and rms<=max(3e-6,scale*3e-5)
    ratio=float(header['rms'])/job['host']['rms'] if job['host']['rms'] else (1 if float(header['rms'])==0 else math.inf)
    chaotic=any(n.startswith(('Gendy','Henon','Cusp','Latoocarfian','Lorenz','FBSine','Standard','Crackle')) or n=='SinOscFB' for n,r in job['type_rates'])
    statistical=not strict and chaotic and .8<=ratio<=1.25 and .5<=float(header['peak'])/max(job['host']['peak'],1e-12)<=2
    checks={key:int(header[key])==job['host'][key] for key in ('updates','rejected','initial_rejections','initial_accepts','restarts')}
    passed=all(checks.values()) and (strict or statistical)
    return dict(passed=passed,comparison='waveform' if strict else 'statistical-only' if statistical else 'failed',
        peak_error=peak,rms_error=rms,relative_rms_ratio=ratio,captured_floats=len(a),event_checks=checks,
        scope='Sparse windows across 11.89 s plus full-duration RMS/peak/fault/canary checks; statistical cases do not establish identical trajectories')

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--edges',action='store_true');p.add_argument('--output',type=Path)
    args=p.parse_args();prepare_plan(args.edges,args.output)
