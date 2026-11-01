#!/usr/bin/env python3
"""Read-only source snapshots and optional normal-DMA source scrolling checks."""
import argparse,hashlib,json,re,struct,subprocess,sys,time
from pathlib import Path
from patches import Device,ROOT
from exercise_timing import output_counter_delta
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--port',required=True);p.add_argument('--output',type=Path,required=True)
p.add_argument('--playback',action='store_true');args=p.parse_args()
report=dict(passed=False,status='incomplete',screens=[],audio=[],saved_patch_writes=False)
def save():args.output.write_text(json.dumps(report,indent=2)+'\n')
save();logpath=args.output.with_suffix('.log')
with logpath.open('wb') as log:
    d=Device(args.port,log);effect=None;slot=1;before=None
    def wait(seconds):
        until=time.monotonic()+seconds
        while time.monotonic()<until:list(d.lines())
    def snapshot(name):
        d.request('PANIC');d.link.write(b'c');wait(.25);d.link.write(b's');lines=[];complete=False;until=time.monotonic()+40
        while time.monotonic()<until and not complete:
            for line in d.lines():
                if line.startswith(b'SCREEN_'):lines.append(line.rstrip(b'\r')+b'\n')
                if line.rstrip(b'\r')==b'SCREEN_END':complete=True;break
        assert complete,'Incomplete source snapshot'
        path=ROOT/f'evidence/source-{name}.log';path.write_bytes(b''.join(lines));png=path.with_suffix('.png')
        subprocess.run([sys.executable,str(ROOT/'host/decode_screen.py'),str(path),'--output',str(png)],check=True)
        report['screens'].append(dict(patch=name,png=str(png.relative_to(ROOT))));save()
    try:
        hello=d.hello();report['hello']=hello
        assert hello['build']==re.search(r'#define BUILD_ID "(.*?)"',(ROOT/'firmware/main/generated.h').read_text())[1]
        d.link.write(b'x');d.request('PANIC');slot=d.request('STATUS')['slot'];effect=d.request('FX');before=d.request('LIST')
        original={}
        for entry in before:
            if entry['slot'] and entry['name']:
                d.request('LOAD',bytes([entry['slot']]));graph,source,info=d.download()
                original[str(entry['slot'])]=dict(graph=hashlib.sha256(graph).hexdigest(),source=hashlib.sha256(source).hexdigest(),metadata=info['manifest'][152:])
        report['initial_packages']=original;save()
        for patch_slot,name in ((0,'factory'),(1,'mac-sine'),(4,'filtered')):
            d.request('LOAD',bytes([patch_slot]));snapshot(name)
        graph=ROOT/'build/host/code-view/CodePreview.scsyndef';source=ROOT/'examples/code-view.scd'
        d.upload(graph.read_bytes(),source.read_bytes(),'Code colours');snapshot('colours')
        if args.playback:
            for patch_slot,name in ((1,'mac-sine'),(4,'filtered'),(2,'phase-fm')):
                d.request('LOAD',bytes([patch_slot]));d.link.write(b'['*6);d.link.write(b'c');wait(.25)
                d.link.write(b'r');offset=log.tell();d.link.write(b'n');wait(12);d.link.write(b'o');wait(1.5);d.link.write(b'r');d.request('PANIC');wait(1.2)
                raw=logpath.read_bytes();text=raw[offset:].decode(errors='replace');baseline,delta=output_counter_delta(text,raw[:offset].decode(errors='replace'))
                assert not any(delta.values()),delta
                assert 'active=1' in text and re.findall(r'active=(\d+)',text)[-1]=='0'
                assert max(map(int,re.findall(r'\bpcm_peak=(\d+)',text)))>0
                report['audio'].append(dict(patch=name,seconds=12,output_counter_baseline=baseline,output_counter_delta=delta,
                    scope='Held note and release with code viewport scrolling/redrawing at 25 Hz; nominal DMA path; no physical continuity claim'))
                save();print('Source scrolling/audio passed: '+name,flush=True)
                d.link.write(b'v')
        final={}
        for key in original:
            d.request('LOAD',bytes([int(key)]));graph,source,info=d.download()
            final[key]=dict(graph=hashlib.sha256(graph).hexdigest(),source=hashlib.sha256(source).hexdigest(),metadata=info['manifest'][152:])
        assert final==original;report['packages_unchanged']=True;report['status']='complete';report['passed']=True
        text=logpath.read_bytes().decode(errors='replace')
        report['minimum']={key:min(map(int,re.findall(r'\b'+key+r'=(\d+)',text))) for key in ('internal_min','internal_largest','stack_free_bytes','controls_stack_free_bytes')}
        report['observed_overall_combined_max_us']=max(map(int,re.findall(r'\bcombined_max_us=(\d+)',text)))
    except Exception as error:report['error']=repr(error);raise
    finally:
        try:
            d.link.write(b'x');d.request('PANIC')
            if effect:d.request('FX',struct.pack('<fff',*[effect[k] for k in ('time','feedback','wet')]))
            d.request('LOAD',bytes([slot if slot>=0 else 1]));report['final_status']=d.request('STATUS');d.link.write(b'c')
            if before is not None:
                report['library_unchanged']=d.request('LIST')==before
                if not report['library_unchanged']:report['passed']=False
        finally:d.link.write(b'!');d.close();save()
print(json.dumps({key:report[key] for key in ('passed','status','library_unchanged')},indent=2))
