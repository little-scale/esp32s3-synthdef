#!/usr/bin/env python3
"""Exercise the on-device source lexer silently under memory sanitizers."""
import json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];build=ROOT/'build/host';build.mkdir(parents=True,exist_ok=True)
ui=ROOT/'firmware/components/ui';exe=build/'source-test'
subprocess.run(['cc','-std=c99','-O1','-Wall','-Wextra','-Werror','-fsanitize=undefined,bounds',
 '-fno-sanitize-recover=all','-I'+str(ui/'include'),str(ui/'sc_source.c'),str(ROOT/'tests/sc_source_test.c'),'-o',str(exe)],check=True)
run=subprocess.run([str(exe)],check=True,capture_output=True,text=True);print(run.stdout.strip())
(ROOT/'evidence/source-lexer.json').write_text(json.dumps(dict(passed=True,details=run.stdout.strip(),hardware=False,
 sanitizers=['undefined','bounds'],memory_checks='Guard pages before/after source and style allocations; randomized inputs end directly at the inaccessible page',
 address_sanitizer='Local runtime deadlocked during initialization before main; not counted as a passed ASan run'),indent=2)+'\n')
