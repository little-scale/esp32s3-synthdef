#!/usr/bin/env python3
"""Real HTTP transport against two isolated simulated modules, without RF/audio."""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import socket
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch
from network import NetworkDevice,Pairings,endpoint,identity,discover
from patches import ROOT,decode,frame
from studio import Studio,Artifact,Problem

GRAPH=(ROOT/'examples/TouchBuses.scsyndef').read_bytes()
SOURCE=(ROOT/'examples/touch-buses.scd').read_bytes()

class Module(ThreadingHTTPServer):
    def __init__(self,number):
        super().__init__(('127.0.0.1',0),Handler)
        self.device_id=f'esp32-{number:012x}';self.key=f'{number:064x}';self.name='Same name'
        self.calls=[];self.meta=None;self.blob=b'';self.stage=b'';self.slot=0;self.cache={}
        self.bad_id=self.bad_crc=self.bad_request=False
        self.master_slot=0;self.master_meta=None;self.master_blob=b'';self.stage_master=False;self.begin_barrier=None
        self.slots=[dict(slot=i,name='Factory' if i==0 else '',generations=[0,0]) for i in range(2)]
        self.thread=threading.Thread(target=self.serve_forever,daemon=True);self.thread.start()
    def info(self):
        return dict(protocol=1,device_id=self.device_id,device_name=self.name,address='127.0.0.1',port=self.server_port,online=True)
    def pairing(self):return dict(self.info(),key=self.key)
    def close(self):self.shutdown();self.server_close();self.thread.join()
    def operation(self,op,data):
        self.calls.append(op)
        if op=='HELLO':return dict(self.info(),model='Waveshare AMOLED 1.8 V2',policy='fm1-compat-v1',chunk=256,definition_lifecycle=True,atomic_install=True,continuous_blocks=True,master_slots=2,slots=1)
        if op=='LIST':return self.slots
        if op=='FXLIST':return [dict(slot=i,name='Bypass' if i==0 else 'FX' if self.master_meta else '',generations=[1 if self.master_meta else 0,0],selected=i==self.master_slot) for i in (0,1)]
        if op in ('FXLOAD','FXSELECT'):self.master_slot=data[0];return dict(slot=self.master_slot)
        if op=='STATUS':return dict(reset_required=False,transfer=self.tx if self.meta else 0,slot=self.slot,received=len(self.stage),continuous=True)
        if op in ('BEGIN','FXBEGIN'):
            if self.begin_barrier:self.begin_barrier.wait(timeout=5)
            self.stage_master=op=='FXBEGIN';self.meta=data;self.tx,self.graph_bytes,self.source_bytes=struct.unpack_from('<III',data);self.stage=b'';return dict(received=0)
        if op=='DATA':
            tx,at=struct.unpack_from('<II',data);assert tx==self.tx and at==len(self.stage);self.stage+=data[8:];return dict(received=len(self.stage))
        if op=='COMMIT':
            assert len(self.stage)==self.graph_bytes+self.source_bytes
            assert hashlib.sha256(self.stage[:self.graph_bytes]).digest()==self.meta[12:44]
            assert hashlib.sha256(self.stage[self.graph_bytes:]).digest()==self.meta[44:76]
            return dict(ready=True)
        if op=='INSTALL':
            if self.stage_master:
                self.master_slot=data[4];self.master_meta=self.meta;self.master_blob=self.stage;return dict(saved=True,slot=self.master_slot)
            self.slot=data[4];self.blob=self.stage;self.slots[self.slot].update(name=self.meta[76:108].split(b'\0')[0].decode(),generations=[1,0]);return dict(saved=True,slot=self.slot)
        if op=='FXINFO':return dict(slot=self.master_slot,manifest=self.master_meta.hex())
        if op=='FXREAD':
            at,count=struct.unpack('<IH',data);return dict(offset=at,data=self.master_blob[at:at+count].hex())
        if op=='INFO':return dict(slot=self.slot,manifest=self.meta.hex())
        if op=='READ':
            at,count=struct.unpack('<IH',data);return dict(offset=at,data=self.blob[at:at+count].hex())
        return {}

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def respond(self,status,raw):
        self.send_response(status);self.send_header('X-Device-ID','esp32-ffffffffffff' if self.server.bad_id else self.server.device_id);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):self.respond(200,json.dumps(self.server.info()).encode())
    def do_POST(self):
        if self.headers.get('X-Device-ID')!=self.server.device_id or self.headers.get('X-Device-Key')!=self.server.key:return self.respond(403,b'Identity/key mismatch')
        request,op,data=decode(self.rfile.read(int(self.headers['Content-Length'])))
        raw=self.server.cache.get(request)
        if raw is None:
            result=self.server.operation(op,data);raw=frame(request+int(self.server.bad_request),'OK',json.dumps(result).encode());self.server.cache[request]=raw
        if self.server.bad_crc:raw=raw[:-3]+b'00\n'
        self.respond(200,raw)

