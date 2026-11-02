#!/usr/bin/env python3
"""Check capture framing/bounds on a headless board without changing its patches.

Close Studio's USB connection first. This replaces the temporary capture buffer.
"""
import argparse
import hashlib
import json
import struct
import time
from pathlib import Path
from patches import Device

def check(device,benchmark=False):
    hello=device.hello();chunk=hello.get('pcm_capture_chunk')
    if hello.get('pcm_capture_id')!=1 or chunk!=1024:raise ValueError('Update the headless capture firmware first')
    def record(frames):
        started=device.request('CAPBEGIN',struct.pack('<I',frames),retries=0)
        deadline=time.monotonic()+3
        while True:
            info=device.request('CAPINFO',retries=0)
            if info['capture_id']!=started['capture_id']:raise RuntimeError('Capture replaced during protocol check')
            if info['state']==2:return started['capture_id'],info['bytes']
            if time.monotonic()>deadline:raise TimeoutError('Capture did not finish')
            time.sleep(.005)
    def rejected(payload):
        try:device.request('CAPREAD',payload,retries=0)
        except RuntimeError:return
        raise AssertionError('Invalid capture read was accepted')
    capture_id,total=record(1024)
    wire=lambda tag,offset,count:struct.pack('<IIH',tag,offset,count)
    full=device.request('CAPREAD',wire(capture_id,0,chunk),retries=0)
    assert full['capture_id']==capture_id and full['offset']==0 and len(bytes.fromhex(full['data']))==chunk
    legacy=device.request('CAPREAD',struct.pack('<IH',0,256),retries=0)
    assert legacy['data']==full['data'][:512]
    for payload in (wire(capture_id,0,chunk+1),wire(capture_id,0,0),wire(capture_id,total,1),
                    wire(capture_id,0xffffffff,1),wire(capture_id^1,0,1),b'\0'*5):rejected(payload)
    assert device.request('CAPREAD',wire(capture_id,0,chunk),retries=0)['data']==full['data']
    replacement,_=record(128);assert replacement!=capture_id
    rejected(wire(capture_id,0,1))
    assert device.request('CAPREAD',wire(replacement,0,1),retries=0)['capture_id']==replacement
    assert not device.request('STATUS')['reset_required']
    report=dict(passed=True,build=hello['build'],device_id=hello['device_id'],chunk_bytes=chunk,
                legacy_reads=True,invalid_reads_rejected=7,replaced_recording_rejected=True)
    if benchmark:
        capture_id,total=record(44100);timings=[];reference=None
        for size in (256,chunk):
            output=bytearray();requests=0;started=time.monotonic()
            while len(output)<total:
                offset=len(output);count=min(size,total-offset)
                response=device.request('CAPREAD',wire(capture_id,offset,count),retries=0)
                data=bytes.fromhex(response['data'])
                assert response['capture_id']==capture_id and response['offset']==offset and len(data)==count
                output.extend(data);requests+=1
            timings.append(dict(chunk_bytes=size,requests=requests,seconds=round(time.monotonic()-started,3)))
            if reference is None:reference=bytes(output)
            else:assert bytes(output)==reference
        report.update(read_benchmark=timings,identical_pcm=True,pcm_sha256=hashlib.sha256(reference).hexdigest())
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',required=True)
    parser.add_argument('--benchmark',action='store_true',help='Also compare 256/1024-byte downloads of the same frozen one-second PCM')
    parser.add_argument('--report',type=Path,default=Path('build/host/capture-protocol.json'))
    args=parser.parse_args();device=Device(args.port)
    try:report=check(device,args.benchmark)
    finally:device.close()
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
