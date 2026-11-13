#!/usr/bin/env python3
"""Prepare pinned mixer graphs or profile them muted on one backed-up XIAO.

No firmware flashing, saved patch writes or audible diagnostics. Each variant
requires a separately audited image and matching effective profiler mix tag.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import statistics
import time

from control_client import schema
from patches import Device, ROOT
from probe_usb_lifecycle import find_port
from profile_ugens import collect
from qualify_current_inventory import backup
from qualify_dsp_transient import restore, volume
from studio import Compiler
from studio_client import StudioClient
from test_signal_reuse import graph


def prepare(path):
    musical = json.loads((ROOT/'build/host/seeded-dsp-plan/plan.json').read_text())
    plan = {name: item for name, item in musical.items()}
    compiler = Compiler('/Applications/SuperCollider.app/Contents/MacOS/sclang')
    for kind in ('Sum3', 'Sum4', 'Pan2'):
        c = lambda i: (-1, i)
        nodes = [('SinOsc', 2, [c(1), c(0)], 1, 0)]
        for _ in range(24):
            index = len(nodes)
            refs = [(0, 0)]*(3 if kind=='Sum3' else 4) if kind!='Pan2' else [(0, 0), c(0), c(2)]
            nodes.append((kind, 2, refs, 2 if kind=='Pan2' else 1, 0))
            nodes.append(('Out', 2, [c(0), (index, 0), (index, 1) if kind=='Pan2' else (index, 0)], 0, 0))
        raw = graph('MixBank'+kind, nodes, constants=(0, 220, 1))
        plan['bank_'+kind] = dict(graph=base64.b64encode(raw).decode(), source='// Muted raw mixer diagnostic.\n', graph_sha256=hashlib.sha256(raw).hexdigest())
    for rate in ('ar', 'kr'):
        source = f'{{ var x=Pan2.{rate}(SinOsc.{rate}(220),SinOsc.kr(1),SinOsc.kr(0.7).range(0.1,1)); '+('K2A.ar(x)' if rate=='kr' else 'x')+' }'
        raw, original, info = compiler.compile(dict(source=source, target='sound'))
        assert info['admitted']
        plan['pan_dynamic_'+rate] = dict(graph=base64.b64encode(raw).decode(), source=original.decode(), graph_sha256=info['graph_sha256'])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, indent=2)+'\n')
    print('Prepared', len(plan), 'pinned musical/mixer graphs', flush=True)


def run(args):
    plan = json.loads(args.plan.read_text())
    report = dict(passed=False, hardware=True, muted=True, saved_patch_writes=False,
        firmware_writes=False, device_id=args.device_id, expected_mix=args.mix,
        plan_sha256=hashlib.sha256(args.plan.read_bytes()).hexdigest(), fixtures={})
    client = StudioClient(); device = None; stream = None; borrowed = mutated = False
    try:
        saved = backup(client, args.device_id, args.backup)
        client.http('disconnect', {}); borrowed = True
        log = ROOT/'build/host/private'/('mix-profile-'+str(time.time_ns())+'.log')
        stream = log.open('wb'); device = Device(find_port(args.device_id), stream)
        hello = device.hello(); assert hello == saved['state']['hello']
        report.update(build=hello['build'], initial_boot=schema(device,0)['boot'])
        assert report['initial_boot'] == saved['main_info']['boot']
        mutated = True; volume(device,0); device.request('FXLOAD',b'\0')
        for name,item in plan.items():
            raw = base64.b64decode(item['graph'], validate=True)
            assert hashlib.sha256(raw).hexdigest() == item['graph_sha256']
            current = device.upload(raw,item['source'].encode(),name,mapping=0,definition=True)
            assert current['graph_sha256'] == item['graph_sha256']
            trials = [collect(device,fixed=True) for _ in range(3)]
            for trial in trials:
                assert trial['setup']['qualified']=='1'
                assert trial['setup'].get('mix','0')==str(args.mix)
                for key in ('warm_sha256','audio_sha256','rng'):
                    assert trial['setup'][key] == trials[0]['setup'][key]
            report['fixtures'][name] = dict(graph_sha256=item['graph_sha256'],
                median_us=statistics.median(t['normal_average_us_at_240mhz'] for t in trials), trials=trials)
            args.output.write_text(json.dumps(report,indent=2)+'\n')
            print(name, round(report['fixtures'][name]['median_us'],3), 'us/block', flush=True)
        report['passed'] = True
    except BaseException as error:
        report['error'] = str(error) or type(error).__name__; raise
    finally:
        try:
            if device and mutated:
                device.request('PANIC')
                report['restoration'] = restore(device,saved,round(saved['volume']*100),save=False)
                assert schema(device,0)['boot'] == report['initial_boot']
                for stage,key in ((0,'main_info'),(1,'fx_info')):
                    assert {c['name']:c['values'] for c in schema(device,stage)['controls']} == {c['name']:c['values'] for c in saved[key]['controls']}
        except BaseException as error:
            report['passed']=False; report['restoration_error']=str(error); raise
        finally:
            if device: device.close()
            if stream: stream.close()
            try:
                if borrowed:
                    state=client.http('connect',dict(port=find_port(args.device_id)))
                    assert state['hello']['device_id']==args.device_id and state['volume_percent']==round(saved['volume']*100)
                    report['studio_connected']=True
            except BaseException as error:
                report['passed']=False; report['studio_error']=str(error)
            client.close(); args.output.write_text(json.dumps(report,indent=2)+'\n')


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepare',type=Path); p.add_argument('--plan',type=Path)
    p.add_argument('--device-id'); p.add_argument('--backup',type=Path)
    p.add_argument('--mix',type=int,choices=(0,1)); p.add_argument('--output',type=Path)
    a=p.parse_args()
    if a.prepare:
        if any(v is not None for v in (a.plan,a.device_id,a.backup,a.mix,a.output)):
            p.error('Preparation is computer-only; run separately')
        prepare(a.prepare)
    else:
        if any(v is None for v in (a.plan,a.device_id,a.backup,a.mix,a.output)):
            p.error('Run requires plan, device-id, backup, mix and output')
        a.output.parent.mkdir(parents=True,exist_ok=True); run(a)
