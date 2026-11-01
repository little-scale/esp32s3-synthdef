#!/usr/bin/env python3
"""Compile the original bus example silently and record its exact source pair."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
subprocess.run(['/Applications/SuperCollider.app/Contents/MacOS/sclang','-D',str(ROOT/'host/export-touch-buses.scd')],cwd=ROOT,check=True)
names=('touch-buses.scd','TouchBuses.scsyndef')
pair={name:hashlib.sha256((ROOT/'examples'/name).read_bytes()).hexdigest() for name in names}
(ROOT/'examples/touch-buses.source.json').write_text(json.dumps(pair,indent=2)+'\n')
print('Touch-bus source/graph pair recorded')
