#!/usr/bin/env python3
"""Offline cue rendering regression. No board access or host playback."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
build = ROOT / 'build/host/identify-tone'
build.mkdir(parents=True, exist_ok=True)
component = ROOT / 'firmware/components/instrument'
binary = build / 'test'
subprocess.run(['cc', '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror',
    '-fno-fast-math', '-ffp-contract=off', '-fsanitize=undefined,bounds,float-cast-overflow',
    '-fno-sanitize-recover=all', '-I'+str(component / 'include'),
    str(component / 'identify_tone.c'), str(ROOT / 'tests/identify_tone_test.c'),
    '-lm', '-o', str(binary)], check=True)
subprocess.run([str(binary)], check=True)
