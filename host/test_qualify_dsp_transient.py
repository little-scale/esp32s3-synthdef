"""Offline safeguards for the single-connection, temporary-patch runner."""
import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import qualify_dsp_transient as tool


class Device:
    def __init__(self): self.calls=[]
    def request(self,op,payload=b''):
        self.calls.append((op,payload))
        if op=='VOLUME': return dict(percent=payload[0])
        if op=='VOLSAVE': return dict(percent=5)
        if op=='LIST': return [dict(slot=1,name='original',generations=[9,10])]
        if op=='FXLIST': return [dict(slot=0,name='Bypass',selected=True),dict(slot=1,name='',selected=False)]
        return {}
    def download(self): return b'original graph',b'original source',{}


class TransientTests(unittest.TestCase):
    def test_listening_bypasses_soak_fx_before_loading_main(self):
        device=Mock()
        def first_install(*args,**kwargs):
            device.request.assert_called_once_with('FXLOAD',b'\0')
            raise RuntimeError('stop before playing')
        with patch.object(tool,'volume') as volume, \
             patch.object(tool,'compile_install',side_effect=first_install):
            with self.assertRaisesRegex(RuntimeError,'stop before playing'):
                tool.listen(device,Mock())
        volume.assert_called_once_with(device,0)

    def test_repeated_soaks_use_fresh_nonzero_streams(self):
        sample=dict.fromkeys(('faults','clips','nonfinite','write_fail','partial',
                              'dma_event_overflow','overflow'),0)
        sample.update(internal_free=10000,psram_free=10000)
        for random_id,expected in ((712,712),(1234,1234),(0,1)):
            device=Mock();device.request.return_value=dict(queued=True)
            telemetry=Mock();telemetry.snapshot.return_value=sample
            with patch.object(tool,'compile_install'),patch.object(tool,'schema',return_value={}), \
                 patch.object(tool,'volume'),patch.object(tool,'packet',return_value=b'event') as packet, \
                 patch.object(tool.secrets,'randbits',return_value=random_id), \
                 patch.object(tool.time,'monotonic',side_effect=[0,4,5,6,16,17,20]), \
                 patch.object(tool.time,'sleep'):
                result=tool.soak(device,Mock(),telemetry,10,recordings=False)
            self.assertTrue(result['passed'])
            self.assertEqual(result['control_stream'],expected)
            self.assertEqual(packet.call_args.args[2:4],(expected,1))

    def test_volume_cap_rejects_before_sending(self):
        d=Device()
        for value in (-1,6,20,50,100,.5,True):
            with self.subTest(value=value),self.assertRaises(AssertionError): tool.volume(d,value)
        self.assertEqual(d.calls,[])
        tool.volume(d,5)
        self.assertEqual(d.calls,[('VOLUME',bytes([5]))])

    def test_saved_patch_generations_and_empty_fx_survive_restore(self):
        d=Device();main=d.request('LIST');fx=d.request('FXLIST');d.calls=[]
        backup=dict(state=dict(status=dict(slot=1),slots=main,masters=fx),
                    main=dict(graph=base64.b64encode(b'original graph').decode(),source='original source'),
                    main_info=dict(active=True,controls=[dict(name='freq',values=[330])]),
                    fx_info=dict(active=False,controls=[]))
        schemas={0:dict(active=True),1:dict(active=False)}
        with patch.object(tool,'schema',side_effect=lambda d,stage:schemas[stage]), \
             patch.object(tool,'instance_packet',return_value=b'instance') as packet:
            result=tool.restore(d,backup,5,save=True)
        self.assertTrue(result['saved_main_fx_lists_unchanged'])
        self.assertEqual(packet.call_args_list[-1].args[-1],['freq',[330]])
        operations=[op for op,payload in d.calls]
        self.assertNotIn('INSTALL',operations)
        self.assertNotIn('SAVE',operations)
        self.assertNotIn('FXSAVE',operations)
        self.assertEqual(operations[-2:],['VOLUME','VOLSAVE'])

    def test_unexpected_saved_graph_fails_before_starting_instances(self):
        d=Device()
        backup=dict(state=dict(status=dict(slot=1)),
                    main=dict(graph=base64.b64encode(b'other graph').decode(),source='original source'))
        with self.assertRaises(AssertionError):tool.restore(d,backup)
        self.assertNotIn('START',[op for op,payload in d.calls])

    def test_wrong_physical_device_never_receives_restore_or_volume(self):
        class OtherDevice:
            def hello(self):return dict(device_id='another-module',headless=True)
            def close(self):pass
        with tempfile.TemporaryDirectory() as folder:
            backup=Path(folder)/'backup.json';output=Path(folder)/'report.json'
            backup.write_text(json.dumps(dict(state=dict(hello=dict(device_id='expected'),
                masters=[dict(slot=0,selected=True)]))))
            argv=['test','--port','test','--device-id','expected','--backup',str(backup),
                  '--output',str(output),'--phase','restore']
            with patch('sys.argv',argv),patch.object(tool,'Device',return_value=OtherDevice()), \
                 patch.object(tool,'restore') as restore,patch.object(tool,'volume') as volume:
                with self.assertRaises(AssertionError):tool.main()
                restore.assert_not_called();volume.assert_not_called()
            self.assertFalse(json.loads(output.read_text())['passed'])


if __name__=='__main__': unittest.main()
