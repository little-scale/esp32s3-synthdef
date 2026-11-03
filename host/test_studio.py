#!/usr/bin/env python3
"""Local compiler, authoritative graph checks, HTTP boundaries and slot transactions.

Real SuperCollider runs silently; USB behavior is faked here. Separate browser and
device evidence records the physical readback test.
"""
import base64
import copy
import http.client
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import threading
import unittest

from patches import ROOT, compile_source, manifest
from studio import Artifact, AudioTelemetry, Compiler, Problem, Server, Studio, text_bytes
from source_input import expression
from engine_profile import generate

SCLANG = '/Applications/SuperCollider.app/Contents/MacOS/sclang'
SOURCE = (ROOT/'examples/touch-buses.scd').read_bytes()
GRAPH = (ROOT/'examples/TouchBuses.scsyndef').read_bytes()


class CompilerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = Compiler(SCLANG)

    def test_real_compile_preserves_source_and_matches_example(self):
        graph, source, info = self.compiler.compile({'source': SOURCE.decode()})
        self.assertEqual(graph, GRAPH)
        self.assertEqual(source, SOURCE)
        self.assertTrue(info['fm1_admitted'])
        self.assertTrue(info['touch_buses'])
        self.assertEqual(info['source_pairing'], 'compiled_from_source')
        self.assertEqual(info['name'], 'TouchBuses')
        added = SOURCE.decode().rstrip()[:-1]+'.add;'
        graph, source, _ = self.compiler.compile({'source': added})
        self.assertEqual(graph, GRAPH); self.assertEqual(source, added.encode())

    def test_binary_import_does_not_claim_source_pairing(self):
        graph, source, info = self.compiler.compile({'graph': base64.b64encode(GRAPH).decode()})
        self.assertEqual(graph, GRAPH); self.assertEqual(source, b'')
        self.assertEqual(info['source_pairing'], 'binary_without_source')
        _, source, info = self.compiler.compile({'graph': base64.b64encode(GRAPH).decode(), 'source': '// attached'})
        self.assertEqual(source, b'// attached')
        self.assertEqual(info['source_pairing'], 'attached_source_not_recompiled')

    def test_bad_graphs_are_rejected_by_native_loader(self):
        for raw in (b'garbage', GRAPH[:-1], GRAPH.replace(b'SinOsc', b'FooOsc')):
            with self.subTest(raw=raw[:12]), self.assertRaisesRegex(Problem, 'Unsupported or invalid'):
                self.compiler.compile({'graph': base64.b64encode(raw).decode()})

    def test_bounds_and_invalid_encoding(self):
        for source in ('x'*65537, '\0', '\ud800'):
            with self.assertRaises(Problem): text_bytes(source)
        for payload in ({'graph': 'not base64!'}, {'graph': 'A'*87385}, {'source': ''}):
            with self.assertRaises(Problem): self.compiler.compile(payload)

    def test_real_syntax_error(self):
        with self.assertRaisesRegex(RuntimeError, 'compilation failed'):
            self.compiler.compile({'source': 'SynthDef(\\broken, { var = ; });'})

    def test_early_exit_does_not_reuse_or_replace_old_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source, output = Path(folder)/'source.scd', Path(folder)/'old.scsyndef'
            source.write_text('0.exit;'); output.write_bytes(GRAPH)
            with self.assertRaisesRegex(RuntimeError, 'compilation failed'):
                compile_source(source, output, Path(SCLANG))
            self.assertEqual(output.read_bytes(), GRAPH)

    def test_compile_can_succeed_while_instrument_admission_fails(self):
        _, _, info = self.compiler.compile({'source': 'SynthDef(\\noGate, { Out.ar(0, SinOsc.ar(440)) });'})
        self.assertFalse(info['fm1_admitted'])
        self.assertIn('Missing live control', info['admission_error'])

    def test_dynamic_banks_compile_to_supported_kernels(self):
        cases=json.loads((ROOT/'tests/dynamic_bank_cases.json').read_text())
        for name in ('DynKlank_ar','DynKlang_ar','DynKlank_kr_audio_parameters','DynKlang_kr_audio_parameters'):
            with self.subTest(name=name):
                graph,source,info=self.compiler.compile({'source':cases[name]})
                self.assertTrue(info['fm1_admitted']);self.assertTrue(info['continuous'])
                self.assertEqual(source,cases[name].encode())
                self.assertIn('Ringz' if name.startswith('DynKlank') else 'SinOsc',info['ugens'])
                self.assertNotIn('DynKlank',info['ugens']);self.assertNotIn('DynKlang',info['ugens'])

    def test_user_sound_block_compiles_and_preserves_original(self):
        original = (ROOT/'examples/sound-block.scd').read_text()
        graph, source, info = self.compiler.compile({'source': original})
        self.assertEqual(source, original.encode()); self.assertTrue(info['fm1_admitted'])
        self.assertFalse(info['touch_buses']); self.assertTrue(info['continuous']); self.assertEqual(info['input_kind'], 'sound_block')
        self.assertEqual(info['name'], 'SoundBlock')
        build = ROOT/'build/host/studio-block-test'; build.mkdir(parents=True, exist_ok=True)
        path = build/'sound-block.scsyndef'; path.write_bytes(graph)
        engine = generate(build/'src', 'fm1'); instrument = ROOT/'firmware/components/instrument'
        patches = ROOT/'firmware/components/patches'; binary = build/'test'
        subprocess.run(['cc','-std=c99','-O2','-fno-fast-math','-ffp-contract=off',
            '-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all',
            '-DPATCH_FM1_COMPAT=1','-I'+str(engine),'-I'+str(instrument/'include'),'-I'+str(patches/'include'),
            str(engine/'fm_load.c'),str(engine/'fm_render.c'),str(instrument/'instrument.c'),
            str(patches/'patch_format.c'),str(ROOT/'tests/sound_block_test.c'),'-lm','-o',str(binary)],check=True)
        result = subprocess.run([str(binary),str(path)],capture_output=True,text=True,check=True)
        (build/'result.txt').write_text(result.stdout)

    def test_bare_and_parenthesized_play_forms(self):
        for source in ('{ SinOsc.ar(220)*0.1 }', '({ SinOsc.ar(220)*0.1 }.play)',
                       '({ SinOsc.ar(220)*0.1 }).play(); // end'):
            with self.subTest(source=source):
                _, raw, info = self.compiler.compile({'source': source})
                self.assertEqual(raw, source.encode()); self.assertTrue(info['fm1_admitted'])

    def test_sound_block_rejects_internal_outputs_and_too_many_channels(self):
        for source in ('{ Out.ar(0,SinOsc.ar(220)) }.play', '{ SinOsc.ar([220,330,440]) }'):
            with self.subTest(source=source), self.assertRaisesRegex(RuntimeError, 'Sound block must return'):
                self.compiler.compile({'source': source})

    def test_play_detection_ignores_comments_literals_and_characters(self):
        source = '''/* outer /* nested */ end */ ( { var text="}.play"; var c=$}; SinOsc.ar(220) } /* .play */ .play; )'''
        kind, bare = expression(source)
        self.assertEqual(kind, 'sound_block'); self.assertTrue(bare.endswith('}'))
        _, _, info = self.compiler.compile({'source': source})
        self.assertTrue(info['fm1_admitted'])

    def test_nontrailing_play_is_not_executed(self):
        for source in ('{ SinOsc.ar(220) }.play(s)', '({ SinOsc.ar(220) }.play; 0.exit)',
                       'var sound={SinOsc.ar(220)}; sound.play;', '{ {SinOsc.ar(220)}.play }'):
            with self.subTest(source=source), self.assertRaises(ValueError): expression(source)

    def test_master_target_and_native_audio_routing(self):
        source='{ In.ar(0,2)*0.5 }.play'
        graph, raw, info=self.compiler.compile({'source':source,'target':'master'})
        self.assertTrue(info['admitted']);self.assertTrue(info['master_admitted']);self.assertFalse(info['continuous'])
        self.assertEqual(raw,source.encode())
        build=ROOT/'build/host/studio-master-test';build.mkdir(parents=True,exist_ok=True)
        gain=build/'gain.scsyndef';gain.write_bytes(graph);engine=generate(build/'src','fm1')
        instrument=ROOT/'firmware/components/instrument';patches=ROOT/'firmware/components/patches';binary=build/'test'
        subprocess.run(['cc','-std=c99','-O2','-fno-fast-math','-ffp-contract=off','-DPATCH_FM1_COMPAT=1',
            '-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all',
            '-I'+str(engine),'-I'+str(instrument/'include'),'-I'+str(patches/'include'),
            str(engine/'fm_load.c'),str(engine/'fm_render.c'),str(instrument/'master_delay.c'),
            str(patches/'patch_format.c'),str(ROOT/'tests/master_effect_test.c'),'-lm','-o',str(binary)],check=True)
        run=subprocess.run([str(binary),str(ROOT/'examples/master-bypass.scsyndef'),str(gain)],capture_output=True,text=True,check=True)
        (build/'result.txt').write_text(run.stdout)

    def test_master_rejects_a_sound_generator_without_audio_input(self):
        _,_,info=self.compiler.compile({'source':'{SinOsc.ar(220)}.play','target':'master'})
        self.assertFalse(info['admitted']);self.assertIn('In.ar',info['admission_error'])


