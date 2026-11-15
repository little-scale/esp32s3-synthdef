#!/usr/bin/env python3
"""Silent regression for literal oscillator domains and startup rejection."""
import subprocess
from engine_profile import ROOT, generate
from synthdef_binary import encode

build=ROOT/'build/host/oscillator-admission'
build.mkdir(parents=True,exist_ok=True)
engine=generate(build/'engine','fm1',qualified_kernels=True)
paths=[]
for kind in ('LFPar','LFCub','VarSaw'):
    for rate in (1,2):
        refs=[(-1,1),(-1,2)]+([(-1,3)] if kind=='VarSaw' else [])
        nodes=[(kind,rate,refs,[rate],0),('In',2,[(-1,0)],[2,2],0),
               ('BinaryOpUGen',2,[(1,0),(0,0)],[2],2),
               ('BinaryOpUGen',2,[(1,1),(0,0)],[2],2),
               ('Out',2,[(-1,0),(2,0),(3,0)],[],0)]
        path=build/f'{kind}-{rate}.scsyndef'
        path.write_bytes(encode(dict(name=kind,constants=[0,.1,0,.5],controls=[],names=[],nodes=nodes)))
        paths.append(path)
patches=ROOT/'firmware/components/patches'
instrument=ROOT/'firmware/components/instrument'
binary=build/'test'
subprocess.run(['cc','-std=c99','-O1','-Wall','-Wextra','-Werror',
    '-fno-fast-math','-ffp-contract=off','-fsanitize=undefined,bounds,float-cast-overflow',
    '-fno-sanitize-recover=all','-DPATCH_FM1_COMPAT=1',
    *['-I'+str(p) for p in (engine,patches/'include',instrument/'include')],
    *map(str,(engine/'fm_load.c',engine/'fm_render.c',patches/'patch_format.c',instrument/'instrument.c',
              ROOT/'tests/oscillator_admission_test.c')),'-lm','-o',str(binary)],check=True)
subprocess.run([str(binary),*map(str,paths)],check=True,timeout=30)
