#!/usr/bin/env python3
"""Verify saved catalog bytes, numerical output and a short final-image exercise.

--install stores qualified examples in empty slots, reusing only byte-identical
existing entries. All work shares one USB connection and finishes on Mac Sine.
"""
import argparse
import json
from pathlib import Path
import re
from patches import Device,ROOT,manifest
from profile_timing import compile_renderer,collect_matrix
from exercise_timing import collect_exercise

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--install',action='store_true')
    p.add_argument('--diagnostic',action='store_true',help='Test unsaved candidates; never writes library slots')
    p.add_argument('--rounds',type=int,choices=range(1,11),default=1);args=p.parse_args()
    assert not (args.install and args.diagnostic)
    report={'passed':False,'status':'incomplete','patches':[]}
    args.output.write_text(json.dumps(report,indent=2)+'\n');renderer=compile_renderer()
    entries=json.loads((ROOT/'examples/catalog.json').read_text())
    assert all(e['status'] in (('candidate','qualified') if args.diagnostic else ('qualified',)) for e in entries)
    with args.output.with_suffix('.log').open('wb') as log:
        d=Device(args.port,log)
        try:
            hello=d.hello();report['hello']=hello
            assert hello['build']==re.search(r'#define BUILD_ID "(.*?)"',(ROOT/'firmware/main/generated.h').read_text())[1]
            inventory=d.request('LIST');report['before_library']=inventory;slots={}
            if not args.diagnostic:
                # Match complete existing entries before reserving any empty slots.
                for entry in entries:
                    name=entry['id'];graph=(ROOT/f'examples/{name}.scsyndef').read_bytes();source=(ROOT/f'examples/{name}.scd').read_bytes()
                    _,expected=manifest(graph,source,entry['name'],entry['labels'],entry['mapping'])
                    for item in inventory:
                        if item['slot'] and item['name']==entry['name']:
                            d.request('LOAD',bytes([item['slot']]))
                            a,b,info=d.download()
                            if a==graph and b==source and bytes.fromhex(info['manifest'])[76:]==expected[76:]:
                                slots[name]=item['slot'];break
                empty=[s['slot'] for s in inventory if s['slot'] and not s['name'] and not any(s['generations'])]
                missing=[e for e in entries if e['id'] not in slots]
                if missing and not args.install:raise RuntimeError('Examples are missing; use --install to add them in empty slots')
                if len(empty)<len(missing):raise RuntimeError('Not enough empty slots; existing patches were retained')
                for entry in missing:
                    slot=entry['slot'] if entry['slot'] in empty else empty[0];empty.remove(slot)
                    d.install_catalog(entry['id']);d.request('SAVE',bytes([slot]));slots[entry['id']]=slot
                report['slots']=slots
                for entry in entries:
                    name=entry['id'];d.request('LOAD',bytes([slots[name]]));a,b,info=d.download()
                    graph=(ROOT/f'examples/{name}.scsyndef').read_bytes();source=(ROOT/f'examples/{name}.scd').read_bytes()
                    _,expected=manifest(graph,source,entry['name'],entry['labels'],entry['mapping'])
                    assert a==graph and b==source and bytes.fromhex(info['manifest'])[76:]==expected[76:]
                report['saved_graph_source_metadata_readback']=True
            d.request('LOAD',b'\1');before=d.request('STATUS')
            changed=bytearray((ROOT/'examples/phase-fm.scsyndef').read_bytes());changed[11]^=1
            try:d.upload(bytes(changed),b'// Changed graph name; valid parser input, different SHA\n')
            except RuntimeError as error:
                assert 'outside upload policy' in str(error) or 'simple-voice-v1' in str(error)
                report['changed_catalog_rejection']=str(error)
            else:raise AssertionError('A changed catalog graph was admitted')
            assert d.request('STATUS')['graph_sha256']==before['graph_sha256']
            ordered=sorted(entries,key=lambda e:e['id']!='filtered') if args.diagnostic else entries
            cases=[(0,'touch-sine',False)]+[(None if args.diagnostic else slots[e['id']],e['id'],True) for e in ordered]+[(1,'mac-sine',True)]
            for slot,name,live in cases:
                if slot is None:active=d.install_catalog(name,diagnostic=True)
                else:d.request('LOAD',bytes([slot]));active=d.request('STATUS')
                numerical=collect_matrix(d,active,ROOT/f'examples/{name}.scsyndef',name,renderer)
                result={'patch':name,'slot':slot,'matrix':numerical}
                if live:
                    offset=log.tell()
                    result['exercise']=collect_exercise(d,args.output.with_suffix('.log'),hello,active,1 if name=='mac-sine' else args.rounds,offset)
                report['patches'].append(result)
                if args.diagnostic and name in {e['id'] for e in entries}:
                    (ROOT/f'evidence/{name}-matrix.json').write_text(json.dumps({'checks_passed':True,'hello':hello,'reports':[numerical]},indent=2)+'\n')
                    (ROOT/f'evidence/{name}-exercise.json').write_text(json.dumps(result['exercise'],indent=2)+'\n')
                args.output.write_text(json.dumps(report,indent=2)+'\n')
                if live:assert result['exercise']['reported_output_checks_passed'] and result['exercise']['timing_budget_passed']
                print('Verified '+name,flush=True)
            d.request('PANIC');d.request('LOAD',b'\1')
            report['final_status']=d.request('STATUS');report['library']=d.request('LIST')
            report['passed']=True;report['status']='complete'
            args.output.write_text(json.dumps(report,indent=2)+'\n')
        finally:
            try:d.link.write(b'x');d.request('PANIC');d.request('LOAD',b'\1')
            finally:d.link.write(b'!');d.close()

if __name__=='__main__':main()