class FakeDevice:
    def __init__(self):
        self.slots = [{'slot': i, 'name': 'Factory' if i == 0 else '',
                       'generations': [0, 0]} for i in range(2)]
        self.calls, self.uploads, self.list_count = [], 0, 0
        self.changed = self.corrupt = self.fail_save = False
        self.slot = 1
        self.graph, self.source = GRAPH, SOURCE
        self.meta = manifest(GRAPH, SOURCE, 'Test', transfer=42)[1]

    def request(self, op, payload=b''):
        self.calls.append(op)
        if op == 'STATUS': return dict(reset_required=False, slot=self.slot, transfer=42)
        if op == 'LIST':
            self.list_count += 1
            if self.changed and self.list_count == 2:
                self.slots[1]['generations'] = [9, 0]
            return copy.deepcopy(self.slots)
        if op == 'SAVE':
            if self.fail_save: raise RuntimeError('Storage write failed')
            self.slot = payload[0]; self.slots[self.slot]['name'] = 'Test'
        if op == 'LOAD': self.slot = payload[0]
        return {}

    def upload(self, graph, source, name, labels, mapping, activate):
        assert not activate
        self.uploads += 1; self.graph, self.source = graph, source
        self.meta = manifest(graph, source, name, labels, mapping, transfer=42)[1]
        return dict(transfer=42)

    def download(self):
        return self.graph, b'wrong' if self.corrupt else self.source, dict(slot=self.slot, manifest=self.meta.hex())

    def close(self): pass


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.app = Studio(SCLANG); self.d = self.app.device = FakeDevice()
        self.app.device_info = dict(policy='fm1-compat-v1'); self.app.device_port = 'fake'
        self.app.artifacts['test'] = Artifact(GRAPH, SOURCE, dict(fm1_admitted=True))

    def payload(self, slot=1):
        return dict(artifact='test', slot=slot, expected=copy.deepcopy(self.d.slots[slot]), name='Test')

    def test_save_and_full_readback(self):
        result = self.app.upload(self.payload())
        self.assertTrue(result['verified']); self.assertEqual(result['slot'], 1)
        self.assertLess(self.d.calls.index('ACTIVATE'), self.d.calls.index('SAVE'))
        self.assertIn('PANIC', self.d.calls)

    def test_factory_and_invalid_slots_never_transfer(self):
        for slot in (0, 2, 8, 9, -1, True, '1', None):
            with self.assertRaises(Problem): self.app.upload(dict(self.payload(), slot=slot))
        self.assertEqual(self.d.uploads, 0)

    def test_occupied_requires_explicit_replace(self):
        self.d.slots[1]['name']='Existing'; payload = self.payload(1)
        with self.assertRaisesRegex(Problem, 'occupied'): self.app.upload(payload)
        self.assertEqual(self.d.uploads, 0)
        self.assertTrue(self.app.upload(dict(payload, replace=True))['verified'])

    def test_stale_destination_never_transfers(self):
        payload = self.payload(); self.d.slots[1]['name'] = 'Someone else'
        with self.assertRaisesRegex(Problem, 'slot changed'): self.app.upload(payload)
        self.assertEqual(self.d.uploads, 0)

    def test_slot_change_during_staging_aborts_before_activation(self):
        self.d.changed = True
        with self.assertRaisesRegex(Problem, 'slot changed'): self.app.upload(self.payload())
        self.assertIn('ABORT', self.d.calls); self.assertNotIn('ACTIVATE', self.d.calls)

    def test_failed_save_and_readback_report_phase(self):
        self.d.fail_save = True
        with self.assertRaises(Problem) as caught: self.app.upload(self.payload())
        self.assertEqual(caught.exception.details['phase'], 'saving')
        self.d.fail_save = False; self.d.corrupt = True
        with self.assertRaises(Problem) as caught: self.app.upload(self.payload())
        self.assertEqual(caught.exception.details['phase'], 'verifying')

    def test_unknown_artifact_never_transfers(self):
        with self.assertRaises(Problem): self.app.upload(dict(self.payload(), artifact='expired'))
        self.assertEqual(self.d.uploads, 0)

    def test_continuous_upload_does_not_stop_the_new_program(self):
        self.app.device_info['continuous_blocks'] = True
        self.app.artifacts['test'] = Artifact(GRAPH, SOURCE, dict(fm1_admitted=True, continuous=True))
        self.assertTrue(self.app.upload(self.payload())['continuous'])
        self.assertNotIn('PANIC', self.d.calls)

    def test_continuous_upload_rejects_old_firmware_before_transfer(self):
        self.app.artifacts['test'] = Artifact(GRAPH, SOURCE, dict(fm1_admitted=True, continuous=True))
        with self.assertRaisesRegex(Problem, 'continuous playback support'): self.app.upload(self.payload())
        self.assertEqual(self.d.uploads, 0)

    def test_read_active_keeps_selection_and_metadata(self):
        patch = self.app.read_active()
        self.assertEqual(patch['slot'], 1); self.assertEqual(patch['source'], SOURCE.decode())
        self.assertEqual(patch['name'], 'Test'); self.assertNotIn('LOAD', self.d.calls)

    def test_read_saved_slot_loads_and_stops_before_readback(self):
        patch = self.app.read_active(1)
        self.assertEqual(patch['slot'], 1); self.assertEqual(self.d.calls, ['LOAD', 'STATUS', 'PANIC'])
        with self.assertRaises(Problem): self.app.read_active(9)

    def test_main_restart_requires_a_saved_main(self):
        with self.assertRaisesRegex(Problem,'Upload a Main'):self.app.main_load({})
        self.assertNotIn('LOAD',self.d.calls)
        self.d.slots[1]['name']='Test';self.d.calls.clear()
        state=self.app.main_load({})
        self.assertEqual(state['status']['slot'],1);self.assertIn('LOAD',self.d.calls)
        self.assertNotIn('SAVE',self.d.calls)

    def test_read_fx_restores_bypass_even_after_read_failure(self):
        class FXDevice(FakeDevice):
            master=0
            def request(self,op,payload=b''):
                if op=='FXLIST':return [dict(slot=i,selected=i==self.master) for i in (0,1)]
                if op=='FXLOAD':self.master=payload[0];self.calls.append((op,self.master));return {}
                return super().request(op,payload)
            def download(self,master=False):
                if self.corrupt:raise RuntimeError('Read failed')
                return self.graph,self.source,dict(slot=self.master,manifest=self.meta.hex())
        self.app.device=d=FXDevice()
        patch=self.app.read_active(1,master=True)
        self.assertEqual(patch['slot'],1);self.assertEqual(d.master,0)
        self.assertEqual(d.calls,[('FXLOAD',1),('FXLOAD',0)])
        d.corrupt=True
        with self.assertRaisesRegex(RuntimeError,'Read failed'):self.app.read_active(1,master=True)
        self.assertEqual(d.master,0)


