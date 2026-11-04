#!/usr/bin/env python3
"""Local browser compiler/uploader. Run with `sh host/studio.sh`.

SuperCollider executes trusted source on the host. No audio server is started by
the compiler wrapper. HTTP binds only to loopback; API access needs the session
token carried by the launch URL. Serial requests are never pipelined.
"""
import argparse
import base64
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
from pathlib import Path
import secrets
import shutil
import struct
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlsplit
import webbrowser

from engine_profile import generate
from patches import Device, ROOT, compile_source, manifest
from network import NetworkDevice, Pairings, discover

WEB = ROOT / 'host/web'
MAX_BODY = 512 * 1024


class Problem(Exception):
    def __init__(self, message, status=400, **details):
        super().__init__(message)
        self.status, self.details = status, details


class AudioTelemetry:
    """Retain numeric audio diagnostics only, never package/source protocol data."""
    fields = {'frame','active','render_max_us','combined_max_us','write_fail','partial',
              'overflow','dma_event_overflow','faults','clips','nonfinite','average_x10','peak_x10',
              'internal_free','internal_min','internal_largest','psram_free','stack_free_bytes',
              'controls_stack_free_bytes'}

    def __init__(self):
        self.pending = b''
        self.values = {}
        self.seen = {}
        self.peak = None
        self.peak_skip = 0
        self.peak_windows = 0
        self.peak_generation = 0
        self.lock = threading.Lock()

    def write(self, data):
        self.pending += data
        while b'\n' in self.pending:
            line, _, self.pending = self.pending.partition(b'\n')
            if b'synthdef:' not in line or line.startswith(b'@SD1 '):
                continue
            values = {key:int(value) for key,value in re.findall(r'\b([a-z_][a-z_0-9]*)=(\d+)',line.decode(errors='replace')) if key in self.fields}
            if values:
                with self.lock:
                    now = time.monotonic()
                    self.values.update(values); self.values['updated'] = now
                    self.seen.update({key:now for key in values})
                    peak=values.get('peak_x10')
                    if peak is not None and peak<0xffffffff:
                        if self.peak_skip:self.peak_skip-=1
                        else:
                            self.peak=peak if self.peak is None else max(self.peak,peak)
                            self.peak_windows+=1
        if len(self.pending)>8192:self.pending=b''

    def flush(self):
        pass

    def reset_peak(self):
        with self.lock:
            self.peak=None;self.peak_windows=0;self.peak_generation+=1
            # The first received reporting window may straddle the click.
            # Skip it; the following complete window starts the new reading.
            self.peak_skip=1

    def snapshot(self):
        with self.lock:
            now = time.monotonic()
            return dict(self.values, ages={key:max(0, now-stamp) for key,stamp in self.seen.items()},
                        peak_tracking=True,peak_since_reset_x10=self.peak,peak_windows=self.peak_windows,
                        peak_waiting=self.peak is None,peak_generation=self.peak_generation)


@contextmanager
def exclusive(lock, message, timeout=0):
    if not lock.acquire(timeout=timeout):
        raise Problem(message, 409)
    try:
        yield
    finally:
        lock.release()


def text_bytes(value):
    if not isinstance(value, str):
        raise Problem('Source must be text')
    try:
        raw = value.encode('utf-8')
    except UnicodeError as error:
        raise Problem('Source must be valid UTF-8') from error
    if len(raw) > 65536 or b'\0' in raw:
        raise Problem('Source must fit in 64 KiB and cannot contain NUL')
    return raw


def slot_number(value):
    if type(value) is not int or value != 1:
        raise Problem('Main uses slot 1; other sound slots are archived')
    return value


def check_graph_limits(info, hello):
    """Reject an expanded graph before transfer to an older/smaller firmware."""
    limits=hello.get('graph_limits')
    if limits is None:
        if hello.get('policy')!='fm1-compat-v1':return
        limits=dict(nodes=160,signals=192,inputs=1024)
    if not isinstance(limits,dict):raise Problem('Device reported invalid graph limits')
    for key in ('nodes','signals','inputs','audio_buffers'):
        maximum=limits.get(key)
        if maximum is None:continue
        if type(maximum) is not int or maximum<0:raise Problem('Device reported invalid graph limits')
        if info.get(key,0)>maximum:
            raise Problem(f'This graph needs {info[key]} {key}; connected firmware allows {maximum}. Update the firmware or simplify the graph.')


