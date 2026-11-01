#!/usr/bin/env python3
"""Compile six silent, real-control Rings performance fixtures with sclang."""
import argparse,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--sclang',default=shutil.which('sclang') or '/Applications/SuperCollider.app/Contents/MacOS/sclang')
args=p.parse_args();build=ROOT/'build/host';build.mkdir(parents=True,exist_ok=True)
config=build/'rings-sclang.yaml'
config.write_text('includePaths:\n  - '+str(ROOT/'upstream/fm1-synthdef/synthdef-engine/sc/Classes')+'\nexcludePaths: []\npostInlineWarnings: false\n')
subprocess.run([args.sclang,'-l',str(config),'-D',str(ROOT/'host/export-rings.scd')],cwd=ROOT,check=True)
assert all((build/f'rings-voices/rings-{model}.scsyndef').is_file() for model in range(1,7))
print('Exported six SynthDefs; no audio server was opened')
