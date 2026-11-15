#!/usr/bin/env python3
"""Computer-only checks. Never imports serial or accesses a connected device."""
import json
import subprocess
from engine_profile import ROOT, generate

build = ROOT / "build/host/voice-pe"
engine = generate(build / "engine", "fm1", qualified_kernels=True)
port = ROOT / "ports/voice_pe/main"
instrument = ROOT / "firmware/components/instrument"
exe = build / "test"
flags = ["cc", "-std=c99", "-O1", "-fno-fast-math", "-ffp-contract=off",
         "-fsanitize=undefined,bounds,float-cast-overflow", "-fno-sanitize-recover=all"]
subprocess.run(flags + ["-I"+str(p) for p in (engine, port, instrument / "include")] +
               [str(p) for p in (engine / "fm_load.c", engine / "fm_render.c",
                instrument / "master_delay.c", port / "voice_pe_format.c",
                port / "voice_pe_probe.c", ROOT / "tests/voice_pe_test.c")] +
               ["-lm", "-o", str(exe)], check=True)
run = subprocess.run([str(exe), str(ROOT / "examples/gated-sine.scsyndef"),
                      str(ROOT / "examples/master-delay.scsyndef")],
                     check=True, capture_output=True, text=True)
for action in ("flash", "erase-flash", "monitor", "app-flash"):
    refused = subprocess.run(["bash", str(ROOT / "host/voice_pe.sh"), action], capture_output=True)
    assert refused.returncode == 2, action
extra = subprocess.run(["bash", str(ROOT / "host/voice_pe.sh"), "build", "flash"], capture_output=True)
assert extra.returncode == 2
report = {"passed": True, "hardware_access": False,
          "scope": "portable packing/core rendering and build-wrapper restrictions; not board validation",
          "production_fx_rates": [44100, 48000],
          "compiler": subprocess.check_output(["cc", "--version"], text=True).splitlines()[0],
          "sanitizers": ["undefined", "bounds", "float-cast-overflow"], "output": run.stdout}
(build / "report.json").write_text(json.dumps(report, indent=2) + "\n")
print(run.stdout, end="")
print("PASS: build wrapper refuses flash/erase/monitor and extra arguments")
