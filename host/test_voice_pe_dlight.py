#!/usr/bin/env python3
"""Computer-only BH1750 state machine and audio mailbox checks; no USB access."""
import json
from pathlib import Path
import subprocess
import tempfile
from engine_profile import generate
from synthdef_binary import encode
ROOT=Path(__file__).resolve().parents[1]
build=ROOT/'build/host/voice-pe-dlight';build.mkdir(parents=True,exist_ok=True)
port=ROOT/'ports/voice_pe/main';binary=build/'test'
subprocess.run(['cc','-std=c11','-O1','-Wall','-Wextra','-Werror',
    '-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all',
    '-I'+str(port),str(port/'voice_pe_dlight.c'),str(ROOT/'tests/voice_pe_dlight_test.c'),'-lm','-o',str(binary)],check=True)
result=subprocess.run([str(binary)],check=True,text=True,capture_output=True,timeout=20)
with tempfile.TemporaryDirectory() as temporary:
    fake=Path(temporary);(fake/'driver').mkdir()
    for header in ('esp_err.h','esp_timer.h','esp_log.h','driver/gpio.h','driver/i2c_master.h'):
        (fake/header).write_text('#include "voice_pe_grove_fake.h"\n')
    for enabled in (False,True):
        adapter=build/('adapter-on' if enabled else 'adapter-off')
        subprocess.run(['cc','-std=c11','-O1','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable',
            '-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all',
            *(['-DCONFIG_SYNTHDEF_VOICE_PE_DLIGHT=1'] if enabled else []),
            *['-I'+str(p) for p in (fake,ROOT/'tests',port,ROOT/'firmware/components/headless_io/include')],
            str(ROOT/'tests/voice_pe_grove_test.c'),str(port/'voice_pe_dlight.c'),'-lm','-o',str(adapter)],check=True)
        for failure in ((0,1,2,3) if enabled else (0,)):
            response=subprocess.run([str(adapter),str(failure)],capture_output=True,text=True,check=True,timeout=20)
            if enabled and not failure:
                status=json.loads('{'+response.stdout.strip()+'}')['grove_light']
                assert status['available'] and status['samples']==2 and status['errors']==1
                assert status['buses']==[42,43] and status['age_ms']==0
graph=dict(name='Grove input bank',constants=[42,39,0],controls=[],names=[],nodes=[
    ('In',1,[(-1,0)],[1,1],0),('Out',1,[(-1,1),(0,0),(0,1)],[],0),
    ('DC',2,[(-1,2)],[2],0),('Out',2,[(-1,2),(2,0),(2,0)],[],0)])
path=build/'grove.scsyndef';path.write_bytes(encode(graph))
engine=generate(build/'engine','fm1',qualified_kernels=True)
bus_test=build/'bus-test'
subprocess.run(['cc','-std=c99','-O1','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off',
    '-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all','-I'+str(engine),
    str(engine/'fm_load.c'),str(engine/'fm_render.c'),str(ROOT/'tests/voice_pe_grove_bus_test.c'),'-lm','-o',str(bus_test)],check=True)
buses=subprocess.run([str(bus_test),str(path)],capture_output=True,text=True,timeout=30)
if buses.stderr:print(buses.stderr,end='')
buses.check_returncode()
(build/'report.json').write_text(json.dumps(dict(passed=True,hardware_access=False,adapter_cases=5,
    engine_bus_rates=[16000,44100,48000],output=result.stdout+buses.stdout),indent=2)+'\n')
print(result.stdout,end='')
print('PASS: production Grove adapter, dedicated GPIO/I2C, optional init failures, disabled profile, JSON status, hold/reconnect')
print(buses.stdout,end='')
