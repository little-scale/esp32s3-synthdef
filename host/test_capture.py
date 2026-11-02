import struct
import unittest
import base64
import threading
import json
import http.client
from unittest.mock import patch
from studio import Studio,Problem,Server
from capture import capture
from patches import frame,decode

class CaptureDevice:
    def __init__(self):self.data=bytes(range(256))*4;self.reads=[]
    def hello(self):return dict(pcm_capture=1,rate=44100)
    def request(self,op,payload=b'',**kwargs):
        if op=='CAPBEGIN':self.frames=struct.unpack('<I',payload)[0];self.data=(self.data*((self.frames*4+1023)//1024))[:self.frames*4];return dict(recording=True)
        if op=='CAPINFO':return dict(state=2,frames=self.frames,requested=self.frames,channels=2,rate=44100,bytes=self.frames*4)
        offset,count=struct.unpack('<IH',payload);self.reads.append(count);return dict(offset=offset,data=self.data[offset:offset+count].hex())

class TaggedCaptureDevice(CaptureDevice):
    def hello(self):return dict(super().hello(),pcm_capture_chunk=1024,pcm_capture_id=1)
    def request(self,op,payload=b'',**kwargs):
        if op=='CAPREAD':
            capture_id=struct.unpack_from('<I',payload)[0]
            if capture_id!=self.capture_id:raise RuntimeError('Stale recording')
            result=super().request(op,payload[4:],**kwargs)
        else:
            result=super().request(op,payload,**kwargs)
            if op=='CAPBEGIN':self.capture_id=0xf1234567
        return dict(result,capture_id=self.capture_id)

class CaptureTests(unittest.TestCase):
    def test_capture_yields_usb_for_controls_between_chunks(self):
        app=Studio('/unused');paused=threading.Event();resume=threading.Event();results=[];failures=[]
        class LockedDevice(CaptureDevice):
            def hello(device):
                self.assertTrue(app.device_lock.locked());return super().hello()
            def request(device,op,*args,**kwargs):
                self.assertTrue(app.device_lock.locked())
                if op=='RCEVENT':return dict(queued=True)
                return super().request(op,*args,**kwargs)
        d=LockedDevice();app.device=d;app.device_info=dict(device_id='expected')
        def yield_usb(seconds):
            if not paused.is_set():paused.set();resume.wait(2)
        def run():
            try:results.append(app.capture_audio(dict(seconds=.01)))
            except Exception as error:failures.append(error)
        try:
            with patch('capture.time.sleep',side_effect=yield_usb):
                worker=threading.Thread(target=run,daemon=True);worker.start()
                self.assertTrue(paused.wait(2));self.assertTrue(app.device_lock.acquire(timeout=.2))
                try:self.assertTrue(d.request('RCEVENT')['queued'])
                finally:app.device_lock.release();resume.set()
                worker.join(2);self.assertFalse(worker.is_alive())
            self.assertFalse(failures);self.assertEqual(base64.b64decode(results[0]['data']),d.data)
        finally:resume.set();app.device=None;app.close()
    def test_device_change_aborts_before_reading_replacement(self):
        app=Studio('/unused');old=CaptureDevice();replacement=CaptureDevice();app.device=old;app.device_info=dict(device_id='expected')
        def replace(seconds):
            with app.device_lock:app.device=replacement
        try:
            with patch('capture.time.sleep',side_effect=replace),self.assertRaisesRegex(Problem,'changed during capture'):
                app.capture_audio(dict(seconds=.01))
            self.assertFalse(hasattr(replacement,'frames'))
        finally:app.device=None;app.close()
    def test_second_capture_is_rejected_without_rearming_device(self):
        app=Studio('/unused');d=CaptureDevice();app.device=d;app.device_info=dict(device_id='expected')
        attempted=[]
        def another_capture(seconds):
            if not attempted:
                attempted.append(True)
                with self.assertRaisesRegex(Problem,'already in progress'):app.capture_audio(dict(seconds=.01))
        try:
            with patch('capture.time.sleep',side_effect=another_capture):result=app.capture_audio(dict(seconds=.01))
            self.assertEqual(base64.b64decode(result['data']),d.data)
        finally:app.device=None;app.close()
    def test_http_route_does_not_hold_usb_for_entire_capture(self):
        app=Studio('/unused');app.device=CaptureDevice();app.device_info=dict(device_id='expected');server=Server(('127.0.0.1',0),app)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();original=app.capture_audio
        def capture_unlocked(payload):
            self.assertFalse(app.device_lock.locked());return original(payload)
        client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=3)
        try:
            with patch.object(app,'capture_audio',side_effect=capture_unlocked):
                client.request('POST','/api/capture',json.dumps(dict(seconds=.01)),headers={'Content-Type':'application/json','X-Studio-Token':server.token})
                response=client.getresponse();result=json.loads(response.read())
                self.assertEqual(response.status,200);self.assertEqual(result['frames'],441)
        finally:client.close();server.shutdown();server.server_close();thread.join();app.device=None;app.close()
    def test_studio_capture_checks_target_and_preserves_bytes(self):
        app=Studio('/unused');d=CaptureDevice();app.device=d;app.device_info=dict(device_id='expected')
        try:
            with self.assertRaises(Problem):app.capture_audio(dict(device_id='other',seconds=.01))
            with self.assertRaises(Problem):app.capture_audio(dict(seconds=True))
            result=app.capture_audio(dict(device_id='expected',seconds=.01))
            self.assertEqual(base64.b64decode(result['data']),d.data)
        finally:app.device=None;app.close()
    def test_exact_stereo_bytes(self):
        d=CaptureDevice();pcm,info=capture(d,.01)
        self.assertEqual(pcm,d.data);self.assertEqual(info['frames'],441)
        self.assertEqual(d.reads,[256]*6+[228])
    def test_larger_chunks_and_recording_ids(self):
        d=TaggedCaptureDevice();pcm,info=capture(d,.01)
        self.assertEqual(pcm,d.data);self.assertEqual(d.reads,[1024,740])
        self.assertEqual(info['capture_id'],d.capture_id)
    def test_invalid_advertised_chunk_limits_are_rejected(self):
        for chunk in (0,-1,True,1025,1.5):
            d=CaptureDevice();d.hello=lambda:dict(pcm_capture=1,rate=44100,pcm_capture_chunk=chunk)
            with self.assertRaisesRegex(ValueError,'chunk limit'):capture(d,.01)
            self.assertFalse(hasattr(d,'frames'))
    def test_invalid_recording_id_is_rejected(self):
        for value in (None,0,-1,True,0x100000000):
            class Bad(TaggedCaptureDevice):
                def request(self,op,*args,**kwargs):
                    result=super().request(op,*args,**kwargs)
                    if op=='CAPBEGIN':result['capture_id']=value
                    return result
            with self.assertRaisesRegex(ValueError,'identifier'):capture(Bad(),.01)
    def test_replaced_recordings_are_rejected_during_poll_and_read(self):
        for operation in ('CAPINFO','CAPREAD'):
            class Bad(TaggedCaptureDevice):
                def request(self,op,*args,**kwargs):
                    result=super().request(op,*args,**kwargs)
                    if op==operation:result['capture_id']+=1
                    return result
            with self.assertRaisesRegex(ValueError,'replaced'):capture(Bad(),.01)
    def test_full_capture_reply_fits_the_existing_wire_limit(self):
        body=json.dumps(dict(offset=176000,capture_id=0xffffffff,data=bytes(range(256)).hex()*4)).encode()
        wire=frame(31,'OK',body)
        self.assertLess(len(wire),9000);self.assertEqual(decode(wire),(31,'OK',body))
    def test_duration_limits(self):
        for duration in (0,-1,1.1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):capture(CaptureDevice(),duration)
    def test_mismatched_chunk_is_rejected(self):
        class Bad(CaptureDevice):
            def request(self,op,*args,**kwargs):
                value=super().request(op,*args,**kwargs)
                if op=='CAPREAD':value['offset']+=1
                return value
        with self.assertRaisesRegex(ValueError,'offset/length'):capture(Bad(),.01)
