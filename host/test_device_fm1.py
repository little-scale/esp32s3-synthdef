#!/usr/bin/env python3
"""Check the optional FM1 image: muted matrices and optional low-level UI playback."""
import argparse
import hashlib
import json
import re
import struct
import time
from pathlib import Path
from engine_profile import generate
from patches import Device,ROOT
import profile_timing as matrix
from exercise_timing import collect_exercise
from synthdef_binary import encode

def operator_graph(kind):
    inventory=json.loads((ROOT/'evidence/fm1-inventory.json').read_text())
    typ='UnaryOpUGen' if kind=='unary' else 'BinaryOpUGen'
    selectors=sorted(map(int,inventory['operators'][typ]))
    g=dict(name=kind+'-diagnostic',constants=[],controls=[440,.5,1,.5,.5,.5,.5],
           names=[(n,i) for i,n in enumerate(('freq','amp','gate','knob1','knob2','knob3','knob4'))],nodes=[])
    def constant(value):
        if value not in g['constants']:g['constants'].append(value)
        return (-1,g['constants'].index(value))
    def node(name,refs,rate=2,outputs=None,special=0):
        index=len(g['nodes']);g['nodes'].append((name,rate,refs,[rate] if outputs is None else outputs,special));return (index,0)
    control=node('Control',[],rate=1,outputs=[1]*7)
    x=node('K2A',[node('MulAdd',[(control[0],3),constant(.5),constant(.25)],rate=1)])
    y=node('K2A',[node('MulAdd',[(control[0],4),constant(.5),constant(.25)],rate=1)])
    integer_x=node('MulAdd',[x,constant(24),constant(6)])
    integer_y=node('MulAdd',[y,constant(24),constant(6)])
    values=[]
    for selector in selectors:
        refs=[x] if kind=='unary' else [integer_x,integer_y] if selector in (17,18) else [x,y]
        output=node(typ,refs,special=selector)
        if kind=='binary' and selector in (17,18):
            output=node('BinaryOpUGen',[output,constant(1/128 if selector==17 else 1/4)],special=2)
        values.append(output)
    index=node('Phasor',[constant(0),constant(1),constant(0),constant(len(values)),constant(0)])
    output=node('Select',[index,*values])
    output=node('BinaryOpUGen',[output,constant(.005 if kind=='unary' else .05)],special=2)
    output=node('Pan2',[output,constant(0),constant(1)],outputs=[2,2])
    node('Out',[constant(0),output,(output[0],1)],outputs=[])
    return encode(g),selectors

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--playback',action='store_true')
    args=p.parse_args();report={'passed':False,'status':'incomplete','matrices':[],'exercises':[],
        'profile':'fm1-compat-v1','playback_authorized':args.playback,'saved_patch_writes':False}
    def save():args.output.write_text(json.dumps(report,indent=2)+'\n')
    save();build=ROOT/'build/host/device-fm1';build.mkdir(parents=True,exist_ok=True)
    matrix.ENGINE=generate(build/'src','fm1').parent
    renderer=matrix.compile_renderer();delay_renderer=matrix.compile_delay_renderer()
    with args.output.with_suffix('.log').open('wb') as log:
        d=Device(args.port,log);original_effect=None;initial_slot=None
        try:
            hello=d.hello();report['hello']=hello
            assert hello['policy']=='fm1-compat-v1' and hello['rate']==44100
            assert hello['build']==re.search(r'#define BUILD_ID "(.*?)"',(ROOT/'firmware/main/generated.h').read_text())[1]
            d.link.write(b'x');d.request('PANIC')
            initial=d.request('STATUS');initial_slot=initial['slot'];report['initial_status']=initial
            original_effect=d.request('FX');report['initial_effect']=original_effect
            report['initial_library']=d.request('LIST');save()
            report['master_delay']=matrix.collect_delay_matrix(d,delay_renderer);save()
            print('PASS: muted delay windows at 20 ms, 350 ms, 1 s and 5 s',flush=True)
            entries=json.loads((ROOT/'examples/catalog.json').read_text())
            for name in ['touch-sine','mac-sine',*(e['id'] for e in entries),'unary','binary']:
                if name in ('unary','binary'):
                    raw,selectors=operator_graph(name);path=build/(name+'.scsyndef');path.write_bytes(raw)
                    active=d.upload(raw,b'// Temporary diagnostic graph; not a musical patch.\n',name.title()+' diagnostics')
                else:
                    path=ROOT/f'examples/{name}.scsyndef';raw=path.read_bytes();selectors=None
                    entry=next((e for e in entries if e['id']==name),None)
                    options=dict(name=entry['name'],labels=entry['labels'],mapping=entry['mapping']) if entry else dict(name=name)
                    active=d.upload(raw,(ROOT/f'examples/{name}.scd').read_bytes(),**options)
                assert active['graph_sha256']==hashlib.sha256(raw).hexdigest()
                result=matrix.collect_matrix(d,active,path,'fm1-'+name,renderer)
                result['patch']=name
                if selectors is not None:
                    result['operator_selectors']=selectors
                    result['diagnostic_graph_hex']=raw.hex()
                report['matrices'].append(result);save()
                print(f'PASS: {name} muted 280-case matrix; max PCM error {result["numerical"]["max_pcm_step_error"]}',flush=True)
            if args.playback:
                for entry in sorted(entries,key=lambda e:e['id']!='filtered'):
                    name=entry['id'];active=d.install_catalog(name,diagnostic=True)
                    # Default amp is 0.5. Reduce to approximately 0.2 before
                    # exercising; constructor/reference matrices stay unchanged.
                    d.link.write(b'['*6)
                    offset=log.tell();print('Playback/timing: '+entry['name'],flush=True)
                    exercise=collect_exercise(d,args.output.with_suffix('.log'),hello,active,1,offset)
                    exercise['patch']=name;exercise['controller_amp_requested']=.2
                    report['exercises'].append(exercise);save()
            report['passed']=all(r['numerical']['passed'] for r in report['matrices']) and all(
                r['reported_output_checks_passed'] and r['timing_budget_passed'] for r in report['exercises'])
            report['status']='complete'
        except Exception as error:
            report['error']=repr(error);raise
        finally:
            try:
                d.link.write(b'x');d.request('PANIC')
                if original_effect:d.request('FX',struct.pack('<fff',*[original_effect[k] for k in ('time','feedback','wet')]))
                if initial_slot is not None and initial_slot>=0:d.request('LOAD',bytes([initial_slot]))
                else:d.request('LOAD',b'\1')
                report['final_status']=d.request('STATUS');report['final_library']=d.request('LIST')
                report['library_unchanged']=report['final_library']==report.get('initial_library')
                if not report['library_unchanged']:report['passed']=False
            finally:d.link.write(b'!');d.close();save()
    print(json.dumps({k:report[k] for k in ('passed','status','library_unchanged')},indent=2),flush=True)
    return report['passed']

if __name__=='__main__':raise SystemExit(0 if main() else 1)
