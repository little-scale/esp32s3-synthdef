"""Guard the effective variant check and restore path of mixer qualification."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import qualify_mix as tool


class MixQualificationTests(unittest.TestCase):
    def test_wrong_variant_restores_without_saved_patch_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'build/host/private').mkdir(parents=True)
            raw=b'graph';digest=hashlib.sha256(raw).hexdigest()
            plan=root/'plan.json';plan.write_text(json.dumps(dict(one=dict(
                graph=base64.b64encode(raw).decode(),source='source',graph_sha256=digest))))
            args=argparse.Namespace(plan=plan,device_id='target',backup=root/'backup.json',mix=1,output=root/'result.json')
            saved=dict(state=dict(hello=dict(device_id='target',build='build')),main_info=dict(boot=1,controls=[]),
                       fx_info=dict(controls=[]),volume=.05)
            client=Mock();client.http.return_value=dict(hello=dict(device_id='target'),volume_percent=5)
            device=Mock();device.hello.return_value=saved['state']['hello']
            device.upload.return_value=dict(graph_sha256=digest)
            sample=dict(setup=dict(qualified='1',mix='0'))
            def restore(d,b,percent,save):
                self.assertEqual((percent,save),(5,False));return dict(verified=True)
            with patch.object(tool,'ROOT',root),patch.object(tool,'StudioClient',return_value=client), \
                 patch.object(tool,'backup',return_value=saved),patch.object(tool,'Device',return_value=device), \
                 patch.object(tool,'find_port',return_value='port'),patch.object(tool,'volume'), \
                 patch.object(tool,'schema',return_value=dict(boot=1,controls=[])), \
                 patch.object(tool,'collect',return_value=sample),patch.object(tool,'restore',side_effect=restore) as restored:
                with self.assertRaises(AssertionError):tool.run(args)
                restored.assert_called_once()
            result=json.loads(args.output.read_text())
            self.assertFalse(result['passed']);self.assertTrue(result['restoration']['verified'])
            self.assertTrue(result['studio_connected'])
            operations=[c.args[0] for c in device.request.call_args_list]
            self.assertNotIn('SAVE',operations);self.assertNotIn('INSTALL',operations)
            device.close.assert_called_once()


if __name__=='__main__':unittest.main()
