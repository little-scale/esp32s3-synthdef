#!/usr/bin/env python3
"""Portable scheduled-control ownership and lifecycle tests, silently."""
import json,subprocess
from pathlib import Path
from engine_profile import generate
from synthdef_binary import encode
ROOT=Path(__file__).resolve().parents[1];build=ROOT/'build/host/remote-control';build.mkdir(parents=True,exist_ok=True)
engine=generate(build/'src','fm1');component=ROOT/'firmware/components/instrument';binary=build/'test'
subprocess.run(['cc','-std=c99','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off','-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all','-I'+str(engine),'-I'+str(component/'include'),str(engine/'fm_load.c'),str(engine/'fm_render.c'),str(component/'instrument.c'),str(component/'master_delay.c'),str(component/'remote_control.c'),str(ROOT/'tests/remote_control_test.c'),'-lm','-o',str(binary)],check=True)
fx=build/'definition-fx.scsyndef'
fx.write_bytes(encode(dict(name='DefinitionFX',constants=[0],controls=[.5],names=[('gain',0)],nodes=[('Control',1,[],[1],0),('In',2,[(-1,0)],[2,2],0),('BinaryOpUGen',2,[(1,0),(0,0)],[2],2),('BinaryOpUGen',2,[(1,1),(0,0)],[2],2),('Out',2,[(-1,0),(2,0),(3,0)],[],0)])))
r=subprocess.run([str(binary),str(ROOT/'examples/gated-sine.scsyndef'),str(fx)],capture_output=True,text=True,check=True);print(r.stdout.strip())
(ROOT/'evidence/remote-control-host.json').write_text(json.dumps(dict(passed=True,hardware=False,details=r.stdout.strip()),indent=2)+'\n')
