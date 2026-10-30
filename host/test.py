#!/usr/bin/env python3
"""Run portable adapter behavior checks with undefined/bounds sanitizers."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'host'))
from prepare import ENGINE, FLAGS

subprocess.run([sys.executable, str(ROOT/'host/prepare.py'), '--check'], check=True)
build = ROOT/'build/host'
component = ROOT/'firmware/components/instrument'
command = ['cc', *FLAGS, '-g', '-fsanitize=undefined,bounds,float-cast-overflow',
           '-fno-sanitize-recover=all', '-I'+str(ENGINE/'src'), '-I'+str(component/'include'),
           str(ENGINE/'src/fm_load.c'), str(ENGINE/'src/fm_render.c'),
           str(component/'instrument.c'), str(ROOT/'tests/instrument_test.c'),
           '-lm', '-o', str(build/'instrument-test')]
subprocess.run(command, check=True)
run = subprocess.run([str(build/'instrument-test'), str(ROOT/'examples/gated-sine.scsyndef'),
                      str(build/'gated-sine.pcm'), str(ROOT/'examples/touch-sine.scsyndef')], text=True, capture_output=True, check=True, timeout=30)
print(run.stdout.strip())
report = {'test': 'portable instrument adapter', 'result': 'passed', 'hardware': False,
          'sample_rates': [44100, 48000], 'seed': 0, 'factory_patch_sha256':
          hashlib.sha256((ROOT/'examples/gated-sine.scsyndef').read_bytes()).hexdigest(),
          'compiler': subprocess.check_output(['cc', '--version'], text=True).splitlines()[0],
          'sanitizers': ['undefined', 'bounds', 'float-cast-overflow'], 'details': run.stdout.strip(),
          'address_sanitizer': 'not run successfully: installed Apple runtime deadlocks during initialization on this OS, before main',
          'pcm_sha256': hashlib.sha256((build/'gated-sine.pcm').read_bytes()).hexdigest(),
          'hash_scope': 'same host/compiler diagnostic; cross-target comparisons require numerical tolerances'}
(ROOT/'evidence/host-adapter.json').write_text(json.dumps(report, indent=2)+'\n')
