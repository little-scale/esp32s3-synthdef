#!/usr/bin/env python3
"""Compile and transfer bounded one-voice SynthDefs over native USB.

Use the ESP-IDF Python environment for serial commands (pyserial). No board
reset is explicitly requested by connecting; native host control-line behavior
can still reset the board. Replies carry independent CRC checks.
"""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import struct
import subprocess
import tempfile
import time
import zlib
from source_input import expression

ROOT = Path(__file__).resolve().parents[1]

def catalog_entry(name):
    entries=json.loads((ROOT/'examples/catalog.json').read_text())
    return next(e for e in entries if e['id']==name)


def frame(request, operation, payload=b''):
    body = f'{request:08x} {operation} {payload.hex() if payload else "-"}'.encode('ascii')
    return b'@SD1 ' + body + f' {zlib.crc32(body):08x}\n'.encode('ascii')


def decode(line):
    if len(line) > 9000 or not line.startswith(b'@SD1 '):
        raise ValueError('Not a bounded protocol reply')
    body, checksum = line.strip()[5:].rsplit(b' ', 1)
    if zlib.crc32(body) != int(checksum, 16):
        raise ValueError('Reply CRC mismatch')
    request, operation, payload = body.split(b' ')
    return int(request, 16), operation.decode('ascii'), b'' if payload == b'-' else bytes.fromhex(payload.decode('ascii'))


def manifest(graph, source=b'', name='Uploaded Sine', labels=('PITCH', 'LEVEL', 'ATTACK', 'RELEASE'), mapping=1, transfer=None, definition=False):
    if type(definition) is not bool:raise ValueError('Definition mode must be true or false')
    if not 0 < len(graph) <= 65536 or len(source) > 65536:
        raise ValueError('Graph/source exceeds the device limits')
    source.decode('utf-8')
    if b'\0' in source:
        raise ValueError('Source cannot contain NUL bytes')
    def field(text, size):
        raw = text.encode('ascii')
        if not 0 < len(raw) < size or any(c < 32 or c > 126 or c in (34, 92) for c in raw):
            raise ValueError(f'Invalid metadata field: {text!r}')
        return raw.ljust(size, b'\0')
    if len(labels) != 4 or mapping not in (0, 1):
        raise ValueError('Four labels and mapping 0 or 1 required')
    tx = transfer or secrets.randbelow(0xffffffff) + 1
    data = struct.pack('<III', tx, len(graph), len(source))
    data += hashlib.sha256(graph).digest() + hashlib.sha256(source).digest()
    data += field(name, 32) + b''.join(field(label, 12) for label in labels) + bytes([mapping, int(definition), 0, 0])
    assert len(data) == 160
    return tx, data


