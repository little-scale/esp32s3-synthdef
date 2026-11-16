#!/usr/bin/env python3
"""Validate a .scd/.scsyndef/.rnbopkg, select its installed app, then upload by USB.

No runtime switch is attempted until compilation/package validation succeeds.
Only explicit patch uploads enter this path; notes/control/discovery do not.
The companion RNBO checkout supplies its existing qualified parser/USB bridge.
"""
import argparse
import base64
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import time

from patches import Device
from runtime_routing import Upload, plan_upload

ROOT = Path(__file__).resolve().parents[1]
MODELS = {'voice-pe': 'Home Assistant Voice PE', 'xiao': 'XIAO ESP32-S3',
          'amoled-v2': 'Waveshare AMOLED 1.8 V2'}


@dataclass
class Artifact:
    engine: str
    rate: int
    data: bytes
    source: bytes
    info: dict

    @property
    def identity(self): return hashlib.sha256(self.data).hexdigest()


def rnbo_root():
    explicit = os.environ.get('RNBO_PROJECT_ROOT')
    candidates = [Path(explicit)] if explicit else [ROOT.parent / 'esp32-rnbo', ROOT.parent / 'esp32s3-rnbo']
    for candidate in candidates:
        path = candidate.expanduser().resolve()
        if (path / 'host/compiler/package.py').is_file(): return path
    raise ValueError('Set RNBO_PROJECT_ROOT to the companion esp32s3-rnbo checkout')


def rnbo_call(code, *args, timeout=45):
    project = rnbo_root()
    # Both checkouts have a namespace named `host`; this project's studio.py
    # otherwise wins over RNBO's namespace directory host/studio. Isolate the
    # child from cwd/PYTHONPATH and let its explicit RNBO root own that namespace.
    result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(project), *map(str, args)],
                            cwd=project, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise ValueError('RNBO operation failed: ' + result.stderr[-4000:])
    return json.loads(result.stdout)


def prepare(path, rate, board, sclang, target='main', definition=False, compiler=None):
    if target not in ('main', 'fx'): raise ValueError('Choose Main or FX')
    if not Path(path).is_file(): raise ValueError('Choose a regular payload file')
    maximum = 128 + 65536 + 524288
    with Path(path).open('rb') as source: raw = source.read(maximum + 1)
    if len(raw) > maximum: raise ValueError('Payload exceeds the package limit; no device access')
    if raw.startswith(b'RNBOS3P1'):
        if target != 'main': raise ValueError('RNBO effects live inside its Main package; no separate FX target')
        if definition: raise ValueError('Definition-only installation applies to SynthDefs, not RNBO packages')
        if len(raw) > 128 + 65536 + 524288: raise ValueError('RNBO package is too large')
        # Use the existing full parser, including ELF/import, profile, checksum
        # and physical-interface schemas; a magic prefix alone never selects an app.
        code = ('import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);'
                'from host.compiler.package import parse;d=parse(Path(sys.argv[2]).read_bytes());'
                'print(json.dumps({k:d[k] for k in ("role","sample_rate","block_frames","profile","metadata","package_sha256")}))')
        with tempfile.TemporaryDirectory(prefix='dual-validate-') as folder:
            file = Path(folder) / 'package.rnbopkg'; file.write_bytes(raw); os.chmod(file, 0o600)
            info = rnbo_call(code, file)
        if info['role'] != 'main' or info['sample_rate'] != rate:
            raise ValueError('RNBO package role/sample rate differs; no runtime switch')
        meta = info['metadata']
        for key, required in [('physical_inputs', 'xiao'), ('touchscreen_inputs', 'amoled-v2'),
                              ('voice_pe_inputs', 'voice-pe'), ('voice_pe_leds', 'voice-pe')]:
            if key in meta and board != required: raise ValueError('RNBO physical metadata requires a different board')
        return Artifact('rnbo', rate, raw, b'', info)
    if not raw.startswith(b'SCgf') and Path(path).suffix.lower() not in ('.scd', '.sc'):
        raise ValueError('Choose SuperCollider .scd source, a compiled SCgf SynthDef, or a valid .rnbopkg')
    from studio import Compiler
    payload = dict(graph=base64.b64encode(raw).decode()) if raw.startswith(b'SCgf') else dict(source=raw.decode('utf-8'))
    payload['target'] = 'master' if target == 'fx' else 'sound'
    payload['definition'] = definition
    graph, source, info = (compiler or Compiler(sclang)).compile(payload)
    if info.get('requires_control_outputs') and board != 'voice-pe':
        raise ValueError('This graph writes Voice PE LED buses; no runtime switch for a different board')
    key = 'master_admitted' if target == 'fx' else 'fm1_admitted'
    admitted = info.get('admission_rates', {}).get(str(rate), {}).get(key, info.get(key))
    if admitted is not True:
        row = info.get('admission_rates', {}).get(str(rate), {})
        raise ValueError('SynthDef is not admitted at this rate: ' + str(row.get('admission_error', info.get('admission_error', 'unknown'))))
    return Artifact('synthdef', rate, graph, source, info)


