#!/usr/bin/env python3
"""Silent native execution of the pinned DSP; never opens audio or serial devices."""
import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from engine_profile import ROOT, SOURCE, generate

UPSTREAM=SOURCE.parent
BUILD=ROOT/'build/host/fm1-parity'
FLAGS=['-std=c99','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off']

def inventory(profile, paths):
    source=generate(BUILD/profile/'src',profile)
    exe=source.parent/'inventory'
    subprocess.run(['cc',*FLAGS,'-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all',
                    '-I'+str(source),str(source/'fm_load.c'),str(source/'fm_render.c'),
                    str(ROOT/'tests/engine_inventory.c'),'-lm','-o',str(exe)],check=True)
    run=subprocess.run([str(exe)],input=''.join(str(p)+'\n' for p in paths),capture_output=True,text=True,check=True)
    rows=[json.loads(line) for line in run.stdout.splitlines()]
    assert len(rows)==len(paths)
    return rows

def osc_string(s):
    b=s.encode()+b'\0';return b+b'\0'*((-len(b))%4)

def cleanup_score(source,destination):
    """Free nodes after the compared interval, before SC unloads plugin code.

    The source score and every compared sample remain unchanged. A final block
    allows normal node destruction on this macOS SC build (including CombL).
    """
    data=source.read_bytes();pos=0;last=0
    while pos<len(data):
        size=struct.unpack_from('>I',data,pos)[0];pos+=4
        packet=data[pos:pos+size];assert len(packet)==size and packet[:8]==b'#bundle\0'
        last=struct.unpack_from('>Q',packet,8)[0];pos+=size
    assert pos==len(data)
    def bundle(time,message):
        packet=b'#bundle\0'+struct.pack('>Q',time)+struct.pack('>I',len(message))+message
        return struct.pack('>I',len(packet))+packet
    # Free root-group contents at the original end time, then end one block later.
    data+=bundle(last,osc_string('/g_freeAll')+osc_string(',i')+struct.pack('>i',0))
    data+=bundle(last+round(64/44100*2**32),osc_string('/c_set')+osc_string(',ii')+struct.pack('>ii',0,0))
    destination.write_bytes(data)

def prepare_mirror():
    mirror=BUILD/'reference-engine';mirror.mkdir(parents=True,exist_ok=True)
    for folder in ('tests','tools'):
        shutil.copytree(UPSTREAM/folder,mirror/folder,dirs_exist_ok=True)
    for folder in ('fixtures','reference'):
        link=mirror/folder
        if not link.exists():link.symlink_to(UPSTREAM/folder,target_is_directory=True)
    shutil.copyfile(UPSTREAM/'Makefile',mirror/'Makefile')
    link=BUILD/'fm1-synth'
    if not link.exists():link.symlink_to(UPSTREAM.parent/'fm1-synth',target_is_directory=True)
    generate(mirror/'src','fm1');(mirror/'build').mkdir(exist_ok=True)
    return mirror

