#!/usr/bin/env python3
"""Reproduce the old closing-segment fault and check the fix without editing vendor files."""
import json,subprocess
from engine_profile import ROOT,SOURCE,generate
from synthdef_binary import decode,encode
build=ROOT/'build/host/gendy-boundary';fixed=generate(build/'src','fm1')
graph=ROOT/'upstream/fm1-synthdef/synthdef-engine/fixtures/m10_Gendy3_ar_cp64.scsyndef'
reports=[]
for version,source in [('original',SOURCE),('fixed',fixed)]:
    exe=build/version
    subprocess.run(['cc','-std=c99','-O2','-fno-fast-math','-ffp-contract=off','-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all',
        '-I'+str(source),str(source/'fm_load.c'),str(source/'fm_render.c'),str(ROOT/'tests/gendy_long.c'),'-lm','-o',str(exe)],check=True)
    cases=[(44100,60,12345)] if version=='original' else [(r,60,12345) for r in (8000,44100,48000,96000,192000)]+[(44100,60,s) for s in (0,1,-12345,16777215)]
    for rate,seconds,seed in cases:
        data=decode(graph.read_bytes());ref=next(n[2][1] for n in data['nodes'] if n[0]=='RandSeed');assert ref[0]==-1
        data['constants'][ref[1]]=float(seed);case=build/f'seed-{seed}.scsyndef';case.write_bytes(encode(data))
        result=json.loads(subprocess.check_output([str(exe),str(case),str(rate),str(seconds),'0'],text=True));reports.append({'version':version,'fixture_seed':seed,**result});print(version,seed,result,flush=True)
data=decode((graph.parent/'m10_Gendy3_kr_cp64.scsyndef').read_bytes())
ref=next(n[2][4] for n in data['nodes'] if n[0]=='Gendy3');assert ref[0]==-1
data['constants'][ref[1]]=.1;slow=build/'slow-control.scsyndef';slow.write_bytes(encode(data))
for version in ('original','fixed'):
    result=json.loads(subprocess.check_output([str(build/version),str(slow),'44100','60','0'],text=True))
    reports.append({'version':version,'calculation_rate':'control','frequency':.1,**result});print(version,'slow control',result,flush=True)
assert reports[0]['fault_block'] and not reports[0]['passed']
assert all(r['passed'] for r in reports if r['version']=='fixed')
report={'passed':True,'original_fault_reproduced':True,'reports':reports,'scope':'Original pinned source versus audited target patch, 64-point Gendy3 at five sample rates and five explicit RandSeed values, with memory canaries and sanitizers.'}
(ROOT/'evidence/gendy-boundary-regression.json').write_text(json.dumps(report,indent=2)+'\n')
