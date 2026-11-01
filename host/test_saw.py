#!/usr/bin/env python3
"""Silent Saw/Pulse comparison at harmonic boundaries and changing widths."""
import hashlib
import json
import re
import subprocess
from engine_profile import ROOT,generate
from patches import compile_source

BUILD=ROOT/'build/host/saw-test'
FIXTURES={
 'Saw':r'SynthDef(\SawCase,{|freq=220|Out.ar(0,Saw.ar(freq)!2)})',
 'SawMod':r'SynthDef(\SawModCase,{Out.ar(0,Saw.ar(SinOsc.kr(3).range(0.01,0.2)*SampleRate.ir)!2)})',
 'Pulse':r'SynthDef(\PulseCase,{|freq=220,width=0.5|Out.ar(0,Pulse.ar(freq,width)!2)})',
 'PulseMod':r'SynthDef(\PulseModCase,{Out.ar(0,Pulse.ar(SinOsc.kr(3).range(0.01,0.2)*SampleRate.ir,SinOsc.kr(7).range(0,1))!2)})',
 'Blip':r'SynthDef(\BlipCase,{|freq=220,harmonics=20|Out.ar(0,Blip.ar(freq,harmonics)!2)})',
}

def main():
 BUILD.mkdir(parents=True,exist_ok=True)
 target=generate(BUILD/'target','fm1');reference=generate(BUILD/'reference','fm1',optimize_saw=False)
 assert (reference/'fm_bandlimited.inc').read_bytes()==(ROOT/'upstream/fm1-synthdef/synthdef-engine/src/fm_bandlimited.inc').read_bytes()
 paths=[]
 for name,source in FIXTURES.items():
  path=BUILD/(name+'.scsyndef');path.with_suffix('.scd').write_text(source)
  compile_source(path.with_suffix('.scd'),path,'/Applications/SuperCollider.app/Contents/MacOS/sclang');paths.append(path)
 text=(reference/'fm_render.c').read_text()+'\n'+(reference/'fm_delay.inc').read_text()
 names=sorted(set(re.findall(r'^(?:int|void|uint32_t) (fm_\w+)\(',text,re.M)))
 flags=['cc','-std=c99','-O2','-fno-fast-math','-ffp-contract=off','-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all']
 objects=[]
 for name,folder,extra in [('reference',reference,[f'-D{x}=fm_ref_{x[3:]}' for x in names]),('target',target,[])]:
  obj=folder/'render.o';result=subprocess.run([*flags,'-I'+str(folder),*extra,'-c',str(folder/'fm_render.c'),'-o',str(obj)],capture_output=True,text=True)
  assert result.returncode==0,result.stderr;objects.append(str(obj))
 exe=BUILD/'compare';subprocess.run([*flags,'-I'+str(target),*objects,str(target/'fm_load.c'),str(ROOT/'tests/saw_equivalence_test.c'),'-lm','-o',str(exe)],check=True)
 result=subprocess.run([str(exe),*[str(p) for p in paths]],capture_output=True,text=True,timeout=90);assert result.returncode==0,result.stdout+result.stderr
 report=dict(json.loads(result.stdout),hardware=False,audio_playback=False,rates=[8000,44100,48000,192000],blocks_per_case=8192,
  compared='Audio and complete voice/random state',sanitizers=['undefined','bounds','float-cast-overflow'],
  graphs={p.stem:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
  target_sha256=hashlib.sha256((target/'fm_bandlimited.inc').read_bytes()).hexdigest(),reference_sha256=hashlib.sha256((reference/'fm_bandlimited.inc').read_bytes()).hexdigest())
 (ROOT/'evidence/saw-crossfade-host.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