class Device:
    def __init__(self, port, log=None, *, open_policy='auto'):
        from serial_port import open_port
        self.link = open_port(port,policy=open_policy,baudrate=115200,timeout=.1,write_timeout=3)
        self.sequence = secrets.randbelow(0xfffffffe) + 1
        self.log = log
        self.pending = bytearray()

    def close(self):
        self.link.close()

    def lines(self):
        data = self.link.read(max(1, self.link.in_waiting))
        if data and self.log:
            self.log.write(data); self.log.flush()
        self.pending.extend(data)
        while b'\n' in self.pending:
            line, _, rest = self.pending.partition(b'\n')
            self.pending = bytearray(rest)
            yield bytes(line)
        if len(self.pending) > 16000:
            self.pending.clear()

    def request(self, operation, payload=b'', timeout=10, retries=2):
        request = self.sequence
        self.sequence = (self.sequence + 1) & 0xffffffff
        wire = frame(request, operation, payload)
        for _ in range(retries + 1):
            self.link.write(wire)
            until = time.monotonic() + timeout
            while time.monotonic() < until:
                for line in self.lines():
                    if not line.startswith(b'@SD1 '):
                        continue
                    try:
                        received, status, data = decode(line)
                    except (ValueError, UnicodeError):
                        continue
                    if received != request:
                        continue
                    if status == 'ERR':
                        raise RuntimeError(data.decode('utf-8', errors='replace'))
                    if status != 'OK':
                        raise RuntimeError('Unknown response status')
                    return json.loads(data)
        raise TimeoutError(f'{operation}: no valid acknowledgement; reconnect and inspect STATUS before retrying a mutation')

    def hello(self):
        result = self.request('HELLO')
        if result.get('protocol') != 1 or result.get('model') not in ('Waveshare AMOLED 1.8 V2', 'XIAO ESP32-S3'):
            raise RuntimeError('Unexpected connected device/protocol')
        if result.get('policy') not in ('simple-voice-v1','catalog-voice-v2','fm1-compat-v1') or result.get('chunk') != 256:
            raise RuntimeError('Unsupported device admission policy')
        return result

    def upload(self, graph, source=b'', name='Uploaded Sine', labels=('PITCH', 'LEVEL', 'ATTACK', 'RELEASE'), mapping=1, activate=True, master=False, definition=False):
        tx, meta = manifest(graph, source, name, labels, mapping, definition=definition)
        blob = graph + source
        received = self.request('FXBEGIN' if master else 'BEGIN', meta)['received']
        while received < len(blob):
            chunk = blob[received:received + 256]
            result = self.request('DATA', struct.pack('<II', tx, received) + chunk)
            if result['received'] != received + len(chunk):
                raise RuntimeError('Device acknowledged an unexpected offset')
            received += len(chunk)
        self.request('COMMIT', struct.pack('<I', tx))
        if activate:
            self.request('ACTIVATE', struct.pack('<I', tx))
        return self.request('STATUS')

    def download(self, master=False):
        info_op,read_op=('FXINFO','FXREAD') if master else ('INFO','READ')
        info = self.request(info_op)
        meta = bytes.fromhex(info['manifest'])
        _, graph_size, source_size = struct.unpack_from('<III', meta)
        total = graph_size + source_size
        if len(meta) != 160 or graph_size > 65536 or source_size > 65536:
            raise RuntimeError('Invalid active package size')
        blob = bytearray()
        while len(blob) < total:
            result = self.request(read_op, struct.pack('<IH', len(blob), min(256, total - len(blob))))
            chunk = bytes.fromhex(result['data'])
            if result['offset'] != len(blob) or not chunk:
                raise RuntimeError('Unexpected read offset')
            blob.extend(chunk)
        graph, source = bytes(blob[:graph_size]), bytes(blob[graph_size:])
        if self.request(info_op) != info or hashlib.sha256(graph).digest() != meta[12:44] or hashlib.sha256(source).digest() != meta[44:76]:
            raise RuntimeError('Active package changed or digest verification failed')
        source.decode('utf-8')
        return graph, source, info

    def install_catalog(self, name, diagnostic=False):
        entry=catalog_entry(name)
        if entry['status']!='qualified' and not (diagnostic and entry['status']=='candidate'):
            raise RuntimeError('This catalog entry has not passed qualification')
        graph=(ROOT/f'examples/{name}.scsyndef').read_bytes()
        advertised=self.hello().get('catalog',[])
        if not any(e['id']==name and e['graph_sha256']==hashlib.sha256(graph).hexdigest() and
                   e['status']==entry['status'] for e in advertised):
            raise RuntimeError('Device catalog does not match this compiled graph')
        return self.upload(graph,(ROOT/f'examples/{name}.scd').read_bytes(),entry['name'],entry['labels'],entry['mapping'])


