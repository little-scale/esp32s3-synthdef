import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from studio import Studio
from ide_bridge import Hub,USBNode
from network import Pairings

IDENTITY='esp32-000000000031'
class USBBridgeTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.app=Studio('/unused')
        self.app.pairings=Pairings(Path(self.folder.name)/'pairs.json')
        self.owner=Mock();self.owner.request.side_effect=self.operation
        self.app.device=self.owner;self.app.device_port='/dev/test-usb'
        self.app.device_info=dict(device_id=IDENTITY,device_name='USB synth',model='XIAO ESP32-S3')
        self.hub=Hub(self.app)
    def tearDown(self):
        self.hub.close();self.app.device=None;self.app.close();self.folder.cleanup()
    def operation(self,op,payload=b'',**kwargs):
        if op=='HELLO':return dict(protocol=1,model='XIAO ESP32-S3',policy='fm1-compat-v1',chunk=256,control_deltas=1)
        if op=='RCINFO':return dict(boot=1,revision=1,now_us=100,active=True,prepared=True,total=1,controls=[dict(name_hex='freq'.encode().hex(),index=0,count=1,writable=True,rate=1)])
        if op=='RCEVENT':return dict(queued=True)
        raise AssertionError(op)
    def test_unpaired_usb_resolves_without_lan_discovery(self):
        with patch('ide_bridge.discover',side_effect=AssertionError('Unexpected discovery')):
            for target in (IDENTITY,'USB synth','/dev/test-usb'):
                row=self.hub.resolve(target,refresh=True)[0];self.assertEqual(row['transport'],'usb')
    def test_shared_device_does_not_close_owners_port(self):
        node=self.hub.node(self.hub.resolve(IDENTITY)[0]);self.assertIsInstance(node,USBNode)
        self.assertIs(node.lock,self.app.device_lock);node.device.close();self.owner.close.assert_not_called()
    def test_pattern_controls_use_shared_usb_and_compress(self):
        args=dict(kind='set',target=IDENTITY,stream=43,args=['freq',440])
        self.assertTrue(self.hub.control(args,'client',1)['queued'])
        self.assertTrue(self.hub.control(args,'client',2)['queued'])
        events=[c.args[1] for c in self.owner.request.call_args_list if c.args[0]=='RCEVENT']
        self.assertEqual([len(v) for v in events],[37,32])
    def test_replaced_device_cannot_receive_old_stream(self):
        args=dict(kind='set',target=IDENTITY,stream=43,args=['freq',440])
        self.assertTrue(self.hub.control(args,'client',1)['queued'])
        replacement=Mock();self.app.device=replacement
        result=self.hub.control(args,'client',2)
        self.assertFalse(result['queued']);replacement.request.assert_not_called()
        new=self.hub.node(self.hub.resolve(IDENTITY)[0]);self.assertIs(new.device.owner,replacement)
    def test_all_deduplicates_wifi_and_usb(self):
        row=dict(device_id=IDENTITY,device_name='Wi-Fi synth',address='192.168.1.9',port=80,online=True,paired=True)
        self.app.pairings.save(dict(row,key='0'*64));self.hub.rows=[row]
        result=self.hub.resolve('all');self.assertEqual(len(result),1);self.assertEqual(result[0]['transport'],'usb')
    def test_node_creation_rejects_replaced_identity(self):
        row=self.hub.resolve(IDENTITY)[0]
        self.app.device=Mock();self.app.device_info=dict(device_id='esp32-000000000032',device_name='Replacement')
        with self.assertRaisesRegex(RuntimeError,'changed before dispatch'):self.hub.node(row)
