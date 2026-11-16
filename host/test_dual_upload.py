"""No-device tests for validated, payload-driven runtime handoff."""
from contextlib import nullcontext
from pathlib import Path
import tempfile
import json
import unittest
from unittest.mock import patch, Mock

import dual_upload as upload


class RoutingTests(unittest.TestCase):
    def test_sc_source_extension_uses_the_same_compiler_and_rate_admission(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'main.sc';path.write_text('{ Silent.ar(2) }')
            compiler=Mock()
            compiler.compile.return_value=(b'SCgf graph',b'original',dict(fm1_admitted=True))
            artifact=upload.prepare(path,16000,'voice-pe','/unused',compiler=compiler)
            self.assertEqual(artifact.engine,'synthdef')
            self.assertEqual(compiler.compile.call_args.args[0]['source'],'{ Silent.ar(2) }')

    def test_voice_led_graph_rejects_a_non_voice_board_before_device_access(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'main.scd';path.write_text('{ Out.kr(3,1); Silent.ar(2) }')
            compiler=Mock();compiler.compile.return_value=(b'graph',b'source',dict(requires_control_outputs=True,fm1_admitted=True))
            with patch.object(upload,'probe') as probe:
                with self.assertRaisesRegex(ValueError,'LED buses'):
                    upload.prepare(path,44100,'xiao','/unused',compiler=compiler)
                probe.assert_not_called()

    def test_usb_reenumeration_waits_for_identity_and_has_a_deadline(self):
        with patch.object(upload, 'resolve', side_effect=[ValueError('gone'), '/new-port']), patch.object(upload.time, 'sleep'):
            self.assertEqual(upload.wait_port('001122334455'), '/new-port')
        with patch.object(upload, 'resolve', side_effect=ValueError('gone')), patch.object(upload.time, 'monotonic', side_effect=[0, 36]), patch.object(upload.time, 'sleep') as sleep:
            with self.assertRaisesRegex(ValueError, 'did not reappear'):
                upload.wait_port('001122334455')
            sleep.assert_not_called()

    def test_companion_namespace_is_not_shadowed_by_synthdef_studio(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            module = root / 'host/studio/device.py'
            module.parent.mkdir(parents=True)
            module.write_text('ENGINE = "rnbo"\n')
            code = ('import sys,json;sys.path.insert(0,sys.argv[1]);'
                    'from host.studio.device import ENGINE;'
                    'print(json.dumps({"engine":ENGINE}))')
            with patch.object(upload, 'rnbo_root', return_value=root):
                self.assertEqual(upload.rnbo_call(code), {'engine': 'rnbo'})

    def test_probe_ignores_console_noise_and_requires_typed_busy_state(self):
        for busy in (False, 'false'):
            reply = dict(version=1, engine='rnbo', rate=16000, busy=busy,
                         model='Home Assistant Voice PE')
            link = Mock(in_waiting=1024)
            link.read.return_value = b'boot log\n@RT1 ' + json.dumps(reply).encode() + b'\n'
            manager = Mock()
            manager.__enter__ = Mock(return_value=link)
            manager.__exit__ = Mock(return_value=False)
            with patch.object(upload, 'resolve', return_value='/fake'), patch('serial_port.open_port', return_value=manager):
                if type(busy) is bool:
                    self.assertEqual(upload.probe('001122334455'), reply)
                else:
                    with self.assertRaisesRegex(ValueError, 'identification'):
                        upload.probe('001122334455')
            link.write.assert_called_once_with(b'@RT1 HELLO\n')

    def test_failed_fade_prevents_boot_and_upload(self):
        a, b, c = self.dependencies(dict(engine='synthdef', model='Home Assistant Voice PE', rate=16000))
        with a, b, c, patch.object(upload, 'fade', side_effect=ValueError('no fade acknowledgement')), patch.object(upload, 'boot') as boot, patch.object(upload, 'send_rnbo') as send:
            with self.assertRaisesRegex(ValueError, 'fade acknowledgement'):
                upload.route(self.artifact('rnbo'), 'voice-pe', '001122334455', 16000)
            boot.assert_not_called(); send.assert_not_called()

    def artifact(self, engine='synthdef', rate=16000):
        return upload.Artifact(engine, rate, b'validated payload', b'', {})

    def dependencies(self, current):
        return (patch.object(upload, 'device_lock', return_value=nullcontext()),
                patch.object(upload, 'installed_pair', return_value={'synthdef', 'rnbo'}),
                patch.object(upload, 'probe', return_value=current))

    def test_matching_engine_uploads_without_fade_or_restart(self):
        a, b, c = self.dependencies(dict(engine='synthdef', model='Home Assistant Voice PE', rate=16000))
        with a, b, c, patch.object(upload, 'fade') as fade, patch.object(upload, 'boot') as boot, patch.object(upload, 'send_synth', return_value={'verified': True}) as send:
            self.assertEqual(upload.route(self.artifact(), 'voice-pe', '001122334455', 16000), {'verified': True})
            fade.assert_not_called(); boot.assert_not_called(); send.assert_called_once()

    def test_cross_engine_orders_fade_boot_and_upload(self):
        events = []
        a, b, c = self.dependencies(dict(engine='synthdef', model='Home Assistant Voice PE', rate=16000))
        with a, b, c, patch.object(upload, 'fade', side_effect=lambda *a: events.append('fade')), patch.object(upload, 'boot', side_effect=lambda *a: events.append('boot')), patch.object(upload, 'send_rnbo', side_effect=lambda *a: events.append('upload')):
            upload.route(self.artifact('rnbo'), 'voice-pe', '001122334455', 16000)
        self.assertEqual(events, ['fade', 'boot', 'upload'])

    def test_custom_sc_sender_runs_once_after_selection_without_default_upload(self):
        a,b,c=self.dependencies(dict(engine='rnbo',model='Home Assistant Voice PE',rate=16000))
        events=[]
        sender=Mock(side_effect=lambda *args: events.append('sc-upload') or dict(verified=True))
        with a,b,c,patch.object(upload,'fade',side_effect=lambda *args:events.append('fade')),patch.object(upload,'boot',side_effect=lambda *args:events.append('boot')),patch.object(upload,'send_synth') as default:
            result=upload.route(self.artifact(),'voice-pe','001122334455',16000,sender=sender)
        self.assertTrue(result['verified']);self.assertEqual(events,['fade','boot','sc-upload'])
        sender.assert_called_once();default.assert_not_called()

    def test_boot_failure_does_not_send_to_wrong_runtime(self):
        a, b, c = self.dependencies(dict(engine='synthdef', model='Home Assistant Voice PE', rate=16000))
        with a, b, c, patch.object(upload, 'fade'), patch.object(upload, 'boot', side_effect=ValueError('boot failed')), patch.object(upload, 'send_rnbo') as send:
            with self.assertRaisesRegex(ValueError, 'boot failed'):
                upload.route(self.artifact('rnbo'), 'voice-pe', '001122334455', 16000)
            send.assert_not_called()

    def test_wrong_rate_and_model_do_not_fade_boot_or_upload(self):
        for current in [dict(engine='rnbo', model='XIAO ESP32-S3', rate=16000),
                        dict(engine='rnbo', model='Home Assistant Voice PE', rate=48000)]:
            a, b, c = self.dependencies(current)
            with a, b, c, patch.object(upload, 'fade') as fade, patch.object(upload, 'boot') as boot, patch.object(upload, 'send_synth') as send:
                with self.assertRaises(ValueError): upload.route(self.artifact(), 'voice-pe', '001122334455', 16000)
                fade.assert_not_called(); boot.assert_not_called(); send.assert_not_called()

    def test_legacy_fallback_verifies_boot_choice_before_upload(self):
        a, b, c = self.dependencies(None); events = []
        with a, b, c, patch.object(upload, 'fade') as fade, patch.object(upload, 'boot', side_effect=lambda *a: events.append('boot')), patch.object(upload, 'send_rnbo', side_effect=lambda *a: events.append('upload')):
            upload.route(self.artifact('rnbo'), 'voice-pe', '001122334455', 16000, allow_legacy_reboot=True)
        fade.assert_not_called(); self.assertEqual(events, ['boot', 'upload'])

    def test_legacy_and_busy_devices_do_not_reboot_without_explicit_maintenance(self):
        for current in [None, dict(engine='rnbo', model='Home Assistant Voice PE', rate=16000, busy=True)]:
            a, b, c = self.dependencies(current)
            with a, b, c, patch.object(upload, 'boot') as boot, patch.object(upload, 'send_synth') as send:
                with self.assertRaises(ValueError): upload.route(self.artifact(), 'voice-pe', '001122334455', 16000)
                boot.assert_not_called(); send.assert_not_called()

    def test_uncommissioned_pair_is_not_probed_or_restarted(self):
        with patch.object(upload, 'device_lock', return_value=nullcontext()), patch.object(upload, 'installed_pair', side_effect=ValueError('not commissioned')), patch.object(upload, 'probe') as probe, patch.object(upload, 'boot') as boot:
            with self.assertRaises(ValueError): upload.route(self.artifact(), 'voice-pe', '001122334455', 16000)
            probe.assert_not_called(); boot.assert_not_called()

    def test_missing_rnbo_runtime_prevents_fade_and_boot(self):
        with patch.object(upload, 'device_lock', return_value=nullcontext()), patch.object(upload, 'installed_pair', return_value={'synthdef'}), patch.object(upload, 'probe', return_value=dict(engine='synthdef', model='Home Assistant Voice PE', rate=16000)), patch.object(upload, 'fade') as fade, patch.object(upload, 'boot') as boot:
            with self.assertRaises(ValueError): upload.route(self.artifact('rnbo'), 'voice-pe', '001122334455', 16000)
            fade.assert_not_called(); boot.assert_not_called()

    def test_invalid_file_fails_before_any_device_access(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'invalid.rnbopkg'; path.write_bytes(b'garbage')
            with patch.object(upload, 'probe') as probe, patch.object(upload, 'boot') as boot:
                with self.assertRaises(ValueError): upload.prepare(path, 16000, 'voice-pe', '/not-used')
                probe.assert_not_called(); boot.assert_not_called()

    def test_oversized_payload_is_rejected_before_parser_or_transport(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'too-large.rnbopkg'
            path.write_bytes(b'RNBOS3P1' + bytes(128 + 65536 + 524288))
            with patch.object(upload, 'rnbo_call') as parser, patch.object(upload, 'probe') as probe:
                with self.assertRaisesRegex(ValueError, 'package limit'):
                    upload.prepare(path, 16000, 'voice-pe', '/not-used')
                parser.assert_not_called(); probe.assert_not_called()

    def test_rnbo_fx_target_rejects_before_parser_or_transport(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'native.rnbopkg'; path.write_bytes(b'RNBOS3P1')
            with patch.object(upload, 'rnbo_call') as parser:
                with self.assertRaisesRegex(ValueError, 'inside its Main'):
                    upload.prepare(path, 16000, 'voice-pe', '/not-used', target='fx')
                parser.assert_not_called()


if __name__ == '__main__': unittest.main()
