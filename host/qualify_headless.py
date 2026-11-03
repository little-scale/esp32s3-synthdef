#!/usr/bin/env python3
"""Exercise one USB XIAO through Studio, then restore its saved Main and FX.

Requires populated Main/FX slots. Saves a private recovery backup before any
upload. Recreates instances on restoration; oscillator phases and effect tails
cannot be restored. Storage generations advance normally. No Wi-Fi or DAC is
required: assertions inspect the actual post-volume I2S samples.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import struct
import time

from patches import ROOT
from studio_client import StudioClient

COMB = r'SynthDef(\qaEcho, { Out.ar(0, CombN.ar(Impulse.ar(1), 0.5, [0.1, 0.15], 1) * 0.03) })'
LONG = r'''SynthDef(\qaLong, {
    var burst = SinOsc.ar(440) * EnvGen.ar(Env.perc(0.001, 0.05));
    Out.ar(0, (DelayN.ar(burst, 5, 4) * 0.1) ! 2);
})'''
BURST = r'SynthDef(\qaBurst, { Out.ar(0, (SinOsc.ar(440) * EnvGen.ar(Env.perc(0.001, 0.03)) * 0.2) ! 2) })'
REVERB = r'''SynthDef(\qaVerb, { arg wet = 1, time = 0.85, damp = 0.5;
    Out.ar(0, MiVerb.ar(In.ar(0, 2), time, wet, damp, 0.05));
})'''
CLOUD = r'''SynthDef(\qaCloud, { arg freq = 330, density = 4, amp = 0.1;
    var copies = 5;
    var frequencies = Array.fill(copies, { |i| freq * (i + 1) * Rand(0.99, 1.01) });
    var decay = SinOsc.kr(0.1, 270.degrad).range(0.1, 2);
    var excitation = Decay2.kr(Dust.kr(density ! copies), 0.01, decay);
    var sound = Splay.ar(excitation * SinOsc.ar(frequencies));
    Out.ar(0, CombC.ar(sound, 0.05, SinOsc.kr(5).range(0.049, 0.05), 5) * amp);
})'''
TOO_LARGE = r'SynthDef(\qaTooLarge, { Out.ar(0, DelayN.ar(In.ar(0, 2), 5, 4)) })'
STALE_A = r'SynthDef(\qaOld, { arg freq = 220, amp = 0.03; Out.ar(0, (SinOsc.ar(freq) * amp) ! 2) })'
STALE_B = r'SynthDef(\qaNew, { arg amp = 0.03, freq = 330; Out.ar(0, (SinOsc.ar(freq) * amp) ! 2) })'


def require(condition, message):
    if not condition: raise AssertionError(message)


def graph_hash(package):
    return hashlib.sha256(base64.b64decode(package['graph'], validate=True)).hexdigest()


def pcm_channels(capture):
    require(capture['format'] == 's16le' and capture['channels'] == 2 and capture['rate'] == 44100,
            'Unexpected PCM format')
    raw = base64.b64decode(capture['data'], validate=True)
    require(len(raw) == capture['frames'] * 4, 'Truncated PCM')
    values = struct.unpack('<' + str(len(raw) // 2) + 'h', raw)
    return values[::2], values[1::2]


def levels(channels):
    return {'peak': max(abs(v) for channel in channels for v in channel),
            'rms': [math.sqrt(sum(v*v for v in channel) / len(channel)) for channel in channels]}


def echo_metrics(channel, period, feedback):
    peak = max(abs(v) for v in channel)
    # Group interpolation lobes together; a low threshold also sees late echoes.
    positions = [i for i, v in enumerate(channel) if abs(v) > max(3, peak * 0.01)]
    groups = []
    for i in positions:
        if not groups or i - groups[-1][-1] > 8: groups.append([])
        groups[-1].append(i)
    peaks = [(max(group, key=lambda i: abs(channel[i])), max(abs(channel[i]) for i in group)) for group in groups]
    pairs = [(b[0]-a[0], b[1]/a[1]) for a,b in zip(peaks, peaks[1:])
             if abs((b[0]-a[0])-period) <= 1 and b[1] < a[1]]
    require(len(pairs) >= 2, 'Too few correctly spaced echoes')
    ratio = statistics.median(p[1] for p in pairs)
    require(abs(ratio-feedback) < 0.025, 'Comb feedback decay differs from expected value')
    return dict(echoes=len(peaks), period_frames=statistics.median(p[0] for p in pairs), feedback=ratio)


class Qualification:
    def __init__(self, client, device_id, backup_path):
        self.client, self.target, self.backup_path = client, device_id, backup_path
        self.backup = None
        self.report = {}
        self.owned = {'sound': set(), 'master': set()}
        self.dirty = set()

    def rpc(self, action, **kwargs):
        result = self.client.rpc(action, dict(target=self.target, **kwargs))
        if 'verified' in result: require(result['verified'], str(result))
        if 'queued' in result: require(result['queued'], str(result))
        return result

    def info(self, stage='main'):
        return self.rpc('info', stage=stage)['results'][0]

    def package(self, target, stored=False):
        return self.client.http('read-active', dict(target=target, device_id=self.target,
                           **({'slot': 1} if stored and target == 'master' else {})))

    def save(self, headless=True):
        state = self.client.http('refresh', {})
        hello = state.get('hello') or {}
        require(hello.get('device_id') == self.target and (not headless or hello.get('headless') is True),
                'Connect the exact USB module in Studio first (headless target required by default)')
        require(state.get('connection') == 'usb' or state.get('port', '').startswith('/dev/cu.'),
                'Qualification requires the shared USB connection')
        for key in ('slots', 'masters'):
            require(any(e['slot'] == 1 and e['name'] for e in state[key]), 'Populate Main and FX slot 1 before qualification')
        require(state['status']['slot'] == 1, 'Select Main slot 1 before qualification')
        self.backup = dict(state=state, main_info=self.info(), fx_info=self.info('fx'),
            volume=self.rpc('meta')['results'][0]['volume'], main=self.package('sound'), fx=self.package('master', True))
        self.owned['sound'].add(graph_hash(self.backup['main']))
        self.owned['master'].add(graph_hash(self.backup['fx']))
        self.backup_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.backup_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as f: json.dump(self.backup, f, indent=2)
        return hello

    def compile(self, source, target='sound', graph=None, definition=True):
        return self.client.http('compile', dict(source=source, target=target, definition=definition,
                                **({'graph': graph} if graph is not None else {})))

    def install(self, artifact, target='sound', package=None):
        require(artifact['admitted'], artifact.get('admission_error'))
        self.owned[target].add(artifact['graph_sha256'])
        state = self.client.http('refresh', {})
        require(state['hello']['device_id'] == self.target, 'USB device changed')
        entry = next(e for e in state['masters' if target == 'master' else 'slots'] if e['slot'] == 1)
        self.dirty.add(target)  # Include uploads whose final acknowledgement is lost.
        payload = dict(artifact=artifact['artifact'], slot=1, expected=entry, replace=True,
                       name=package['name'] if package else artifact['name'], device_id=self.target)
        if package: payload.update(labels=package['labels'], mapping=package['mapping'])
        result = self.client.http('upload', payload)
        require(result.get('verified') is True, 'Upload verification failed')

    def load(self, source, target='sound'):
        artifact = self.compile(source, target)
        self.install(artifact, target)
        # HTTP uploads and OSC control share the device, but the control client
        # must prepare its metadata after replacing a definition, just as SC's
        # player does before starting a new pattern.
        self.rpc('prepare', stage='fx' if target == 'master' else 'main')
        return {k: artifact[k] for k in ('graph_sha256', 'nodes', 'delay_samples')}

    def capture(self, seconds=1):
        return pcm_channels(self.client.http('capture', dict(seconds=seconds, device_id=self.target)))

    def restore(self):
        if not self.backup: return {}
        result = {}
        # Refuse to overwrite an unrelated patch uploaded by another user/session.
        state = self.client.http('refresh', {})
        require(state['hello']['device_id'] == self.target, 'Reconnect the original module to restore its backup')
        for target, key in (('sound', 'main'), ('master', 'fx')):
            if target not in self.dirty: continue
            current = self.package(target, True)
            require(graph_hash(current) in self.owned[target], 'An unrelated patch appeared; keep the private backup and restore manually')
            package = self.backup[key]
            artifact = self.compile(package['source'], target, package['graph'], package['definition'])
            self.install(artifact, target, package)
            actual = self.package(target, True)
            require(actual == package, 'Restored package differs from its backup')
            result[key + '_package_verified'] = True
        self.rpc('meta', args=['volume', self.backup['volume']])
        selected = next(e['slot'] for e in self.backup['state']['masters'] if e['selected'])
        self.rpc('bypass', bypassed=selected == 0)
        for stage, key in (('fx', 'fx_info'), ('main', 'main_info')):
            if stage == 'fx' and selected == 0: continue
            old = self.backup[key]
            args = []
            for control in old['controls']:
                if not control['name'].startswith('__esp32_'):
                    args += [control['name'], control['values']]
            self.rpc('play' if old['active'] else 'stop', stage=stage, args=args)
            require(self.info(stage)['active'] == old['active'], 'Instance activity was not restored')
        result.update(fx_selected=selected, volume=self.backup['volume'], instances_restored=True)
        return result


def run(q, seconds):
    hello = q.save()
    report = dict(device_id=q.target, build=hello['build'], soak_seconds=seconds, tests={})
    q.report = report
    tests = report['tests']
    baseline = q.client.http('audio')
    print('Backup saved; testing stereo CombN echo spacing and decay', flush=True)
    q.rpc('meta', args=['volume', 1])
    q.rpc('bypass', bypassed=True)
    tests['comb'] = q.load(COMB)
    q.rpc('play', stage='main')
    channels = q.capture()
    tests['comb']['channels'] = [echo_metrics(channel, period, 10**(-3*delay))
        for channel,period,delay in zip(channels, (4410,6615), (.1,.15))]

    print('Testing a four-second delay using the complete 1 MiB Main arena', flush=True)
    tests['long_delay'] = q.load(LONG)
    require(tests['long_delay']['delay_samples'] == 262144, 'Long delay did not reserve the expected arena')
    q.rpc('play', stage='main'); time.sleep(3.35)
    channels = q.capture()
    tests['long_delay'].update(levels(channels))
    require(channels[0] == channels[1] and tests['long_delay']['peak'] > 100, 'Long delayed burst missing or stereo copy differs')
    require(sum(abs(v)>20 for v in channels[0]) < 4410, 'Delayed burst did not end')
    large = q.compile(TOO_LARGE, 'master')
    require(not large['admitted'], 'Oversized stereo delay was admitted')
    tests['oversized_delay_rejected'] = large['admission_error']

    print('Testing MiVerb wet tails and panic silence', flush=True)
    tests['reverb'] = q.load(REVERB, 'master')
    q.load(BURST)
    q.rpc('play', stage='fx'); q.rpc('play', stage='main'); time.sleep(.2)
    tail = q.capture()
    tests['reverb']['tail'] = levels(tail)
    require(min(tests['reverb']['tail']['rms']) > 1, 'Wet reverb tail is missing')
    q.rpc('stop', stage='main')
    tests['reverb']['tail_after_main_stop'] = levels(q.capture(.5))
    require(min(tests['reverb']['tail_after_main_stop']['rms']) > .1, 'Stopping Main incorrectly removed the FX tail')
    q.rpc('panic'); time.sleep(.1)
    require(levels(q.capture(.2))['peak'] == 0, 'Panic did not silence Main and FX')
    tests['reverb']['panic_silence'] = True

    print('Starting combined Comb Cloud KR + MiVerb soak at 8 control events/second', flush=True)
    tests['soak'] = q.load(CLOUD)
    q.rpc('play', stage='fx', args=['wet', .35]); q.rpc('play', stage='main')
    control_start = q.info()
    samples, captures, sent = [], [], 0
    start = time.monotonic(); next_sample = start; next_capture = start + 5; future = None
    with ThreadPoolExecutor(max_workers=1) as pool:
        while time.monotonic() - start < seconds:
            q.rpc('control', stage='main', kind='set', stream=701,
                  args=['freq', (110,220,330,440,660)[sent % 5], 'amp', .1, 'density', 4])
            sent += 1
            now = time.monotonic()
            if future is not None and future.done():
                measured = levels(future.result()); require(measured['peak'] < 32767 and min(measured['rms']) > .1, 'Soak PCM is silent or clipped')
                captures.append(measured); future = None
            if now >= next_capture and future is None:
                future = pool.submit(q.capture, .5); next_capture = now + 45
            if now >= next_sample:
                samples.append(q.client.http('audio')); next_sample = now + 2
            if sent % 240 == 0: print(f'Soak: {sent} updates, {now-start:.0f}s, {len(captures)} PCM captures', flush=True)
            time.sleep(max(0, start + sent/8 - time.monotonic()))
        if future is not None: captures.append(levels(future.result()))
    time.sleep(.05)
    control_end = q.info()
    control_deltas = {key:control_end[key]-control_start[key] for key in ('applied','rejected','late')}
    require(control_deltas == dict(applied=sent,rejected=0,late=0), 'Queued controls were lost, rejected or late')
    require(sent >= seconds*7.5, 'Control throughput fell below the intended 8 Hz workload')
    tests['soak'].update(events=sent, control_deltas=control_deltas, elapsed_seconds=time.monotonic()-start, captures=captures,
        average_cpu_max_percent=max(s.get('average_x10',0) for s in samples)/10,
        peak_cpu_max_percent=max(s.get('peak_x10',0) for s in samples)/10,
        memory={k:dict(min=min(s[k] for s in samples if k in s), max=max(s[k] for s in samples if k in s))
                for k in ('internal_free','internal_largest','psram_free','stack_free_bytes','controls_stack_free_bytes') if any(k in s for s in samples)})
    for key,tolerance in (('internal_free',8192),('psram_free',65536)):
        readings = [s[key] for s in samples if key in s]
        if len(readings) >= 6:
            require(statistics.median(readings[-3:]) >= statistics.median(readings[:3])-tolerance,
                    'Memory declined during the soak: '+key)

    print('Checking stale stream rejection after a patch revision change', flush=True)
    q.rpc('bypass', bypassed=True)
    q.load(STALE_A)
    q.rpc('control', stage='main', kind='set', stream=702, args=['freq', 220])
    q.load(STALE_B)
    before = q.info()
    try:
        q.rpc('control', stage='main', kind='set', stream=702, args=['freq', 660])
    except (RuntimeError, AssertionError) as error:
        require(any(word in str(error).lower() for word in ('stale','patch changed')), 'Unexpected stale-stream error')
    else: raise AssertionError('Old control stream was accepted by the replacement patch')
    after = q.info()
    require(before['controls'] == after['controls'], 'Stale stream modified replacement controls')
    q.rpc('control', stage='main', kind='set', stream=703, args=['freq', 550])
    require(next(c for c in q.info()['controls'] if c['name']=='freq')['values'] == [550], 'New control stream failed to recover')
    tests['stale_stream'] = dict(rejected=True, replacement_unchanged=True, new_stream_recovered=True)
    final = q.client.http('audio')
    report['diagnostic_deltas'] = {k:final.get(k,0)-baseline.get(k,0)
        for k in ('write_fail','partial','dma_event_overflow','faults','clips','nonfinite','overflow')}
    require(not any(report['diagnostic_deltas'].values()), 'Audio diagnostics changed during qualification')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device-id', required=True)
    parser.add_argument('--seconds', type=int, default=180, choices=range(30,1801), metavar='30..1800')
    parser.add_argument('--studio-port', type=int, default=8765)
    parser.add_argument('--report', type=Path, default=ROOT/'build/host/headless-qualification.json')
    args = parser.parse_args()
    stamp = time.strftime('%Y%m%d-%H%M%S') + '-' + os.urandom(3).hex()
    q = Qualification(StudioClient(args.studio_port), args.device_id,
        ROOT/'build/host/private'/('qualification-'+stamp+'.json'))
    print('Recovery backup: '+str(q.backup_path), flush=True)
    report = {}; error = None
    try:
        report = run(q, args.seconds)
    except BaseException as exc:
        error = exc; report = q.report; report['error'] = str(exc)
    finally:
        print('Restoring saved packages and instance settings', flush=True)
        try: report['restored'] = q.restore()
        except Exception as exc:
            report['restore_error'] = str(exc)
            if error is None: error = exc
        q.client.close()
        report['passed'] = error is None
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2)+'\n')
    if error: raise error
    print('PASS: headless qualification; original Main/FX restored', flush=True)


if __name__ == '__main__': main()
