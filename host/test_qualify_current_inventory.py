"""Restoration and evidence safeguards for the physical inventory runner."""
import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import qualify_current_inventory as tool


class InventoryTests(unittest.TestCase):
    def test_failed_graph_cannot_count_as_covered(self):
        rows = [dict(id='good', type_rates=[['Lag', 2]], comparison=dict(passed=True)),
                dict(id='bad', type_rates=[['Klank', 2]], comparison=dict(passed=False))]
        result = tool.coverage(rows, [['Lag', 2], ['Klank', 2]])
        self.assertEqual(result['missing_type_rates'], [('Klank', 2)])
        self.assertEqual(result['failed_graphs'], ['bad'])

    def test_corrupted_graph_or_native_reference_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(tool, 'ROOT', Path(directory)):
            root = Path(directory)
            (root/'graph').write_bytes(b'graph'); (root/'samples').write_bytes(b'samples')
            job = dict(graph='graph', samples='samples', graph_sha256=tool.sha(root/'graph'),
                       samples_sha256=tool.sha(root/'samples'))
            tool.audit_job(job)
            for key in ('graph', 'samples'):
                before = (root/key).read_bytes(); (root/key).write_bytes(b'changed')
                with self.assertRaises(AssertionError): tool.audit_job(job)
                (root/key).write_bytes(before)

    def test_wrong_device_loud_volume_or_active_fx_does_not_write_backup(self):
        for change in ('identity', 'volume', 'fx'):
            state = dict(hello=dict(device_id='target', headless=True), status=dict(slot=1),
                         volume_percent=5, masters=[dict(slot=0, selected=True)])
            if change == 'identity': state['hello']['device_id'] = 'other'
            if change == 'volume': state['volume_percent'] = 20
            if change == 'fx': state['masters'] = [dict(slot=1, selected=True)]
            client = Mock(); client.http.return_value = state
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'backup.json'
                with self.assertRaises(AssertionError): tool.backup(client, 'target', path)
                self.assertFalse(path.exists()); client.rpc.assert_not_called()
                self.assertEqual([c.args[0] for c in client.http.call_args_list], ['refresh'])

    def session(self, failing=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'firmware/main').mkdir(parents=True)
            (root/'firmware/main/generated.h').write_text('#define BUILD_ID "build"')
            (root/'graph').write_bytes(b'graph'); (root/'samples').write_bytes(b'samples')
            job = dict(id='one', graph='graph', samples='samples', graph_sha256=tool.sha(root/'graph'),
                       samples_sha256=tool.sha(root/'samples'), type_rates=[['SinOsc', 2]])
            plan = root/'plan.json'; plan.write_text(json.dumps(dict(passed=True, qualified=True,
                reference_sources={}, jobs=[job], expected_type_rates=job['type_rates'])))
            args = argparse.Namespace(plan=plan, device_id='target', backup=root/'backup.json',
                                      output=root/'report.json', limit=None, profile=False)
            saved = dict(state=dict(hello=dict(device_id='target', build='build')),
                         main_info=dict(boot=1, controls=[]), fx_info=dict(controls=[]), volume=.05)
            client = Mock(); client.http.return_value = dict(hello=saved['state']['hello'], volume_percent=5)
            device = Mock(); device.hello.return_value = saved['state']['hello']
            device.upload.return_value = dict(graph_sha256=job['graph_sha256'])
            device.request.return_value = dict(percent=0)
            streams = []
            def open_device(port, stream):
                streams.append(stream)
                return device
            def restore(d, b, percent, save):
                self.assertFalse(streams[0].closed, 'Log must stay open through restoration')
                self.assertIs(d, device); self.assertIs(b, saved)
                self.assertEqual((percent, save), (5, False))
                return dict(verified=True)
            with patch.object(tool, 'ROOT', root), patch.object(tool, 'StudioClient', return_value=client), \
                 patch.object(tool, 'backup', return_value=saved), patch.object(tool, 'find_port', return_value='port'), \
                 patch.object(tool, 'Device', side_effect=open_device), \
                 patch.object(tool, 'schema', return_value=dict(boot=1, controls=[])), \
                 patch.object(tool, 'profile', return_value=dict(setup=dict(qualified='1'))), \
                 patch.object(tool, 'collect', side_effect=RuntimeError('capture failed') if failing else None,
                              return_value=(dict(max_us='10'), b'capture')), \
                 patch.object(tool, 'compare', return_value=dict(passed=True, comparison='waveform')), \
                 patch.object(tool, 'restore', side_effect=restore) as restored:
                if failing:
                    with self.assertRaisesRegex(RuntimeError, 'capture failed'): tool.run(args)
                else:
                    tool.run(args)
                restored.assert_called_once()
            self.assertTrue(streams[0].closed)
            device.close.assert_called_once()
            result = json.loads(args.output.read_text())
            self.assertTrue(result['restoration']['verified']); self.assertTrue(result['studio_connected'])
            self.assertEqual(result['passed'], not failing)

    def test_restoration_precedes_log_close_on_success(self): self.session()
    def test_restoration_precedes_log_close_on_capture_failure(self): self.session(True)


if __name__ == '__main__': unittest.main()
