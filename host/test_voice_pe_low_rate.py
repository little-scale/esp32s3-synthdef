#!/usr/bin/env python3
"""Computer-only feasibility, explicitly not a 16k production firmware test."""
import json,subprocess
from engine_profile import ROOT,generate
build=ROOT/'build/host/voice-pe-low-rate';engine=generate(build/'engine','fm1',qualified_kernels=True)
exe=build/'test'
subprocess.run(['cc','-std=c99','-O1','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off',
    '-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all','-I'+str(engine),
    str(engine/'fm_load.c'),str(engine/'fm_render.c'),str(ROOT/'tests/voice_pe_low_rate_test.c'),'-lm','-o',str(exe)],check=True)
run=subprocess.run([str(exe),str(ROOT/'examples/gated-sine.scsyndef')],check=True,capture_output=True,text=True)
(build/'report.json').write_text(json.dumps(dict(passed=True,hardware_access=False,production_option=False,rates=[16000,48000],output=run.stdout),indent=2)+'\n')
print(run.stdout,end='')
