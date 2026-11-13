"""USB probe tests with fake serial devices; never touch hardware."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import json
import unittest
from unittest.mock import Mock,patch

import probe_usb_lifecycle as tool

TARGET='esp32-1c29043eeb84'


class Device:
    def __init__(self,target=TARGET,boot=123):
        self.target=target;self.boot=boot;self.ops=[];self.closed=False;self.clock=100
        self.link=SimpleNamespace(write=Mock())
    def request(self,op,payload=b'',**kwargs):
        self.ops.append(op)
        if op=='HELLO':return dict(device_id=self.target,build='build')
        if op=='RCINFO':
            self.clock+=100
            return dict(boot=self.boot,revision=9,now_us=self.clock,active=True)
        if op=='STATUS':return dict(graph_sha256='graph')
        if op=='VOLUME':
            assert payload==b'', 'Probe changed volume'
            return dict(percent=5)
        raise AssertionError('Unexpected operation: '+op)
    def close(self):self.closed=True


class ProbeTests(unittest.TestCase):
    def test_target_port_is_found_by_identity_not_cached_path(self):
        rows=[SimpleNamespace(vid=0x303a,pid=0x1001,serial_number='1C:29:04:3E:EB:84',device='/dev/cu.changed'),
              SimpleNamespace(vid=0x303a,pid=0x1001,serial_number='000000000001',device='/dev/cu.other')]
        self.assertEqual(tool.find_port(TARGET,rows),'/dev/cu.changed')
        with self.assertRaises(RuntimeError):tool.find_port(TARGET,[])
        with self.assertRaises(RuntimeError):tool.find_port(TARGET,[rows[0],rows[0]])

    def test_malformed_target_is_rejected(self):
        for target in ('all','XIAO-3eeb84','esp32-1','esp32-ABCDEFGHIJKL'):
            with self.subTest(target=target),self.assertRaises(ValueError):tool.serial_id(target)

    def test_snapshot_only_uses_queries(self):
        device=Device();s=tool.snapshot(device,TARGET)
        self.assertEqual(device.ops,['HELLO','RCINFO','STATUS','VOLUME'])
        self.assertEqual(s['boot'],123);self.assertEqual(s['volume_percent'],5)

    def test_wrong_handshake_stops_before_other_queries(self):
        device=Device('another-device')
        with self.assertRaisesRegex(RuntimeError,'identity changed'):tool.snapshot(device,TARGET)
        self.assertEqual(device.ops,['HELLO'])

    def test_unread_case_leaves_connection_open(self):
        device=Device();log=SimpleNamespace(bytes=0)
        with patch.object(tool,'pause') as pause:
            actual,result=tool.probe_case(device,TARGET,'unread',15,log)
        self.assertIs(actual,device);self.assertFalse(device.closed)
        pause.assert_called_once_with(15);self.assertTrue(result['passed'])

    def test_partial_case_contains_no_complete_or_mutating_frame(self):
        device=Device()
        with patch.object(tool,'pause'):
            _,row=tool.probe_case(device,TARGET,'partial',2,SimpleNamespace(bytes=0))
        wire=device.link.write.call_args.args[0]
        self.assertTrue(wire.startswith(b'@SD1 '));self.assertNotIn(b'\n',wire)
        self.assertNotIn(b'!',wire);self.assertTrue(row['passed'])

    def test_reopened_device_closes_on_detected_reboot(self):
        old=Device();new=Device(boot=456)
        with patch.object(tool,'pause'),patch.object(tool,'find_port',return_value='test'), \
             patch.object(tool,'Device',return_value=new):
            with self.assertRaisesRegex(AssertionError,'MCU rebooted'):
                tool.probe_case(old,TARGET,'closed',2,SimpleNamespace(bytes=0))
        self.assertTrue(old.closed);self.assertTrue(new.closed)

    def test_absent_board_does_not_disconnect_studio(self):
        with tempfile.TemporaryDirectory() as folder:
            argv=['probe','--device-id',TARGET,'--output',str(Path(folder)/'report.json')]
            with patch('sys.argv',argv),patch.object(tool,'find_port',side_effect=RuntimeError('absent')), \
                 patch.object(tool,'StudioClient') as client:
                with self.assertRaisesRegex(RuntimeError,'absent'):tool.main()
                client.assert_not_called()

    def test_connected_studio_uses_refresh_for_identity_and_returns_same_boot(self):
        class Client:
            def __init__(self):self.calls=[]
            def http(self,path,payload=None):
                self.calls.append(path)
                if path=='config':return dict(connected=True)  # Real config has no hello.
                if path in ('refresh','connect'):return dict(hello=dict(device_id=TARGET))
                if path=='disconnect':return dict(connected=False)
                raise AssertionError(path)
            def rpc(self,*args):return dict(results=[dict(boot=123)])
            def close(self):pass
        client=Client();device=Device();log=SimpleNamespace(bytes=0,resets=[],close=Mock())
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'report.json'
            argv=['probe','--device-id',TARGET,'--output',str(output),'--modes','unread','--gaps','0']
            with patch('sys.argv',argv),patch.object(tool,'find_port',return_value='test'), \
                 patch.object(tool,'StudioClient',return_value=client),patch.object(tool,'PrivateLog',return_value=log), \
                 patch.object(tool,'Device',return_value=device),patch.object(tool,'pause'),patch('builtins.print'):
                tool.main()
            report=json.loads(output.read_text())
        self.assertEqual(client.calls,['config','refresh','disconnect','connect'])
        self.assertTrue(report['passed']);self.assertEqual(report['studio_final_boot'],123)

    def test_selected_other_module_is_not_disconnected(self):
        client=SimpleNamespace(http=Mock(side_effect=[dict(connected=True),dict(hello=dict(device_id='other'))]),close=Mock())
        with tempfile.TemporaryDirectory() as folder:
            argv=['probe','--device-id',TARGET,'--output',str(Path(folder)/'report.json')]
            with patch('sys.argv',argv),patch.object(tool,'find_port',return_value='test'), \
                 patch.object(tool,'StudioClient',return_value=client),patch.object(tool,'Device') as device:
                with self.assertRaisesRegex(RuntimeError,'another module'):tool.main()
            self.assertEqual([c.args[0] for c in client.http.call_args_list],['config','refresh'])
            device.assert_not_called()


if __name__=='__main__':unittest.main()
