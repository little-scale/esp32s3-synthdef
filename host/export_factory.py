#!/usr/bin/env python3
"""Compile the factory SynthDef and record its exact pre-compile source pair."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--sclang',default=shutil.which('sclang') or '/Applications/SuperCollider.app/Contents/MacOS/sclang')
args=p.parse_args()
subprocess.run([args.sclang,'-D',str(ROOT/'host/export-touch.scd')],cwd=ROOT,check=True)
pair={name:hashlib.sha256((ROOT/'examples'/name).read_bytes()).hexdigest() for name in ('touch-sine.scd','touch-sine.scsyndef')}
(ROOT/'examples/touch-sine.source.json').write_text(json.dumps(pair,indent=2)+'\n')
print('Factory graph/source pair recorded')
