#!/usr/bin/env python3
"""Collect the explicitly muted, audio-owner diagnostic control matrix."""
import argparse
import json
from pathlib import Path
import re
import time
import struct
import subprocess
import zlib
from prepare import ENGINE, FLAGS
from patches import Device, ROOT

def compile_renderer():
    renderer=ROOT/'build/host/render-matrix'
    subprocess.run(['cc',*FLAGS,'-I'+str(ENGINE/'src'),'-I'+str(ROOT/'firmware/components/instrument/include'),
                    str(ENGINE/'src/fm_load.c'),str(ENGINE/'src/fm_render.c'),
                    str(ROOT/'firmware/components/instrument/instrument.c'),str(ROOT/'tests/render_matrix.c'),
                    '-lm','-o',str(renderer)],check=True)
    return renderer

def collect_matrix(d,active,patch,slot,renderer):
    d.link.write(b'b')
    lines=[];end=False;until=time.monotonic()+30
    while time.monotonic()<until and not end:
        for line in d.lines():
            line=line.rstrip(b'\r')
            if line.startswith(b'BENCH_'):lines.append(line.decode())
            if line==b'BENCH_END':end=True;break
    assert end,lines[-3:]
    header=dict(re.findall(r'(\w+)=(\d+)',lines[0]))
    assert header['failures']=='0' and header['cases']=='280' and len(lines)==2*int(header['cases'])+2
    cases=[{k:float(v) for k,v in re.findall(r'(\w+)=([\d.]+)',line)} for line in lines if line.startswith('BENCH_CASE ')]
    samples=[]
    for line in lines:
        if not line.startswith('BENCH_PCM '):continue
        _,index,checksum,hexdata=line.split();raw=bytes.fromhex(hexdata)
        assert int(index)==len(samples) and len(raw)==384 and zlib.crc32(raw)==int(checksum,16)
        samples.append(raw)
    assert len(samples)==int(header['cases'])
    actual=b''.join(samples);reference=ROOT/f'build/host/matrix-{slot}.pcm'
    subprocess.run([str(renderer),str(patch),str(reference)],check=True)
    a=struct.unpack('<'+str(len(actual)//2)+'h',actual);b=struct.unpack('<'+str(len(actual)//2)+'h',reference.read_bytes())
    peak=max(abs(x-y) for x,y in zip(a,b));assert peak<=1,peak
    return {'slot':slot,'active':active,'header':header,'cases':cases,'worst':max(cases,key=lambda case:case['total']),
                    'numerical':{'samples':len(a),'max_pcm_step_error':peak,'limit_pcm_steps':1,'passed':True}}

def compile_delay_renderer():
    exe=ROOT/'build/host/delay-matrix'
    subprocess.run(['cc',*FLAGS,'-I'+str(ENGINE/'src'),'-I'+str(ROOT/'firmware/components/instrument/include'),
                    str(ENGINE/'src/fm_load.c'),str(ENGINE/'src/fm_render.c'),
                    str(ROOT/'firmware/components/instrument/master_delay.c'),str(ROOT/'tests/delay_matrix.c'),
                    '-lm','-o',str(exe)],check=True)
    return exe

def collect_delay_matrix(d,renderer):
    reference=ROOT/'build/host/delay-matrix-final.f32'
    subprocess.run([str(renderer),str(ROOT/'examples/master-delay.scsyndef'),str(reference)],check=True)
    d.link.write(b'e');lines=[];end=False;until=time.monotonic()+35
    while time.monotonic()<until and not end:
        for raw in d.lines():
            line=raw.rstrip(b'\r')
            if line.startswith(b'DELAY_BENCH_'):lines.append(line.decode())
            if line==b'DELAY_BENCH_END':end=True;break
    assert end and len(lines)==6,lines[-2:]
    header=dict(re.findall(r'(\w+)=(\d+)',lines[0]));assert header['failures']=='0' and header['cases']=='4'
    actual=b''
    for i,line in enumerate(lines[1:-1]):
        _,index,checksum,hexdata=line.split();raw=bytes.fromhex(hexdata)
        assert int(index)==i and len(raw)==1024 and zlib.crc32(raw)==int(checksum,16);actual+=raw
    a=struct.unpack('<1024f',actual);b=struct.unpack('<1024f',reference.read_bytes())
    peak=max(abs(x-y) for x,y in zip(a,b));assert peak<=1e-6,peak
    return {'passed':True,'max_float_error':peak,'limit':1e-6,'samples':1024,'times':[.02,.35,1,5]}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--catalog-entry',help='Test one unsaved catalog entry, then restore Mac Sine')
    args=parser.parse_args()
    args.output.write_text(json.dumps({'checks_passed':False,'status':'incomplete'})+'\n')
    renderer=compile_renderer()
    with args.output.with_suffix('.log').open('wb') as log:
        d=Device(args.port,log)
        try:
            hello=d.hello();reports=[]
            expected=re.search(r'#define BUILD_ID "(.*?)"',(ROOT/'firmware/main/generated.h').read_text())[1]
            assert hello['build']==expected
            for slot in ([args.catalog_entry] if args.catalog_entry else [0,1]):
                if isinstance(slot,str):
                    active=d.install_catalog(slot,diagnostic=True)
                    patch=ROOT/f'examples/{slot}.scsyndef'
                else:
                    d.request('LOAD',bytes([slot]));active=d.request('STATUS')
                    patch=ROOT/('examples/touch-sine.scsyndef' if slot==0 else 'examples/mac-sine.scsyndef')
                reports.append(collect_matrix(d,active,patch,slot,renderer))
            d.request('LOAD',b'\1')
            args.output.write_text(json.dumps({'checks_passed':True,'hello':hello,'scope':'offline matrix on parked audio owner; no DAC output; not a realtime guarantee','reports':reports},indent=2)+'\n')
            print(json.dumps([{'slot':r['slot'],'math':r['header'],'worst':r['worst']} for r in reports],indent=2))
        finally:
            try:d.request('PANIC');d.request('LOAD',b'\1')
            finally:d.link.write(b'!');d.close()

if __name__=="__main__":main()
