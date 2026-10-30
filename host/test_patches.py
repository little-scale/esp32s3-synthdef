#!/usr/bin/env python3
"""Exercise the real portable device parser and persistence record reader."""
import json
import subprocess
from prepare import ROOT, ENGINE, FLAGS
from patches import frame, decode, manifest

build = ROOT/'build/host'
build.mkdir(parents=True, exist_ok=True)
component = ROOT/'firmware/components/patches'
subprocess.run(['cc', *FLAGS, '-fsanitize=undefined,bounds,float-cast-overflow',
                '-fno-sanitize-recover=all', '-I'+str(ENGINE/'src'), '-I'+str(component/'include'),
                str(ENGINE/'src/fm_load.c'), str(ENGINE/'src/fm_render.c'),
                str(component/'patch_format.c'), str(ROOT/'tests/patch_test.c'),
                '-lm', '-o', str(build/'patch-test')], check=True)
run = subprocess.run([str(build/'patch-test'), str(ROOT/'examples/touch-sine.scsyndef'),
                      str(build/'patch-record-test.wsp')], capture_output=True, text=True, check=True, timeout=60)
for size in range(513):
    data = bytes(i % 256 for i in range(size))
    assert decode(frame(123, 'DATA', data)) == (123, 'DATA', data)
_, meta = manifest((ROOT/'examples/touch-sine.scsyndef').read_bytes(), b'// source\n')
assert len(meta) == 160
report = {'test': 'portable patch protocol/storage formats', 'passed': True,
          'hardware': False, 'details': run.stdout.strip(),
          'sanitizers': ['undefined', 'bounds', 'float-cast-overflow'],
          'scope': 'Byte-boundary interruption/corruption of individual files; physical power-cut/filesystem tests remain pending'}
(ROOT/'evidence/patch-host.json').write_text(json.dumps(report, indent=2)+'\n')
print(run.stdout.strip())
