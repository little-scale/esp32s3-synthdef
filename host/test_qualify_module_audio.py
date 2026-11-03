import itertools
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import qualify_module_audio as check


class FakeStudio:
    def __init__(self, admitted=True, device='module-one'):
        self.calls = []
        self.admitted = admitted
        self.state = dict(connected=True, hello=dict(device_id=device, build='test'),
                          slots=[dict(slot=1, name='', generations=[0,0])],
                          masters=[dict(slot=0, selected=True), dict(slot=1, selected=False)])

    def http(self, action, payload=None):
        self.calls.append(action)
        if action == 'refresh': return self.state
        if action == 'compile':
            assert payload['definition'] is False
            return dict(admitted=self.admitted, continuous=True, artifact='compiled')
        if action == 'read-active': return dict(slot=0, name='Factory Sine', graph='factory', source='factory')
        if action == 'upload':
            assert payload['expected']['name'] == '' and payload['device_id'] == 'module-one'
            return dict(verified=True)
        if action == 'audio': return dict(average_x10=900, peak_x10=1400)
        raise AssertionError(action)

    def rpc(self, action, payload):
        self.calls.append(action)
        if action == 'meta': return dict(verified=True, results=[dict(volume=1)])
        if action == 'bypass': return dict(verified=True)
        if action == 'info': return dict(results=[dict(active=True)])
        raise AssertionError(action)


class ModuleAudioTests(unittest.TestCase):
    def test_fresh_empty_main_uses_private_factory_backup_and_allows_cpu_peaks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'examples').mkdir()
            (root/'examples/module-audio-check.scd').write_text('{0}.play')
            client, report = FakeStudio(), {}
            clock = itertools.count(0, .25)
            with patch.object(check, 'ROOT', root), patch.object(check.time, 'monotonic', side_effect=lambda: next(clock)), patch.object(check.time, 'sleep'):
                check.run(client, 'module-one', 1, .25, report)
            self.assertTrue(report['passed'] and report['fx_bypassed'] and report['main_active'])
            self.assertEqual(report['peak_cpu_max_percent'], 140)
            backups = list((root/'build/host/private').glob('*.json'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].stat().st_mode & 0o077, 0)

    def test_wrong_module_has_no_mutations(self):
        client = FakeStudio(device='another-module')
        with self.assertRaisesRegex(RuntimeError, 'exact requested'):
            check.run(client, 'module-one', 1, .25, {})
        self.assertEqual(client.calls, ['refresh'])

    def test_rejected_compile_has_no_mutations(self):
        client = FakeStudio(admitted=False)
        with self.assertRaisesRegex(RuntimeError, 'not admitted'):
            check.run(client, 'module-one', 1, .25, {})
        self.assertEqual(client.calls, ['refresh', 'compile'])


if __name__ == '__main__':
    unittest.main()
