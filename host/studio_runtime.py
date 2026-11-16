"""Studio USB runtime-aware uploads: immutable review, identity binding and jobs.

Installed pairs only. Firmware commissioning and Wi-Fi handoff are separate.
No payload is stored in a job reply or retried after an application restart.
"""
import base64
from collections import OrderedDict
from contextlib import contextmanager
import json
from pathlib import Path
import re
import secrets
import tempfile
import threading
import time

import dual_upload as dual

MAX_FILE = 128 + 65536 + 524288


class RuntimeUploads:
    def __init__(self, studio):
        self.studio = studio
        self.lock = threading.Lock()
        self.inspections = OrderedDict()
        self.plans = OrderedDict()
        self.job = None
        self.worker = None
        self.last_target = None

    @contextmanager
    def connection(self):
        if not self.studio.device_lock.acquire(timeout=2):
            raise ValueError('A device operation is in progress; wait before inspecting runtimes')
        try: yield
        finally: self.studio.device_lock.release()

    def target(self, port):
        row = self.studio.firmware_port(port)
        mac = (row['usb_id'][2] or '').replace(':', '').replace('-', '').lower()
        if not re.fullmatch('[0-9a-f]{12}', mac):
            raise ValueError('The USB module must report its permanent MAC identity')
        return dict(port=port, mac=mac, usb_id=tuple(row['usb_id']))

    def identify(self, target):
        owner = self.studio.usb_monitor or self.studio.device
        try:
            if (owner is not None and
                    getattr(getattr(owner, 'link', None), 'port', None) == target['port']):
                reply = dual.probe_connection(owner)
            else:
                reply = dual.probe(target['mac'], target['port'])
        except OSError as failure:
            raise ValueError('USB is unavailable or owned by another app. Disconnect its USB session, then inspect again.') from failure
        if not reply:
            raise ValueError('This app lacks runtime identification. Install the matching runtime-aware pair first.')
        board = next((key for key, model in dual.MODELS.items() if model == reply.get('model')), None)
        if board is None or reply['rate'] not in ((16000, 48000) if board == 'voice-pe' else (44100,)):
            raise ValueError('Unrecognized board or native sample rate')
        prior = self.last_target or {}
        owned = self.studio.device_info or {}
        name = owned.get('device_name') if owned.get('device_id') == 'esp32-' + target['mac'] else None
        if not name and prior.get('mac') == target['mac']: name = prior.get('device_name')
        prefix = {'voice-pe':'VoicePE','xiao':'XIAO','amoled-v2':'AMOLED'}[board]
        return dict(target, board=board, rate=reply['rate'], engine=reply['engine'], busy=reply['busy'], model=reply['model'],
                    device_name=name or prefix + '-' + target['mac'][-6:])

    def inspect(self, payload):
        with self.connection():
            found = self.identify(self.target(payload.get('port')))
        error = ''
        try: dual.installed_pair(found['board'], found['mac'], found['rate'])
        except ValueError as failure: error = str(failure)
        token = secrets.token_urlsafe(24)
        with self.lock:
            if not error: self.last_target = dict(found)
            self.inspections[token] = (time.monotonic(), found)
            while len(self.inspections) > 8: self.inspections.popitem(last=False)
        return dict(inspection=token, port=found['port'], device_id='esp32-' + found['mac'],
                    model=found['model'], board=found['board'], engine=found['engine'], rate=found['rate'],
                    ready=not error and not found['busy'], busy=found['busy'], error=error)

    def usb_hint(self):
        """Publish only an explicitly inspected RNBO USB node, without probing it.

        Discovery/control must never reboot a node. Studio's selected SynthDef
        connection remains the normal source of SynthDef USB routing.
        """
        with self.lock:
            target = dict(self.last_target) if self.last_target else None
            active = bool(self.job and self.job['active'])
        if not target or active or target['engine'] != 'rnbo': return None
        try:
            if self.target(target['port']) != {key:target[key] for key in ('port','mac','usb_id')}: return None
        except Exception: return None
        return dict(device_id='esp32-'+target['mac'], device_name=target['device_name'],
                    address=target['port'], port=0, transport='usb', runtime='rnbo', rate=target['rate'],
                    online=True, paired=True)

    def send_from_sc(self, row, artifact, deliver):
        """Select SynthDef for one validated SC Main, then use the normal SC sender.

        The callback runs once while holding Studio's connection lease, after
        re-identification/restart. It retains definition/instance/args semantics.
        """
        with self.lock:
            target = dict(self.last_target) if self.last_target else None
            if self.job and self.job['active']: raise ValueError('A runtime upload is already in progress')
            if not target or row['device_id'] != 'esp32-' + target['mac']:
                raise ValueError('Inspect this USB node in Runtimes before deploying from SC')
        if artifact.info.get('target', 'sound') != 'sound':
            raise ValueError('This node is running RNBO. Send a SynthDef Main before sending FX.')
        if artifact.info.get('requires_control_outputs') and target['board'] != 'voice-pe':
            raise ValueError('This graph writes Voice PE LED buses; no runtime switch for a different board')
        rates = artifact.info.get('admission_rates', {})
        admitted = rates.get(str(target['rate']), artifact.info if target['rate']==44100 else {})
        if admitted.get('fm1_admitted') is not True:
            raise ValueError('The SynthDef is not admitted at this USB node\'s native rate; no runtime switch')
        payload = dual.Artifact('synthdef',target['rate'],artifact.graph,artifact.source,artifact.info)
        with self.lock:
            if self.job and self.job['active']: raise ValueError('A runtime upload is already in progress')
            self.job = dict(job=secrets.token_urlsafe(24),active=True,state='waiting',
                            progress='SC Main waiting for the USB connection',started=time.time(),
                            engine='synthdef',rate=target['rate'],model=target['model'],device_id=row['device_id'])
        locked=self.studio.device_lock.acquire(timeout=30)
        if not locked:
            self.update(active=False,state='failed',error='Device busy; SC Main was not sent',
                        studio_connected=self.studio.device is not None)
            raise ValueError('Device busy; SC Main was not sent')
        try:
            if self.target(target['port']) != {key:target[key] for key in ('port','mac','usb_id')}:
                raise ValueError('The inspected USB node changed before the SC deployment')
            if self.studio.device_port == target['port'] or (self.studio.device_info or {}).get('device_id') == row['device_id']:
                self.studio.disconnect()
            def sender(*args):
                self.studio.connect(dual.wait_port(target['mac']))
                reply=deliver()
                if reply.get('verified') is not True: raise ValueError('SC Main upload was not verified')
                return dict(engine='synthdef',verified=True,graph_sha256=payload.identity,sc_reply=reply)
            result=dual.route(payload,target['board'],target['mac'],target['rate'],sender=sender,
                              progress=lambda text:self.update(state='uploading',progress=text))
            with self.lock: self.last_target=dict(target,engine='synthdef',busy=False)
            self.update(active=False,state='complete',progress='SC Main saved and verified',studio_connected=True,
                        result={key:result[key] for key in ('engine','verified','graph_sha256')})
            return result['sc_reply']
        except Exception as failure:
            self.update(active=False,state='failed',error=str(failure)[-4000:],studio_connected=self.studio.device is not None)
            raise
        finally: self.studio.device_lock.release()

    def review(self, payload):
        with self.lock: record = self.inspections.get(payload.get('inspection'))
        if not record or time.monotonic() - record[0] > 600:
            raise ValueError('Inspect the USB module again before reviewing an upload')
        found = record[1]
        if type(payload.get('definition', False)) is not bool:
            raise ValueError('Definition mode must be true or false')
        if 'data' in payload:
            encoded = payload['data']; name = payload.get('filename', '')
            if (not isinstance(encoded, str) or len(encoded) > ((MAX_FILE + 2) // 3) * 4
                    or not isinstance(name, str) or not 0 < len(name) <= 128 or name in ('.', '..') or Path(name).name != name):
                raise ValueError('Choose a bounded SC source, SCgf SynthDef or RNBO package file')
            try: raw = base64.b64decode(encoded, validate=True)
            except ValueError as failure: raise ValueError('Invalid file encoding') from failure
            if len(raw) > MAX_FILE: raise ValueError('File exceeds the package limit')
        else:
            source = payload.get('source')
            if not isinstance(source, str): raise ValueError('Paste SuperCollider source or choose a file')
            raw = source.encode('utf-8'); name = 'source.scd'
            if not raw.strip() or len(raw) > 65536 or b'\0' in raw:
                raise ValueError('Source must fit in 64 KiB and cannot be empty or contain NUL')
        with tempfile.TemporaryDirectory(prefix='studio-runtime-') as folder:
            path = Path(folder) / name; path.write_bytes(raw)
            artifact = dual.prepare(path, found['rate'], found['board'], str(self.studio.compiler.sclang),
                                    definition=payload.get('definition', False), compiler=self.studio.compiler)
        # Compilation/package validation finishes before any new device access.
        with self.connection():
            current = self.target(found['port'])
            if current != {key: found[key] for key in ('port', 'mac', 'usb_id')}:
                raise ValueError('The inspected USB module changed; inspect it again')
            current = self.identify(current)
            if current['board'] != found['board'] or current['rate'] != found['rate'] or current['busy']:
                raise ValueError('The module changed or is receiving a transfer; inspect it again')
            dual.installed_pair(found['board'], found['mac'], found['rate'])
        token = secrets.token_urlsafe(24)
        with self.lock:
            self.plans[token] = (time.monotonic(), current, artifact)
            while len(self.plans) > 4: self.plans.popitem(last=False)
        return dict(plan=token, engine=artifact.engine, rate=artifact.rate, bytes=len(artifact.data),
                    sha256=artifact.identity, name=artifact.info.get('name', artifact.info.get('metadata', {}).get('name', 'Main')),
                    device_id='esp32-' + found['mac'], switch=current['engine'] != artifact.engine,
                    definition=artifact.info.get('definition', False))

    def snapshot(self):
        with self.lock:
            if self.job is None: return dict(active=False)
            return json.loads(json.dumps(self.job))

    def start(self, payload):
        with self.lock:
            if self.job and self.job['active']: raise ValueError('A runtime upload is already in progress')
            record = self.plans.pop(payload.get('plan'), None)
            if not record or time.monotonic() - record[0] > 600:
                raise ValueError('The reviewed upload expired or was used; review it again')
            _, target, artifact = record
            token = secrets.token_urlsafe(24)
            self.job = dict(job=token, active=True, state='waiting', progress='Waiting for the device connection',
                            device_id='esp32-' + target['mac'], engine=artifact.engine, rate=target['rate'],
                            model=target['model'], started=time.time())
            self.worker = threading.Thread(target=self.run, args=(token, target, artifact), daemon=True)
            self.worker.start()
            return dict(self.job)

    def update(self, **values):
        with self.lock: self.job.update(values)

    def run(self, token, target, artifact):
        locked = self.studio.device_lock.acquire(timeout=30)
        if not locked:
            self.update(active=False, state='failed', error='Device operation did not finish; no upload was started',
                        studio_connected=self.studio.device is not None)
            return
        try:
            current = self.target(target['port'])
            if current != {key: target[key] for key in ('port', 'mac', 'usb_id')}:
                raise ValueError('The reviewed USB module disconnected or changed; no upload started')
            # Stop stale Studio/SC sessions for this physical node before a reboot.
            info = self.studio.device_info or {}
            if info.get('device_id') == 'esp32-' + target['mac'] or self.studio.device_port == target['port']:
                self.studio.disconnect()
            self.update(state='uploading', progress='Checking the selected module')
            result = dual.route(artifact, target['board'], target['mac'], target['rate'],
                                progress=lambda text: self.update(progress=text))
            if artifact.engine == 'synthdef': self.studio.connect(dual.wait_port(target['mac']))
            with self.lock: self.last_target=dict(target,engine=artifact.engine,busy=False)
            self.update(active=False, state='complete', progress='Saved and verified',
                        result={key: result[key] for key in ('engine', 'verified', 'graph_sha256', 'package_sha256') if key in result},
                        studio_connected=self.studio.device is not None)
        except Exception as failure:
            self.update(active=False, state='failed', progress='Upload stopped', error=str(failure)[-4000:],
                        studio_connected=self.studio.device is not None)
        finally: self.studio.device_lock.release()

    def close(self):
        if self.worker: self.worker.join(timeout=600)
