"""Hash binding, transfer failures and scheduler timing without a device."""
import hashlib
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import Mock
from patches import ROOT
from pattern_program import compile_pattern,HEADER,NODE,PatternError
from program_transport import upload_program
from engine_profile import generate

def pattern(*pairs):return dict(op='Pbind',args=list(pairs))
def op(name,*args):return dict(op=name,args=list(args))

class ProgramTransport(unittest.TestCase):
 def setUp(self):
  self.raw,_=compile_pattern(pattern('freq',440),'12'*32)
  self.calls=[];self.body=bytearray()
  def request(name,payload=b''):
   self.calls.append(name)
   if name=='STATUS':return dict(graph_sha256='12'*32)
   if name=='PBEGIN':return dict(received=0)
   if name=='PDATA':self.body.extend(payload[8:]);return dict(received=len(self.body))
   if name=='PCOMMIT':return dict(sha256=hashlib.sha256(self.body).hexdigest())
   if name=='PSAVE':return dict(saved=True)
   if name=='PPLAY':return dict(running=True)
   if name=='PINFO':return dict(loaded=True,bound=True,sha256=hashlib.sha256(self.body).hexdigest())
   if name=='PABORT':return dict(aborted=True)
   raise AssertionError(name)
  self.d=Mock();self.d.hello.return_value=dict(pattern_programs=1);self.d.request.side_effect=request
 def test_verified_transaction(self):
  self.assertTrue(upload_program(self.d,self.raw)['verified'])
  self.assertEqual(bytes(self.body),self.raw)
  self.assertEqual(self.calls[-4:],['PCOMMIT','PSAVE','PPLAY','PINFO'])
 def test_capability_before_mutation(self):
  self.d.hello.return_value={}
  with self.assertRaises(ValueError):upload_program(self.d,self.raw)
  self.assertFalse(self.calls)
 def test_graph_mismatch_before_begin(self):
  self.d.request.side_effect=lambda *_:dict(graph_sha256='34'*32)
  with self.assertRaisesRegex(ValueError,'Main changed'):upload_program(self.d,self.raw)
  self.assertEqual(self.d.request.call_count,1)
 def test_failed_data_aborts_and_never_saves(self):
  original=self.d.request.side_effect
  def request(name,*args):
   if name=='PDATA':self.calls.append(name);return dict(received=999)
   return original(name,*args)
  self.d.request.side_effect=request
  with self.assertRaisesRegex(ValueError,'offset'):upload_program(self.d,self.raw)
  self.assertEqual(self.calls[-1],'PABORT');self.assertNotIn('PSAVE',self.calls)

class ProgramScheduler(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.folder=ROOT/'build/host/pattern-player';cls.folder.mkdir(parents=True,exist_ok=True)
  engine=generate(cls.folder/'engine','fm1')
  cls.binary=cls.folder/'player'
  subprocess.run(['cc','-std=c99','-O2','-Wall','-Wextra','-Werror',
   '-fno-fast-math','-ffp-contract=off','-fsanitize=undefined,bounds,float-cast-overflow',
   '-fno-sanitize-recover=all','-I'+str(engine),
   '-I'+str(ROOT/'firmware/components/instrument/include'),
   str(ROOT/'firmware/components/instrument/pattern_vm.c'),
   str(ROOT/'firmware/components/instrument/pattern_player.c'),
   str(ROOT/'tests/pattern_player_test.c'),'-lm','-o',str(cls.binary)],check=True)
 def run_case(self,name,tree):
  raw,_=compile_pattern(tree,'12'*32,tempo=2)
  path=self.folder/(name+'.espp');path.write_bytes(raw)
  r=subprocess.run([str(self.binary),str(path),name],capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stderr)
 def test_notes(self):self.run_case('notes',pattern('degree',op('Pseq',[0,2,4]),'dur',.25))
 def test_rest(self):self.run_case('rest',pattern('dur',op('Pseq',[op('rest',.25),.25])))
 def test_set(self):self.run_case('set',pattern('type','set','freq',550))
 def test_late(self):self.run_case('late',pattern('freq',440))
 def test_unknown(self):self.run_case('unknown',pattern('foo',440))
 def test_invalid_values(self):
  for tree in (pattern('dur',0),pattern('dur',.0001),pattern('degree',op('Infinity')),pattern('sustain',1000)):
   with self.subTest(tree=tree):self.run_case('fault',tree)

if __name__=='__main__':unittest.main()
