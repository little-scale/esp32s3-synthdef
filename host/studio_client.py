"""Authenticated loopback client for hardware qualification through a running Studio.

Borrows Studio's USB connection; never opens another serial port. The descriptor
is private and its token must not appear in reports or logs.
"""
import http.client
import json
from pathlib import Path
import secrets
import socket
import struct
import threading

from ide_bridge import MAX_MESSAGE, osc_decode, osc_message
from patches import ROOT


def untyped(value):
    tag = value[0]
    if tag == 'n': return None
    if tag == 'b': return value[1] == '1'
    if tag == 'i': return int(value[1])
    if tag == 'f': return float(value[1])
    if tag == 's': return value[1]
    if tag == 'a': return [untyped(v) for v in value[1]]
    if tag == 'o': return {k: untyped(v) for k, v in value[1]}
    raise ValueError('Unknown bridge value type')


class StudioClient:
    def __init__(self, port=8765, config=None):
        self.config = json.loads(Path(config or ROOT/'build/host/private/studio-client.json').read_text())
        self.port = port
        self.client = 'qualification-' + secrets.token_hex(8)
        self.sequence = 0
        self.socket = None
        self.lock = threading.Lock()

    def http(self, path, payload=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=120)
        try:
            connection.request('GET' if payload is None else 'POST', '/api/' + path,
                None if payload is None else json.dumps(payload, allow_nan=False),
                {'Content-Type': 'application/json', 'X-Studio-Token': self.config['token']})
            response = connection.getresponse()
            value = json.loads(response.read(2 * 1024 * 1024))
            if response.status != 200: raise RuntimeError(str(value))
            return value
        finally:
            connection.close()

    def _exact(self, count):
        data = bytearray()
        while len(data) < count:
            block = self.socket.recv(count - len(data))
            if not block: raise ConnectionError('Studio bridge disconnected')
            data.extend(block)
        return bytes(data)

    def rpc(self, action, payload):
        with self.lock:
            if self.socket is None:
                self.socket = socket.create_connection(('127.0.0.1', self.config['port']), timeout=120)
            self.sequence += 1
            message = osc_message('/esp32/request', self.config['token'], self.client,
                self.sequence, action, json.dumps(payload, allow_nan=False), b'\x01', b'\x01')
            try:
                self.socket.sendall(struct.pack('>I', len(message)) + message)
                size = struct.unpack('>I', self._exact(4))[0]
                if not 0 < size <= MAX_MESSAGE: raise ValueError('Invalid bridge reply size')
                path, values = osc_decode(self._exact(size))
                if path != '/esp32/reply' or len(values) != 3 or values[0] != self.sequence:
                    raise ValueError('Unexpected bridge reply')
                value = untyped(json.loads(values[2]))
                if not values[1]: raise RuntimeError(str(value))
                return value
            except (OSError, ValueError):
                self.close()
                raise

    def close(self):
        if self.socket is not None:
            self.socket.close()
            self.socket = None
