"""Check timing connection ownership and restoration after diagnostic failure."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import qualify_dsp_kernels as tool


class Client:
    def __init__(self):self.connected=True;self.calls=[]
    def http(self,op,payload=None):
        self.calls.append(op)
        if op=='disconnect':self.connected=False;return {}
        if op=='connect':self.connected=True;return {}
        if op=='config':return dict(connected=self.connected)
        if op=='refresh':return dict(port='test-usb',hello=dict(device_id='test-node'))
        raise AssertionError(op)
    def close(self):self.calls.append('close')


class Qualification:
    def __init__(self,client,*args):self.client=client
    def save(self):return dict(build='test-build')
    def rpc(self,*args,**kwargs):return {}
    def compile(self,*args,**kwargs):return dict(graph_sha256='hash',nodes=1)
    def install(self,*args,**kwargs):pass
    def restore(self):
        assert self.client.connected,'Restoration was attempted without reattaching USB'
        self.client.calls.append('restore');return dict(verified=True)


class Device:
    opens=0
    def __init__(self,port):Device.opens+=1
    def hello(self):return dict(device_id='test-node')
    def close(self):pass


class TimingTests(unittest.TestCase):
    def test_one_direct_open_per_fixture_and_restore(self):
        c=Client();Device.opens=0
        with tempfile.TemporaryDirectory() as d,patch.object(tool,'StudioClient',return_value=c),patch.object(tool,'Qualification',Qualification),patch.object(tool,'Device',Device),patch.object(tool,'FIXTURES',{'one':'source'}),patch.object(tool,'collect',return_value=dict(header={},by_type=[],normal_average_us_at_240mhz=10)) as collect:
            r=tool.run('test-node','before',3,Path(d)/'report.json')
        self.assertTrue(r['passed']);self.assertEqual(collect.call_count,3);self.assertEqual(Device.opens,1)
        self.assertEqual(c.calls[-3:],['connect','restore','close'])

    def test_failed_diagnostic_reattaches_before_restoring(self):
        c=Client()
        with tempfile.TemporaryDirectory() as d,patch.object(tool,'StudioClient',return_value=c),patch.object(tool,'Qualification',Qualification),patch.object(tool,'Device',Device),patch.object(tool,'FIXTURES',{'one':'source'}),patch.object(tool,'collect',side_effect=RuntimeError('diagnostic failed')):
            with self.assertRaisesRegex(RuntimeError,'diagnostic failed'):tool.run('test-node','before',3,Path(d)/'report.json')
        self.assertEqual(c.calls[-3:],['connect','restore','close'])


if __name__=='__main__':unittest.main()
