#!/usr/bin/env python3
"""Capture post-volume stereo PCM from a headless node; never starts a synth."""
import argparse
import base64
import http.client
import json
import struct
import time
import wave
from pathlib import Path
from patches import Device,ROOT

def capture(device,seconds=1.0):
    hello=device.hello()
    if hello.get('pcm_capture')!=1:raise ValueError('This firmware does not support PCM capture')
    chunk=hello.get('pcm_capture_chunk',256)
    if type(chunk) is not int or not 1<=chunk<=1024:raise ValueError('Unsupported capture chunk limit')
    if not 0<seconds<=1:raise ValueError('Capture duration must be greater than zero and at most one second')
    rate=hello['rate'];frames=round(rate*seconds)
    if not frames:raise ValueError('Capture duration is shorter than one frame')
    started=device.request('CAPBEGIN',struct.pack('<I',frames),retries=0)
    capture_id=started.get('capture_id') if hello.get('pcm_capture_id')==1 else None
    if hello.get('pcm_capture_id')==1 and (type(capture_id) is not int or not 0<capture_id<=0xffffffff):raise ValueError('Invalid capture identifier')
    deadline=time.monotonic()+seconds+5
    while True:
        info=device.request('CAPINFO',timeout=2,retries=0)
        if capture_id is not None and info.get('capture_id')!=capture_id:raise ValueError('Capture was replaced while recording')
        if info['state']==2:break
        if time.monotonic()>deadline:raise TimeoutError('Audio capture did not finish; inspect audio status')
        time.sleep(.05)
    if (info['frames'],info['requested'],info['rate'],info['channels'],info['bytes'])!=(frames,frames,rate,2,frames*4):raise ValueError('Unexpected capture format or length')
    pcm=bytearray()
    while len(pcm)<info['bytes']:
        offset=len(pcm);count=min(chunk,info['bytes']-offset)
        wire=struct.pack('<IH',offset,count)
        if capture_id is not None:wire=struct.pack('<I',capture_id)+wire
        # An identified recording makes this read idempotent. Resend the same
        # request once if its reply is lost; never re-arm CAPBEGIN, and still
        # reject a capture replaced while downloading. Untagged legacy devices
        # retain their single-attempt behavior.
        result=device.request('CAPREAD',wire,timeout=3,retries=1 if capture_id is not None else 0)
        if capture_id is not None and result.get('capture_id')!=capture_id:raise ValueError('Capture was replaced while downloading')
        data=bytes.fromhex(result['data'])
        if result['offset']!=offset or len(data)!=count:raise ValueError('Capture read offset/length mismatch')
        pcm.extend(data)
        # Let pending control transactions acquire the shared USB connection.
        time.sleep(0)
    return bytes(pcm),info

def save_wav(path,pcm,rate):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(path),'wb') as output:
        output.setnchannels(2);output.setsampwidth(2);output.setframerate(rate);output.writeframes(pcm)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    connection=p.add_mutually_exclusive_group(required=True)
    connection.add_argument('--port');connection.add_argument('--module')
    connection.add_argument('--studio',action='store_true',help='Use the device already connected in Studio; shares its USB connection')
    p.add_argument('--studio-port',type=int,default=8765)
    p.add_argument('--seconds',type=float,default=1)
    p.add_argument('--output',type=Path,default=Path('build/host/headless-capture.wav'))
    args=p.parse_args()
    if args.studio:
        session=json.loads((ROOT/'build/host/private/studio-client.json').read_text())
        client=http.client.HTTPConnection('127.0.0.1',args.studio_port,timeout=30)
        try:
            client.request('POST','/api/capture',json.dumps(dict(seconds=args.seconds)),headers={'Content-Type':'application/json','X-Studio-Token':session['token']})
            response=client.getresponse();result=json.loads(response.read(400000))
            if response.status!=200:raise SystemExit(result.get('error','Capture failed'))
            pcm=base64.b64decode(result['data'],validate=True)
            if result['format']!='s16le' or result['channels']!=2 or len(pcm)!=result['frames']*4:raise SystemExit('Unexpected capture format')
            save_wav(args.output,pcm,result['rate']);print(f'Saved {result["frames"]} stereo frames to {args.output}')
        finally:client.close()
        raise SystemExit(0)
    if args.module:
        from network import Pairings,NetworkDevice,discover
        pairings=Pairings();pairing=pairings.get(args.module)
        row=next((row for row in discover(pairings) if row['device_id']==args.module and row.get('online')),None)
        if row is None:raise SystemExit('The paired module is not currently reachable')
        device=NetworkDevice(row,pairing)
    else:device=Device(args.port)
    try:
        pcm,info=capture(device,args.seconds);save_wav(args.output,pcm,info['rate'])
        print(f'Saved {info["frames"]} stereo frames at {info["rate"]} Hz to {args.output}')
    finally:device.close()