class HTTPTests(unittest.TestCase):
    def test_volume_endpoint_guards_identity_bounds_and_save(self):
        class VolumeDevice(FakeDevice):
            percent=20
            saved=20
            def request(self,op,payload=b''):
                if op in ('VOLUME','VOLSAVE'):
                    self.calls.append((op,payload))
                    if payload:self.percent=payload[0]
                    if op=='VOLSAVE':self.saved=self.percent
                    return dict(percent=self.percent)
                return super().request(op,payload)
        app=self.server.studio;d=VolumeDevice();auth={'X-Studio-Token':self.server.token,'Content-Type':'application/json'}
        with app.device_lock:
            app.device=d;app.device_info=dict(device_id='test-node',global_volume=True);app.device_port='fake'
        try:
            for body in ({'percent':50},{'device_id':'another-node','percent':50},
                         *[dict(device_id='test-node',percent=x) for x in (-1,101,True,20.5,'20',None)],
                         dict(device_id='test-node',percent=20,save='yes')):
                self.assertIn(self.request('POST','/api/volume',body,auth)[0],(400,409))
            self.assertEqual(d.calls,[])
            for percent,save in ((0,False),(100,False),(37,True)):
                status,raw,_=self.request('POST','/api/volume',dict(device_id='test-node',percent=percent,save=save),auth)
                self.assertEqual(status,200,raw);self.assertEqual(json.loads(raw),dict(device_id='test-node',percent=percent,saved=save))
            self.assertEqual(d.saved,37);self.assertEqual([op for op,_ in d.calls].count('VOLSAVE'),1)
            self.assertEqual(app.state()['volume_percent'],37)
            with self.assertRaises(Problem):app.volume_value(dict(percent=True))
        finally:
            with app.device_lock:app.disconnect()

    def test_audio_telemetry_retains_only_numeric_diagnostics(self):
        telemetry = AudioTelemetry()
        telemetry.write(b'I (1) synthdef: CPU average_x10=123 peak_x10=456\n')
        telemetry.write(b'@SD1 synthdef: average_x10=9999\n')
        telemetry.write(b'I (2) synthdef: active=1 faults=0 graph_sha256=123\n')
        values = telemetry.snapshot()
        self.assertEqual(values['average_x10'], 123); self.assertEqual(values['active'], 1)
        self.assertNotIn('graph_sha256', values)

    @classmethod
    def setUpClass(cls):
        cls.server = Server(('127.0.0.1', 0), Studio(SCLANG))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True); cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()

    def request(self, method='GET', path='/api/config', data=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        conn.request(method, path, body=None if data is None else json.dumps(data), headers=headers or {})
        response = conn.getresponse(); result = response.status, response.read(), response.headers; conn.close(); return result

    def test_api_needs_session_token(self):
        self.assertEqual(self.request()[0], 403)
        self.assertEqual(self.request(headers={'X-Studio-Token': self.server.token})[0], 200)

    def test_cross_origin_and_rebinding_rejected_even_with_token(self):
        for headers in ({'Origin': 'https://example.com'}, {'Host': 'evil.example'}, {'Sec-Fetch-Site': 'cross-site'}):
            self.assertEqual(self.request(headers={'X-Studio-Token': self.server.token, **headers})[0], 403)

    def test_static_assets_and_no_directory_traversal(self):
        status, body, headers = self.request(path='/')
        self.assertEqual(status, 200); self.assertIn(b'SynthDef Studio', body)
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        self.assertEqual(self.request(path='/../../host/patches.py')[0], 404)

    def test_json_and_request_size_bounds(self):
        auth = {'X-Studio-Token': self.server.token}
        self.assertEqual(self.request('POST', '/api/compile', {}, auth)[0], 400)
        headers = dict(auth, **{'Content-Type': 'application/json'})
        self.assertEqual(self.request('POST', '/api/compile', [], headers)[0], 400)
        self.assertEqual(self.request('POST', '/api/compile', headers=dict(headers, **{'Content-Length': '524289'}))[0], 413)


if __name__ == '__main__':
    unittest.main(verbosity=2)
