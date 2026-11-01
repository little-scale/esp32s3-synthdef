#!/usr/bin/env python3
"""Bit-exact native comparison of optimized kernels against the pinned baseline."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from engine_profile import ROOT,generate
from patches import compile_source

FIXTURES={
    'SineControl':r'{ |freq=220, phase=0| Out.ar(0, SinOsc.ar(freq,phase)!2) }',
    'SineAudio':r'{ |freq=220, phase=0| Out.ar(0, SinOsc.ar(SinOsc.ar(7).range(-1200,1200)+freq, SinOsc.ar(3)*phase)!2) }',
    'SineKR':r'{ |freq=5, phase=0| Out.ar(0, K2A.ar(SinOsc.kr(freq,phase))!2) }',
    'DustShared':r'{ |density=1| var a=WhiteNoise.ar; var b=Dust.ar(density); var c=Dust2.ar(density); Out.ar(0,[a*b+PinkNoise.ar(0.01),c+WhiteNoise.ar(0.01)]) }',
    'DustKR':r'{ |density=1| Out.ar(0, K2A.ar([Dust.kr(density),Dust2.kr(density)])) }',
    'Decay2Control':r'{ |attack=0.01,decay=2| Out.ar(0, Decay2.ar(Dust.ar(10),attack,decay)!2) }',
    'Decay2Modulated':r'{ |attack=0.01,decay=2| Out.ar(0, Decay2.ar(Dust.ar(10),attack, SinOsc.kr(0.1).range(0.01,2)+decay)!2) }',
    'Decay2KR':r'{ |attack=0.01,decay=2| Out.ar(0, K2A.ar(Decay2.kr(Dust.kr(10),attack,decay))!2) }',
    'DecaySingle':r'{ |decay=2| Out.ar(0, Decay.ar(Dust.ar(10),decay)!2) }',
}
def main():
    build=ROOT/'build/host/comb-kernel-test';build.mkdir(parents=True,exist_ok=True)
    target=generate(build/'optimized','fm1');reference=generate(build/'reference','fm1',optimize_kernels=False)
    destination=str(build).replace('\\','\\\\').replace('"','\\"')
    script=build/'fixtures.scd'
    script.write_text('(\n'+''.join(f'SynthDef(\\{name}, {expr}).writeDefFile("{destination}");\n' for name,expr in FIXTURES.items())+'0.exit;\n)\n')
    sclang=shutil.which('sclang') or '/Applications/SuperCollider.app/Contents/MacOS/sclang'
    compile_result=subprocess.run([sclang,'-D',str(script)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=60)
    (build/'compiler.log').write_text(compile_result.stdout)
    assert compile_result.returncode==0
    graphs=[build/(name+'.scsyndef') for name in FIXTURES]
    comb=build/'CombCloud.scsyndef'
    compile_source(ROOT/'examples/comb-cloud-efficient.scd',comb,sclang)
    graphs += [comb]
    graphs += [ROOT/'examples'/name for name in ('mac-sine.scsyndef','phase-fm.scsyndef','additive.scsyndef','filtered.scsyndef')]
    assert all(p.is_file() for p in graphs)
    definitions=(reference/'fm_render.c').read_text()+'\n'+(reference/'fm_delay.inc').read_text()
    names=sorted(set(re.findall(r'^(?:int|void|uint32_t) (fm_\w+)\(',definitions,re.M)))
    flags=['cc','-std=c99','-O1','-fno-fast-math','-ffp-contract=off','-fsanitize=undefined,bounds']
    objects=[]
    for name,src,include,extra in (
        ('reference',reference/'fm_render.c',reference,[f'-D{x}=fm_ref_{x[3:]}' for x in names]),
        ('optimized',target/'fm_render.c',target,[]),
        ('load',target/'fm_load.c',target,[]),
        ('test',ROOT/'tests/kernel_equivalence_test.c',target,[])):
        obj=build/(name+'.o');subprocess.run([*flags,'-I'+str(include),*extra,'-c',str(src),'-o',str(obj)],check=True);objects.append(str(obj))
    exe=build/'compare';subprocess.run([*flags,*objects,'-lm','-o',str(exe)],check=True)
    result=subprocess.run([str(exe),*[str(p) for p in graphs]],capture_output=True,text=True,timeout=90)
    (build/'result.txt').write_text(result.stdout+result.stderr)
    assert result.returncode==0,result.stdout+result.stderr
    report={'passed':True,'details':result.stdout.strip(),'rates':[8000,44100,48000,192000],'legacy_presets_rate':44100,
            'graphs':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in graphs},
            'kernel_files':{str(p.relative_to(build)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in (target,reference) for p in (folder/'fm_fast.inc',folder/'fm_extensions.inc')},
            'sanitizers':'undefined,bounds; local AddressSanitizer runtime deadlocks before main on this Mac',
            'hardware':False}
    (ROOT/'evidence/comb-kernel-equivalence.json').write_text(json.dumps(report,indent=2)+'\n');print(result.stdout.strip())
if __name__=='__main__':main()
