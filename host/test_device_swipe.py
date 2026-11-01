#!/usr/bin/env python3
"""Check queued patch navigation on the board; pointer gestures are tested in LVGL."""
import argparse, hashlib, json, re, subprocess, sys, time
from pathlib import Path
from patches import Device, ROOT, manifest
from exercise_timing import output_counter_delta

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--port',required=True);p.add_argument('--output',type=Path,required=True)
args=p.parse_args();args.output=args.output.resolve()
report=dict(passed=False,hardware=True,physical_touch_tested=False,steps=[],saved_patch_writes=False)
def save(): args.output.write_text(json.dumps(report,indent=2)+'\n')
save()
with args.output.with_suffix('.log').open('wb') as log:
    d=Device(args.port,log);original_slot=1
    def wait(seconds):
        until=time.monotonic()+seconds
        while time.monotonic()<until:list(d.lines())
    def selected(slot):
        until=time.monotonic()+12
        while time.monotonic()<until:
            status=d.request('STATUS');assert not status['reset_required']
            if status['slot']==slot:return status
            wait(.1)
        raise AssertionError(f'Navigation did not reach slot {slot}: {status}')
    def digest():
        graph,source,info=d.download()
        return dict(graph=hashlib.sha256(graph).hexdigest(),source=hashlib.sha256(source).hexdigest(),metadata=info['manifest'][152:])
    def snapshot(code=True):
        d.request('PANIC');d.link.write(b's');lines=[];complete=False;until=time.monotonic()+40
        while time.monotonic()<until and not complete:
            for line in d.lines():
                if line.startswith(b'SCREEN_'):lines.append(line.rstrip(b'\r')+b'\n')
                if line.rstrip(b'\r')==b'SCREEN_END':complete=True;break
        assert complete,'Incomplete screenshot'
        stem=args.output.stem.removesuffix('-device')+('-code' if code else '-play')
        path=args.output.with_name(stem+'.log');path.write_bytes(b''.join(lines));png=path.with_suffix('.png')
        subprocess.run([sys.executable,str(ROOT/'host/decode_screen.py'),str(path),'--output',str(png)],check=True)
        raw=b''.join(bytes.fromhex(data.decode()) for data in re.findall(rb'SCREEN_DATA \d+ ([0-9a-f]+)',b''.join(lines)))
        offset=(100*368+360)*2
        if code:assert raw[offset:offset+2]==b'\xff\xff','CODE did not remain visible'
        report['code_after_navigation' if code else 'play_layout']=str(png.relative_to(ROOT));save()
    try:
        hello=d.hello();report['hello']=hello
        assert hello['build']==re.search(r'#define BUILD_ID "(.*?)"',(ROOT/'firmware/main/generated.h').read_text())[1]
        d.link.write(b'x');d.request('PANIC');original_slot=d.request('STATUS')['slot'];before=d.request('LIST');fx=d.request('FX')
        packages={}
        for entry in before:
            if entry['name']:
                d.request('LOAD',bytes([entry['slot']]));packages[str(entry['slot'])]=digest()
        report['initial_packages']=packages;save()
        d.request('LOAD',b'\1');d.link.write(b'c');wait(.25)
        baseline=args.output.with_suffix('.log').read_text(errors='replace')
        for direction,slot in [('>',2),('>',3),('>',4),('>',0),('<',4),('<',3),('<',2),('<',1),('<',0),('<',4)]:
            d.link.write(direction.encode());status=selected(slot)
            assert digest()==packages[str(slot)]
            report['steps'].append(dict(direction=direction,slot=slot,name=status['name']));save()
        snapshot()
        d.link.write(b'v');wait(.2);snapshot(False)
        # A queued UI action during a host upload must not leave navigation stuck.
        d.request('LOAD',b'\1');graph,source,_=d.download();_,meta=manifest(graph,source,'Navigation staging check')
        d.request('BEGIN',meta);d.link.write(b'>');wait(.4)
        assert d.request('STATUS')['slot']==1
        d.request('ABORT');d.link.write(b'>');selected(2)
        report['navigation_recovers_after_upload_rejection']=True
        assert d.request('LIST')==before,'Saved library changed'
        assert d.request('FX')==fx,'Delay controls changed'
        wait(1);text=args.output.with_suffix('.log').read_text(errors='replace')
        report['counter_baseline'],report['new_output_errors']=output_counter_delta(text,baseline)
        assert not any(report['new_output_errors'].values())
        report['passed']=True;save()
    finally:
        try:
            d.request('ABORT');d.request('PANIC')
            d.request('LOAD',bytes([original_slot if original_slot>=0 else 1]))
            d.link.write(b'c');wait(.3);report['final_status']=d.request('STATUS');save()
        finally:d.close()
print(json.dumps(report,indent=2))
