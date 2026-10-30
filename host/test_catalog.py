#!/usr/bin/env python3
"""Check exact catalog admission in normal and explicit diagnostic builds."""
import hashlib
import json
import subprocess
from prepare import ROOT,ENGINE,FLAGS
component=ROOT/'firmware/components/patches'
entries=json.loads((ROOT/'examples/catalog.json').read_text());reports=[]
for diagnostic in [False,True]:
    exe=ROOT/f'build/host/catalog-test-{int(diagnostic)}'
    subprocess.run(['cc',*FLAGS,'-DPATCH_ALLOW_CANDIDATES='+str(int(diagnostic)),
                    '-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all',
                    '-I'+str(ENGINE/'src'),'-I'+str(component/'include'),
                    str(ENGINE/'src/fm_load.c'),str(ENGINE/'src/fm_render.c'),str(component/'patch_format.c'),
                    str(ROOT/'tests/catalog_test.c'),'-lm','-o',str(exe)],check=True)
    for entry in entries:
        graph=ROOT/f'examples/{entry["id"]}.scsyndef'
        allowed=entry['status']=='qualified' or (diagnostic and entry['status']=='candidate')
        run=subprocess.run([str(exe),str(graph),hashlib.sha256(graph.read_bytes()).hexdigest(),str(int(allowed))],check=True,capture_output=True,text=True)
        reports.append({'patch':entry['id'],'diagnostic':diagnostic,'admitted':allowed,'passed':True})
(ROOT/'evidence/catalog-admission.json').write_text(json.dumps({'passed':True,'reports':reports},indent=2)+'\n')
print('PASS: catalog hashes and per-build admission; altered binaries remain outside the generic family')
