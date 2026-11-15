#!/usr/bin/env python3
"""Portable normalized inputs + real FM1 In.kr integration; no hardware/audio I/O."""
import json
import os
import subprocess
from pathlib import Path
from engine_profile import ROOT, generate
from synthdef_binary import encode

build = ROOT / "build/host/input-buses"
build.mkdir(parents=True, exist_ok=True)
engine = generate(build / "engine", "fm1", qualified_kernels=True)
component = ROOT / "firmware/components/input_buses"
flags = ["-std=c99", "-O1", "-fno-fast-math", "-ffp-contract=off",
         "-fsanitize=undefined,bounds,float-cast-overflow", "-fno-sanitize-recover=all"]
compiler = os.environ.get("CC", "cc")
# Strict warnings on new code; existing generated-engine warnings retain the
# upstream treatment and are not relabeled as warnings in the new component.
objects = []
for source in (component / "input_buses.c", ROOT / "tests/input_buses_test.c"):
    obj = build / (source.stem + ".o")
    subprocess.run([compiler, *flags, "-Wall", "-Wextra", "-Werror",
                    "-I"+str(component / "include"), "-I"+str(engine),
                    "-c", str(source), "-o", str(obj)], check=True)
    objects.append(obj)
# Each In is eight-channel, so admission and the last slot are both exercised.
# A control chooses which pair reaches the stereo output; no oscillator needed.
fixture = dict(name="NormalizedInputs", constants=[16, 24, 0], controls=[0],
    names=[("slot", 0)], nodes=[
        ("Control", 1, [], [1], 0),
        ("In", 1, [(-1, 0)], [1]*8, 0),
        ("In", 1, [(-1, 1)], [1]*8, 0),
        ("Select", 1, [(0, 0)]+[(1, k) for k in range(8)], [1], 0),
        ("Select", 1, [(0, 0)]+[(2, k) for k in range(8)], [1], 0),
        ("K2A", 2, [(3, 0)], [2], 0),
        ("K2A", 2, [(4, 0)], [2], 0),
        ("Out", 2, [(-1, 2), (5, 0), (6, 0)], [], 0)])
graph = build / "normalized-inputs.scsyndef"
graph.write_bytes(encode(fixture))
exe = build / "test"
subprocess.run([compiler, *flags, "-I"+str(engine), str(engine / "fm_load.c"),
                str(engine / "fm_render.c"), *map(str, objects), "-lm", "-o", str(exe)], check=True)
run = subprocess.run([str(exe), str(graph)], check=True, capture_output=True, text=True)
report = {"passed": True, "hardware_access": False, "audio_playback": False,
          "scope": "portable input core and generated FM1 In.kr at both rates; two raw engine voices, not production Main/FX lifecycle integration",
          "compiler": subprocess.check_output([compiler, "--version"], text=True).splitlines()[0],
          "sanitizers": ["undefined", "bounds", "float-cast-overflow"],
          "rates": [16000, 44100, 48000], "slots": 8, "output": run.stdout}
# Optional compile-only check, explicit compiler path; no device enumeration.
cross = os.environ.get("INPUT_BUSES_TARGET_CC")
if cross:
    subprocess.run([cross, "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-fno-fast-math", "-ffp-contract=off", "-I"+str(component / "include"),
                    "-c", str(component / "input_buses.c"),
                    "-o", str(build / "input_buses.esp32s3.o")], check=True)
    report["target_compile"] = {"passed": True, "scope": "portable component object only; no target link or execution",
        "compiler": subprocess.check_output([cross, "--version"], text=True).splitlines()[0]}
(build / "report.json").write_text(json.dumps(report, indent=2)+"\n")
print(json.dumps(report, indent=2))
