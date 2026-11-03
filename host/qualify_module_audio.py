#!/usr/bin/env python3
"""Install the standard autonomous post-flash listening patch on one module.

Uses Studio's selected connection. Replaces Main slot 1, selects master bypass,
and leaves the test playing at the requested software volume after observation.
Saves a private recovery snapshot first. Does not flash firmware or alter FX code.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import time

from patches import ROOT
from studio_client import StudioClient

FAULTS = ('faults', 'clips', 'nonfinite', 'overflow', 'write_fail', 'partial', 'dma_event_overflow')


def run(client, target, seconds, volume, report):
    state = client.http('refresh', {})
    hello = state.get('hello') or {}
    if hello.get('device_id') != target:
        raise RuntimeError('Connect the exact requested module in Studio first')
    source = (ROOT/'examples/module-audio-check.scd').read_text()
    artifact = client.http('compile', dict(source=source, target='sound', definition=False))
    if not artifact.get('admitted') or not artifact.get('continuous'):
        raise RuntimeError('Standard sound block was not admitted as autonomous audio')
    entry = next(row for row in state['slots'] if row['slot'] == 1)
    backup = dict(state=state, main=client.http('read-active', dict(target='sound', device_id=target)),
                  volume=client.rpc('meta', dict(target=target))['results'][0]['volume'])
    path = ROOT/'build/host/private'/('module-audio-'+time.strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(3)+'.json')
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(backup, stream, indent=2)
    report.update(device_id=target, build=hello['build'], source='examples/module-audio-check.scd',
                  volume=volume, listening='pending', graph={key:artifact[key] for key in
                  ('nodes','signals','inputs','audio_buffers','scalar_values','delay_samples','graph_sha256') if key in artifact})
    level = client.rpc('meta', dict(target=target, args=['volume', volume]))
    if not level.get('verified'):
        raise RuntimeError('Could not set the test output volume')
    bypass = client.rpc('bypass', dict(target=target, bypassed=True))
    if not bypass.get('verified'):
        raise RuntimeError('Could not select master bypass')
    result = client.http('upload', dict(device_id=target, target='sound', artifact=artifact['artifact'],
                          slot=1, expected=entry, replace=True, name='Module audio check'))
    if not result.get('verified'):
        raise RuntimeError('Saved sound-block verification failed')
    report['saved_and_verified'] = True
    print('PLAYING: standard eight-saw resonator/MiVerb block; separate master FX bypassed', flush=True)
    before = client.http('audio')
    samples = []
    start = time.monotonic()
    while time.monotonic() - start < seconds:
        sample = client.http('audio')
        samples.append(sample)
        # CPU timing peaks are recorded, not used as an automatic stop threshold.
        if any(sample.get(key,0) != before.get(key,0) for key in FAULTS):
            raise RuntimeError('Audio fault counters changed; inspect the report')
        time.sleep(.5)
    report.update(observation_seconds=round(time.monotonic()-start,2),
                  average_cpu_max_percent=max(s.get('average_x10',0) for s in samples)/10,
                  peak_cpu_max_percent=max(s.get('peak_x10',0) for s in samples)/10,
                  diagnostic_deltas={key:samples[-1].get(key,0)-before.get(key,0) for key in FAULTS})
    state = client.http('refresh', {})
    if state['hello']['device_id'] != target:
        raise RuntimeError('Selected module changed during observation')
    report['fx_bypassed'] = next(row['slot'] for row in state['masters'] if row['selected']) == 0
    info = client.rpc('info', dict(target=target, stage='main'))['results'][0]
    report['main_active'] = info['active']
    if not report['fx_bypassed'] or not report['main_active']:
        raise RuntimeError('Expected running Main with master bypass')
    report['passed'] = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device-id', required=True)
    parser.add_argument('--seconds', type=float, default=30)
    parser.add_argument('--volume', type=float, default=.20)
    parser.add_argument('--report', type=Path, default=ROOT/'build/host/module-audio-check.json')
    args = parser.parse_args()
    if not 1 <= args.seconds <= 600 or not 0 <= args.volume <= 1:
        parser.error('Use 1–600 seconds and volume 0–1')
    client = StudioClient()
    report = dict(passed=False, scope='Host telemetry; analogue listening requires user confirmation')
    try:
        run(client, args.device_id, args.seconds, args.volume, report)
    except BaseException as error:
        report['error'] = str(error)
        if report.get('saved_and_verified'):
            try:
                client.rpc('stop', dict(target=args.device_id, stage='main'))
            except Exception as stop_error:
                report['stop_error'] = str(stop_error)
        raise
    finally:
        client.close()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2), flush=True)
    print('Test remains playing; use Panic or ESP32.stop(target) to stop.', flush=True)


if __name__ == '__main__':
    main()