def compile_source(source, output, sclang, target='sound', definition=False):
    # Source returns a SynthDef or a sound Function. SC runs on the host only.
    # Paths are passed through SC string literals, not shell interpolation.
    quote = lambda p: json.dumps(str(p))
    source, output = source.resolve(), output.resolve()
    raw = source.read_bytes()
    raw.decode('utf-8')
    if not raw.strip() or len(raw) > 65536 or b'\0' in raw:
        raise ValueError('Source must be nonempty UTF-8, without NUL, at most 64 KiB')
    input_kind, input_source = expression(raw.decode('utf-8'))
    with tempfile.TemporaryDirectory(prefix='synthdef-compile-', dir=output.parent) as folder:
        script = Path(folder) / 'compile.scd'
        compiled = Path(folder) / 'compiled.scsyndef'
        input_path = source
        if input_kind == 'sound_block':
            input_path = Path(folder) / 'sound.scd'
            input_path.write_text(input_source, encoding='utf-8')
        script.write_text('try {\nvar autoPlay = '+('false' if target=='master' else 'true')+';\nvar definitionOnly = '+('true' if definition else 'false')+';\nvar def = thisProcess.interpreter.executeFile(' + quote(input_path) + ');\n'
                          + (ROOT/'host/compile-sound-block.scd').read_text() + '\n'
                          'if(def.isKindOf(SynthDef).not) { Error("Source must return one SynthDef or sound Function").throw };\n'
                          'File.use(' + quote(compiled) + ', "wb", { |f| f.write(def.asBytes) });\n'
                          '0.exit;\n} { |err| err.reportError; 1.exit };\n')
        try:
            result = subprocess.run([str(sclang), '-D', str(script)], text=True, capture_output=True, timeout=60)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError('SuperCollider compilation timed out after 60 seconds') from error
        log = (result.stdout + result.stderr)[-16000:]
        if result.returncode or not compiled.exists() or not compiled.read_bytes().startswith(b'SCgf'):
            error_start = log.find('ERROR:')
            raise RuntimeError('SuperCollider compilation failed:\n' + (log[error_start:] if error_start >= 0 else log))
        if compiled.stat().st_size > 65536:
            raise ValueError('Compiled SynthDef exceeds the 64 KiB device limit')
        compiled.replace(output)
    return {'graph': str(output.resolve()), 'bytes': output.stat().st_size,
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(), 'compiler_log': log, 'input_kind': input_kind}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', help='Native USB serial device')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('hello', 'status', 'list', 'info', 'panic', 'abort'):
        sub.add_parser(name)
    for name in ('save', 'load'):
        sub.add_parser(name).add_argument('slot', type=int, choices=range(0 if name == 'load' else 1, 2))
    upload = sub.add_parser('upload')
    upload.add_argument('graph', type=Path)
    upload.add_argument('--source', type=Path)
    upload.add_argument('--name', default='Uploaded Sine')
    upload.add_argument('--labels', nargs=4, default=['PITCH', 'LEVEL', 'ATTACK', 'RELEASE'])
    upload.add_argument('--mapping', type=int, choices=[0, 1], default=1)
    upload.add_argument('--save', type=int, choices=(1,))
    compile_cmd = sub.add_parser('compile')
    compile_cmd.add_argument('source', type=Path)
    compile_cmd.add_argument('output', type=Path)
    compile_cmd.add_argument('--sclang', type=Path, default=Path('/Applications/SuperCollider.app/Contents/MacOS/sclang'))
    sub.add_parser('download').add_argument('output', type=Path, help='New output file prefix; existing files are protected')
    install=sub.add_parser('install',help='Activate an exact qualified example from the local catalog')
    install.add_argument('entry',choices=[e['id'] for e in json.loads((ROOT/'examples/catalog.json').read_text())])
    install.add_argument('--save',type=int,choices=(1,))
    fx=sub.add_parser('fx',help='Query or change the shared delay')
    fx.add_argument('--time',type=float);fx.add_argument('--feedback',type=float);fx.add_argument('--wet',type=float);fx.add_argument('--save',action='store_true')
    args = parser.parse_args()
    if args.command == 'compile':
        result = compile_source(args.source, args.output, args.sclang)
    else:
        if not args.port:
            parser.error('--port is required for device commands')
        device = Device(args.port)
        try:
            hello = device.hello()
            if args.command == 'hello':
                result = hello
            elif args.command=='fx':
                current=device.request('FX')
                values=[args.time if args.time is not None else current['time'],args.feedback if args.feedback is not None else current['feedback'],args.wet if args.wet is not None else current['wet']]
                result=device.request('FX',struct.pack('<fff',*values)) if any(v is not None for v in [args.time,args.feedback,args.wet]) else current
                if args.save:result={'effect':result,'storage':device.request('FXSAVE')}
            elif args.command=='install':
                result=device.install_catalog(args.entry)
                if args.save:
                    device.request('SAVE',bytes([args.save]))
                    result=device.request('STATUS')
            elif args.command == 'upload':
                result = device.upload(args.graph.read_bytes(), args.source.read_bytes() if args.source else b'',
                                       args.name, args.labels, args.mapping)
                if args.save:
                    device.request('SAVE', bytes([args.save]))
                    result = device.request('STATUS')
            elif args.command == 'download':
                paths = [Path(str(args.output)+suffix) for suffix in ('.scsyndef', '.scd', '.json')]
                if any(path.exists() for path in paths):
                    raise RuntimeError('Download would replace an existing file; choose a new prefix')
                graph, source, result = device.download()
                paths[0].write_bytes(graph); paths[1].write_bytes(source)
                paths[2].write_text(json.dumps(result, indent=2)+'\n')
            else:
                result = device.request(args.command.upper(), bytes([args.slot]) if args.command in ('load', 'save') else b'')
        finally:
            device.close()
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
