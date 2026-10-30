#!/usr/bin/env python3
"""Integration checks against a connected V2; writes only the chosen test slot.

Run --phase setup once, then --phase restore after a real board restart. The
restore phase leaves a deliberately incomplete RAM upload for another restart.
It never corrupts the board's flash filesystem or claims physical power-cut QA.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import time
import re
import subprocess
import sys
from patches import ROOT, Device, frame, decode, manifest

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port', required=True)
parser.add_argument('--phase', choices=['setup', 'restore', 'finish'], required=True)
parser.add_argument('--slot', type=int, choices=range(1, 9), default=1)
parser.add_argument('--report-name', help='Distinct evidence name for an additional restart observation')
parser.add_argument('--reset-after-stage', action='store_true', help='Restart immediately while the incomplete transfer is pending (restore phase only)')
args = parser.parse_args()
if args.reset_after_stage and args.phase != 'restore': parser.error('--reset-after-stage requires --phase restore')
label = args.report_name or args.phase
if not re.fullmatch('[a-z0-9-]+', label): parser.error('Invalid report name')
log_path = ROOT/f'evidence/patch-device-{label}.log'
report_path = ROOT/f'evidence/patch-device-{label}.json'
report_path.write_text(json.dumps({'test': 'target patch workflow', 'phase': args.phase,
                                  'passed': False, 'status': 'incomplete; inspect the matching log'}, indent=2)+'\n')
graph = (ROOT/'examples/mac-sine.scsyndef').read_bytes()
source = (ROOT/'examples/mac-sine.scd').read_bytes()
checks = []

with log_path.open('wb') as log:
    d = Device(args.port, log)
    try:
        hello = d.hello()
        assert hello['storage']
        assert hello['build'] == re.search(r'#define BUILD_ID "(.*?)"', (ROOT/'firmware/main/generated.h').read_text())[1]
        def drain(seconds):
            until = time.monotonic() + seconds
            while time.monotonic() < until:
                list(d.lines())
        def reject(operation, payload):
            try:
                d.request(operation, payload)
            except RuntimeError as error:
                checks.append(f'{operation} rejected: {error}')
            else:
                raise AssertionError(f'{operation} unexpectedly accepted')
        def unchanged(expected):
            assert d.request('STATUS')['graph_sha256'] == expected
        if args.phase == 'setup':
            d.request('LOAD', b'\0')
            before = d.request('STATUS')['graph_sha256']
            # Invalid CRC produces an uncorrelated error and no mutation.
            wire = bytearray(frame(0x12345678, 'HELLO'))
            wire[-2] = ord('0') if wire[-2] != ord('0') else ord('1')
            d.link.write(wire)
            bad_crc = False
            until = time.monotonic() + 3
            while time.monotonic() < until and not bad_crc:
                for line in d.lines():
                    if line.startswith(b'@SD1 '):
                        rid, op, data = decode(line)
                        bad_crc = rid == 0 and op == 'ERR' and b'CRC' in data
            assert bad_crc
            checks.append('Corrupt frame rejected')
            tx, meta = manifest(graph, source)
            d.request('BEGIN', meta)
            chunk = struct.pack('<II', tx, 0) + graph[:256]
            assert d.request('DATA', chunk)['received'] == 256
            assert d.request('DATA', chunk)['received'] == 256
            checks.append('Identical DATA retry idempotent')
            reject('DATA', struct.pack('<II', tx, 0) + b'wrong')
            reject('DATA', struct.pack('<II', tx, 512) + b'gap')
            reject('COMMIT', struct.pack('<I', tx))
            unchanged(before)
            # A package with internally matching hashes but invalid graph.
            invalid = b'NOT A SYNTHDEF'
            badtx, badmeta = manifest(invalid)
            d.request('BEGIN', badmeta)
            d.request('DATA', struct.pack('<II', badtx, 0) + invalid)
            reject('COMMIT', struct.pack('<I', badtx))
            unchanged(before)
            # A complete blob with a manifest SHA that describes other bytes.
            tx, meta = manifest(graph)
            corrupt = bytearray(graph); corrupt[-1] ^= 1
            d.request('BEGIN', meta)
            for at in range(0, len(corrupt), 256):
                d.request('DATA', struct.pack('<II', tx, at) + corrupt[at:at+256])
            reject('COMMIT', struct.pack('<I', tx))
            unchanged(before)
            checks.append('Failed uploads retained active graph')
            unsupported = graph.replace(b'\x06SinOsc', b'\x05LFTri')
            assert unsupported != graph
            try:
                d.upload(unsupported)
            except RuntimeError as error:
                assert 'LFTri' in str(error), error
                checks.append('Compiled but unqualified LFTri rejected by admission')
            else:
                raise AssertionError('Unsupported upload admitted')
            unchanged(before)
            d.request('SAVE', bytes([args.slot]))
            d.link.write(b'n'); drain(1.2)
            ready = d.upload(graph, source, name='Mac Sine', activate=False)
            assert ready['state'] == 2
            unchanged(before)
            tx = ready['transfer']
            reject('ACTIVATE', struct.pack('<I', tx ^ 1))
            d.request('ACTIVATE', struct.pack('<I', tx))
            d.link.write(b'n'); drain(1.2); d.link.write(b'o'); drain(.6)
            unchanged(hashlib.sha256(graph).hexdigest())
            d.request('SAVE', bytes([args.slot]))
            generations = d.request('LIST')[args.slot]['generations']
            d.request('SAVE', bytes([args.slot]))
            assert d.request('LIST')[args.slot]['generations'] == generations
            checks.append('Repeated SAVE preserved generation counters')
            d.request('LOAD', b'\0')
            assert d.request('STATUS')['name'] == 'Touch Sine'
            d.request('LOAD', bytes([args.slot]))
            actual_graph, actual_source, info = d.download()
            assert actual_graph == graph and actual_source == source
            checks.append('Factory recovery and saved reload; graph/source read back byte-identical')
        else:
            status = d.request('STATUS')
            assert status['slot'] == args.slot and status['name'] == 'Mac Sine'
            actual_graph, actual_source, info = d.download()
            assert actual_graph == graph and actual_source == source
            meta = bytes.fromhex(info['manifest'])
            assert meta[76:108].split(b'\0')[0] == b'Mac Sine'
            assert meta[108:156] == b''.join(label.ljust(12, b'\0') for label in (b'PITCH', b'LEVEL', b'ATTACK', b'RELEASE'))
            checks.append('Restart restored selected graph, source and metadata')
            d.link.write(b'n'); drain(1.2); d.link.write(b'o'); drain(.8)
            if args.phase == 'restore':
                tx, meta = manifest(graph, source, name='Interrupted')
                d.request('BEGIN', meta)
                d.request('DATA', struct.pack('<II', tx, 0) + graph[:256])
                assert d.request('STATUS')['state'] == 1
                unchanged(hashlib.sha256(graph).hexdigest())
                checks.append('Incomplete RAM upload left for restart')
        d.request('PANIC'); drain(1.1)
        status = d.request('STATUS')
        text = log_path.read_text(errors='replace')
        counters = {}
        for key in ('write_fail', 'partial', 'dma_event_overflow', 'faults', 'clips', 'nonfinite', 'overflow', 'budget70_exceeded'):
            values = [int(value) for value in re.findall(r'\b'+key+r'=(\d+)', text)]
            assert values, ('Missing runtime telemetry', key)
            counters[key] = max(values)
        fatal = bool(re.search('watchdog got triggered|Guru Meditation|Stack canary|assert failed', text, re.I))
        assert 'active=1' in text and re.findall(r'active=(\d+)', text)[-1] == '0'
        output_ok = all(value == 0 for key, value in counters.items() if key != 'budget70_exceeded') and not fatal
        timing_ok = counters['budget70_exceeded'] == 0
        maximum = {key: max(map(int, re.findall(r'\b'+key+r'=(\d+)', text)))
                   for key in ('render_max_us', 'prep_max_us', 'combined_max_us')}
        report = {'test': 'target patch workflow', 'phase': args.phase, 'passed': output_ok and timing_ok,
                  'functional_checks_passed': True, 'output_checks_passed': output_ok,
                  'timing_budget_passed': timing_ok, 'fatal_runtime_event': fatal,
                  'maximum': maximum, 'max_combined_fraction_of_block': maximum['combined_max_us']/(64/44100*1e6),
                  'telemetry_scope': 'Cumulative since boot, including front-panel activity; timing failures remain failures',
                  'hello': hello, 'status': status, 'checks': checks, 'counters': counters,
                  'log': str(log_path.relative_to(ROOT)), 'immediate_restart_requested': args.reset_after_stage}
        report_path.write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report, indent=2), flush=True)
        if not report['passed']:
            raise SystemExit('Functional checks completed; output or timing acceptance failed; see the report')
    finally:
        d.link.write(b'!')
        d.close()
if args.reset_after_stage:
    reset = subprocess.run([sys.executable, '-m', 'esptool', '--chip', 'esp32s3', '--port', args.port,
                            '--after', 'watchdog_reset', 'chip_id'], capture_output=True, text=True, check=True, timeout=15)
    (ROOT/'evidence/patch-interrupted-reset.log').write_text(reset.stdout+reset.stderr)
