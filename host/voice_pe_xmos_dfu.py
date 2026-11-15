#!/usr/bin/env python3
"""Read-only XMOS DFU inventory and repeat-verified private partition backup.

This helper never downloads firmware to a device, detaches, erases or reboots it.
The Voice PE must already have USB SELECT set to XU316. Its XMOS serial number
is not unique, so selection requires one physical USB path and all three named
alternate interfaces. These reads are a recovery prerequisite, not proof that
every failed custom firmware can be recovered without external hardware.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
try:
    import resource
except ImportError:
    resource = None

ROOT = Path(__file__).resolve().parents[1]
NAMES = {0: 'DFU FACTORY', 1: 'DFU UPGRADE', 2: 'DFU DATAPARTITION'}
MAX_BYTES = 16 * 1024 * 1024
LINE = re.compile(r'Found DFU: \[2886:0019\] ver=([0-9a-fA-F]{4}), '
    r'devnum=(\d+), cfg=(\d+), intf=(\d+), path="([^"]+)", '
    r'alt=(\d+), name="([^"]+)", serial="([^"]*)"', re.I)


def inventory(text):
    devices = {}
    for line in text.splitlines():
        match = LINE.search(line)
        if not match: continue
        version, number, configuration, interface, path, alternate, name, serial = match.groups()
        alternate = int(alternate)
        key = (path, int(number), int(configuration), int(interface), version.lower(), serial)
        row = devices.setdefault(key, {})
        if alternate in row: raise ValueError('Duplicate DFU alternate interface.')
        row[alternate] = name
    if len(devices) != 1:
        raise ValueError('Connect exactly one Voice PE XMOS DFU device; USB SELECT must point to XU316.')
    (path, number, configuration, interface, version, serial), rows = next(iter(devices.items()))
    if rows != NAMES:
        raise ValueError('Unexpected XMOS alternate-interface map; no backup attempted.')
    return dict(path=path, devnum=number, configuration=configuration,
                interface=interface, usb_version=version, serial=serial)


def tool_path():
    tool = shutil.which('dfu-util')
    if not tool: raise ValueError('Install dfu-util before reading the XMOS flash.')
    return tool


def inspect(tool):
    result = subprocess.run([tool, '--list'], capture_output=True, text=True, check=True, timeout=15)
    return inventory(result.stdout + result.stderr)


def upload_file_limit():
    # dfu-util 0.11's --upload-size only adjusts its progress display; it does
    # not cap received bytes. Apply an actual per-child file-size limit.
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_BYTES, MAX_BYTES))


def read_partition(tool, device, alternate, destination):
    if alternate not in NAMES: raise ValueError('Unknown partition.')
    if resource is None: raise ValueError('Bounded DFU backups currently require macOS or Linux.')
    if destination.exists(): raise ValueError('Refusing to overwrite a backup file.')
    # Refuse re-enumeration, replacement or an additional matching device.
    if inspect(tool) != device: raise ValueError('XMOS USB identity changed during backup.')
    command = [tool, '--device', '2886:0019', '--path', device['path'],
               '--devnum', str(device['devnum']),
               '--cfg', str(device['configuration']), '--intf', str(device['interface']),
               '--alt', str(alternate), '--transfer-size', '4096',
               '--upload', str(destination)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180,
                            preexec_fn=upload_file_limit)
    log = destination.with_suffix('.log')
    log.write_text(result.stdout + result.stderr)
    os.chmod(log, 0o600)
    result.check_returncode()
    os.chmod(destination, 0o600)
    size = destination.stat().st_size
    if size >= MAX_BYTES or size % 4096:
        raise ValueError('Read reached its safety bound or returned a non-sector-aligned partition.')
    if alternate == 0 and not size:
        raise ValueError('Factory partition is unexpectedly empty.')
    data = destination.read_bytes()
    return dict(file=destination.name, bytes=size, sha256=hashlib.sha256(data).hexdigest())


def backup(tool, expected_path, root):
    device = inspect(tool)
    if device['path'] != expected_path: raise ValueError('USB path does not match the reviewed device.')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-'), dir=root))
    os.chmod(folder, 0o700)
    record = dict(device=device, status='reading', flash_written=False, partitions=[])
    journal = folder/'backup.json'
    def save():
        journal.write_text(json.dumps(record, indent=2)+'\n'); os.chmod(journal, 0o600)
    save()
    previous_umask = os.umask(0o077)
    try:
        for alternate, name in NAMES.items():
            print('Reading twice:', name, flush=True)
            rows = [read_partition(tool, device, alternate, folder/f'alt{alternate}-read{n}.bin') for n in (1,2)]
            if (rows[0]['bytes'], rows[0]['sha256']) != (rows[1]['bytes'], rows[1]['sha256']):
                raise ValueError('Repeated partition reads differ; backup is not verified.')
            record['partitions'].append(dict(alternate=alternate, name=name, verified=True,
                availability='nonempty' if rows[0]['bytes'] else 'not_exposed_or_absent', reads=rows));save()
        if inspect(tool) != device: raise ValueError('XMOS USB identity changed before verification finished.')
        record['status']='repeat_verified';save()
    except Exception as error:
        record['status']='failed';record['error']=str(error);save();raise
    finally:
        os.umask(previous_umask)
    print('Verified private XMOS backup:', folder, flush=True)
    return record


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('inspect','backup'))
    parser.add_argument('--path', help='Reviewed USB topology path printed by inspect')
    args=parser.parse_args()
    if args.action=='backup' and not args.path: parser.error('backup requires --path from inspect')
    try:
        tool=tool_path()
        if args.action=='inspect': print(json.dumps(inspect(tool), indent=2))
        else: backup(tool,args.path,ROOT/'recovery/voice-pe/private/xmos')
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(2,str(error)+'\n')
