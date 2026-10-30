#!/usr/bin/env python3
"""Compare a complete target float capture with the pinned host sine fixture."""
import argparse
import array
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('log', type=Path)
parser.add_argument('--patch',choices=['gated-sine','touch-sine'],default='gated-sine')
parser.add_argument('--build-dir',default='build-capture')
parser.add_argument('--output',default='target-numerical.json')
args = parser.parse_args()
text = args.log.read_text(errors='replace')
assert 'CAPTURE_END' in text, 'Incomplete capture'
header = re.search(r'CAPTURE_BEGIN blocks=(\d+) gate_off=(\d+) rate=(\d+) seed=(\d+) bytes=(\d+) render_us=(\d+)', text)
assert header, 'Capture header missing'
blocks, gateoff, rate, seed, size, elapsed = map(int, header.groups())
assert (blocks, gateoff, rate, seed, size) == (345, 172, 44100, 0, 345*64*2*4)
chunks = re.findall(r'CAPTURE_BLOCK (\d+) ([0-9a-f]+)', text)
assert [int(i) for i,_ in chunks] == list(range(blocks)), 'Missing or duplicate capture block'
assert all(len(data) == 1024 for _,data in chunks), 'Truncated block'
raw = b''.join(bytes.fromhex(data) for _,data in chunks)
build = ROOT/'build/host'
actual_path = build/f'target-{args.patch}.f32'
actual_path.write_bytes(raw)
reference = build/f'host-{args.patch}.f32'
subprocess.run([str(ROOT/'upstream/fm1-synthdef/synthdef-engine/build/fm-render'),
                str(ROOT/f'examples/{args.patch}.scsyndef'), str(reference), str(blocks), str(gateoff), '0'], check=True)
def samples(data):
    a = array.array('f'); a.frombytes(data)
    if sys.byteorder != 'little': a.byteswap()
    return a
actual, expected = samples(raw), samples(reference.read_bytes())
assert len(actual) == len(expected) == blocks*64*2
assert all(math.isfinite(x) for x in actual)
peak = max(abs(a-b) for a,b in zip(actual, expected))
rms = math.sqrt(sum((a-b)**2 for a,b in zip(actual, expected))/len(actual))
# Existing upstream ordinary waveform tolerance, not a new relaxed limit.
passed = peak <= 1e-4 and rms <= 3e-5
capture_build=ROOT/'firmware'/args.build_dir
source_build=re.search(r'build=([0-9a-f]+)',text)[1]
assert source_build.encode() in (capture_build/'waveshare_synthdef.bin').read_bytes(), 'Capture binary does not match log build'
report = {'test': f'ESP32 offline {args.patch} vs pinned host', 'passed': passed,
          'firmware_build_id': re.search(r'build=([0-9a-f]+)', text)[1],
          'engine_commit': re.search(r'engine=([0-9a-f]+)', text)[1],
          'capture_binary_sha256': hashlib.sha256((capture_build/'waveshare_synthdef.bin').read_bytes()).hexdigest(),
          'capture_sdkconfig_sha256': hashlib.sha256((capture_build/'sdkconfig').read_bytes()).hexdigest(),
          'source_log': str(args.log.relative_to(ROOT)) if args.log.is_relative_to(ROOT) else str(args.log),
          'fixture_sha256': hashlib.sha256((ROOT/f'examples/{args.patch}.scsyndef').read_bytes()).hexdigest(),
          'frames': blocks*64, 'sample_rate': rate, 'seed': seed, 'gate_off_block': gateoff,
          'peak_error': peak, 'rms_error': rms, 'peak_limit': 1e-4, 'rms_limit': 3e-5,
          'target_float_sha256': hashlib.sha256(raw).hexdigest(),
          'host_float_sha256': hashlib.sha256(reference.read_bytes()).hexdigest(),
          'offline_render_us_including_psram_output': elapsed,
          'scope': 'one fixture, no codec, no real-time scheduling/latency claim'}
(ROOT/'evidence'/args.output).write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
if not passed: raise SystemExit(1)
