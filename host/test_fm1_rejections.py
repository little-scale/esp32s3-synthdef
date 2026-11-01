#!/usr/bin/env python3
"""Keep authoritative parsing and live-control restrictions in the wider policy."""
import copy
import json
import subprocess
from engine_profile import ROOT,generate
from synthdef_binary import decode,encode
build=ROOT/'build/host/fm1-rejections';source=generate(build/'src','fm1')
base=decode((ROOT/'build/host/fm1-voice/long-delay-voice.scsyndef').read_bytes())
cases=[]
def case(name,g,loaded=1,normal=0,compat=0):
    raw=g if isinstance(g,bytes) else encode(g)
    path=build/(name+'.scsyndef');path.write_bytes(raw);cases.append((name,path,loaded,normal,compat))
case('memory-voice',base,compat=1)
case('generic-touch-sine',(ROOT/'examples/touch-sine.scsyndef').read_bytes(),normal=1,compat=1)
g=copy.deepcopy(base);g['names'][2]=('other_gate',2);case('missing-gate',g)
g=copy.deepcopy(base);n=g['nodes'][0];g['nodes'][0]=(n[0],0,n[2],[0,0,0],n[4]);case('scalar-interface',g)
g=copy.deepcopy(base)
g['nodes']=[('Control',0,[],[0,0,0],0)]+[(n,r,[(i+1 if i>=0 else i,o) for i,o in refs],rates,s) for n,r,refs,rates,s in g['nodes']]
case('overlapping-scalar-alias',g)
for selector in (14,15,16,26,27,28,29,47,48,999):
    g=copy.deepcopy(base);n=g['nodes'][2];g['nodes'][2]=(*n[:4],selector);case('unsupported-binary-'+str(selector),g,loaded=0)
for selector in (1,2,3,4,6,7,37,38,39,40,41,44,45,999):
    g=copy.deepcopy(base);g['nodes'].append(('UnaryOpUGen',2,[(1,0)],[2],selector));case('unsupported-unary-'+str(selector),g,loaded=0)
g=copy.deepcopy(base);g['constants'][1]=100;case('arena-over-budget',g)
g=copy.deepcopy(base);g['controls'][0]=20001;case('frequency-range',g)
g=copy.deepcopy(base);g['controls'][1]=-.1;case('amplitude-range',g)
g=copy.deepcopy(base);g['controls'][2]=float('nan');case('nan-default',g,loaded=0)
g=copy.deepcopy(base);n=g['nodes'][1];g['nodes'][1]=('UnknownUGen',*n[1:]);case('unknown-ugen',g,loaded=0)
g=copy.deepcopy(base);n=g['nodes'][1];g['nodes'][1]=(n[0],3,n[2],[3],n[4]);case('demand-rate',g,loaded=0)
g=copy.deepcopy(base);g['nodes'] += [('DC',2,[(-1,0)],[2],0)]*(161-len(g['nodes']));case('node-limit',g,loaded=0)
g=copy.deepcopy(base);g['nodes'] += [('Pan2',2,[(1,0),(-1,0),(-1,3)],[2,2],0)]*100;case('signal-limit',g,loaded=0)
g=copy.deepcopy(base);g['nodes'].append(('Select',2,[(-1,0)]+[(1,0)]*1024,[2],0));case('input-limit',g,loaded=0)
case('truncated',encode(base)[:-1],loaded=0);case('file-limit',encode(base)+b'\0'*65537,loaded=0)
reports=[];component=ROOT/'firmware/components/patches'
for compat in (0,1):
    exe=build/f'probe-{compat}'
    subprocess.run(['cc','-std=c99','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off',
        '-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all','-DPATCH_ALLOW_CANDIDATES=0',
        '-DPATCH_FM1_COMPAT='+str(compat),'-I'+str(source),'-I'+str(component/'include'),str(source/'fm_load.c'),
        str(source/'fm_render.c'),str(component/'patch_format.c'),str(ROOT/'tests/admission_probe.c'),'-lm','-o',str(exe)],check=True)
    for name,path,loaded,normal,full in cases:
        run=subprocess.run([str(exe),str(path),str(loaded),str(full if compat else normal)],capture_output=True,text=True)
        reports.append(dict(name=name,compatibility=bool(compat),passed=run.returncode==0,error=run.stderr))
report=dict(passed=all(r['passed'] for r in reports),hardware_tested=False,reports=reports)
(ROOT/'evidence/fm1-admission.json').write_text(json.dumps(report,indent=2)+'\n')
print('Admission cases:',len(reports),'passed:',report['passed'])
for row in reports:
    if not row['passed']:print(row)
assert report['passed']
