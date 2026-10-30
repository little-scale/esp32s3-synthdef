#!/usr/bin/env python3
"""Compile real LVGL/widgets on host, exercise touch flow and save previews."""
import binascii
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import zlib
ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/'build/host/ui'
BUILD.mkdir(parents=True,exist_ok=True)
lvgl=ROOT/'firmware/managed_components/lvgl__lvgl'
component=ROOT/'firmware/components/ui'
binary=BUILD/'ui-preview'
flags=['-std=c99','-O1','-DLV_CONF_SKIP','-DLV_MEM_CUSTOM=0','-DLV_MEM_SIZE=65536','-DLV_COLOR_DEPTH=16',
       '-DLV_COLOR_16_SWAP=1','-DLV_FONT_MONTSERRAT_22=1','-DLV_USE_SNAPSHOT=1',
       '-DLV_DISP_DEF_REFR_PERIOD=40','-DLV_THEME_DEFAULT_GROW=0','-DLV_THEME_DEFAULT_TRANSITION_TIME=0']
includes=[ROOT/'tests/ui_stubs',lvgl,component/'include',ROOT/'firmware/components/instrument/include',
          ROOT/'upstream/fm1-synthdef/synthdef-engine/src']
sources=[component/'touch_ui.c',ROOT/'tests/ui_preview.c',*sorted((lvgl/'src').rglob('*.c'))]
fingerprint=hashlib.sha256((''.join(str(p)+hashlib.sha256(p.read_bytes()).hexdigest() for p in
                         sources+sorted((ROOT/'tests/ui_stubs').rglob('*.h')))+str(flags)).encode()).hexdigest()
stamp=BUILD/'source.sha256'
if not binary.exists() or not stamp.exists() or stamp.read_text()!=fingerprint:
    subprocess.run(['cc',*flags,*['-I'+str(p) for p in includes],*[str(p) for p in sources],
                    '-lm','-o',str(binary)],check=True)
    stamp.write_text(fingerprint)
idle,playing,library=BUILD/'idle.rgb565',BUILD/'playing.rgb565',BUILD/'library.rgb565'
result=subprocess.run([str(binary),str(idle),str(playing),str(library)],capture_output=True,text=True,check=True)
print(result.stdout.strip())
def png(raw,path):
    assert len(raw)==368*448*2
    rows=[]
    for y in range(448):
        row=bytearray([0])
        for x in range(368):
            pixel=int.from_bytes(raw[(y*368+x)*2:(y*368+x)*2+2],'big')
            row.extend((((pixel>>11)&31)*255//31,((pixel>>5)&63)*255//63,(pixel&31)*255//31))
        rows.append(row)
    def chunk(tag,data):
        return struct.pack('>I',len(data))+tag+data+struct.pack('>I',binascii.crc32(tag+data)&0xffffffff)
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',368,448,8,2,0,0,0))+
                     chunk(b'IDAT',zlib.compress(b''.join(rows)))+chunk(b'IEND',b''))
for name,file in [('idle',idle),('playing',playing),('library',library)]: png(file.read_bytes(),ROOT/f'evidence/ui-{name}-preview.png')
report={'test':'real LVGL host simulation','passed':True,'details':result.stdout.strip(),
        'source_sha256':fingerprint,'hardware':False,'dimensions':[368,448]}
(ROOT/'evidence/ui-host.json').write_text(json.dumps(report,indent=2)+'\n')
