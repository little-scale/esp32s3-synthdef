#!/usr/bin/env python3
"""Decode the device's complete RGB565 snapshot without image dependencies."""
import argparse
import binascii
from pathlib import Path
import re
import struct
import zlib
parser=argparse.ArgumentParser()
parser.add_argument('log',type=Path)
parser.add_argument('--output',type=Path,default=Path('evidence/ui-device.png'))
args=parser.parse_args()
text=args.log.read_text(errors='replace')
assert 'SCREEN_END' in text, 'Incomplete screen capture'
match=re.search(r'SCREEN_BEGIN width=(\d+) height=(\d+) bytes=(\d+) big_endian=(\d+)',text)
assert match
width,height,size,big=map(int,match.groups())
assert size==width*height*2 and width<=1024 and height<=1024
chunks=re.findall(r'SCREEN_DATA (\d+) ([0-9a-f]+)',text)
raw=bytearray()
for offset,data in chunks:
    assert int(offset)==len(raw), 'Missing/duplicate screen data'
    raw.extend(bytes.fromhex(data))
assert len(raw)==size
rows=[]
for y in range(height):
    row=bytearray([0])
    for x in range(width):
        i=(y*width+x)*2; pixel=int.from_bytes(raw[i:i+2],'big' if big else 'little')
        row.extend((((pixel>>11)&31)*255//31,((pixel>>5)&63)*255//63,(pixel&31)*255//31))
    rows.append(row)
def chunk(tag,data):
    return struct.pack('>I',len(data))+tag+data+struct.pack('>I',binascii.crc32(tag+data)&0xffffffff)
args.output.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+
                       chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b''))
print(f'Decoded actual device screen: {width} x {height}, {args.output}')