def resolve(mac, port=None):
    from serial.tools import list_ports
    found = [p for p in list_ports.comports() if p.vid == 0x303a and
             (p.serial_number or '').replace(':', '').replace('-', '').lower() == mac]
    if port: found = [p for p in found if p.device == port]
    if len(found) != 1: raise ValueError('Could not resolve exactly one USB port for the requested MAC')
    return found[0].device


def probe(mac, port=None, timeout=1):
    """The @ prefix is harmless to both legacy parsers and never plays a note."""
    from serial_port import open_port
    with open_port(resolve(mac, port), baudrate=115200, timeout=.1, exclusive=True) as link:
        link.write(b'@RT1 HELLO\n'); pending = bytearray(); until = time.monotonic() + timeout
        while time.monotonic() < until:
            pending.extend(link.read(min(max(1, link.in_waiting), 1024)))
            while b'\n' in pending:
                line, _, pending = pending.partition(b'\n')
                if not line.startswith(b'@RT1 '): continue
                data = json.loads(line[5:])
                if (data.get('version') != 1 or data.get('engine') not in ('synthdef', 'rnbo')
                        or type(data.get('rate')) is not int or type(data.get('busy')) is not bool):
                    raise ValueError('Invalid runtime identification reply')
                return data
            if len(pending) > 8192: raise ValueError('Oversized runtime probe response')
    return None


def probe_connection(device, timeout=1):
    """Use Studio's existing USB owner and its pending-line/telemetry reader."""
    device.link.write(b'@RT1 HELLO\n')
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for line in device.lines():
            if not line.startswith(b'@RT1 '): continue
            data = json.loads(line[5:])
            if (data.get('version') != 1 or data.get('engine') not in ('synthdef', 'rnbo')
                    or type(data.get('rate')) is not int or type(data.get('busy')) is not bool):
                raise ValueError('Invalid runtime identification reply')
            return data
    return None


