#!/usr/bin/env python3
"""Portable transition ramp regression; no USB or playback."""
from pathlib import Path
import subprocess
from engine_profile import ROOT,generate
b=ROOT/'build/host/audio-transition';src=generate(b/'src','fm1')
exe=b/'test'
subprocess.run(['cc','-std=c99','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off',
 '-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all','-I'+str(src),
 '-I'+str(ROOT/'firmware/components/instrument/include'),str(ROOT/'tests/audio_transition_test.c'),'-o',str(exe)],check=True)
subprocess.run([str(exe)],check=True)
