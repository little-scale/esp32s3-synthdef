"""Admission failures, malformed binaries and bounded pathological streams."""
from pathlib import Path
import struct
import subprocess
import unittest
from pattern_program import compile_pattern,PatternError,HEADER,NODE
from test_pattern_program import build,BUILD

def op(name,*args):return dict(op=name,args=list(args))
def bind(*args):return op('Pbind',*args)

class PatternBounds(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.binary=build()
 def execute(self,raw):
  path=BUILD/'invalid.espp';path.write_bytes(raw)
  return subprocess.run([str(self.binary),str(path),'8'],capture_output=True,text=True,timeout=10)
 def test_host_rejects_unsupported_structure(self):
  bad=[op('Pfunc',1),bind('freq',None),bind('a',1,'a',2),bind('module','all'),op('Pseq',[1,2]),
       bind('a',op('Pseq',[])),bind('a',op('Pbinop','+',1,2,'x'))]
  for tree in bad:
   with self.subTest(tree=tree),self.assertRaises(PatternError):compile_pattern(tree,'12'*32)
 def test_nesting_and_graph_limits(self):
  tree=1
  for _ in range(26):tree=op('Pn',tree,1)
  with self.assertRaisesRegex(PatternError,'nesting'):compile_pattern(bind('a',tree),'12'*32)
  tree=bind(*[x for i in range(32) for x in ('a'+str(i),op('Pseq',list(range(20)),1))])
  with self.assertRaises(PatternError):compile_pattern(tree,'12'*32)
 def test_binary_rejection(self):
  good,_=compile_pattern(bind('freq',440),'12'*32)
  samples=[b'',good[:-1],good+b'x',b'bad!'+good[4:]]
  for offset,value in ((4,99),(60,255),(61,10),(64,255),(66,1)):
   raw=bytearray(good);raw[offset]=value;samples.append(raw)
  for raw in samples:
   with self.subTest(raw=raw[:12]):self.assertEqual(self.execute(raw).returncode,3)
 def test_empty_infinite_stream_stops_with_budget_error(self):
  raw,_=compile_pattern(op('Pn',op('Pfin',0,bind('freq',440)),op('Infinity')),'12'*32)
  result=self.execute(raw);self.assertEqual(result.returncode,4);self.assertIn('budget',result.stderr)
 def test_seed_is_repeatable_and_xrand_does_not_repeat(self):
  raw,_=compile_pattern(bind('freq',op('Pxrand',[220,330,440],100)),'12'*32,seed=111)
  first=self.execute(raw);second=self.execute(raw)
  self.assertEqual(first.returncode,0);self.assertEqual(first.stdout,second.stdout)
  import json
  items=[e['freq'] for e in json.loads(first.stdout)['events']]
  self.assertTrue(all(a!=b for a,b in zip(items,items[1:])))
 def test_random_domains_and_weighted_distribution(self):
  import json
  cases=[
   (op('Pwhite',-4,4,10000),-4,4,True),
   (op('Pexprand',.1,20.,10000),.1,20.,False),
   (op('Pbrown',-5,5,1,10000),-5,5,True),
   (op('Pgbrown',.1,10.,.2,10000),.1,10.,False),
   (op('Pwrand',[0,1,2],[.1,.2,.7],10000),0,2,True)]
  for tree,lo,hi,integer in cases:
   with self.subTest(op=tree['op']):
    raw,_=compile_pattern(bind('a',tree),'12'*32,seed=991)
    path=BUILD/'domains.espp';path.write_bytes(raw)
    result=subprocess.run([str(self.binary),str(path),'10000'],capture_output=True,text=True,timeout=10)
    self.assertEqual(result.returncode,0,result.stderr)
    items=[event['a'] for event in json.loads(result.stdout)['events']]
    self.assertEqual(len(items),10000)
    self.assertTrue(all(lo<=x<=hi and (not integer or int(x)==x) for x in items))
    if tree['op']=='Pbrown':self.assertTrue(all(abs(x-y)<=1 for x,y in zip(items,items[1:])))
    if tree['op']=='Pwrand':
     for value,expected in enumerate((1000,2000,7000)):
      self.assertLess(abs(items.count(value)-expected),400)
 def test_mutated_binary_fuzz(self):
  raw,_=compile_pattern(bind('freq',op('Pseq',[220,330,440],op('Infinity'))),'12'*32)
  path=BUILD/'fuzz.espp';path.write_bytes(raw)
  r=subprocess.run([str(self.binary),str(path),'8','fuzz'],capture_output=True,text=True,timeout=30)
  self.assertEqual(r.returncode,0,r.stderr)

if __name__=='__main__':unittest.main()
