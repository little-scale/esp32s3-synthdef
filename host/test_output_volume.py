#!/usr/bin/env python3
"""Silent mono/stereo output conversion and gain-ramp regression."""
import subprocess
from pathlib import Path
from engine_profile import generate
ROOT=Path(__file__).resolve().parents[1]
build=ROOT/'build/host/output-volume';source=generate(build/'src','fm1')
component=ROOT/'firmware/components/instrument';binary=build/'test'
subprocess.run(['cc','-std=c99','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off',
    '-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all',
    '-I'+str(source),'-I'+str(component/'include'),str(source/'fm_load.c'),str(source/'fm_render.c'),
    str(component/'instrument.c'),str(component/'output_volume.c'),str(ROOT/'tests/output_volume_test.c'),
    '-lm','-o',str(binary)],check=True)
subprocess.run([str(binary)],check=True)
