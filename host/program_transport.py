"""Transactional, hash-verified local-pattern upload over the existing device link."""
import hashlib
import secrets
import struct


def upload_program(device, raw, *, save=True, start=True):
    if type(save) is not bool or type(start) is not bool:
        raise ValueError('Program save/start must be booleans')
    if not device.hello().get('pattern_programs'):
        raise ValueError('Update device firmware for standalone pattern programs')
    if not isinstance(raw,bytes) or not 60<=len(raw)<=32768 or raw[:4]!=b'ESPp':
        raise ValueError('Invalid pattern program')
    status=device.request('STATUS')
    if bytes.fromhex(status['graph_sha256'])!=raw[28:60]:
        raise ValueError('Main changed before program upload')
    digest=hashlib.sha256(raw).digest();transfer=secrets.randbits(32) or 1
    begun=False
    try:
        reply=device.request('PBEGIN',struct.pack('<II',transfer,len(raw))+digest)
        begun=True
        if reply['received']!=0:raise ValueError('Unexpected program transfer offset')
        for offset in range(0,len(raw),256):
            chunk=raw[offset:offset+256]
            if device.request('PDATA',struct.pack('<II',transfer,offset)+chunk)['received']!=offset+len(chunk):
                raise ValueError('Program transfer offset mismatch')
        result=device.request('PCOMMIT',struct.pack('<I',transfer))
        if result.get('sha256')!=digest.hex():raise ValueError('Program activation digest mismatch')
        begun=False
        if save and device.request('PSAVE').get('saved') is not True:
            raise ValueError('Program storage not verified')
        if start and device.request('PPLAY').get('running') is not True:
            raise ValueError('Program did not start')
        info=device.request('PINFO')
        if not info['loaded'] or not info['bound'] or info['sha256']!=digest.hex():
            raise ValueError('Program readback verification failed')
        return dict(verified=True,saved=save,started=start,program=info)
    finally:
        if begun:
            try:device.request('PABORT')
            except (OSError,TimeoutError,RuntimeError):pass