class Compiler:
    def __init__(self, sclang):
        self.sclang = Path(sclang)
        self.lock = threading.Lock()

    def validator(self):
        build = ROOT / 'build/host/studio'
        source = generate(build / 'src', 'fm1')
        component = ROOT / 'firmware/components/patches'
        files = [*sorted(source.iterdir()), component/'patch_format.c',
                 *sorted((component/'include').glob('*.h')),
                 ROOT/'firmware/components/instrument/include/playback_mode.h', ROOT/'host/studio_probe.c']
        digest = hashlib.sha256(b''.join(p.read_bytes() for p in files)).hexdigest()
        binary, stamp = build/'inspect', build/'inspect.sha256'
        if not binary.exists() or not stamp.exists() or stamp.read_text() != digest:
            cc = shutil.which('cc')
            if not cc:
                raise Problem('Graph checks need a C compiler. Install the Command Line Tools (cc).', 503)
            result = subprocess.run([cc, '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror',
                '-fno-fast-math', '-ffp-contract=off', '-DPATCH_FM1_COMPAT=1',
                '-I'+str(source), '-I'+str(component/'include'), str(source/'fm_load.c'),
                str(source/'fm_render.c'), str(component/'patch_format.c'),
                str(ROOT/'host/studio_probe.c'), '-lm', '-o', str(binary)],
                capture_output=True, text=True, timeout=60)
            if result.returncode:
                raise Problem('Could not build the graph checker:\n'+result.stderr[-8000:], 503)
            stamp.write_text(digest)
        return binary

    def compile(self, payload, wait=False):
        with exclusive(self.lock, 'A compilation is already running', timeout=60 if wait else 0):
            source = text_bytes(payload.get('source', ''))
            target=payload.get('target','sound')
            if type(payload.get('definition',False)) is not bool:raise Problem('Definition mode must be true or false')
            if target not in ('sound','master'):raise Problem('Choose Sound or Master FX')
            binary_input = payload.get('graph')
            with tempfile.TemporaryDirectory(prefix='synthdef-studio-') as folder:
                graph_path, source_path = Path(folder)/'patch.scsyndef', Path(folder)/'source.scd'
                compiler_log = ''
                input_kind = 'compiled_file'
                if binary_input is None:
                    if not source.strip():
                        raise Problem('Paste source or open a source file first')
                    if not self.sclang.is_file():
                        raise Problem('SuperCollider compiler not found. Install SuperCollider or pass --sclang PATH.', 503)
                    source_path.write_bytes(source)
                    compilation = compile_source(source_path, graph_path, self.sclang, target, definition=payload.get('definition',False))
                    compiler_log, input_kind = compilation['compiler_log'], compilation['input_kind']
                    pairing = 'compiled_from_source'
                else:
                    if not isinstance(binary_input, str) or len(binary_input) > 87384:
                        raise Problem('Compiled file must fit in 64 KiB')
                    try:
                        graph = base64.b64decode(binary_input, validate=True)
                    except (ValueError, base64.binascii.Error) as error:
                        raise Problem('Invalid compiled file encoding') from error
                    if not 0 < len(graph) <= 65536:
                        raise Problem('Compiled file must fit in 64 KiB')
                    graph_path.write_bytes(graph)
                    pairing = 'attached_source_not_recompiled' if source else 'binary_without_source'
                graph = graph_path.read_bytes()
                result = subprocess.run([str(self.validator()), str(graph_path), str(int(payload.get('definition',False)))],
                    capture_output=True, text=True, timeout=15)
                if result.returncode:
                    raise Problem('Graph inspection failed: '+result.stderr[-4000:])
                info = json.loads(result.stdout)
                if payload.get('args'):
                    if not info.get('loaded'):raise Problem('Invalid SynthDef')
                    from control_client import defaults
                    definitions=[dict(c,name=bytes.fromhex(c['name_hex']).decode('utf8')) for c in info['controls']]
                    graph=defaults(graph,payload['args'],dict(controls=definitions));graph_path.write_bytes(graph)
                    result=subprocess.run([str(self.validator()),str(graph_path),str(int(payload.get('definition',False)))],capture_output=True,text=True,timeout=15,check=True)
                    info=json.loads(result.stdout)
                error = bytes.fromhex(info.pop('error_hex')).decode('utf-8', errors='replace')
                if not info.pop('loaded'):
                    raise Problem('Unsupported or invalid SynthDef: '+error)
                info['name'] = bytes.fromhex(info.pop('name_hex')).decode('utf-8', errors='replace')
                master_error=bytes.fromhex(info.pop('master_error_hex')).decode('utf-8',errors='replace')
                info['definition']=bool(payload.get('definition',False))
                info.update(target=target,admitted=info['master_admitted'] if target=='master' else info['fm1_admitted'])
                if target=='master':error=master_error
                for control in info['controls']:
                    control['name'] = bytes.fromhex(control.pop('name_hex')).decode('utf-8', errors='replace')
                info.update(graph_bytes=len(graph), source_bytes=len(source),
                    graph_sha256=hashlib.sha256(graph).hexdigest(),
                    source_sha256=hashlib.sha256(source).hexdigest(), admission_error=error,
                    source_pairing=pairing, compiler_log=compiler_log, input_kind=input_kind)
                info['ugens'] = list(dict.fromkeys(info['ugens']))
                return graph, source, info


