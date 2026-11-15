#!/usr/bin/env python3
"""Portable codec sequencing and failure tests; no serial or hardware access."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
build = ROOT/'build/host/voice-pe-codec'
build.mkdir(parents=True, exist_ok=True)
port = ROOT/'ports/voice_pe/main'
exe = build/'test'
subprocess.run(['cc', '-std=c99', '-O1', '-Wall', '-Wextra', '-Werror',
    '-fsanitize=undefined,bounds', '-fno-sanitize-recover=all', '-I'+str(port),
    str(port/'voice_pe_codec_sequence.c'), str(ROOT/'tests/voice_pe_codec_test.c'),
    '-o', str(exe)], check=True)
run = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
tone = build/'tone-test'
subprocess.run(['cc','-std=c99','-O1','-Wall','-Wextra','-Werror',
    '-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all',
    '-I'+str(port),str(port/'voice_pe_test_tone.c'),str(port/'voice_pe_format.c'),
    str(ROOT/'tests/voice_pe_tone_test.c'),'-lm','-o',str(tone)],check=True)
tone_run = subprocess.run([str(tone)],check=True,capture_output=True,text=True)
(build/'report.json').write_text(json.dumps({'passed':True, 'hardware_access':False,
    'scope':'portable sequence and fault model; not electrical or audio qualification',
    'output':run.stdout, 'tone_output':tone_run.stdout}, indent=2)+'\n')
print(run.stdout, end='')
print(tone_run.stdout,end='')
