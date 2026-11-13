#!/usr/bin/env python3
"""Current-build long-trace coverage and muted hotspot profiling on one XIAO.

Prepare qualified native references first, then borrow Studio's USB connection.
Temporary RAM activation only; no firmware or saved-patch writes. Private backup,
same-boot checks and verified package/control restoration bracket every session.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from control_client import schema
from engine_profile import generate
from long_trace import BLOCKS, WINDOWS, collect, compare
from patches import Device, ROOT
from probe_usb_lifecycle import find_port
from profile_ugens import collect as profile
from qualify_dsp_transient import restore, volume
from studio_client import StudioClient

BUILD = ROOT/'build/host/current-inventory'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(output):
    """Never reuse old native samples: regenerate with the enabled kernel set."""
    BUILD.mkdir(parents=True, exist_ok=True)
    src = generate(BUILD/'src', 'fm1', qualified_kernels=True)
    component = ROOT/'firmware/components/instrument'
    exe = BUILD/'render-trace'
    subprocess.run(['cc', '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror',
        '-fno-fast-math', '-ffp-contract=off', '-fsanitize=undefined,bounds,float-cast-overflow',
        '-fno-sanitize-recover=all', '-I'+str(src), '-I'+str(component/'include'),
        str(src/'fm_load.c'), str(src/'fm_render.c'), str(component/'trace_probe.c'),
        str(ROOT/'tests/render_trace.c'), '-lm', '-o', str(exe)], check=True)
    jobs, seen = [], set()
    for name in ('long-trace-plan.json', 'long-trace-edges-plan.json'):
        old = json.loads((ROOT/'evidence'/name).read_text())
        assert old['passed'] and old['blocks'] == BLOCKS and old['windows'] == WINDOWS
        for item in old['jobs']:
            path = ROOT/item['graph']
            assert sha(path) == item['graph_sha256'], 'Fixture changed: '+item['id']
            if item['graph_sha256'] in seen:
                continue
            seen.add(item['graph_sha256'])
            job = dict(item)
            sample = BUILD/(job['id']+'.f32')
            run = subprocess.run([str(exe), str(path), str(sample)], capture_output=True,
                                 text=True, timeout=90, check=True)
            summary = json.loads(run.stdout)
            assert summary['passed'] and not summary['rejected'], job['id']
            job.update(samples=str(sample.relative_to(ROOT)), samples_sha256=sha(sample), host=summary)
            jobs.append(job)
            if len(jobs) % 20 == 0:
                print('Qualified native preflight:', len(jobs), flush=True)
    result = dict(passed=True, qualified=True, blocks=BLOCKS, windows=WINDOWS,
        jobs=jobs, expected_type_rates=sorted({tuple(pair) for job in jobs for pair in job['type_rates']}),
        reference_sources={str(p.relative_to(ROOT)): sha(p) for p in (
            ROOT/'host/engine_profile.py', ROOT/'host/qualified_kernels.py',
            component/'trace_probe.c', ROOT/'tests/render_trace.c')},
        generated_render_sha256=sha(src/'fm_render.c'))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(f'Prepared {len(jobs)} graphs / {len(result["expected_type_rates"])} type-rate pairs', flush=True)


def backup(client, target, path):
    state = client.http('refresh', {})
    assert state['hello']['device_id'] == target and state['hello']['headless']
    assert state['status']['slot'] == 1 and state['volume_percent'] <= 5
    assert next(e['slot'] for e in state['masters'] if e['selected']) == 0, 'Requires FX bypass'
    value = dict(state=state, main=client.http('read-active', dict(target='sound', device_id=target)),
        main_info=client.rpc('info', dict(target=target, stage='main'))['results'][0],
        fx_info=client.rpc('info', dict(target=target, stage='fx'))['results'][0],
        volume=state['volume_percent']/100)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
        json.dump(value, stream, indent=2)
    return value


def audit_job(job):
    assert sha(ROOT/job['graph']) == job['graph_sha256'], 'Graph changed'
    assert sha(ROOT/job['samples']) == job['samples_sha256'], 'Native reference changed'


def coverage(rows, expected):
    # Completion and numerical agreement are deliberately distinct.
    covered = sorted({tuple(pair) for row in rows if row['comparison']['passed'] for pair in row['type_rates']})
    missing = sorted(set(map(tuple, expected))-set(covered))
    return dict(type_rates_passed=covered, missing_type_rates=missing,
                failed_graphs=[r['id'] for r in rows if not r['comparison']['passed']])


def run(args):
    plan = json.loads(args.plan.read_text())
    assert plan['passed'] and plan['qualified']
    if not getattr(args, 'profiles_only', None):
        for key, value in plan['reference_sources'].items():
            assert sha(ROOT/key) == value, 'Reference source changed: '+key
    for job in plan['jobs']:
        audit_job(job)
    normal = StudioClient()
    device = None
    stream = None
    borrowed = mutated = False
    report = dict(passed=False, complete=False, hardware=True, device_id=args.device_id,
        saved_patch_writes=False, firmware_writes=False, muted=True, captures=[], profiles=[],
        plan_sha256=sha(args.plan), blocks_per_graph=BLOCKS,
        scope='Sparse float windows plus full-duration fault/arena/RMS checks; statistical grades remain distinct. Parked diagnostics are not live deadline certification.')
    previous = None
    if getattr(args, 'profiles_only', None):
        previous = json.loads(args.profiles_only.read_text())
        assert previous['complete'] and previous['device_id'] == args.device_id
        assert previous['plan_sha256'] == report['plan_sha256']
        report['captures'] = previous['captures']
        report['numerical_source'] = dict(path=str(args.profiles_only.resolve().relative_to(ROOT)),
                                         sha256=sha(args.profiles_only))
    log = ROOT/'build/host/private'/('current-inventory-'+str(time.time_ns())+'.log')
    log.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        saved = backup(normal, args.device_id, args.backup)
        normal.http('disconnect', {})
        borrowed = True
        stream = log.open('wb')
        device = Device(find_port(args.device_id), stream)
        hello = device.hello()
        assert hello == saved['state']['hello'], 'Device/build changed'
        expected = previous['build'] if previous else re.search(r'#define BUILD_ID "(.*?)"', (ROOT/'firmware/main/generated.h').read_text())[1]
        assert hello['build'] == expected, 'Firmware does not match this source build'
        if previous:
            assert previous['build'] == hello['build'], 'Cannot reuse captures from another image'
        initial = schema(device, 0)
        assert initial['boot'] == saved['main_info']['boot'], 'USB open rebooted board'
        report.update(build=hello['build'], initial_boot=initial['boot'])
        mutated = True
        volume(device, 0)
        device.request('FXLOAD', b'\0')
        initial_profile = profile(device, fixed=True)
        assert initial_profile['setup']['qualified'] == '1', 'Qualified kernels are not enabled'
        report['initial_profile'] = initial_profile
        jobs = [] if previous else plan['jobs'][:args.limit] if args.limit else plan['jobs']
        for index, job in enumerate(jobs):
            raw = (ROOT/job['graph']).read_bytes()
            status = device.upload(raw, b'// Temporary muted current-build diagnostic.\n',
                                   'Check '+job['id'][:24], mapping=0, definition=True)
            assert status['graph_sha256'] == job['graph_sha256']
            header, data = collect(device)
            result = compare(header, data, job)
            row = dict(id=job['id'], graph_sha256=job['graph_sha256'],
                type_rates=job['type_rates'], device=header, comparison=result)
            if 'selectors' in job:
                row.update(operator_selectors=job['selectors'], operator_rate=job['rate'])
            report['captures'].append(row)
            args.output.write_text(json.dumps(report, indent=2)+'\n')
            print(f'{index+1}/{len(jobs)} {job["id"]}: {result["comparison"]}; max {header["max_us"]} us', flush=True)
        report.update(coverage(report['captures'], plan['expected_type_rates']))
        report['complete'] = bool(previous) or len(jobs) == len(plan['jobs'])
        # Profile representative real graphs and the slowest diagnostic graphs
        # only after numerical coverage. Repeat each fixed seed three times.
        if args.profile or previous:
            ranked = sorted(report['captures'], key=lambda r: int(r['device']['max_us']), reverse=True)
            chosen = []
            report['profiles_unavailable'] = []
            for row in ranked:
                if row['id'] == 'm5_addy':
                    report['profiles_unavailable'].append(dict(id=row['id'],
                        reason='Finite Line doneAction=2 stops this graph before the fixed profiler window finishes; long-trace numerical check passes.'))
                    continue
                # Limit operator mega-banks to one: they are not typical sounds.
                if row['id'].startswith('operators-') and any(j['id'].startswith('operators-') for j in chosen):
                    continue
                chosen.append(next(j for j in plan['jobs'] if j['id'] == row['id']))
                if len(chosen) == 8:
                    break
            for job in chosen:
                device.upload((ROOT/job['graph']).read_bytes(), b'// Muted fixed-seed profile.\n', job['id'][:31], mapping=0, definition=True)
                trials = [profile(device, fixed=True) for _ in range(3)]
                for t in trials:
                    assert t['setup']['qualified'] == '1'
                    for key in ('warm_sha256', 'audio_sha256', 'rng'):
                        assert t['setup'][key] == trials[0]['setup'][key]
                report['profiles'].append(dict(id=job['id'], trials=trials))
                args.output.write_text(json.dumps(report, indent=2)+'\n')
                print('PROFILE', job['id'], trials[0]['normal_average_us_at_240mhz'], 'us/block', flush=True)
        report['passed'] = report['complete'] and not report['failed_graphs'] and not report['missing_type_rates']
    except BaseException as error:
        report['error'] = str(error) or type(error).__name__
        raise
    finally:
        try:
            if device and mutated:
                device.request('PANIC')
                report['restoration'] = restore(device, saved, round(saved['volume']*100), save=False)
                assert schema(device, 0)['boot'] == report['initial_boot'], 'Unexpected reboot'
                for stage, key in ((0, 'main_info'), (1, 'fx_info')):
                    current = schema(device, stage)
                    assert {c['name']: c['values'] for c in current['controls']} == {c['name']: c['values'] for c in saved[key]['controls']}
                report['same_boot'] = True
        except BaseException as error:
            report['passed'] = False
            report['restoration_error'] = str(error) or type(error).__name__
            raise
        finally:
            if device:
                device.close()
            if stream:
                stream.close()
            try:
                if borrowed:
                    state = normal.http('connect', dict(port=find_port(args.device_id)))
                    assert state['hello']['device_id'] == args.device_id
                    assert state['volume_percent'] == round(saved['volume']*100)
                    report['studio_connected'] = True
            except BaseException as error:
                report['passed'] = False
                report['studio_error'] = str(error)
            normal.close()
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2)+'\n')
    print('Finished; original patch/controls restored; Studio reconnected', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', type=Path)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--device-id')
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--limit', type=int)
    parser.add_argument('--profile', action='store_true')
    parser.add_argument('--profiles-only', type=Path, help='Reuse complete same-build captures; rerun only sustained hotspot profiles')
    args = parser.parse_args()
    if args.prepare:
        if any((args.plan, args.device_id, args.backup, args.output, args.limit, args.profile, args.profiles_only)):
            parser.error('Preparation is computer-only; run separately')
        prepare(args.prepare)
    else:
        if not all((args.plan, args.device_id, args.backup, args.output)):
            parser.error('Run requires --plan --device-id --backup --output')
        if args.limit is not None and args.limit < 1:
            parser.error('--limit must be positive')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        run(args)


if __name__ == '__main__':
    main()