def wait_port(mac, port=None, timeout=35):
    """Wait for USB re-enumeration only; never retry a payload mutation."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            return resolve(mac, port)
        except ValueError as error:
            if time.monotonic() >= deadline:
                raise ValueError('USB did not reappear for the selected MAC after restart') from error
            time.sleep(.2)


def boot(board, engine, mac, port=None):
    helper = ROOT / 'host' / ('voice_pe_apps.py' if board == 'voice-pe' else 'dual_apps.py')
    command = [sys.executable, '-u', str(helper), engine, '--mac', mac]
    if board != 'voice-pe': command += ['--board', board]
    if port: command += ['--port', port]
    result = subprocess.run(command, capture_output=True, text=True, timeout=240)
    if result.returncode: raise ValueError('Runtime selection failed: ' + result.stderr[-3000:] + result.stdout[-1500:])


def fade(mac, engine, port=None):
    # RAM-only gain: each app's independently saved setting survives the reboot.
    if engine == 'synthdef':
        device = Device(resolve(mac, port), exclusive=True)
        try:
            reply = device.request('VOLUME', bytes([0]), timeout=2, retries=0)
            if type(reply.get('percent')) is not int or reply['percent'] != 0:
                raise ValueError('Outgoing SynthDef did not acknowledge the RAM-only fade')
        finally: device.close()
    else:
        # This is used only after an explicit RNBO identity response. Never
        # synthesize these bytes into an unidentified character console.
        from serial_port import open_port
        with open_port(resolve(mac, port), baudrate=115200, timeout=.1, exclusive=True) as link:
            link.write(b'player-volume 0\n')
            until = time.monotonic() + 2; pending = bytearray(); ok = False
            while time.monotonic() < until:
                pending.extend(link.read(min(max(1, link.in_waiting), 1024)))
                while b'\n' in pending:
                    line, _, pending = pending.partition(b'\n')
                    try: reply = json.loads(line)
                    except (ValueError, UnicodeError): continue
                    if reply.get('volume') == 0 and reply.get('accepted') is True: ok = True
                if ok: break
            if not ok: raise ValueError('Outgoing RNBO did not acknowledge the RAM-only fade')
    # Allow the gain ramp plus the queued DMA/FIFO samples to reach silence at
    # all qualified rates, including the longer native-16 queue duration.
    time.sleep(.15)


def send_synth(artifact, mac, rate, port=None):
    deadline = time.monotonic() + 35; device = None; error = None
    while time.monotonic() < deadline:
        try:
            device = Device(resolve(mac, port), exclusive=True); hello = device.request('HELLO', timeout=2, retries=0)
            break
        except Exception as caught:
            error = caught
            if device: device.close(); device = None
            time.sleep(.2)
    if device is None: raise ValueError('SynthDef did not become ready: ' + str(error))
    try:
        if hello.get('device_id') != 'esp32-' + mac or hello.get('rate') != rate:
            raise ValueError('Selected SynthDef device identity/rate differs')
        if not hello.get('atomic_install'): raise ValueError('This uploader requires atomic Main installation')
        state = device.request('STATUS')
        if state.get('reset_required'): raise ValueError('SynthDef reports reset required')
        name = re.sub(r'[^\x20-\x7e]|["\\]', '_', artifact.info.get('name', 'Uploaded sound'))[:31]
        master = artifact.info.get('target') == 'master'
        staged = device.upload(artifact.data, artifact.source, name=name, activate=False, master=master,
                               definition=artifact.info.get('definition', False))
        device.request('INSTALL', struct.pack('<IB', staged['transfer'], 1))
        graph, source, info = device.download(master=master)
        if graph != artifact.data or source != artifact.source or info.get('slot') != 1:
            raise ValueError('Saved SynthDef package readback differs')
        if artifact.info.get('program'):
            from program_transport import upload_program
            upload_program(device, base64.b64decode(artifact.info['program']['data'], validate=True))
        return dict(engine='synthdef', verified=True, graph_sha256=artifact.identity, name=name)
    finally: device.close()


def send_rnbo(artifact, mac, rate, port=None):
    # Keep the established bridge's full capability checks, bounded transfer,
    # acknowledgement checks and device startup qualification in one place.
    code = '''import sys,json,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from host.studio.device import DeviceBridge
b=DeviceBridge();deadline=time.monotonic()+35
try:
 while True:
  try: ready=b.connect(sys.argv[3])
  except Exception:
   b.disconnect()
   if time.monotonic()>deadline:raise
   time.sleep(.25);continue
  device=ready['device']
  if device['rate']!=int(sys.argv[5]):raise ValueError('Selected RNBO rate differs')
  if device['board_model']=='Home Assistant Voice PE' and not device.get('boot_verified'):
   b.disconnect()
   if time.monotonic()>deadline:raise RuntimeError('RNBO startup guard did not complete')
   time.sleep(.25);continue
  break
 result=b.upload_package(Path(sys.argv[2]),sys.argv[3],lambda text:print(text,file=sys.stderr),expected_sha256=sys.argv[4])
 print(json.dumps(result))
finally:b.disconnect()
'''
    with tempfile.TemporaryDirectory(prefix='dual-upload-') as folder:
        file = Path(folder) / 'package.rnbopkg'; file.write_bytes(artifact.data); os.chmod(file, 0o600)
        result = rnbo_call(code, file, wait_port(mac, port), artifact.identity, rate, timeout=180)
    return dict(engine='rnbo', verified=True, package_sha256=artifact.identity, result=result)


@contextmanager
def device_lock(mac):
    if not re.fullmatch('[0-9a-f]{12}', mac): raise ValueError('Invalid device identity')
    folder = ROOT / 'build/host/private/runtime-locks'; folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (folder / (mac + '.lock')).open('a') as handle:
        os.chmod(handle.name, 0o600)
        try: fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error: raise ValueError('Another runtime upload owns this device') from error
        try: yield
        finally: fcntl.flock(handle, fcntl.LOCK_UN)


def installed_pair(board, mac, rate):
    base = ROOT / ('recovery/voice-pe/private/dual-apps' if board == 'voice-pe' else 'build/host/private/dual-apps')
    path = base / mac / 'installed-apps.json'
    if not path.is_file(): raise ValueError('Commission and verify both applications on this device before automatic uploads')
    data = json.loads(path.read_text())
    if (type(data.get('version')) is not int or data['version'] != 1 or data.get('mac') != mac
            or type(data.get('rate')) is not int or data['rate'] != rate
            or data.get('board', 'voice-pe') != board):
        raise ValueError('Saved dual-app identity/rate does not match this request')
    roles = data.get('apps', {})
    if type(roles) is not dict or not {'synthdef', 'rnbo'} <= roles.keys():
        raise ValueError('Both verified applications are required')
    for role in ('synthdef', 'rnbo'):
        record = roles[role]
        if (type(record) is not dict or type(record.get('bytes')) is not int or record['bytes'] <= 0
                or record.get('rate',rate)!=rate
                or not re.fullmatch('[0-9a-f]{64}', record.get('sha256', ''))):
            raise ValueError('Incomplete verified dual-app inventory')
    return set(roles)


def route(artifact, board, mac, rate, port=None, *, allow_legacy_reboot=False, progress=None, sender=None):
    report = progress or (lambda text: None)
    request = Upload(artifact.engine, artifact.rate, artifact.identity)
    if artifact.rate != rate: raise ValueError('Artifact/device rate differs')
    with device_lock(mac):
        report('Checking the installed pair and USB identity')
        installed = installed_pair(board, mac, rate)
        current = probe(mac, port)
        if current:
            if current.get('model') != MODELS[board]: raise ValueError('Runtime reports a different board')
            if current.get('busy'): raise ValueError('The device is receiving/installing or faulted; no runtime switch attempted')
            plan = plan_upload(request, board=board, current_engine=current['engine'],
                               device_rate=current['rate'], installed=installed)
            if plan['switch']:
                report('Fading ' + current['engine'] + ' before restart')
                print('Fading and switching to ' + artifact.engine + '…', file=sys.stderr, flush=True)
                fade(mac, current['engine'], port)
                report('Selecting ' + artifact.engine + ' and restarting the module')
                boot(board, artifact.engine, mac, port)
        else:
            if not allow_legacy_reboot:
                raise ValueError('Install the runtime-aware app images first. For explicit legacy maintenance only, use --allow-legacy-reboot with Studio disconnected.')
            print('Legacy runtime: verifying installed apps and boot selection…', file=sys.stderr, flush=True)
            boot(board, artifact.engine, mac, port)
        # No mutation is retried across the reboot; each fresh transport receives
        # the complete immutable, already-validated payload once.
        report('Uploading and verifying the ' + artifact.engine + ' Main package')
        if sender is not None:
            result = sender(artifact, mac, rate, port)
        else:
            result = send_synth(artifact, mac, rate, port) if artifact.engine == 'synthdef' else send_rnbo(artifact, mac, rate, port)
        report('Upload verified')
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', type=Path)
    parser.add_argument('--board', required=True, choices=tuple(MODELS))
    parser.add_argument('--mac', required=True); parser.add_argument('--port')
    parser.add_argument('--rate', type=int, choices=(16000, 44100, 48000))
    parser.add_argument('--target', choices=('main', 'fx'), default='main')
    parser.add_argument('--definition', action='store_true', help='Save a SynthDef without starting an instance')
    parser.add_argument('--sclang', default=shutil.which('sclang') or '/Applications/SuperCollider.app/Contents/MacOS/sclang')
    parser.add_argument('--check', action='store_true', help='Compile/validate only; no USB access')
    parser.add_argument('--allow-legacy-reboot', action='store_true', help='Explicitly allow ROM inspection/reboot when older images cannot identify their runtime')
    args = parser.parse_args()
    try:
        if not re.fullmatch('[0-9a-f]{12}', args.mac): raise ValueError('Use the exact lowercase 12-digit MAC')
        rate = args.rate or (44100 if args.board != 'voice-pe' else None)
        if args.board == 'voice-pe' and rate not in (16000, 48000): raise ValueError('Choose the installed Voice PE native --rate')
        if args.board == 'xiao' and rate not in (16000,44100):raise ValueError('XIAO uses a matched 16000 or 44100 Hz pair')
        if args.board == 'amoled-v2' and rate != 44100:raise ValueError('AMOLED uses 44100 Hz')
        artifact = prepare(args.file, rate, args.board, args.sclang, target=args.target, definition=args.definition)
        result = dict(engine=artifact.engine, rate=rate, payload_sha256=artifact.identity, valid=True)
        if not args.check: result = route(artifact, args.board, args.mac, rate, args.port, allow_legacy_reboot=args.allow_legacy_reboot)
        print(json.dumps(result, indent=2)); return 0
    except Exception as error:
        print(str(error), file=sys.stderr); return 1


if __name__ == '__main__': sys.exit(main())