@dataclass(frozen=True)
class Artifact:
    graph: bytes
    source: bytes
    info: dict


class Studio:
    def __init__(self, sclang):
        self.compiler = Compiler(sclang)
        self.device = None
        self.usb_monitor = None
        self.device_info = None
        self.device_port = None
        self.device_lock, self.artifact_lock = threading.Lock(), threading.Lock()
        self.capture_lock = threading.Lock()
        self.artifacts = OrderedDict()
        self.stop_reader = threading.Event()
        self.reader = None
        self.telemetry = AudioTelemetry()
        self.pairings = Pairings()
        self.network_devices = []

    def start_reader(self):
        def drain():
            while not self.stop_reader.wait(.25):
                if not self.device_lock.acquire(blocking=False):
                    continue
                try:
                    # Consume idle console output without competing with an ACK reader.
                    source=self.usb_monitor or self.device
                    if source and source.link and source.link.in_waiting:
                        for _ in source.lines():
                            pass
                except OSError:
                    if self.usb_monitor:
                        # Losing an optional log cable must not drop Wi-Fi control.
                        monitor,self.usb_monitor=self.usb_monitor,None
                        try:monitor.close()
                        except OSError:pass
                    else:self.disconnect()
                finally:
                    self.device_lock.release()
        self.reader = threading.Thread(target=drain, daemon=True)
        self.reader.start()

    def close(self):
        self.stop_reader.set()
        if self.reader:
            self.reader.join(timeout=2)
        with self.device_lock:
            self.disconnect()

    def ports(self):
        try:
            from serial.tools import list_ports
        except ImportError:
            return [], False
        ports = sorted(list_ports.comports(), key=lambda p: (p.vid != 0x303A, p.device))
        return [dict(port=p.device, name=p.description, esp32=p.vid == 0x303A) for p in ports], True

    def config(self):
        ports, serial_ready = self.ports()
        return dict(ports=ports, serial_ready=serial_ready,
            compiler_ready=self.compiler.sclang.is_file(),
            connected=self.device is not None,
            paired_devices=self.pairings.public(),
            example=(ROOT/'examples/main-patch.scd').read_text(),master_example=(ROOT/'examples/master-fx.scd').read_text())

    def compile(self, payload):
        graph, source, info = self.compiler.compile(payload)
        token = secrets.token_hex(16)
        with self.artifact_lock:
            self.artifacts[token] = Artifact(graph, source, info)
            while len(self.artifacts) > 8:
                self.artifacts.popitem(last=False)
        return dict(artifact=token, **info)

    def artifact(self, token):
        with self.artifact_lock:
            artifact = self.artifacts.get(token) if isinstance(token, str) else None
        if artifact is None:
            raise Problem('This compile result has expired. Compile or check the file again.', 404)
        return artifact

    def disconnect(self):
        if self.device:
            self.device.close()
        if self.usb_monitor:
            self.usb_monitor.close();self.usb_monitor=None
        self.device = self.device_info = self.device_port = None

    def connected(self):
        if not self.device:
            raise Problem('Connect the device first', 409)
        return self.device

    def audio_snapshot(self):
        """Cached diagnostics only; caller holds device_lock, no device requests."""
        if not self.device:
            return dict(connected=False, device_id=None, source=None)
        usb = self.usb_monitor is not None or not isinstance(self.device, NetworkDevice)
        values = self.telemetry.snapshot() if usb else {}
        return dict(values, connected=True, device_id=self.device_info.get('device_id'),
                    source='usb' if usb else None)

    def reset_audio_peak(self,payload):
        if not self.device_info or payload.get('device_id')!=self.device_info.get('device_id'):
            raise Problem('Choose the connected module before resetting its peak',409)
        if self.audio_snapshot().get('source')!='usb':
            raise Problem('Peak measurement needs the module’s USB diagnostics',409)
        self.telemetry.reset_peak()
        return self.audio_snapshot()

    def state(self):
        d = self.connected()
        state=dict(connected=True, port=self.device_port, hello=self.device_info,
                    status=d.request('STATUS'), slots=d.request('LIST'), audio=self.audio_snapshot())
        if self.device_info.get('master_slots')==2:state['masters']=d.request('FXLIST')
        if self.device_info.get('global_volume'):state['volume_percent']=self.volume_value(d.request('VOLUME'))
        state['connection']=dict(transport='wifi' if isinstance(d,NetworkDevice) else 'usb',
            device_id=self.device_info.get('device_id'),device_name=self.device_info.get('device_name'),address=self.device_port)
        return state

    @staticmethod
    def volume_value(reply):
        percent=reply.get('percent')
        if type(percent) is not int or not 0<=percent<=100:
            raise Problem('The module did not confirm its output volume',409)
        return percent

    def volume(self,payload):
        self.check_target(payload)
        if not payload.get('device_id') or payload['device_id']!=self.device_info.get('device_id'):
            raise Problem('Choose the connected module before changing volume',409)
        if not self.device_info.get('global_volume'):
            raise Problem('This firmware does not support module volume',409)
        percent=payload.get('percent');save=payload.get('save',False)
        if type(percent) is not int or not 0<=percent<=100 or type(save) is not bool:
            raise Problem('Volume must be a whole percentage from 0 to 100')
        d=self.connected();actual=self.volume_value(d.request('VOLUME',bytes([percent])))
        if actual!=percent:raise Problem('The module did not confirm the requested volume',409)
        if save:
            if self.volume_value(d.request('VOLSAVE'))!=percent:
                raise Problem('The module did not confirm the saved volume',409)
        return dict(device_id=self.device_info['device_id'],percent=actual,saved=save)

    def check_target(self,payload):
        if not self.device or not self.device_info:raise Problem('Connect the device first',409)
        if isinstance(self.device,NetworkDevice) and payload.get('device_id')!=self.device.device_id:
            raise Problem('Selected module changed. Reconnect and choose its destination again.',409)
        if payload.get('device_id') and payload['device_id']!=self.device_info.get('device_id'):
            raise Problem('The request targets a different module',409)

    def profile_ugens(self,payload):
        """Explicit muted maintenance, borrowing USB without closing/reopening it."""
        self.check_target(payload)
        if payload.get('device_id')!=self.device_info.get('device_id'):
            raise Problem('Name the exact module for profiling',409)
        if isinstance(self.device,NetworkDevice):raise Problem('Use USB for UGen profiling',409)
        fixed=payload.get('fixed',True)
        if type(fixed) is not bool:raise Problem('Fixed profiling mode must be true or false')
        if self.volume_value(self.device.request('VOLUME'))!=0:
            raise Problem('Mute the module before UGen profiling',409)
        from profile_ugens import collect
        try:result=collect(self.device,fixed=fixed)
        except (AssertionError,KeyError,ValueError) as error:
            raise Problem('Profiler output failed validation; check the diagnostic firmware and result before retrying',409) from error
        return dict(device_id=self.device_info['device_id'],**result)

    def network_scan(self,payload):
        self.network_devices=discover(self.pairings,payload.get('address') or None)
        return dict(devices=self.network_devices)

    def broadcast_prepare(self,payload):
        target=payload.get('target')
        if target not in ('sound','master'):raise Problem('Choose Main or FX')
        # Freeze identities and destination generations for this review. Devices
        # discovered later cannot silently join an already prepared broadcast.
        rows=[dict(row) for row in self.network_devices if row.get('online') and row.get('paired')]
        if not rows:raise Problem('Find paired online Wi-Fi modules first',409)
        if len(rows)>64:raise Problem('A broadcast supports up to 64 modules')
        def inspect(row):
            d=None
            try:
                d=NetworkDevice(row,self.pairings.get(row['device_id']));hello=d.hello()
                entries=d.request('FXLIST' if target=='master' else 'LIST')
                entry=next(e for e in entries if e['slot']==1)
                return dict(row,ready=True,expected=entry)
            except Exception as error:return dict(row,ready=False,error=str(error))
            finally:
                if d:d.close()
        with ThreadPoolExecutor(max_workers=min(8,len(rows))) as pool:recipients=list(pool.map(inspect,rows))
        if not hasattr(self,'broadcast_plans'):self.broadcast_plans=OrderedDict()
        now=time.monotonic()
        self.broadcast_plans=OrderedDict((k,v) for k,v in self.broadcast_plans.items() if now-v['created']<600)
        while len(self.broadcast_plans)>=8:self.broadcast_plans.popitem(last=False)
        token=secrets.token_urlsafe(24)
        self.broadcast_plans[token]=dict(target=target,recipients=recipients,created=now)
        return dict(plan=token,target=target,recipients=recipients)

    def broadcast_upload(self,payload):
        artifact=self.artifact(payload.get('artifact'))
        token=payload.get('plan')
        if not isinstance(token,str):raise Problem('Refresh the broadcast recipients before uploading',409)
        plan=getattr(self,'broadcast_plans',{}).pop(token,None)
        if not plan or time.monotonic()-plan['created']>=600:
            raise Problem('Refresh the broadcast recipients before uploading',409)
        if plan['target']!=artifact.info.get('target','sound'):
            raise Problem('Compile for the reviewed Main or FX destination',409)
        def send(row):
            result={k:row[k] for k in ('device_id','device_name','address')}
            if not row['ready']:return dict(result,verified=False,error=row['error'])
            worker=Studio(str(self.compiler.sclang))
            try:
                worker.device=NetworkDevice(row,self.pairings.get(row['device_id']))
                worker.device_info=worker.device.hello();worker.device_port=row['address']
                worker.artifacts['broadcast']=artifact
                uploaded=worker.upload(dict(payload,artifact='broadcast',slot=1,
                    expected=row['expected'],replace=True,device_id=row['device_id']))
                return dict(result,verified=uploaded['verified'],name=uploaded['name'])
            except Exception as error:return dict(result,verified=False,error=str(error))
            finally:worker.close()
        with ThreadPoolExecutor(max_workers=min(8,len(plan['recipients']))) as pool:
            results=list(pool.map(send,plan['recipients']))
        return dict(target=plan['target'],graph_sha256=hashlib.sha256(artifact.graph).hexdigest(),
            source_sha256=hashlib.sha256(artifact.source).hexdigest(),results=results,
            verified=all(row['verified'] for row in results))

    def network_connect(self,payload):
        device_id=payload.get('device_id')
        selected=next((row for row in self.network_devices if row['device_id']==device_id and row.get('online')),None)
        if selected is None:raise Problem('Scan and select an online module first',409)
        device=NetworkDevice(selected,self.pairings.get(device_id))
        try:
            hello=device.hello()
            self.pairings.save(dict(self.pairings.get(device_id),device_name=hello.get('device_name',selected['device_name']),address=selected['address'],port=selected['port']))
        except Exception:device.close();raise
        monitor=None
        if self.device and not isinstance(self.device,NetworkDevice) and self.device_info.get('device_id')==device_id:
            monitor=self.device;self.device=None
        self.disconnect();self.usb_monitor=monitor;self.device,self.device_info=device,hello
        self.device_port=selected['address']
        if not monitor:self.telemetry=AudioTelemetry()
        return self.state()

    def network_setup(self,payload):
        device=self.connected()
        self.check_target(payload)
        if isinstance(device,NetworkDevice):raise Problem('Use USB to configure or pair a module')
        if not self.device_info.get('wifi_upload'):raise Problem('Update the board firmware to enable Wi-Fi uploads')
        if payload.get('ssid'):
            ssid,password,name=(payload.get(k) for k in ('ssid','password','name'))
            if not all(isinstance(x,str) for x in (ssid,password,name)):raise Problem('Enter network details and a module name')
            if not 0<len(ssid.encode())<=32 or not (len(password.encode())==0 or 8<=len(password.encode())<=63):raise Problem('Wi-Fi name must fit 32 bytes and password must be empty or 8–63 bytes')
            if not re.fullmatch(r'[A-Za-z0-9 _-]{1,31}',name):raise Problem('Use 1–31 letters, digits, spaces, underscores or hyphens for the module name')
            settings=dict(ssid=ssid,password=password,name=name)
            device.request('NETCFG',json.dumps(settings,ensure_ascii=False,separators=(',',':')).encode())
        info=device.request('NETPAIR');self.pairings.save(info)
        self.device_info=device.hello()
        return {k:v for k,v in info.items() if k!='key'}

    def connect(self, port):
        ports, ready = self.ports()
        if not ready:
            raise Problem('USB support needs pyserial. Launch with sh host/studio.sh or install host/requirements.txt.', 503)
        if port not in [p['port'] for p in ports]:
            raise Problem('That USB port is no longer available; refresh the port list')
        self.disconnect()
        self.telemetry = AudioTelemetry()
        device = Device(port, self.telemetry)
        try:
            if hasattr(device.link, 'exclusive'):
                device.link.exclusive = True
            hello = device.hello()
        except Exception:
            device.close()
            raise
        self.device, self.device_info, self.device_port = device, hello, port
        return self.state()

    def capture_audio(self,payload):
        seconds=payload.get('seconds',1)
        if type(seconds) not in (int,float) or not 0<seconds<=1:raise Problem('Capture duration must be greater than zero and at most one second')
        from capture import capture
        studio=self
        with exclusive(self.capture_lock,'A capture is already in progress',timeout=0):
            with self.device_lock:
                self.check_target(payload);owner=self.connected()
            class Connection:
                def call(self,function):
                    with studio.device_lock:
                        if studio.device is not owner:raise Problem('Device changed during capture; select the intended module again',409)
                        studio.check_target(payload)
                        return function()
                def hello(self):return self.call(owner.hello)
                def request(self,*args,**kwargs):return self.call(lambda:owner.request(*args,**kwargs))
            try:pcm,info=capture(Connection(),seconds)
            except (OSError,TimeoutError) as error:
                raise Problem('Capture connection failed: '+str(error)+'. Check the module connection before retrying.',409) from error
        return dict(rate=info['rate'],channels=2,frames=info['frames'],format='s16le',data=base64.b64encode(pcm).decode('ascii'))

    def read_active(self, slot=None,master=False):
        d=self.connected()
        previous=None
        if slot is not None:
            if type(slot) is not int or slot not in ((0,1) if master else (1,)):
                raise Problem('Choose Main or FX')
            if master:
                previous=next(e['slot'] for e in d.request('FXLIST') if e.get('selected'))
                if previous!=slot:d.request('FXLOAD',bytes([slot]))
            else:
                d.request('LOAD', bytes([slot]))
                if not d.request('STATUS').get('continuous'):d.request('PANIC')
        try:
            graph, source, info = d.download(master=True) if master else d.download()
        finally:
            if previous is not None and previous!=slot:d.request('FXLOAD',bytes([previous]))
        meta = bytes.fromhex(info['manifest'])
        field = lambda start, size: meta[start:start+size].split(b'\0', 1)[0].decode('ascii')
        return dict(slot=info['slot'], graph=base64.b64encode(graph).decode(), source=source.decode('utf-8'),
                    name=field(76, 32), labels=[field(i, 12) for i in range(108, 156, 12)], mapping=meta[156],definition=bool(meta[157]&1))

    def main_load(self,payload):
        self.check_target(payload)
        if not any(e['slot']==1 and e['name'] for e in self.connected().request('LIST')):
            raise Problem('Upload a Main patch first',409)
        self.connected().request('LOAD',b'\x01')
        return self.state()

    def upload(self, payload):
        self.check_target(payload)
        artifact = self.artifact(payload.get('artifact'))
        master=artifact.info.get('target')=='master'
        slot=payload.get('slot')
        if master:
            if type(slot) is not int or slot!=1:raise Problem('Only master FX slot 1 is writable; Bypass is protected')
        else:slot=slot_number(slot)
        name = payload.get('name')
        labels = payload.get('labels', ['X', 'Y', 'ATTACK', 'RELEASE'])
        mapping = payload.get('mapping', 1)
        if not isinstance(name, str) or not isinstance(labels, list) or any(not isinstance(x, str) for x in labels):
            raise Problem('Invalid patch name or control labels')
        if type(mapping) is not int:
            raise Problem('Invalid legacy mapping')
        _, expected_meta = manifest(artifact.graph, artifact.source, name, labels, mapping, transfer=1, definition=artifact.info.get('definition',False))
        d = self.connected()
        check_graph_limits(artifact.info,self.device_info)
        if master and self.device_info.get('master_slots')!=2:raise Problem('Update firmware to use the master slots')
        if master and not artifact.info.get('master_admitted'):raise Problem(artifact.info['admission_error'])
        if not master and self.device_info['policy'] == 'fm1-compat-v1' and not artifact.info['fm1_admitted']:
            raise Problem('This graph cannot be used as an instrument: '+artifact.info['admission_error'])
        if artifact.info.get('definition') and not self.device_info.get('definition_lifecycle'):raise Problem('Update device firmware to support definition-only uploads')
        if artifact.info.get('continuous') and not self.device_info.get('continuous_blocks'):
            raise Problem('This sound block needs firmware with continuous playback support. Update the device firmware first.')
        status = d.request('STATUS')
        if status['reset_required']:
            raise Problem('The board requires a restart before uploading', 409)
        def unchanged():
            entry = next((e for e in d.request('FXLIST' if master else 'LIST') if e['slot'] == slot), None)
            expected=payload.get('expected')
            if entry is None or not isinstance(expected,dict) or any(entry.get(k)!=expected.get(k) for k in ('slot','name','generations')):
                raise Problem('The destination slot changed. Refresh the slots before uploading.', 409)
            if entry['name'] and payload.get('replace') is not True:
                raise Problem('This slot is occupied. Choose Replace to overwrite it.', 409)
        unchanged()
        phase = 'transferring'
        try:
            staged = d.upload(artifact.graph, artifact.source, name, labels, mapping, activate=False,**({'definition':True} if artifact.info.get('definition') else {}),**({'master':True} if master else {}))
            try:
                unchanged()
            except Problem:
                d.request('ABORT')
                raise
            if self.device_info.get('atomic_install'):
                phase='installing'
                d.request('INSTALL',struct.pack('<IB',staged['transfer'],slot))
            else:
                phase = 'activating'
                d.request('ACTIVATE', struct.pack('<I', staged['transfer']))
                phase = 'saving'
                d.request('FXSAVE' if master else 'SAVE', bytes([slot]))
            phase = 'verifying'
            graph, source, info = d.download(master=True) if master else d.download()
            if (graph != artifact.graph or source != artifact.source or info['slot'] != slot or
                    bytes.fromhex(info['manifest'])[4:] != expected_meta[4:]):
                raise RuntimeError('Saved package readback does not match the compiled package')
            if not master and not artifact.info.get('continuous') and not artifact.info.get('definition'):
                d.request('PANIC')
            return dict(saved=True, verified=True, target='master' if master else 'sound',continuous=artifact.info.get('continuous',False), slot=slot, name=name, **self.state())
        except Exception as error:
            if isinstance(error, (OSError, TimeoutError)):
                self.disconnect()
            raise Problem('Upload did not finish ('+phase+'): '+str(error)+
                '. Inspect the device and refresh before retrying.', 409, phase=phase) from error


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, studio, ide=False):
        self.ide=None
        super().__init__(address, Handler)
        self.studio, self.token = studio, secrets.token_urlsafe(32)
        self.origins = {f'http://127.0.0.1:{self.server_port}', f'http://localhost:{self.server_port}'}
        self.ide=None
        if ide:
            from ide_bridge import Bridge
            self.ide=Bridge(studio,self.token)

    def server_close(self):
        if self.ide:self.ide.server_close()
        super().server_close()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def reply(self, status, body, kind='application/json; charset=utf-8', filename=None):
        if isinstance(body, dict):
            body = json.dumps(body, ensure_ascii=True).encode()
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        if filename:
            self.send_header('Content-Disposition', 'attachment; filename="'+filename+'"')
        self.end_headers()
        self.wfile.write(body)

    def guard(self, api=False):
        host = self.headers.get('Host', '')
        if 'http://'+host not in self.server.origins:
            raise Problem('Invalid local host', 403)
        origin = self.headers.get('Origin')
        if origin and origin not in self.server.origins:
            raise Problem('Cross-origin requests are not allowed', 403)
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise Problem('Cross-site requests are not allowed', 403)
        if api and not secrets.compare_digest(self.headers.get('X-Studio-Token', ''), self.server.token):
            raise Problem('Open the session URL printed by the host service', 403)

    def dispatch(self):
        path = urlsplit(self.path).path
        api = path.startswith('/api/')
        self.guard(api)
        studio = self.server.studio
        if self.command == 'GET':
            static = {'/': ('index.html', 'text/html; charset=utf-8'),
                      '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                      '/style.css': ('style.css', 'text/css; charset=utf-8')}
            if path in static:
                file, kind = static[path]
                return self.reply(200, (WEB/file).read_bytes(), kind)
            if path == '/api/config':
                return self.reply(200, studio.config())
            if path == '/api/audio':
                with exclusive(studio.device_lock, 'The device is busy. Wait for the current operation.'):
                    return self.reply(200, studio.audio_snapshot())
            if path.startswith('/api/artifact/'):
                token, _, extension = path.removeprefix('/api/artifact/').partition('.')
                artifact = studio.artifact(token)
                if extension not in ('scsyndef', 'scd'):
                    raise Problem('Unknown download', 404)
                return self.reply(200, artifact.graph if extension == 'scsyndef' else artifact.source,
                                  'application/octet-stream', 'patch.'+extension)
            raise Problem('Not found', 404)
        if self.command != 'POST' or not api:
            raise Problem('Not found', 404)
        if self.headers.get_content_type() != 'application/json' or self.headers.get('Transfer-Encoding'):
            raise Problem('Expected a JSON request')
        try:
            length = int(self.headers.get('Content-Length', '-1'))
        except ValueError:
            length = -1
        if not 0 <= length <= MAX_BODY:
            raise Problem('Request too large or missing length', 413)
        payload = json.loads(self.rfile.read(length))
        if not isinstance(payload, dict):
            raise Problem('Expected a JSON object')
        if path == '/api/compile':
            return self.reply(200, studio.compile(payload))
        if path == '/api/capture':
            return self.reply(200, studio.capture_audio(payload))
        with exclusive(studio.device_lock, 'The device is busy. Wait for the current operation.', timeout=.25):
            try:
                if path == '/api/connect':
                    result = studio.connect(payload.get('port'))
                elif path == '/api/network/scan':
                    result = studio.network_scan(payload)
                elif path == '/api/network/connect':
                    result = studio.network_connect(payload)
                elif path == '/api/network/broadcast-prepare':
                    result = studio.broadcast_prepare(payload)
                elif path == '/api/network/broadcast-upload':
                    result = studio.broadcast_upload(payload)
                elif path == '/api/network/setup':
                    result = studio.network_setup(payload)
                elif path == '/api/network/status':
                    result = studio.connected().request('NETINFO')
                elif path == '/api/network/nearby':
                    studio.check_target(payload)
                    if isinstance(studio.connected(),NetworkDevice):raise Problem('Use USB for network setup')
                    result = studio.connected().request('NETSCAN',timeout=25,retries=0)
                elif path == '/api/disconnect':
                    studio.disconnect(); result = dict(connected=False)
                elif path == '/api/refresh':
                    result = studio.state()
                elif path == '/api/panic':
                    studio.check_target(payload)
                    result = studio.connected().request('PANIC')
                elif path == '/api/volume':
                    result = studio.volume(payload)
                elif path == '/api/audio/reset-peak':
                    result = studio.reset_audio_peak(payload)
                elif path == '/api/diagnostics/ugen-profile':
                    result = studio.profile_ugens(payload)
                elif path == '/api/read-active':
                    studio.check_target(payload)
                    result = studio.read_active(payload.get('slot'),payload.get('target')=='master')
                elif path == '/api/master-load':
                    studio.check_target(payload)
                    slot=payload.get('slot')
                    if type(slot) is not int or slot not in (0,1):raise Problem('Choose Bypass or FX')
                    studio.connected().request('FXLOAD',bytes([slot]));result=studio.state()
                elif path == '/api/main-load':
                    result = studio.main_load(payload)
                elif path == '/api/upload':
                    result = studio.upload(payload)
                else:
                    raise Problem('Not found', 404)
                return self.reply(200, result)
            except (OSError, TimeoutError) as error:
                studio.disconnect()
                raise Problem('Device connection failed: '+str(error)+'. Reconnect and inspect the device before retrying.', 409) from error

    def handle_request(self):
        try:
            self.dispatch()
        except Problem as error:
            self.reply(error.status, dict(error=str(error), **error.details))
        except (ValueError, RuntimeError, UnicodeError, subprocess.SubprocessError) as error:
            self.reply(400, dict(error=str(error)[-16000:]))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as error:
            self.reply(500, dict(error='Host service error: '+str(error)))

    do_GET = do_POST = do_OPTIONS = handle_request


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', type=int, default=8765, help='Local web port, not a USB device')
    p.add_argument('--no-open', action='store_true')
    p.add_argument('--sclang', default=shutil.which('sclang') or '/Applications/SuperCollider.app/Contents/MacOS/sclang')
    args = p.parse_args()
    studio = Studio(args.sclang)
    server = Server(('127.0.0.1', args.port), studio, ide=True)
    studio.start_reader()
    url = f'http://127.0.0.1:{server.server_port}/#{server.token}'
    print('SynthDef Studio — local compiler and USB uploader\n'+url+'\nPress Ctrl-C to stop.', flush=True)
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        studio.close()


if __name__ == '__main__':
    main()
