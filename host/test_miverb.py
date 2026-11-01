#!/usr/bin/env python3
"""Silent bit-exact MiVerb comparison, including the private write quantiser."""
import hashlib
import json
import re
import subprocess
from engine_profile import ROOT,generate
from patches import compile_source

BUILD=ROOT/'build/host/miverb-test'
FIXTURES={
 'Stereo':r'SynthDef(\MiStereo,{|freq=220,time=0.99,wet=1,damp=0.01,hp=0.05,freeze=0,diff=0.625,level=0.4|Out.ar(0,MiVerb.ar([SinOsc.ar(freq)*level,Dust.ar(3)*level],time,wet,damp,hp,freeze,diff))})',
 'Mono':r'SynthDef(\MiMono,{|time=0.99,wet=1,damp=0.01,hp=0.05,freeze=0,diff=0.625,level=0.4|Out.ar(0,MiVerb.ar(PinkNoise.ar(level),time,wet,damp,hp,freeze,diff))})',
 'Silence':r'SynthDef(\MiSilence,{|time=0.99,wet=1,damp=0.01,hp=0.05,freeze=0,diff=0.625|Out.ar(0,MiVerb.ar(DC.ar(0),time,wet,damp,hp,freeze,diff))})',
 'SawResonz':r'{|freq=220,dev=20|MiVerb.ar(Resonz.ar(Splay.ar(Saw.ar(freq+{Lag.kr(LFNoise2.kr(1,dev),1)}!2,0.1)),SinOsc.kr(0.1).range(110,1720),0.1,3),0.99,1,0.01)}.play',
}

def main():
 BUILD.mkdir(parents=True,exist_ok=True)
 target=generate(BUILD/'target','fm1');reference=generate(BUILD/'reference','fm1',optimize_miverb=False)
 assert (reference/'fm_miverb.inc').read_bytes()==(ROOT/'upstream/fm1-synthdef/synthdef-engine/src/fm_miverb.inc').read_bytes()
 paths=[]
 for name,source in FIXTURES.items():
  path=BUILD/(name+'.scsyndef');path.with_suffix('.scd').write_text(source)
  compile_source(path.with_suffix('.scd'),path,'/Applications/SuperCollider.app/Contents/MacOS/sclang');paths.append(path)
 text=(reference/'fm_render.c').read_text()+'\n'+(reference/'fm_delay.inc').read_text()
 names=sorted(set(re.findall(r'^(?:int|void|uint32_t) (fm_\w+)\(',text,re.M)))
 flags=['cc','-std=c99','-O2','-fno-fast-math','-ffp-contract=off','-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all']
 objects=[]
 for name,folder,extra in [('reference',reference,[*[f'-D{x}=fm_ref_{x[3:]}' for x in names],'-Dmiverb_probe=miverb_ref_probe']),('target',target,[])]:
  wrapper=folder/'test_render.c';wrapper.write_text('#include "fm_render.c"\n#include "miverb_clamp_probe.inc"\n')
  obj=folder/'render.o';result=subprocess.run([*flags,'-I'+str(folder),'-I'+str(ROOT/'tests'),*extra,'-c',str(wrapper),'-o',str(obj)],capture_output=True,text=True)
  assert result.returncode==0,result.stderr;objects.append(str(obj))
 exe=BUILD/'compare'
 subprocess.run([*flags,'-I'+str(target),*objects,str(target/'fm_load.c'),str(ROOT/'tests/miverb_equivalence_test.c'),'-lm','-o',str(exe)],check=True)
 result=subprocess.run([str(exe),*[str(p) for p in paths]],capture_output=True,text=True,timeout=90)
 assert result.returncode==0,result.stdout+result.stderr
 report=dict(json.loads(result.stdout),hardware=False,audio_playback=False,rates=[8000,44100,48000,192000],blocks_per_case=4096,
  compared_state='Full voice, random state, complete delay arena and audio output',sanitizers=['undefined','bounds','float-cast-overflow'],
  graphs={p.stem:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
  target_sha256=hashlib.sha256((target/'fm_miverb.inc').read_bytes()).hexdigest(),reference_sha256=hashlib.sha256((reference/'fm_miverb.inc').read_bytes()).hexdigest())
 (ROOT/'evidence/miverb-clamp-host.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
