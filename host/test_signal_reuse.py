#!/usr/bin/env python3
"""Silent, sanitizer-backed comparison with unreused storage; no audio or USB."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import struct
import subprocess
import time
from engine_profile import ROOT,generate

BUILD=ROOT/'build/host/signal-reuse'
FLAGS=['-std=c99','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off',
       '-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all']


def graph(name,nodes,constants=(0,.1,1,220),controls=()):
    def text(s):
        raw=s.encode();assert len(raw)<256;return bytes([len(raw)])+raw
    def i(n):return struct.pack('>i',n)
    data=b'SCgf'+i(2)+struct.pack('>H',1)+text(name)+i(len(constants))
    data+=b''.join(struct.pack('>f',v) for v in constants)+i(len(controls))
    data+=b''.join(struct.pack('>f',v) for v in controls)+i(0)+i(len(nodes))
    for kind,rate,inputs,outputs,special in nodes:
        data+=text(kind)+bytes([rate])+i(len(inputs))+i(outputs)+struct.pack('>h',special)
        data+=b''.join(i(n)+i(o) for n,o in inputs)+bytes([rate])*outputs
    return data+struct.pack('>H',0)


def custom_cases():
    c=lambda i:(-1,i)
    cases={}
    for count in (1,10,80,150):
        nodes=[('DC',2,[c(1)],1,0)]
        nodes += [('UnaryOpUGen',2,[(i-1,0)],1,5) for i in range(1,count)]
        nodes += [('Out',2,[c(0),(count-1,0)],0,0)]
        cases['chain-'+str(count)]=graph('Chain',nodes)
    # Long-lived source, duplicate references, two outputs with different consumers,
    # and several writes to Out (the mixer must not live in recycled scratch).
    nodes=[('DC',2,[c(1)],1,0),('Pan2',2,[(0,0),c(0),c(2)],2,0),
           ('BinaryOpUGen',2,[(1,1),(0,0)],1,0),('Out',2,[c(0),(1,0),(2,0)],0,0),
           ('BinaryOpUGen',2,[(0,0),(0,0)],1,2),('Out',2,[c(0),(4,0)],0,0)]
    cases['branch-multi-out']=graph('Branch',nodes)
    # Cached .ir values must be restored when alternating two independent voices.
    nodes=[('Rand',0,[c(1),c(2)],1,0),('DC',1,[c(1)],1,0),
           ('K2A',2,[(1,0)],1,0),('BinaryOpUGen',2,[(2,0),(0,0)],1,2),
           ('Out',2,[c(0),(3,0)],0,0)]
    cases['initial-and-control']=graph('Cached',nodes)
    for seed in range(40):
        rng=random.Random(seed);nodes=[('DC',2,[c(1)],1,0)]
        for _ in range(rng.randint(15,100)):
            sources=[(i,k) for i,n in enumerate(nodes) for k in range(n[3]) if n[1]==2]
            a,b=rng.choice(sources),rng.choice(sources)
            if rng.random()<.25:nodes.append(('Pan2',2,[a,c(0),c(2)],2,0))
            else:nodes.append(('BinaryOpUGen',2,[a,b],1,2 if rng.random()<.5 else 1))
        nodes.append(('Out',2,[c(0),(len(nodes)-1,0)],0,0))
        cases['dag-'+str(seed)]=graph('DAG',nodes)
    return cases


def capacity_cases():
    c=lambda i:(-1,i)
    cases={}
    for count in (159,160,192,240,255,256):
        nodes=[('DC',2,[c(1)],1,0)]
        nodes += [('UnaryOpUGen',2,[(i-1,0)],1,5) for i in range(1,count)]
        nodes += [('Out',2,[c(0),(count-1,0)],0,0)]
        cases['nodes-'+str(count+1)]=(graph('NodeBoundary',nodes),count+1<=256)
    for count in (511,512,513):
        controls=min(count-448,64)
        nodes=[('Control',1,[],controls,0)]
        nodes += [('Pan2',2,[c(1),c(0),c(2)],2,0) for _ in range(224)]
        if count>512:nodes.append(('DC',2,[c(1)],1,0))
        nodes += [('Out',2,[c(0),(224,0)],0,0)]
        cases['outputs-'+str(count)]=(graph('OutputBoundary',nodes,controls=[.1]*controls),count<=512)
    for count in (2048,2049):
        nodes=[('Select',1,[c(0)]*(count-3),1,0),('K2A',2,[(0,0)],1,0),('Out',2,[c(0),(1,0)],0,0)]
        cases['inputs-'+str(count)]=(graph('InputBoundary',nodes),count<=2048)
    for rate in (0,1):
        nodes=[('Control',rate,[],64,0) for _ in range(8)]
        cases['scalar-bank-'+str(rate)]=(graph('ScalarBank',nodes,controls=[.1]*64),True)
    for count in (191,192):
        nodes=[('Pan2',2,[c(1),c(0),c(2)],2,0) for _ in range(count//2)]
        if count%2:nodes.append(('DC',2,[c(1)],1,0))
        pending=[(i,k) for i,n in enumerate(nodes) for k in range(n[3])]
        while len(pending)>1:
            batch=pending[:4];del pending[:4]
            kind={2:'BinaryOpUGen',3:'Sum3',4:'Sum4'}[len(batch)]
            nodes.append((kind,2,batch,1,0));pending.append((len(nodes)-1,0))
        nodes.append(('Out',2,[c(0),pending[0]],0,0))
        cases['live-'+str(count+1)]=(graph('LiveBoundary',nodes),count+1<=192)
    return cases


def executable(folder,reuse):
    src=generate(folder/'src','fm1',reuse_buffers=reuse);exe=folder/'run'
    subprocess.run(['cc',*FLAGS,'-I'+str(src),str(src/'fm_load.c'),str(src/'fm_render.c'),
                    str(ROOT/'tests/signal_reuse_test.c'),'-lm','-o',str(exe)],check=True)
    return exe


def run(exe,path,blocks):
    result=subprocess.run([str(exe),str(path),str(blocks)],capture_output=True,timeout=30)
    assert result.returncode==0,(path,result.stderr.decode(errors='replace')[-2000:])
    return result.stdout,json.loads(result.stderr)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--quick',action='store_true',help='custom cases and project examples only')
    args=parser.parse_args();BUILD.mkdir(parents=True,exist_ok=True)
    reference=executable(BUILD/'reference',False);planned=executable(BUILD/'planned',True)
    paths=[]
    for name,data in custom_cases().items():
        path=BUILD/(name+'.scsyndef');path.write_bytes(data);paths.append(path)
    paths+=sorted((ROOT/'examples').glob('*.scsyndef'))
    if not args.quick:paths+=sorted((ROOT/'upstream/fm1-synthdef/synthdef-engine/fixtures').glob('*.scsyndef'))
    report=dict(passed=False,hardware=False,block_frames=64,cases=[],sanitizers=FLAGS[-2:])
    started=time.monotonic()
    for index,path in enumerate(paths):
        old,a=run(reference,path,32);new,b=run(planned,path,32)
        assert a['loaded']==b['loaded'],(path,a,b)
        assert a.get('prepared')==b.get('prepared'),(path,a,b)
        assert old==new,('Sample/state mismatch',path,a,b)
        report['cases'].append(dict(path=str(path.relative_to(ROOT)),**b,
            trace_sha256=hashlib.sha256(new).hexdigest(),graph_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        if index%100==0:print(f'{index+1}/{len(paths)} graphs compared',flush=True)
    report['capacity_cases']=[]
    for name,(data,expected) in capacity_cases().items():
        path=BUILD/(name+'.scsyndef');path.write_bytes(data)
        old,a=run(reference,path,64);new,b=run(planned,path,64)
        assert b['loaded']==expected,(name,expected,b)
        if expected:assert a['loaded'] and old==new,(name,a,b)
        else:assert not b.get('valid'),(name,b)
        report['capacity_cases'].append(dict(name=name,expected=expected,**b,graph_sha256=hashlib.sha256(data).hexdigest()))
    report['long_cases']=[]
    selected=[]
    for family in ('comb','delay','allpass','freeverb','miverb','pluck','rings','gendy','env','noise'):
        matches=[p for p in paths if family in p.stem.lower()]
        selected+=matches[:2]
    for path in dict.fromkeys(selected):
        old,a=run(reference,path,2048);new,b=run(planned,path,2048)
        assert a['loaded']==b['loaded'] and old==new,('Long state mismatch',path,a,b)
        report['long_cases'].append(dict(path=str(path.relative_to(ROOT)),blocks=2048,
                                        sha256=hashlib.sha256(new).hexdigest(),**b))
    report.update(passed=True,elapsed_seconds=time.monotonic()-started,graphs=len(paths),
                  loaded=sum(c['loaded'] for c in report['cases']),
                  limits=dict(nodes=256,outputs=512,inputs=2048,audio_buffers=192),
                  profile=json.loads((BUILD/'planned/profile.json').read_text()))
    report['comparison']='Byte-identical float output, lifecycle flags, final pointer-normalized voice state and delay arena; alternating graphs use different physical layouts.'
    (ROOT/'evidence/signal-reuse.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'PASS: {len(paths)} graphs; byte-identical samples and state flags; independent lifetime validation',flush=True)


if __name__=='__main__':main()
