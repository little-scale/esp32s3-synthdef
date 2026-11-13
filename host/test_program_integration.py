"""Compile real SC program bundles and verify the new bridge/API contract."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock
from studio import Artifact,Compiler,Problem,Studio
from patches import ROOT
from patches import compile_source
from ide_bridge import Bridge

SCLANG=Path('/Applications/SuperCollider.app/Contents/MacOS/sclang')
SOURCE=(ROOT/'examples/standalone-pattern.scd').read_text()

class ProgramIntegration(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.compiler=Compiler(SCLANG)
 def test_combined_source_and_graph_binding(self):
  graph,source,info=self.compiler.compile(dict(source=SOURCE))
  self.assertTrue(info['admitted']);self.assertTrue(info['definition'])
  self.assertEqual(info['input_kind'],'program');self.assertEqual(source,SOURCE.encode())
  self.assertEqual(info['program']['graph_sha256'],info['graph_sha256'])
  self.assertIn('gate',[c['name'] for c in info['controls']])
 def test_plain_source_without_installed_esp32_classes(self):
  with tempfile.TemporaryDirectory() as folder:
   folder=Path(folder);config=folder/'language.yaml'
   installed=Path.home()/'Library/Application Support/SuperCollider/Extensions/ESP32Studio'
   config.write_text(json.dumps(dict(includePaths=[],excludePaths=[str(installed),str(ROOT/'supercollider')],postInlineWarnings=False)))
   wrapper=folder/'sclang';wrapper.write_text('#!/bin/sh\nexec "'+str(SCLANG)+'" -l "'+str(config)+'" "$@"\n');wrapper.chmod(0o700)
   source=folder/'source.scd';source.write_text('{SinOsc.ar(220,0,0.01)!2}')
   result=compile_source(source,folder/'graph.scsyndef',wrapper)
   self.assertIsNone(result['program']);self.assertGreater(result['bytes'],0)
 def test_unknown_control_rejected_before_upload(self):
  with self.assertRaisesRegex(Problem,'not writable Main controls'):
   self.compiler.compile(dict(source=SOURCE.replace(r'\degree,',r'\unknownControl,')))
 def test_fx_bundle_is_rejected(self):
  with self.assertRaisesRegex(RuntimeError,'Main'):
   self.compiler.compile(dict(source=SOURCE,target='master'))
 def test_program_api_is_bound_to_selected_device(self):
  studio=Studio(SCLANG);device=studio.device=Mock()
  studio.device_info=dict(device_id='esp32-000000000001',pattern_programs=1)
  studio.state=Mock(return_value=dict(connected=True))
  with self.assertRaises(Problem):studio.pattern_command(dict(device_id='esp32-000000000002',command='stop'))
  device.request.assert_not_called()
  studio.pattern_command(dict(device_id='esp32-000000000001',command='stop'))
  device.request.assert_called_once_with('PSTOP')
 def test_older_firmware_is_rejected_before_main_write(self):
  graph,source,info=self.compiler.compile(dict(source=SOURCE))
  studio=Studio(SCLANG);device=studio.device=Mock();studio.device_info=dict(device_id='esp32-000000000001')
  studio.artifacts['program']=Artifact(graph,source,info)
  with self.assertRaisesRegex(Problem,'before uploading Main'):
   studio.upload(dict(artifact='program',slot=1,name='Test',device_id=studio.device_info['device_id']))
  device.request.assert_not_called();device.upload.assert_not_called()
 def test_real_sc_program_methods_and_source_roundtrip(self):
  with tempfile.TemporaryDirectory() as folder:
   folder=Path(folder);studio=Studio(SCLANG);bridge=Bridge(studio,'pattern-contract',config=folder/'connection.json')
   calls=[];original=bridge.hub.dispatch
   def dispatch(action,p,source,graph,*args):
    if action in ('program','pattern'):
     calls.append((action,p,source,graph));return dict(verified=True,results=[])
    return original(action,p,source,graph,*args)
   bridge.hub.dispatch=dispatch
   script=folder/'test.scd';roundtrip=folder/'roundtrip.scd'
   script.write_text(r'''
Routine({
 var program;
 try {
  ESP32.connect(%CONFIG%).wait;
  program=ESP32Program({arg freq=440,amp=0.1,gate=0;
   SinOsc.ar(freq)*EnvGen.kr(Env.asr,gate)*amp},
   Pbind(\degree,Pseq([0,2,4],inf),\dur,0.25),tempo:2,seed:123);
  File.use(%SOURCE%,"w",{|f|f.write(program.source)});
  program.sendESP32(\all).wait;
  ESP32.programInfo(\all).wait;
  ESP32.programStop(\all).wait;
  ESP32.programPlay(\all).wait;
  ESP32.disconnect;0.exit;
 } {|error|error.reportError;1.exit}
}).play(SystemClock);
'''.replace('%CONFIG%',json.dumps(str(folder/'connection.json'))).replace('%SOURCE%',json.dumps(str(roundtrip))))
   try:
    run=subprocess.run([str(SCLANG),'-D',str(script)],capture_output=True,text=True,timeout=40)
    self.assertEqual(run.returncode,0,run.stdout+run.stderr)
    self.assertEqual([c[0] for c in calls],['program','pattern','pattern','pattern'])
    _,payload,source,graph=calls[0]
    self.assertEqual(payload['target'],'all');self.assertEqual(payload['tempo'],2)
    self.assertEqual(payload['seed'],123);self.assertTrue(graph.startswith(b'SCgf'))
    self.assertIn('ESP32Program',source)
    _,_,info=self.compiler.compile(dict(source=roundtrip.read_text()))
    self.assertTrue(info['admitted']);self.assertIn('program',info)
   finally:bridge.server_close();studio.close()

if __name__=='__main__':unittest.main()
