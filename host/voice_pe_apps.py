#!/usr/bin/env python3
"""Keep SynthDef and RNBO installed on the reviewed Voice PE layout.

USB maintenance restarts the ESP32. It never writes XMOS, the bootloader,
partition table, settings or patch storage. Other board migrations are separate.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import struct
import sys
import tempfile
import zlib

from voice_pe_firmware import (
    FLASH_BYTES, PROJECT, PROJECT_LATEST, active_slot, image_length,
    partitions, project_name, save_region, verified_image,
)

ROOT = Path(__file__).resolve().parents[1]
SLOTS = {'synthdef': (0, 0x10000, 0x7c0000, 'waveshare_synthdef'),
         'rnbo': (1, 0x7d0000, 0x3c0000, 'rnbo_s3_voice-pe')}


def ota_selection(ota, slot):
    """Write the older sector only, retaining one previous valid boot record."""
    if slot not in (0, 1):
        raise ValueError('Unknown application slot')
    active_slot(ota)  # Reject damaged and pending-verification metadata.
    valid = []
    for offset in (0, 4096):
        seq = struct.unpack_from('<I', ota, offset)[0]
        state, crc = struct.unpack_from('<II', ota, offset + 24)
        if (seq not in (0, 0xffffffff) and state not in (3, 4)
                and crc == zlib.crc32(ota[offset:offset + 4], 0xffffffff)):
            valid.append((seq, offset))
    previous = max(valid) if valid else (0, 4096)
    seq = previous[0] + 1
    if (seq - 1) % 2 != slot:
        seq += 1
    if seq >= 0xffffffff:
        raise ValueError('OTA sequence exhausted; refusing an unsafe wrap')
    record = bytearray(b'\xff' * 4096)
    struct.pack_into('<I', record, 0, seq)
    struct.pack_into('<I', record, 28, zlib.crc32(record[:4], 0xffffffff))
    offset = 4096 - previous[1]
    changed = bytearray(ota)
    changed[offset:offset + 4096] = record
    if active_slot(bytes(changed)) != slot:
        raise ValueError('Invalid generated boot selection')
    return offset, bytes(record)


def image_bytes(data, expected, limit):
    class Image:
        def read_flash(self, offset, count):
            return data[offset:offset + count]
    length = image_length(Image(), 0, limit)
    data = data[:length]
    verified_image(data)
    if project_name(data[:256]) != expected or b'Home Assistant Voice PE' not in data:
        raise ValueError('Wrong application or Voice PE board identity')
    return data


def read_application(chip, role, known=None):
    slot, offset, capacity, expected = SLOTS[role]
    prefix = chip.read_flash(offset, 256)
    if prefix == b'\xff' * 256:
        return None
    if project_name(prefix) != expected:
        raise ValueError(f'{role} slot contains an unrecognized application; nothing will be overwritten')
    # A previous complete image verification can be reused only when the device
    # still matches the exact image digest. Never trust the filename/cache alone.
    if (isinstance(known, dict) and type(known.get('bytes')) is int
            and 24 <= known['bytes'] <= capacity and known.get('project') == expected
            and re.fullmatch('[0-9a-f]{32}', known.get('md5', ''))
            and re.fullmatch('[0-9a-f]{64}', known.get('sha256', ''))
            and chip.flash_md5sum(offset, known['bytes']) == known['md5']):
        return dict(slot=slot, offset=offset, capacity=capacity, project=expected,
                    bytes=known['bytes'], sha256=known['sha256'], md5=known['md5'], data=None)
    length = image_length(chip, offset, capacity)
    chunks = []
    for at in range(0, length, 0x40000):
        count = min(0x40000, length - at)
        part = chip.read_flash(offset + at, count)
        if len(part) != count:
            raise ValueError('Incomplete application read')
        chunks.append(part)
    data = image_bytes(b''.join(chunks), expected, capacity)
    return dict(slot=slot, offset=offset, capacity=capacity, project=expected,
                bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                md5=hashlib.md5(data).hexdigest(), data=data)


def inspect(chip, known=None):
    layout = partitions(chip.read_flash(0x8000, 4096))
    if layout not in (PROJECT, PROJECT_LATEST):
        raise ValueError('Dual apps require the reviewed Voice PE project layout; migrate separately first')
    boot = chip.read_flash(0, 4)
    if len(boot) != 4 or boot[0] != 0xe9 or boot[2] != 2 or boot[3] >> 4 != 4:
        raise ValueError('Unexpected Voice PE bootloader')
    ota = chip.read_flash(0x9000, 8192)
    selected = active_slot(ota)
    apps = {role: read_application(chip, role, (known or {}).get(role)) for role in SLOTS}
    if apps['synthdef'] is None:
        raise ValueError('Install SynthDef in app0 before enabling dual apps')
    if selected == 1 and apps['rnbo'] is None:
        raise ValueError('Selected RNBO slot has no valid image')
    return layout, ota, selected, apps


def public_info(selected, apps):
    return dict(selected='synthdef' if selected == 0 else 'rnbo',
                apps={role: None if app is None else {k: v for k, v in app.items() if k != 'data'}
                      for role, app in apps.items()})


def private_folder(root, mac):
    parent = Path(root) / mac
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder = Path(tempfile.mkdtemp(prefix='dual-apps-', dir=parent))
    os.chmod(folder, 0o700)
    return folder


def save_inventory(backup_root, mac, rate, applications, board='voice-pe'):
    parent = Path(backup_root) / mac
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    record = dict(version=1, mac=mac, board=board, rate=rate,
                  apps={role: {k: v for k, v in app.items() if k != 'data'}
                        for role, app in applications.items()})
    fd, name = tempfile.mkstemp(prefix='.inventory-', dir=parent)
    with os.fdopen(fd, 'w') as out:
        os.chmod(name, 0o600)
        json.dump(record, out, indent=2); out.write('\n'); out.flush(); os.fsync(out.fileno())
    os.replace(name, parent / 'installed-apps.json')


def stage(folder, name, data):
    path = folder / name
    with path.open('xb') as out:
        os.chmod(path, 0o600)
        out.write(data)
        out.flush()
        os.fsync(out.fileno())
    return path


def write(chip, esptool, offset, path, data):
    chip.sync()
    if not chip.sync_stub_detected:
        raise ValueError('Flash loader lost synchronization')
    esptool.main(['--chip', 'esp32s3', '--baud', '3000000', '--after', 'no_reset_stub',
                  'write_flash', '--flash_mode', 'keep', '--flash_freq', 'keep',
                  '--flash_size', 'keep', hex(offset), str(path)], esp=chip)
    if chip.flash_md5sum(offset, len(data)) != hashlib.md5(data).hexdigest():
        raise ValueError('Written range failed independent verification; retain the recovery backup')


def install_rnbo(chip, esptool, data, rate, backup_root, mac):
    layout, ota, selected, apps = inspect(chip)
    data = image_bytes(data, SLOTS['rnbo'][3], SLOTS['rnbo'][2])
    profile = f'voice-pe-{rate}-256-v1'.encode()
    other = f'voice-pe-{48000 if rate == 16000 else 16000}-256-v1'.encode()
    if profile not in data or other in data:
        raise ValueError('RNBO image does not identify the requested native clock profile')
    # The SynthDef image must match a locally validated same-rate build. This
    # avoids guessing its compiled sample rate from incidental binary strings.
    from firmware_upload import load_image
    synth = load_image('voice-pe-native-16k' if rate == 16000 else 'voice-pe')
    if synth.app_hash != apps['synthdef']['sha256']:
        raise ValueError('Installed SynthDef differs from the checked matching-rate local build')
    folder = private_folder(backup_root, mac)
    old = save_region(chip, folder, 'app1-before.bin', SLOTS['rnbo'][1], SLOTS['rnbo'][2])
    # An empty prefix alone never authorizes overwriting unrelated slot data.
    if apps['rnbo'] is None:
        with (folder / old['file']).open('rb') as saved:
            while chunk := saved.read(0x40000):
                if chunk != b'\xff' * len(chunk):
                    raise ValueError('Unused slot is not wholly erased; backup retained, no write')
    save_region(chip, folder, 'ota-before.bin', 0x9000, 8192)
    protected = {'boot_and_table': (0, 0x9000), 'ota_and_phy': (0x9000, 0x3000),
                 'synthdef_slot': (0x10000, 0x7c0000),
                 'storage': (0xb90000, 0x400000), 'nvs': (0xf90000, layout[-1][-1])}
    before = {key: chip.flash_md5sum(*region) for key, region in protected.items()}
    record = dict(operation='install-rnbo-app1', rate=rate, status='backup_verified',
                  backup=old, application_sha256=hashlib.sha256(data).hexdigest(), protected=before)
    journal = folder / 'operation.json'
    journal.write_text(json.dumps(record, indent=2) + '\n'); os.chmod(journal, 0o600)
    path = stage(folder, 'rnbo-to-install.bin', data)
    record['status'] = 'writing'; journal.write_text(json.dumps(record, indent=2) + '\n')
    write(chip, esptool, SLOTS['rnbo'][1], path, data)
    after = {key: chip.flash_md5sum(*region) for key, region in protected.items()}
    if after != before:
        raise ValueError('A protected region changed; inspect the recovery backup')
    record.update(status='installed_verified', protected_after=after)
    journal.write_text(json.dumps(record, indent=2) + '\n')
    slot, offset, capacity, expected = SLOTS['rnbo']
    apps['rnbo'] = dict(slot=slot, offset=offset, capacity=capacity, project=expected,
                        bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), md5=hashlib.md5(data).hexdigest())
    save_inventory(backup_root, mac, rate, apps)
    return dict(installed='rnbo', selected='synthdef' if selected == 0 else 'rnbo',
                rate=rate, backup=str(folder), app_sha256=record['application_sha256'])


def switch(chip, esptool, role, backup_root, mac, known=None):
    layout, ota, selected, apps = inspect(chip, known)
    if any(app is None for app in apps.values()):
        raise ValueError('Install both verified applications before switching')
    target = SLOTS[role][0]
    if selected == target:
        return dict(selected=role, changed=False, **{'apps': public_info(selected, apps)['apps']})
    offset, record = ota_selection(ota, target)
    folder = private_folder(backup_root, mac)
    save_region(chip, folder, 'ota-before.bin', 0x9000, 8192)
    # Only one OTA sector changes; both application images and user storage are
    # untouched, and the other valid boot record survives an interrupted write.
    protected = {'low': (0, 0x9000), 'other_ota_sector': (0x9000 + 4096 - offset, 4096),
                 'rest': (0xb000, FLASH_BYTES - 0xb000)}
    before = {key: chip.flash_md5sum(*region) for key, region in protected.items()}
    path = stage(folder, 'ota-selection.bin', record)
    journal = dict(operation='switch', target=role, status='writing', previous_slot=selected)
    receipt = folder / 'operation.json'; receipt.write_text(json.dumps(journal, indent=2) + '\n'); os.chmod(receipt, 0o600)
    write(chip, esptool, 0x9000 + offset, path, record)
    if active_slot(chip.read_flash(0x9000, 8192)) != target:
        raise ValueError('Boot selection verification failed')
    if before != {key: chip.flash_md5sum(*region) for key, region in protected.items()}:
        raise ValueError('An unrelated flash region changed during selection')
    journal.update(status='selected_verified', selected=role)
    receipt.write_text(json.dumps(journal, indent=2) + '\n')
    return dict(selected=role, changed=True, backup=str(folder))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('status', 'install-rnbo', 'synthdef', 'rnbo'))
    parser.add_argument('--mac', required=True)
    parser.add_argument('--port')
    parser.add_argument('--image', type=Path)
    parser.add_argument('--rate', type=int, choices=(16000, 48000))
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{12}', args.mac):
        parser.error('Use the exact 12-character lowercase MAC')
    if args.action == 'install-rnbo' and (not args.image or args.rate is None):
        parser.error('install-rnbo requires --image and --rate matching XMOS')
    try:
        import esptool
        from serial.tools import list_ports
        from serial_port import open_port
        if not re.match(r'4\.(?:9|[1-9][0-9])(?:\.|$)', esptool.__version__):
            raise ValueError('Use the ESP-IDF Python environment with esptool 4.9–4.x')
        if not args.port:
            ports = [p.device for p in list_ports.comports() if p.vid == 0x303a and
                     (p.serial_number or '').replace(':', '').replace('-', '').lower() == args.mac]
            if len(ports) != 1:
                raise ValueError('Could not select exactly one matching USB device; use --port')
            args.port = ports[0]
        data = args.image.read_bytes() if args.action == 'install-rnbo' else None
        with open_port(args.port, baudrate=115200, timeout=5, exclusive=True) as link:
            chip = esptool.detect_chip(port=link, connect_mode='usb_reset', connect_attempts=3)
            try:
                if chip.CHIP_NAME != 'ESP32-S3' or chip.secure_download_mode or bytes(chip.read_mac()).hex() != args.mac:
                    raise ValueError('Unexpected chip or USB identity')
                sec = chip.get_security_info()
                if sec['parsed_flags']['SECURE_BOOT_EN'] or sec['parsed_flags']['SECURE_DOWNLOAD_ENABLE'] or sec['flash_crypt_cnt'].bit_count() % 2:
                    raise ValueError('Secured/encrypted devices are not supported')
                if not chip.IS_STUB:
                    chip = chip.run_stub()
                chip.flash_set_parameters(FLASH_BYTES)
                if esptool.cmds.detect_flash_size(chip) != '16MB':
                    raise ValueError('Voice PE requires 16 MB flash')
                chip.change_baud(3000000)
                backup = ROOT / 'recovery/voice-pe/private/dual-apps'
                known = None
                inventory = backup / args.mac / 'installed-apps.json'
                if inventory.exists():
                    saved = json.loads(inventory.read_text())
                    if saved.get('version') == 1 and saved.get('mac') == args.mac:
                        known = saved.get('apps')
                if args.action == 'status':
                    _, _, selected, apps = inspect(chip, known); result = public_info(selected, apps)
                elif args.action == 'install-rnbo':
                    result = install_rnbo(chip, esptool, data, args.rate, backup, args.mac)
                else:
                    result = switch(chip, esptool, args.action, backup, args.mac, known)
                print(json.dumps(result, indent=2))
            finally:
                original = sys.exc_info()[0]
                try:
                    chip.write_reg(chip.RTC_CNTL_OPTION1_REG, 0, chip.RTC_CNTL_FORCE_DOWNLOAD_BOOT_MASK)
                    chip.watchdog_reset()
                except Exception:
                    if original is None:
                        raise ValueError('Operation completed; normal unplug/reconnect is required')
        return 0
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