class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.a,self.b=Module(1),Module(2);self.directory=tempfile.TemporaryDirectory();self.pairs=Pairings(Path(self.directory.name)/'pairs.json')
        for module in (self.a,self.b):self.pairs.save(module.pairing())
    def tearDown(self):self.a.close();self.b.close();self.directory.cleanup()
    def app(self,module):
        app=Studio('/not-needed');app.pairings=self.pairs;app.network_devices=[dict(self.a.info(),paired=True),dict(self.b.info(),paired=True)]
        state=app.network_connect({'device_id':module.device_id});self.assertEqual(state['hello']['device_id'],module.device_id)
        app.artifacts['test']=Artifact(GRAPH,SOURCE,dict(fm1_admitted=True,continuous=True));return app
    def upload(self,app,module):
        return app.upload(dict(artifact='test',slot=1,name='Network test',expected=module.slots[1].copy(),device_id=module.device_id))
    def test_two_same_name_modules_receive_only_their_target(self):
        app=self.app(self.b);self.a.calls.clear();self.b.calls.clear();result=self.upload(app,self.b)
        self.assertTrue(result['saved'] and result['verified']);self.assertEqual(self.a.calls,[])
        self.assertEqual(self.b.blob,GRAPH+SOURCE);self.assertIn('INSTALL',self.b.calls);self.assertNotIn('PANIC',self.b.calls)
    def test_wrong_target_and_missing_target_never_transfer(self):
        app=self.app(self.a);self.a.calls.clear()
        for target in (None,self.b.device_id):
            with self.assertRaises(Problem):app.upload(dict(artifact='test',slot=1,name='Bad',device_id=target))
        self.assertEqual(self.a.calls,[])
    def test_usb_network_setup_rejects_stale_module_identity(self):
        class USB:
            def request(self,*args):raise AssertionError('Must reject before sending credentials')
        app=Studio('/not-needed');app.device=USB();app.device_info={'device_id':self.a.device_id,'wifi_upload':True}
        with self.assertRaisesRegex(Problem,'different module'):app.network_setup({'device_id':self.b.device_id,'ssid':'test','password':'12345678','name':'Module B'})
    def test_disconnected_stale_browser_reports_connection_problem(self):
        app=Studio('/not-needed')
        with self.assertRaisesRegex(Problem,'Connect the device first'):app.check_target({'device_id':self.a.device_id})
    def test_switch_from_same_usb_module_retains_read_only_audio_monitor(self):
        class Monitor:
            closed=False
            def close(self):self.closed=True
        app=Studio('/not-needed');monitor=app.device=Monitor();telemetry=app.telemetry
        app.device_info={'device_id':self.a.device_id};app.pairings=self.pairs;app.network_devices=[self.a.info()]
        app.network_connect({'device_id':self.a.device_id})
        self.assertIs(app.usb_monitor,monitor);self.assertIs(app.telemetry,telemetry);self.assertFalse(monitor.closed)
        app.disconnect();self.assertTrue(monitor.closed);self.assertIsNone(app.usb_monitor)
    def test_unplugged_log_monitor_does_not_drop_wifi_control(self):
        class BrokenLink:
            @property
            def in_waiting(self):raise OSError('Cable unplugged')
        class Monitor:
            link=BrokenLink()
            closed=threading.Event()
            def close(self):self.closed.set()
        app=self.app(self.a);device=app.device;monitor=app.usb_monitor=Monitor();app.start_reader()
        try:
            self.assertTrue(monitor.closed.wait(2));self.assertIsNone(app.usb_monitor)
            self.assertIs(app.device,device);self.assertEqual(app.device.hello()['device_id'],self.a.device_id)
        finally:app.close()
    def test_changed_ip_identity_is_rejected_before_any_command(self):
        wrong=dict(self.b.info(),device_id=self.a.device_id)
        with self.assertRaisesRegex(RuntimeError,'different device'):NetworkDevice(wrong,self.a.pairing())
        self.assertEqual(self.b.calls,[])
    def test_per_request_identity_crc_and_sequence_checks(self):
        for attribute,expected in (('bad_id','identity changed'),('bad_crc','CRC'),('bad_request','request ID')):
            device=NetworkDevice(self.a.info(),self.a.pairing());setattr(self.a,attribute,True)
            try:
                with self.assertRaisesRegex((RuntimeError,ValueError),expected):device.request('STATUS')
            finally:setattr(self.a,attribute,False)
    def test_wrong_pairing_key_is_rejected(self):
        device=NetworkDevice(self.a.info(),dict(self.a.pairing(),key='f'*64))
        with self.assertRaisesRegex(RuntimeError,'403'):device.request('STATUS')
        self.assertEqual(self.a.calls,[])
    def test_pairings_are_private_and_public_results_exclude_keys(self):
        self.assertEqual(self.pairs.path.stat().st_mode&0o777,0o600)
        self.assertEqual(len(self.pairs.public()),2);self.assertNotIn('key',json.dumps(self.pairs.public()))
        with self.assertRaises(ValueError):self.pairs.get('esp32-000000000003')
    def test_discovery_deduplicates_by_id_not_name_and_handles_saved_ips(self):
        with patch('network.socket.socket') as sock:
            sock.return_value.recvfrom.side_effect=socket.timeout()
            with patch('network.time.monotonic',side_effect=[0,0,2]),patch('network.identity',side_effect=lambda ip,port,timeout: self.a.info() if port==self.a.server_port else self.b.info()):rows=discover(self.pairs)
        self.assertEqual({row['device_id'] for row in rows},{self.a.device_id,self.b.device_id});self.assertTrue(all(row['online'] and row['paired'] for row in rows))
    def test_broadcast_concurrently_sends_identical_bytes_only_to_reviewed_modules(self):
        app=self.app(self.a)
        plan=app.broadcast_prepare({'target':'sound'})
        self.assertEqual(len(plan['recipients']),2)
        barrier=threading.Barrier(2);self.a.begin_barrier=self.b.begin_barrier=barrier
        app.network_devices.append(dict(device_id='esp32-000000000003',online=True,paired=True))
        result=app.broadcast_upload(dict(plan=plan['plan'],artifact='test',name='Broadcast'))
        self.assertTrue(result['verified']);self.assertEqual(len(result['results']),2)
        self.assertEqual(self.a.blob,GRAPH+SOURCE);self.assertEqual(self.b.blob,self.a.blob)
        self.assertEqual(result['graph_sha256'],hashlib.sha256(GRAPH).hexdigest())
        with self.assertRaisesRegex(Problem,'Refresh'):app.broadcast_upload(dict(plan=plan['plan'],artifact='test'))

    def test_broadcast_failure_is_reported_per_node_and_others_finish(self):
        app=self.app(self.a);plan=app.broadcast_prepare({'target':'sound'});self.b.bad_crc=True
        result=app.broadcast_upload(dict(plan=plan['plan'],artifact='test',name='Broadcast'))
        self.assertFalse(result['verified']);by_id={r['device_id']:r for r in result['results']}
        self.assertTrue(by_id[self.a.device_id]['verified']);self.assertIn('CRC',by_id[self.b.device_id]['error'])

    def test_broadcast_rejects_changed_destination_before_sending_that_node(self):
        app=self.app(self.a);plan=app.broadcast_prepare({'target':'sound'})
        self.b.slots[1]['generations']=[9,0];self.b.calls.clear()
        result=app.broadcast_upload(dict(plan=plan['plan'],artifact='test',name='Broadcast'))
        self.assertFalse(result['verified']);self.assertNotIn('BEGIN',self.b.calls);self.assertEqual(self.a.blob,GRAPH+SOURCE)

    def test_broadcast_excludes_offline_and_unpaired_modules(self):
        app=self.app(self.a);app.network_devices[1]['paired']=False
        plan=app.broadcast_prepare({'target':'sound'});self.assertEqual([r['device_id'] for r in plan['recipients']],[self.a.device_id])
        app.network_devices[0]['online']=False
        with self.assertRaisesRegex(Problem,'paired online'):app.broadcast_prepare({'target':'sound'})

    def test_broadcast_master_does_not_replace_either_main(self):
        app=self.app(self.a);self.upload(app,self.a)
        plan=app.broadcast_prepare({'target':'master'})
        app.artifacts['fx']=Artifact(GRAPH,SOURCE,dict(target='master',master_admitted=True,fm1_admitted=True))
        result=app.broadcast_upload(dict(plan=plan['plan'],artifact='fx',name='Broadcast FX'))
        self.assertTrue(result['verified']);self.assertEqual(self.a.blob,GRAPH+SOURCE);self.assertEqual(self.b.blob,b'')
        self.assertEqual(self.a.master_blob,self.b.master_blob);self.assertEqual(self.a.master_slot,1)

    def test_broadcast_expired_or_wrong_destination_never_transfers(self):
        app=self.app(self.a);plan=app.broadcast_prepare({'target':'master'});self.a.calls.clear();self.b.calls.clear()
        for token in (None,[],{}):
            with self.assertRaisesRegex(Problem,'Refresh'):app.broadcast_upload(dict(plan=token,artifact='test'))
        with self.assertRaisesRegex(Problem,'destination'):app.broadcast_upload(dict(plan=plan['plan'],artifact='test'))
        self.assertEqual(self.a.calls,[]);self.assertEqual(self.b.calls,[])
        plan=app.broadcast_prepare({'target':'sound'});app.broadcast_plans[plan['plan']]['created']-=601
        with self.assertRaisesRegex(Problem,'Refresh'):app.broadcast_upload(dict(plan=plan['plan'],artifact='test'))

    def test_public_urls_redirects_and_invalid_endpoints_are_not_accepted(self):
        for address in ('8.8.8.8','http://192.168.1.1','user@192.168.1.1','example.com','0.0.0.0','224.0.0.1'):
            with self.assertRaises(ValueError):endpoint(address)
        self.a.bad_id=True
        with self.assertRaisesRegex(RuntimeError,'identity mismatch'):identity('127.0.0.1',self.a.server_port)

if __name__=='__main__':unittest.main(verbosity=2)
