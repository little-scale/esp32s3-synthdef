#!/usr/bin/env python3
import json,subprocess
from prepare import ROOT,ENGINE,FLAGS
component=ROOT/'firmware/components/instrument';exe=ROOT/'build/host/master-delay-test'
subprocess.run(['cc',*FLAGS,'-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all','-I'+str(ENGINE/'src'),'-I'+str(component/'include'),str(ENGINE/'src/fm_load.c'),str(ENGINE/'src/fm_render.c'),str(component/'master_delay.c'),str(component/'instrument.c'),str(ROOT/'tests/master_delay_test.c'),'-lm','-o',str(exe)],check=True)
r=subprocess.run([str(exe),str(ROOT/'examples/master-delay.scsyndef'),str(ROOT/'examples/touch-sine.scsyndef')],text=True,capture_output=True,check=True)
(ROOT/'evidence/master-delay-host.json').write_text(json.dumps({'passed':True,'sanitizers':['undefined','bounds','float-cast-overflow'],'details':r.stdout.strip(),'arena_bytes':1048576},indent=2)+'\n');print(r.stdout.strip())
