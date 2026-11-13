#!/usr/bin/env python3
"""Silent native VM versus real sclang streams, plus binary/admission probes."""
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import unittest

from patches import ROOT
from pattern_program import compile_pattern,PatternError,UNARY,BINARY

BUILD=ROOT/'build/host/pattern-program'
CASES={
 'nested':r'Pbind(\a,Pseq([Pseq([1,2],2),3],2,1),\dur,0.25)',
 'concat':r'Pbind(\a,Pseq([1,2],2) ++ Pseq([3,4],1),\dur,0.25)',
 'ser_nested':r'Pbind(\a,Pser([Pseq([1,2],2),3],3,1))',
 'repeat_scalar':r'Pbind(\a,Pn(7,3))',
 'repeat_pattern':r'Pbind(\a,Pn(Pseq([1,2],2),3))',
 'series':r'Pbind(\a,Pseries(5,Pseq([1,2,3],1),10))',
 'geom':r'Pbind(\a,Pgeom(2,Pseq([2,3,4],1),10))',
 'stutter':r'Pbind(\a,Pdup(Pseq([1,3,2],1),Pseq([4,5,6],1)))',
 'zero_stutter':r'Pbind(\a,Pdup(Pseq([0,0,-2,1],1),Pseq([4,5,6,7],1)))',
 'event_stutter':r'Pdup(2,Pbind(\a,Pseq([1,2,3],1),\dur,0.25))',
 'fin':r'Pfin(3,Pbind(\a,Pseries(1,1,inf)))',
 'drop':r'Pdrop(3,Pbind(\a,Pseq([1,2,3,4,5],1)))',
 'drop_event_keys':r'Pdrop(1,Pseq([Pbind(\a,Pseq([1],1)),Pbind(\b,Pseq([2],1))],1))',
 'key':r'Pbind(\a,Pseries(1,1,8),\b,Pkey(\a)*2,\dur,0.25)',
 'unary':r'Pbind(\a,Pseq([60,72,48],1).midicps)',
 'array_unary':r'Pbind(\a,Pseq([[60,64,67],[62,65,69]],1).midicps)',
 'array_binary':r'Pbind(\a,Pseq([[1,2,3],[4,5,6]],1)*Pseq([[10,20],[30,40]],1))',
 'chain':r'Pbind(\b,Pkey(\a)*3) <> Pbind(\a,Pseq([1,2,3],1))',
 'bindf':r'Pbindf(Pbind(\a,Pseq([1,2,3],1)),\b,Pkey(\a)*2,\dur,0.25)',
 'tuple':r'Pbind(\a,Ptuple([Pseq([1,2,3],1),Pseries(4,1,3)],2))',
 'switch':r'Pbind(\a,Pswitch([Pseq([1,2],1),Pseq([3,4,5],1)],Pseq([0,1,0],1)))',
 'switch1':r'Pbind(\a,Pswitch1([Pseq([1,2],1),Pseq([3,4,5],1)],Pseq([0,1,0,1,1],1)))',
 'rest':r'Pbind(\a,Pseq([1,2,3],1),\dur,Pseq([0.25,Rest(0.5),0.25],1))',
 'rand_nested_single':r'Pbind(\a,Prand([Pseq([1,2],1)],3))',
 'xrand_single':r'Pbind(\a,Pxrand([7],3))',
 'shuf_repeats':r'Pbind(\a,Pshuf([7,7,7],2))',
 'wrand_nested':r'Pbind(\a,Pwrand([Pseq([1,2],1),9],[1,0],3))',
 'white_constant':r'Pbind(\a,Pwhite(0.5,0.5,4))',
 'exprand_constant':r'Pbind(\a,Pexprand(2.0,2.0,4))',
 'brown_constant_stream':r'Pbind(\a,Pbrown(Pseq([0.5,0.5,0.5,0.5],1),0.5,0.1,10))',
 'gbrown_constant_stream':r'Pbind(\a,Pgbrown(Pseq([0.5,0.5,0.5,0.5],1),0.5,0.1,10))',
 'seed_finite_child':r'Pbind(\a,Pseed(Pseq([1,2],1),Pseq([7,8],1)))',
 'time':r'Pbind(\a,Ptime(4),\dur,0.25)',
 'bj_bits':r'Pbind(\a,Pbjorklund(3,8,2))',
 'bj_durations':r'Pbind(\dur,Pbjorklund2(3,8,2)/4)',
 'bj_dynamic':r'Pbind(\a,Pbjorklund(Pseq([3,5,2],1),8,3,-2))',
 'bj2_dynamic':r'Pbind(\dur,Pbjorklund2(Pseq([3,5,2],1),Pseq([8,13,7],1),3,1)/4)',
}
for pulses,steps in ((0,1),(1,1),(0,8),(8,8),(1,32),(31,32),(11,32),(5,13)):
 CASES['bj_edge_'+str(pulses)+'_'+str(steps)]=r'Pbind(\a,Pbjorklund(%d,%d,2,-31))'%(pulses,steps)
 if pulses:
  CASES['bj2_edge_'+str(pulses)+'_'+str(steps)]=r'Pbind(\dur,Pbjorklund2(%d,%d,2,31)/4)'%(pulses,steps)