def fuzz(prefix='fm1'):
    mirror=prepare_mirror()
    run=subprocess.run(['make','-C',str(mirror),'sanitize'],capture_output=True,text=True)
    log=run.stdout+run.stderr
    seeds=log.count('20,000 malformed/truncated graphs: sanitizer run passed')
    report={'passed':run.returncode==0 and seeds>0,'hardware_tested':False,'audio_playback':False,
            'profile':'fm1','seed_count':seeds,'mutated_or_truncated_inputs':seeds*20000,
            'sanitizers':['undefined','bounds','float-cast-overflow']}
    (ROOT/'evidence'/f'{prefix}-fuzz.log').write_text(log)
    (ROOT/'evidence'/f'{prefix}-fuzz.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)
    return report['passed']

def reference(prefix='fm1'):
    mirror=prepare_mirror()
    subprocess.run(['cc',*FLAGS,'-I'+str(mirror/'src'),str(mirror/'src/fm_load.c'),str(mirror/'src/fm_render.c'),
                    str(mirror/'tools/render.c'),'-lm','-o',str(mirror/'build/fm-render')],check=True)
    sys.path.insert(0,str(mirror/'tests'))
    spec=importlib.util.spec_from_file_location('fm1_reference',mirror/'tests/compare_reference.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    original_run=subprocess.run
    def run(args,*a,**kw):
        if isinstance(args,list) and '-N' in args:
            args=list(args);i=args.index('-N')+1;score=Path(args[i]);copy=mirror/'build'/score.name
            cleanup_score(score,copy);args[i]=str(copy)
        return original_run(args,*a,**kw)
    subprocess.run=run
    try:passed=module.main()
    finally:subprocess.run=original_run
    rows=json.loads((mirror/'build/reference-results.json').read_text())
    report={'passed':passed,'hardware_tested':False,'audio_playback':False,
            'mode':'SuperCollider 3.14.1 non-real-time files versus native C renderer; not Xtensa cycle emulation',
            'score_cleanup':'Original bytes retained; free all nodes at original end, one cleanup block appended',
            'profile':json.loads((mirror/'profile.json').read_text()),'results':rows}
    (ROOT/'evidence'/f'{prefix}-reference.json').write_text(json.dumps(report,indent=2)+'\n')
    return passed

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--reference',action='store_true')
    parser.add_argument('--fuzz',action='store_true')
    parser.add_argument('--prefix',default='fm1')
    args=parser.parse_args();BUILD.mkdir(parents=True,exist_ok=True)
    paths=sorted((UPSTREAM/'fixtures').glob('*.scsyndef'))
    extra=[ROOT/'examples/master-delay.scsyndef']
    full=inventory('fm1',paths+extra);compact=inventory('compact',paths+extra)
    counts={};operators={'UnaryOpUGen':{},'BinaryOpUGen':{}}
    for row in full:
        for node in row.get('ugens',[]):
            entry=counts.setdefault(node['name'],{'fixtures':set(),'rates':set(),'smoke_passed':True})
            entry['fixtures'].add(Path(row['path']).stem);entry['rates'].add(node['rate']);entry['smoke_passed'] &= row['smoke_passed']
            if node['name'] in operators:
                op=operators[node['name']].setdefault(str(node['selector']),{'rates':set(),'fixtures':set()})
                op['rates'].add(node['rate']);op['fixtures'].add(Path(row['path']).stem)
    for entry in [*counts.values(),*(e for ops in operators.values() for e in ops.values())]:
        entry['rates']=sorted(entry['rates']);entry['fixtures']=sorted(entry['fixtures'])
    enum=re.search(r'typedef enum\s*\{(.*?)FM_TYPES',(SOURCE/'fm_synth.h').read_text(),re.S)[1]
    missing=sorted(set(re.findall(r'\bFM_(\w+)\b',enum))-set(counts))
    passed=not missing and all(r['loaded'] and r['smoke_passed'] for r in full)
    report={'passed':passed,'hardware_tested':False,'audio_playback':False,'sample_rate':44100,'smoke_blocks':16,
            'scope':'Native C host emulation with undefined-behaviour, bounds and float-cast checks; no ESP32 timing claim',
            'fixture_count':len(paths),'additional_graph_count':len(extra),'ugen_count':len(counts),'operator_counts':{k:len(v) for k,v in operators.items()},
            'missing_fixture_types':missing,'types':counts,'operators':operators,'profiles':{'fm1':full,'compact':compact}}
    (ROOT/'evidence'/f'{args.prefix}-inventory.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('passed','fixture_count','ugen_count','operator_counts')}),flush=True)
    print('Compact accepted:',sum(r['loaded'] for r in compact),'/',len(compact),flush=True)
    if args.reference:passed=reference(args.prefix) and passed
    if args.fuzz:passed=fuzz(args.prefix) and passed
    return passed

if __name__=='__main__':raise SystemExit(0 if main() else 1)
