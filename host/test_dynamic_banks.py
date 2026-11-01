#!/usr/bin/env python3
"""Silent DynKlang/DynKlank integration checks against SuperCollider NRT output."""
import argparse
import array
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
from engine_profile import ROOT,generate
from patches import compile_source
from synthdef_binary import decode,encode

BLOCKS=4096
BUILD=ROOT/'build/host/dynamic-banks'
SCLANG=Path('/Applications/SuperCollider.app/Contents/MacOS/sclang')
SCSYNTH=Path('/Applications/SuperCollider.app/Contents/Resources/scsynth')

def string(s):
    b=s.encode()+b'\0';return b+b'\0'*((-len(b))%4)
def message(address,*args):
    tags=',';data=b''
    for a in args:
        if isinstance(a,str):tags+='s';data+=string(a)
        elif isinstance(a,bytes):tags+='b';data+=struct.pack('>I',len(a))+a+b'\0'*((-len(a))%4)
        elif isinstance(a,int):tags+='i';data+=struct.pack('>i',a)
        else:tags+='f';data+=struct.pack('>f',a)
    return string(address)+string(tags)+data
def wave_data(path):
    data=path.read_bytes();pos=12
    while pos+8<=len(data):
        tag,n=struct.unpack_from('<4sI',data,pos);pos+=8
        if tag==b'data':return data[pos:pos+n]
        pos+=n+(n%2)
    raise AssertionError('Missing WAV data')
def reference(graph,path):
    name=decode(graph)['name'];score=path.with_suffix('.osc')
    events=[(0,[message('/g_new',1,0,0),message('/d_recv',graph),message('/s_new',name,1000,1,1)]),
            (BLOCKS,[message('/n_free',1000)]),(BLOCKS+1,[message('/c_set',0,0)])]
    packets=[]
    for block,msgs in events:
        packet=b'#bundle\0'+struct.pack('>Q',round(block*64/44100*2**32))+b''.join(struct.pack('>I',len(m))+m for m in msgs)
        packets.append(struct.pack('>I',len(packet))+packet)
    score.write_bytes(b''.join(packets))
    r=subprocess.run([str(SCSYNTH),'-U',str(SCSYNTH.parent/'plugins'),'-N',str(score),'_',str(path),'44100','WAV','float','-o','2','-i','0','-z','64'],capture_output=True,text=True,timeout=30)
    path.with_suffix('.sc.log').write_text(r.stdout+r.stderr)
    assert r.returncode==0 and 'ERROR' not in r.stdout+r.stderr,r.stdout+r.stderr
    values=array.array('f');values.frombytes(wave_data(path));return values[:BLOCKS*128]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'evidence/dynamic-banks-host.json');args=p.parse_args()
    BUILD.mkdir(parents=True,exist_ok=True);engine=generate(BUILD/'src','fm1')
    inst=ROOT/'firmware/components/instrument';patches=ROOT/'firmware/components/patches';exe=BUILD/'render'
    flags=['-std=c99','-O2','-fno-fast-math','-ffp-contract=off','-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all','-DPATCH_FM1_COMPAT=1']
    subprocess.run(['cc',*flags,'-I'+str(engine),'-I'+str(inst/'include'),'-I'+str(patches/'include'),str(engine/'fm_load.c'),str(engine/'fm_render.c'),str(patches/'patch_format.c'),str(ROOT/'tests/dynamic_bank_test.c'),'-lm','-o',str(exe)],check=True)
    report={'passed':False,'hardware':False,'audio_playback':False,'frames_per_case':BLOCKS*64,'cases':[]}
    cases=json.loads((ROOT/'tests/dynamic_bank_cases.json').read_text())
    for name,source in cases.items():
        row={'name':name};path=BUILD/(name+'.scsyndef');scd=path.with_suffix('.scd');scd.write_text(source)
        try:
            compile_source(scd,path,SCLANG);raw=path.read_bytes();g=decode(raw)
            types=[n[0] for n in g['nodes']];assert 'DynKlang' not in types and 'DynKlank' not in types
            kernel='Ringz' if name.startswith('DynKlank') else 'SinOsc';assert types.count(kernel)>=3
            expected=reference(raw,path.with_suffix('.wav'))
            result=subprocess.run([str(exe),str(path),str(path.with_suffix('.f32')),str(BLOCKS)],capture_output=True,text=True,timeout=30)
            if result.returncode:raise AssertionError(result.stderr or result.stdout)
            actual=array.array('f');actual.frombytes(path.with_suffix('.f32').read_bytes())
            assert len(actual)==len(expected)==BLOCKS*128 and all(math.isfinite(x) for x in actual)
            peak=max(abs(x-y) for x,y in zip(actual,expected));rms=math.sqrt(sum((x-y)**2 for x,y in zip(actual,expected))/len(actual))
            row.update(native=json.loads(result.stdout),types=sorted(set(types)),kernel=kernel,kernel_count=types.count(kernel),graph_sha256=hashlib.sha256(raw).hexdigest(),peak_error=peak,rms_error=rms,peak_limit=2e-4,rms_limit=3e-5,passed=peak<=2e-4 and rms<=3e-5)
        except Exception as e:row.update(passed=False,error=str(e))
        report['cases'].append(row);print(json.dumps(row),flush=True)
        args.output.write_text(json.dumps(report,indent=2)+'\n')
    report['rejections']=[]
    for name,base,mutate in (
        ('audio_excitation_into_control_ringz','DynKlank_kr_audio_parameters',True),
        ('audio_coefficients_into_resonz','DynKlank_audio_parameters',False)):
        g=decode((BUILD/(base+'.scsyndef')).read_bytes());index=next(i for i,n in enumerate(g['nodes']) if n[0]=='Ringz')
        typ,rate,refs,outputs,special=g['nodes'][index];refs=list(refs)
        if mutate:
            source=next(i for i,n in enumerate(g['nodes'][:index]) if n[1]==2)
            refs[0]=(source,0)
        else:typ='Resonz'
        g['nodes'][index]=(typ,rate,refs,outputs,special);path=BUILD/(name+'.scsyndef');path.write_bytes(encode(g))
        r=subprocess.run([str(exe),str(path),str(path.with_suffix('.f32')),'1'],capture_output=True,text=True,timeout=10)
        expected='Input rate exceeds' if mutate else 'require control or initial'
        report['rejections'].append(dict(name=name,passed=r.returncode!=0 and expected in r.stderr,error=r.stderr.strip()))
    report['passed']=all(r['passed'] for r in report['cases']+report['rejections']);args.output.write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if report['passed'] else 1)
if __name__=='__main__':main()
