"""Paired LAN transport. Device identity is checked before and during every upload."""
import concurrent.futures
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import socket
import time
from patches import Device, ROOT, decode, frame

DISCOVERY_PORT = 32101
DEVICE_ID = re.compile(r'esp32-[0-9a-f]{12}\Z')


def with_usb_module(rows, usb):
    """Prefer Studio's live USB connection when both transports see an ID."""
    if usb is None:
        return list(rows)
    return [row for row in rows if row['device_id'] != usb['device_id']] + [usb]


def endpoint(address, port=80):
    # IP literals only: no redirects, URL credentials, proxy or DNS rebinding.
    try:
        ip = ipaddress.IPv4Address(address)
    except (ValueError, ipaddress.AddressValueError):
        raise ValueError('Enter the device’s local IPv4 address') from None
    if not (ip.is_private or ip.is_link_local) or ip.is_multicast or ip.is_unspecified:
        raise ValueError('Choose a device on the local network')
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Invalid device port')
    return str(ip), port


def identity(address, port=80, timeout=2):
    address, port = endpoint(address, port)
    connection = http.client.HTTPConnection(address, port, timeout=timeout)
    try:
        connection.request('GET', '/v1/identity')
        response = connection.getresponse(); raw = response.read(1025)
        if response.status != 200 or len(raw) > 1024:
            raise RuntimeError('Not a compatible SynthDef device')
        info = json.loads(raw)
        if info.get('protocol') != 1 or not DEVICE_ID.fullmatch(info.get('device_id', '')):
            raise RuntimeError('Invalid device identity')
        if response.getheader('X-Device-ID') != info['device_id']:
            raise RuntimeError('Device identity mismatch')
        return dict(device_id=info['device_id'], device_name=str(info.get('device_name', 'ESP32'))[:31],
                    address=address, port=port, online=True)
    finally:
        connection.close()


class Pairings:
    def __init__(self, path=None):
        self.path = Path(path) if path else ROOT/'build/host/private/network-devices.json'

    def read(self):
        if not self.path.exists(): return {}
        data = json.loads(self.path.read_text())
        if not isinstance(data, dict): raise ValueError('Invalid paired-device store')
        return data

    def save(self, info):
        device_id, key = info.get('device_id', ''), info.get('key', '')
        if not DEVICE_ID.fullmatch(device_id) or not re.fullmatch(r'[0-9a-f]{64}', key):
            raise ValueError('Invalid USB pairing response')
        entries = self.read()
        entries[device_id] = {k: info[k] for k in ('device_id', 'device_name', 'key', 'address', 'port')}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name('.'+self.path.name+'.'+secrets.token_hex(8))
        try:
            fd = os.open(temporary, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as stream:
                json.dump(entries, stream, indent=2); stream.write('\n')
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def get(self, device_id):
        info = self.read().get(device_id)
        if info is None: raise ValueError('Pair this particular device over USB first')
        return info

    def public(self):
        return [{k:v for k,v in entry.items() if k != 'key'} for entry in self.read().values()]


def discover(pairings, address=None):
    candidates = {}
    if address:
        info = identity(address); candidates[info['device_id']] = info
    else:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind(('', 0)); sock.settimeout(.2)
            sock.sendto(b'SYNTHDEF_DISCOVER_V1', ('255.255.255.255', DISCOVERY_PORT))
            until = time.monotonic()+1.5
            while time.monotonic() < until:
                try:
                    raw, peer = sock.recvfrom(1025)
                    info = json.loads(raw)
                    if len(raw)<=1024 and info.get('protocol') == 1 and DEVICE_ID.fullmatch(info.get('device_id', '')):
                        ip, port = endpoint(peer[0], info.get('port', 80))
                        candidates[info['device_id']] = dict(device_id=info['device_id'], device_name=str(info.get('device_name','ESP32'))[:31], address=ip,port=port)
                except (socket.timeout, ValueError, UnicodeError): pass
        finally: sock.close()
    paired = {row['device_id']:row for row in pairings.public()}
    # Recheck announcements by unicast and include saved IPs when broadcast is blocked.
    probes = {(row['address'],row['port']) for row in [*paired.values(),*candidates.values()] if row['address']!='0.0.0.0'}
    found = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(identity, ip, port, 1) for ip,port in list(probes)[:64]]
        for future in concurrent.futures.as_completed(futures):
            try:
                row = future.result(); row['paired'] = row['device_id'] in paired; found[row['device_id']] = row
            except (OSError, ValueError, RuntimeError, http.client.HTTPException): pass
    for device_id,row in paired.items():
        if device_id not in found: found[device_id] = dict(row, paired=True, online=False)
    return sorted(found.values(), key=lambda row:(not row.get('online'),row['device_name'],row['device_id']))


class NetworkDevice(Device):
    def __init__(self, info, pairing):
        self.address, self.port = endpoint(info['address'], info['port'])
        self.device_id = pairing['device_id']; self.key = pairing['key']
        if info['device_id'] != self.device_id: raise ValueError('Selected device does not match its pairing')
        self.client_id = secrets.token_hex(16); self.sequence = secrets.randbelow(0xfffffffe)+1
        self.link = None
        actual = identity(self.address,self.port)
        if actual['device_id'] != self.device_id:
            raise RuntimeError('This IP now belongs to a different device; scan again')

    def close(self): pass

    def request(self, operation, payload=b'', timeout=25, retries=1):
        self.sequence = self.sequence%0xffffffff+1; request = self.sequence
        wire = frame(request,operation,payload)
        for attempt in range(retries+1):
            connection = http.client.HTTPConnection(self.address,self.port,timeout=timeout)
            try:
                connection.request('POST','/v1/request',body=wire,headers={
                    'Content-Type':'text/plain','X-Device-ID':self.device_id,
                    'X-Device-Key':self.key,'X-Client-ID':self.client_id})
                response = connection.getresponse(); raw = response.read(9001)
                if response.getheader('X-Device-ID') != self.device_id:
                    raise RuntimeError('Device identity changed; upload stopped')
                if response.status != 200:
                    raise RuntimeError(f'Device refused request ({response.status}): '+raw[:300].decode(errors='replace'))
                if len(raw)>9000: raise RuntimeError('Device response exceeds protocol limit')
                received,status,data = decode(raw)
                if received != request: raise RuntimeError('Device returned a different request ID')
                if status == 'ERR': raise RuntimeError(data.decode(errors='replace'))
                if status != 'OK': raise RuntimeError('Invalid device acknowledgement')
                result = json.loads(data)
                if operation=='HELLO' and result.get('device_id')!=self.device_id:
                    raise RuntimeError('Device HELLO identity mismatch')
                return result
            except (OSError,http.client.HTTPException):
                if attempt==retries: raise
            finally: connection.close()
