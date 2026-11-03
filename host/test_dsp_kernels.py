#!/usr/bin/env python3
"""Silent differential checks of exact filter/Lag/unary block specialisations."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
from engine_profile import ROOT,generate
from test_signal_reuse import graph

BUILD=ROOT/'build/host/dsp-kernels'


def fixtures():
 result={}
 for typ in ('Resonz','Ringz','LPF','HPF','RLPF','RHPF','BPF','BRF'):
  for rate in ('ar','kr'):
   args='freq' if typ in ('LPF','HPF') else 'freq,time' if typ=='Ringz' else 'freq,rq'
   expression=f'{typ}.{rate}(SinOsc.{rate}(110,0,0.01),{args})'
   result[f'{typ}_{rate}']=f'SynthDef(\\{typ}_{rate},{{|freq=440,rq=0.1,time=0.2|Out.ar(0,{"K2A.ar("+expression+")" if rate=="kr" else expression}!2)}})'
 # Audio-rate Ringz coefficient inputs retain SC's offset-zero sampling.
 result['Ringz_audio_parameters']=r'SynthDef(\Ringz_audio_parameters,{Out.ar(0,Ringz.ar(Impulse.ar(2),SinOsc.ar(0.1).range(100,2000),SinOsc.ar(0.2).range(0.01,2))!2)})'
 for typ in ('Lag','LagUD','LeakDC'):
  for rate in ('ar','kr'):
   args='lagUp,lagDown' if typ=='LagUD' else '0.99' if typ=='LeakDC' else 'lagUp'
   expression=f'{typ}.{rate}(SinOsc.{rate}(110,0,0.01),{args})'
   result[f'{typ}_{rate}']=f'SynthDef(\\{typ}_{rate},{{|lagUp=1,lagDown=0.5|Out.ar(0,{"K2A.ar("+expression+")" if rate=="kr" else expression}!2)}})'
 methods=['neg','abs','ceil','floor','frac','sign','squared','cubed','sqrt','exp','reciprocal','midicps','cpsmidi','midiratio','ratiomidi','dbamp','ampdb','octcps','cpsoct','log','log2','log10','sin','cos','tan','asin','acos','atan','sinh','cosh','tanh','distort','softclip']
 for method in methods:
  result['Unary_'+method]=f'SynthDef(\\Unary_{method},{{|x=0.1|var audio=SinOsc.ar(110,0,0.1);Out.ar(0,[audio.{method},K2A.ar(x.{method})])}})'
 return result


def main():
 BUILD.mkdir(parents=True,exist_ok=True)
 sources=fixtures();destination=str(BUILD)
 script=BUILD/'fixtures.scd';script.write_text('(\n'+''.join(s+'.writeDefFile('+json.dumps(destination)+');\n' for s in sources.values())+'0.exit;\n)')
 run=subprocess.run(['/Applications/SuperCollider.app/Contents/MacOS/sclang','-D',str(script)],capture_output=True,text=True,timeout=60)
 (BUILD/'compile.log').write_text(run.stdout+run.stderr);assert run.returncode==0,run.stdout+run.stderr
 paths=[BUILD/(name+'.scsyndef') for name in sources];assert all(p.is_file() for p in paths)
 # Force audio-output unary nodes with scalar inputs; normal sclang chooses
 # .kr here. The loader admits this form and the kernel must fill all 64 frames.
 for op in (0,5,*range(8,37),42,43):
  p=BUILD/f'Unary_scalar_ar_{op}.scsyndef'
  p.write_bytes(graph('ScalarUnary',[('In',1,[(-1,0)],1,0),('UnaryOpUGen',2,[(0,0)],1,op),('Out',2,[(-1,0),(1,0),(1,0)],0,0)],constants=(0,)))
  paths.append(p)
 # Lower-rate excitation is legal in the file even where sclang's convenience
 # constructors normally insert/restrict conversion. Exercise the scalar arm
 # of each audio kernel with changing bus snapshots and poisoned scratch.
 for typ in ('Resonz','Ringz','LPF','HPF','RLPF','RHPF','BPF','BRF','Lag','LagUD','LeakDC'):
  constants=(0,440,.1) if typ not in ('Lag','LagUD','LeakDC') else (0,1,.5)
  refs=[(0,0),(-1,1)]
  if typ in ('Resonz','Ringz','RLPF','RHPF','BPF','BRF','LagUD'):refs.append((-1,2))
  p=BUILD/f'{typ}_scalar_audio_input.scsyndef';p.write_bytes(graph('ScalarInput',[
   ('In',1,[(-1,0)],1,0),(typ,2,refs,1,0),('Out',2,[(-1,0),(1,0),(1,0)],0,0)],constants=constants));paths.append(p)
 target=generate(BUILD/'target','fm1');reference=generate(BUILD/'reference','fm1',optimize_filters=False,optimize_lag=False,optimize_unary=False,optimize_miverb_packed=False)
 text=(reference/'fm_render.c').read_text()+'\n'+(reference/'fm_delay.inc').read_text()
 names=sorted(set(re.findall(r'^(?:int|void|uint32_t) (fm_\w+)\(',text,re.M)))
 flags=['cc','-std=c99','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off','-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all']
 objects=[]
 for name,src,include,extra in [('reference',reference/'fm_render.c',reference,[f'-D{x}=dsp_ref_{x[3:]}' for x in names]),('target',target/'fm_render.c',target,[]),('load',target/'fm_load.c',target,[]),('test',ROOT/'tests/dsp_kernels_test.c',target,[])]:
  obj=BUILD/(name+'.o');r=subprocess.run([*flags,'-I'+str(include),*extra,'-c',str(src),'-o',str(obj)],capture_output=True,text=True);assert r.returncode==0,r.stderr;objects.append(str(obj))
 binary=BUILD/'compare';subprocess.run([*flags,*objects,'-lm','-o',str(binary)],check=True)
 r=subprocess.run([str(binary),*map(str,paths)],capture_output=True,text=True,timeout=120)
 (BUILD/'result.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr
 report=json.loads(r.stdout);report.update(hardware=False,rates=[8000,44100,48000,192000],sanitizers=['undefined','bounds','float-cast-overflow'],comparison='Byte-identical samples, recursive voice state, RNG, flags and delay arena. Only documented new otherwise-unused unary/Lag cache fields normalized.',kernel_source_sha256=hashlib.sha256((ROOT/'host/dsp_kernels.py').read_bytes()).hexdigest(),graphs={p.stem:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
 (ROOT/'evidence/dsp-kernels-host.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