for name in UNARY:
 CASES['operator_unary_'+name]=r'Pbind(\a,Punop(%s.asSymbol,Pseq([0.25,1.0,2.0],1)))'%json.dumps(name)
for name in BINARY:
 CASES['operator_binary_'+name]=r'Pbind(\a,Pbinop(%s.asSymbol,Pseq([-2.0,0.25,1.0,3.0],1),2.0))'%json.dumps(name)


def build():
 BUILD.mkdir(parents=True,exist_ok=True)
 binary=BUILD/'vm'
 subprocess.run(['cc','-std=c99','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off',
  '-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all',
  '-I'+str(ROOT/'firmware/components/instrument/include'),str(ROOT/'firmware/components/instrument/pattern_vm.c'),
  str(ROOT/'tests/pattern_vm_test.c'),'-lm','-o',str(binary)],check=True)
 return binary


def main():
 binary=build();script=BUILD/'oracle.scd';output=BUILD/'oracle.json'
 expressions=',\n'.join('['+json.dumps(name)+', '+source+']' for name,source in CASES.items())
 script.write_text(r'''(
var cases=[%CASES%],rows,clean;
clean={|value|
 if(value.isKindOf(Rest)){value.value}{
 if(value.isKindOf(Dictionary)){var result=Dictionary.new;value.keysValuesDo{|k,v|result[k]=clean.value(v)};result}{
 if(value.isArray){value.collect(clean)}{value}}}
};
try {
 rows=cases.collect{|item|
  var stream=item[1].asStream,events=List.new,value,beat=0;
  64.do{var step;thisThread.beats=beat;value=stream.next(());
   if(value.notNil){events.add(clean.value(value));step=value[\delta] ? value[\dur] ? 1;
    if(step.isKindOf(Rest)){step=step.value};beat=beat+step}};
  (name:item[0],tree:ESP32Pattern.tree(item[1]),events:events.asArray)
 };
 File.use(%OUT%,"w",{|f|f.write(ESP32.json(rows))});0.exit;
} {|error|error.reportError;1.exit};
)
'''.replace('%CASES%',expressions).replace('%OUT%',json.dumps(str(output))))
 run=subprocess.run(['/Applications/SuperCollider.app/Contents/MacOS/sclang','-D',str(script)],capture_output=True,text=True,timeout=90)
 (BUILD/'oracle.log').write_text(run.stdout+run.stderr)
 if run.returncode or not output.exists():raise RuntimeError('SC pattern oracle failed; inspect '+str(BUILD/'oracle.log'))
 rows=json.loads(output.read_text());report=dict(passed=False,hardware=False,audio_playback=False,cases=[])
 try:
  for row in rows:
   path=BUILD/(hashlib.sha256(row['name'].encode()).hexdigest()[:16]+'.espp');raw,info=compile_pattern(row['tree'],'00'*32);path.write_bytes(raw)
   result=subprocess.run([str(binary),str(path),'64'],capture_output=True,text=True,timeout=10)
   if result.returncode:raise AssertionError(row['name']+': '+result.stderr)
   actual=json.loads(result.stdout)
   def same(a,b):
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):return math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-12)
    if isinstance(a,list) and isinstance(b,list):return len(a)==len(b) and all(same(x,y) for x,y in zip(a,b))
    if isinstance(a,dict) and isinstance(b,dict):return a.keys()==b.keys() and all(same(a[k],b[k]) for k in a)
    return a==b
   if not same(actual['events'],row['events']):
    raise AssertionError(row['name']+':\nexpected '+str(row['events'])+'\nactual '+str(actual['events']))
   report['cases'].append(dict(name=row['name'],events=len(actual['events']),vm_bytes=actual['vm_bytes'],steps=actual['steps'],pattern_sha256=info['pattern_sha256'],absolute_tolerance=1e-12,relative_tolerance=1e-12))
   print('PASS',row['name'],len(actual['events']),'events',flush=True)
  report['passed']=True
 finally:
  report['source_sha256']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in ('host/pattern_program.py','firmware/components/instrument/pattern_vm.c','firmware/components/instrument/include/pattern_vm.h','supercollider/ESP32Pattern.sc','host/test_pattern_program.py')}
  (ROOT/'evidence/pattern-program-host.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
