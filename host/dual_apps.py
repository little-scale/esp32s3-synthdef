#!/usr/bin/env python3
"""Guarded two-app setup/selection on XIAO and AMOLED; Voice PE uses voice_pe_apps.

New layouts stay entirely inside the previous application area, preserving NVS,
PHY, the bootloader and the exact SPIFFS geometry. First setup requires a full
verified backup. USB maintenance restarts the ESP32. No erase-chip operation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys

from runtime_routing import compact_layout
from voice_pe_apps import ota_selection, private_folder, stage, write, save_inventory
from voice_pe_firmware import encode_partitions, partitions, project_name, image_length, verified_image, save_region, active_slot

ROOT = Path(__file__).resolve().parents[1]
MODELS = {'xiao': 'XIAO ESP32-S3', 'amoled-v2': 'Waveshare AMOLED 1.8 V2'}
RNBO_BOARDS = {'xiao': 'xiao', 'amoled-v2': 'amoled'}


def identities(board):
    return {'synthdef': 'waveshare_synthdef', 'rnbo': 'rnbo_s3_' + RNBO_BOARDS[board]}


def legacy_layout(board):
    flash = 0x800000 if board == 'xiao' else 0x1000000
    return (('nvs', 1, 2, 0x9000, 0x6000), ('phy_init', 1, 1, 0xf000, 0x1000),
            ('factory', 0, 0, 0x10000, 0x300000), ('storage', 1, 0x82, 0x310000, flash - 0x310000))


def dual_layout(board, plan):
    a, b = plan['app0'], plan['app1']
    return legacy_layout(board)[:2] + (
        ('app0', 0, 0x10, a['offset'], a['capacity']),
        ('app1', 0, 0x11, b['offset'], b['capacity']),
        ('otadata', 1, 0, 0x300000, 8192), legacy_layout(board)[-1])


def validate_dual_layout(board, rows):
    if len(rows) != 6:
        raise ValueError('Unrecognized dual-app partition layout')
    a, b = rows[2], rows[3]
    if (a[:4] != ('app0', 0, 0x10, 0x10000) or a[4] <= 0 or a[4] % 0x10000
            or b[:3] != ('app1', 0, 0x11) or b[3] != 0x10000 + a[4]
            or b[4] <= 0 or b[4] % 0x10000 or b[3] + b[4] != 0x300000):
        raise ValueError('Unrecognized dual-app application bounds')
    plan = dict(app0=dict(offset=a[3], capacity=a[4]), app1=dict(offset=b[3], capacity=b[4]))
    if rows != dual_layout(board, plan):
        raise ValueError('Settings/storage geometry changed; no writes allowed')
    return plan


def complete_image(chip, offset, capacity, expected, model):
    length = image_length(chip, offset, capacity)
    chunks = []
    for at in range(0, length, 0x40000):
        count = min(0x40000, length - at); block = chip.read_flash(offset + at, count)
        if len(block) != count: raise ValueError('Incomplete application read')
        chunks.append(block)
    data = b''.join(chunks); verified_image(data)
    if project_name(data[:256]) not in expected or model.encode() not in data:
        raise ValueError('Installed application belongs to a different/unrecognized board')
    return data


def image_rate(data, board):
    markers=set(re.findall(rb'S3_NATIVE_RATE=([0-9]+)u?\x00',data))
    if len(markers)>1:raise ValueError('Conflicting application sample-rate markers')
    if b'S3_NATIVE_RATE=' in data and not markers:raise ValueError('Malformed application sample-rate marker')
    # Images predating explicit rate markers on these boards were 44.1 kHz only.
    rate=int(next(iter(markers))) if markers else 44100
    if rate not in ((16000,44100) if board=='xiao' else (44100,)):
        raise ValueError('Unsupported application board/sample rate')
    return rate


def inspect(chip, board):
    rows = partitions(chip.read_flash(0x8000, 4096)); plan = validate_dual_layout(board, rows)
    current = active_slot(chip.read_flash(0x300000, 8192))
    apps = {}
    for role, key in [('synthdef', 'app0'), ('rnbo', 'app1')]:
        slot = plan[key]
        data = complete_image(chip, slot['offset'], slot['capacity'], {identities(board)[role]}, MODELS[board])
        apps[role] = dict(**slot, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),rate=image_rate(data,board))
    selected='synthdef' if current == 0 else 'rnbo'
    return dict(board=board, rate=apps[selected]['rate'], selected=selected, apps=apps)


def select(chip, esptool, board, role, backup, mac):
    info = inspect(chip, board)
    if info['selected'] == role: return dict(**info, changed=False)
    ota = chip.read_flash(0x300000, 8192); offset, data = ota_selection(ota, int(role == 'rnbo'))
    folder = private_folder(backup, mac); save_region(chip, folder, 'ota-before.bin', 0x300000, 8192)
    flash = 0x800000 if board == 'xiao' else 0x1000000
    ranges = [(0, 0x300000), (0x300000 + 4096 - offset, 4096), (0x302000, flash - 0x302000)]
    before = [chip.flash_md5sum(*r) for r in ranges]
    path = stage(folder, 'ota-selection.bin', data)
    write(chip, esptool, 0x300000 + offset, path, data)
    if active_slot(chip.read_flash(0x300000, 8192)) != int(role == 'rnbo'):
        raise ValueError('Boot selection verification failed')
    if before != [chip.flash_md5sum(*r) for r in ranges]: raise ValueError('Protected flash changed')
    return dict(board=board, rate=info['apps'][role]['rate'], selected=role, changed=True, backup=str(folder))


def setup(chip, esptool, board, synth, rnbo, backup, mac):
    if board not in MODELS: raise ValueError('Unknown board')
    rate=image_rate(synth,board)
    if image_rate(rnbo,board)!=rate:raise ValueError('Both applications must have the same sample rate for setup')
    for role, data in [('synthdef', synth), ('rnbo', rnbo)]:
        verified_image(data)
        if project_name(data[:256]) != identities(board)[role] or MODELS[board].encode() not in data:
            raise ValueError('Wrong target image identity/model')
    rows = partitions(chip.read_flash(0x8000, 4096))
    if rows != legacy_layout(board):
        raise ValueError('First setup requires the exact reviewed factory layout; existing pairs are not repartitioned')
    flash = 0x800000 if board == 'xiao' else 0x1000000
    boot = chip.read_flash(0, 4)
    if len(boot) != 4 or boot[0] != 0xe9 or boot[3] >> 4 != (3 if board == 'xiao' else 4):
        raise ValueError('Unexpected flash bootloader/size')
    old = complete_image(chip, 0x10000, 0x300000, set(identities(board).values()), MODELS[board])
    plan = compact_layout(board, max(len(synth), len(old)), len(rnbo))
    folder = private_folder(backup, mac)
    saved = save_region(chip, folder, 'full-flash-before.bin', 0, flash)
    # The old running image ends before app1, so installing RNBO first does not
    # disturb the old app. Once the table changes, RNBO is the recovery app while
    # SynthDef is written. A first partition-table write still needs stable USB.
    protected = [(0, 0x8000), (0x9000, 0x7000), (0x310000, flash - 0x310000)]
    before = [chip.flash_md5sum(*r) for r in protected]
    paths = {'rnbo': stage(folder, 'rnbo.bin', rnbo), 'synthdef': stage(folder, 'synthdef.bin', synth)}
    table = encode_partitions(dual_layout(board, plan))
    table_path = stage(folder, 'dual-partitions.bin', table)
    offset, record = ota_selection(b'\xff' * 8192, 1)
    ota = bytearray(b'\xff' * 8192); ota[offset:offset + 4096] = record
    ota_path = stage(folder, 'initial-ota-rnbo.bin', bytes(ota))
    receipt = folder / 'operation.json'
    result = dict(board=board, mac=mac, rate=rate, status='backup_verified',
                  backup=saved, layout_before=rows, layout_after=dual_layout(board, plan))
    def journal(stage_name):
        result['status'] = stage_name; receipt.write_text(json.dumps(result, indent=2) + '\n'); os.chmod(receipt, 0o600)
    journal('installing-rnbo')
    write(chip, esptool, plan['app1']['offset'], paths['rnbo'], rnbo)
    write(chip, esptool, 0x300000, ota_path, bytes(ota))
    journal('installing-partition-table')
    write(chip, esptool, 0x8000, table_path, table)
    journal('installing-synthdef')
    write(chip, esptool, 0x10000, paths['synthdef'], synth)
    for role, offset in [('synthdef', 0x10000), ('rnbo', plan['app1']['offset'])]:
        data = synth if role == 'synthdef' else rnbo
        if chip.flash_md5sum(offset, len(data)) != hashlib.md5(data).hexdigest():
            raise ValueError('A completed application changed; retain recovery backup')
    if before != [chip.flash_md5sum(*r) for r in protected]: raise ValueError('Settings/storage protection failed')
    journal('both-apps-verified')
    selected = select(chip, esptool, board, 'synthdef', backup, mac)
    journal('setup_verified')
    applications = {}
    for role, data, slot in [('synthdef', synth, plan['app0']), ('rnbo', rnbo, plan['app1'])]:
        applications[role] = dict(**slot, project=identities(board)[role], bytes=len(data),
                                  sha256=hashlib.sha256(data).hexdigest(), md5=hashlib.md5(data).hexdigest(),rate=rate)
    save_inventory(backup, mac, rate, applications, board=board)
    return dict(board=board, rate=rate, selected=selected['selected'], backup=str(folder),
                layout=plan, status='setup_verified')


def update(chip, esptool, board, role, data, backup, mac):
    info = inspect(chip, board)
    rate=image_rate(data,board)
    if role not in ('synthdef', 'rnbo'): raise ValueError('Choose the runtime to update')
    verified_image(data)
    if project_name(data[:256]) != identities(board)[role] or MODELS[board].encode() not in data:
        raise ValueError('Wrong target runtime/board')
    target = info['apps'][role]
    if len(data) > target['capacity']: raise ValueError('Updated image exceeds its installed slot; no write')
    other = 'rnbo' if role == 'synthdef' else 'synthdef'
    untouched = info['apps'][other]
    folder = private_folder(backup, mac)
    old_app = save_region(chip, folder, 'application-before.bin', target['offset'], target['capacity'])
    old_ota = save_region(chip, folder, 'ota-before.bin', 0x300000, 8192)
    record = dict(board=board, mac=mac, operation='update', engine=role,
                  previous_selection=info['selected'], application_backup=old_app,
                  ota_backup=old_ota, target_sha256=hashlib.sha256(data).hexdigest())
    receipt = folder / 'operation.json'
    def journal(status):
        record['status'] = status; receipt.write_text(json.dumps(record, indent=2) + '\n'); os.chmod(receipt, 0o600)
    journal('backup_verified')
    ranges = [(0, 0x10000), (untouched['offset'], untouched['capacity']),
              (0x302000, (0x800000 if board == 'xiao' else 0x1000000) - 0x302000)]
    before = [chip.flash_md5sum(*r) for r in ranges]
    # Keep the other already-verified runtime selected during the write. A
    # power failure in this application's update can still boot its companion.
    select(chip, esptool, board, other, backup, mac)
    path = stage(folder, role + '-update.bin', data)
    journal('writing')
    write(chip, esptool, target['offset'], path, data)
    if before != [chip.flash_md5sum(*r) for r in ranges]: raise ValueError('Protected flash changed during app update')
    selected = select(chip, esptool, board, info['selected'], backup, mac)
    journal('updated_verified')
    applications = dict(info['apps'])
    applications[role] = dict(target, bytes=len(data), project=identities(board)[role],rate=rate,
                              sha256=hashlib.sha256(data).hexdigest(), md5=hashlib.md5(data).hexdigest())
    applications[other] = dict(untouched, project=identities(board)[other],
                               md5=chip.flash_md5sum(untouched['offset'], untouched['bytes']))
    common_rate=rate if rate==applications[other]['rate'] else None
    # A staged rate change may temporarily leave different app rates. Keep the
    # per-app facts, but disable automatic routing until both images match.
    save_inventory(backup, mac, common_rate, applications, board=board)
    return dict(updated=role, selected=selected['selected'], verified=True, backup=str(folder),
                app_sha256=hashlib.sha256(data).hexdigest())


def load_targets(board, synth_folder, rnbo_folder):
    """Check board build metadata before any device connection."""
    synth_folder, rnbo_folder = Path(synth_folder), Path(rnbo_folder)
    sdk = json.loads((synth_folder / 'config/sdkconfig.json').read_text())
    desc = json.loads((synth_folder / 'project_description.json').read_text())
    size = '8MB' if board == 'xiao' else '16MB'
    if (desc.get('project_name') != 'waveshare_synthdef' or desc.get('target') != 'esp32s3'
            or sdk.get('ESPTOOLPY_FLASHSIZE') != size or sdk.get('SYNTHDEF_VOICE_PE', False)
            or sdk.get('SYNTHDEF_HEADLESS', False) is not (board == 'xiao')
            or sdk.get('SYNTHDEF_TOUCH_UI', False) is not (board == 'amoled-v2')):
        raise ValueError('SynthDef build metadata does not match the chosen board')
    rate=16000 if sdk.get('SYNTHDEF_XIAO_NATIVE_16K', False) else 44100
    if rate==16000 and board!='xiao':raise ValueError('Native 16 kHz is only supported on XIAO here')
    report = json.loads((rnbo_folder / 'build-report.json').read_text())
    if (report.get('board') != RNBO_BOARDS[board] or report.get('player') is not True
            or report.get('sample_rate') != rate or report.get('block_frames') != 256
            or report.get('usb_midi_host', False)):
        raise ValueError('RNBO must be the matching board player with USB console and matching sample rate / 256-frame profile')
    rnbo_sdk = json.loads((rnbo_folder / 'config/sdkconfig.json').read_text())
    geometry = ('SPIFFS_PAGE_SIZE', 'SPIFFS_OBJ_NAME_LEN', 'SPIFFS_META_LENGTH',
                'SPIFFS_USE_MAGIC', 'SPIFFS_USE_MAGIC_LENGTH', 'SPIFFS_USE_MTIME',
                'SPIFFS_ALIGNED_OBJECT_INDEX_TABLES')
    if any(sdk.get(key) != rnbo_sdk.get(key) for key in geometry):
        raise ValueError('The two builds have incompatible filesystem formats; no device access')
    def bounded_image(path):
        if not path.is_file(): raise ValueError('Expected a regular firmware image')
        with path.open('rb') as source: data = source.read(0x300001)
        if not 0 < len(data) <= 0x300000: raise ValueError('Firmware exceeds the old application area')
        return data
    synth = bounded_image(synth_folder / 'waveshare_synthdef.bin')
    rnbo_path = rnbo_folder / (identities(board)['rnbo'] + '.bin'); rnbo = bounded_image(rnbo_path)
    hashes = [v.get('sha256') for k, v in report.get('artifacts', {}).items() if k.endswith('/' + rnbo_path.name)]
    if hashes != [hashlib.sha256(rnbo).hexdigest()]: raise ValueError('RNBO image differs from its build report')
    for role, data in [('synthdef', synth), ('rnbo', rnbo)]:
        verified_image(data)
        if image_rate(data,board)!=rate:raise ValueError('Application rate marker differs from its build metadata')
        if project_name(data[:256]) != identities(board)[role] or MODELS[board].encode() not in data:
            raise ValueError('Wrong target firmware image')
    compact_layout(board, len(synth), len(rnbo))
    return synth, rnbo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('plan', 'setup', 'update', 'status', 'synthdef', 'rnbo'))
    parser.add_argument('--board', required=True, choices=('voice-pe', *MODELS))
    parser.add_argument('--mac'); parser.add_argument('--port')
    parser.add_argument('--synthdef-build', type=Path); parser.add_argument('--rnbo-build', type=Path)
    parser.add_argument('--engine', choices=('synthdef', 'rnbo'), help='Runtime to update')
    parser.add_argument('--live', action='store_true', help='Read-only runtime status without entering the ROM loader')
    args = parser.parse_args()
    try:
        if args.live:
            if args.action != 'status' or not args.mac or not re.fullmatch('[0-9a-f]{12}', args.mac):
                raise ValueError('--live requires status and the exact --mac')
            from dual_upload import probe, MODELS as LIVE_MODELS
            result = probe(args.mac, args.port)
            if not result: raise ValueError('Older app has no safe live probe; ordinary status performs a maintenance reboot')
            if result.get('model') != LIVE_MODELS[args.board]: raise ValueError('The runtime reports a different board')
            print(json.dumps(result, indent=2)); return 0
        if args.board == 'voice-pe':
            if args.action not in ('status', 'synthdef', 'rnbo'):
                raise ValueError('Voice PE uses host/voice_pe_apps.sh install-rnbo and its guarded SynthDef updater')
            if not args.mac: raise ValueError('Provide the exact --mac')
            command = [sys.executable, str(ROOT/'host/voice_pe_apps.py'), args.action, '--mac', args.mac]
            if args.port: command += ['--port', args.port]
            return subprocess.run(command).returncode
        images = None
        if args.action in ('plan', 'setup', 'update'):
            if not args.synthdef_build or not args.rnbo_build: raise ValueError('Provide both complete board build folders')
            images = load_targets(args.board, args.synthdef_build, args.rnbo_build)
            if args.action == 'plan':
                print(json.dumps(compact_layout(args.board, *map(len, images)), indent=2)); return 0
        if args.action == 'update' and not args.engine: raise ValueError('update requires --engine')
        if not args.mac or not re.fullmatch('[0-9a-f]{12}', args.mac): raise ValueError('Provide the exact lowercase 12-digit --mac')
        import esptool
        from serial.tools import list_ports
        from serial_port import open_port
        if not re.match(r'4\.(?:9|[1-9][0-9])(?:\.|$)', esptool.__version__): raise ValueError('Use esptool 4.9–4.x')
        if not args.port:
            found = [p.device for p in list_ports.comports() if p.vid == 0x303a and
                     (p.serial_number or '').replace(':', '').replace('-', '').lower() == args.mac]
            if len(found) != 1: raise ValueError('Select exactly one matching USB device with --port')
            args.port = found[0]
        with open_port(args.port, baudrate=115200, timeout=5, exclusive=True) as link:
            chip = esptool.detect_chip(port=link, connect_mode='usb_reset', connect_attempts=3)
            try:
                if chip.CHIP_NAME != 'ESP32-S3' or chip.secure_download_mode or bytes(chip.read_mac()).hex() != args.mac:
                    raise ValueError('Unexpected USB chip/identity')
                sec = chip.get_security_info()
                if sec['parsed_flags']['SECURE_BOOT_EN'] or sec['parsed_flags']['SECURE_DOWNLOAD_ENABLE'] or sec['flash_crypt_cnt'].bit_count() % 2:
                    raise ValueError('Secured/encrypted devices are not supported')
                if not chip.IS_STUB: chip = chip.run_stub()
                flash = '8MB' if args.board == 'xiao' else '16MB'
                chip.flash_set_parameters(0x800000 if args.board == 'xiao' else 0x1000000)
                if esptool.cmds.detect_flash_size(chip) != flash: raise ValueError('Unexpected physical flash size')
                chip.change_baud(3000000)
                backup = ROOT / 'build/host/private/dual-apps'
                if args.action == 'setup': result = setup(chip, esptool, args.board, *images, backup, args.mac)
                elif args.action == 'update': result = update(chip, esptool, args.board, args.engine, images[0 if args.engine == 'synthdef' else 1], backup, args.mac)
                elif args.action == 'status': result = inspect(chip, args.board)
                else: result = select(chip, esptool, args.board, args.action, backup, args.mac)
                print(json.dumps(result, indent=2))
            finally:
                original = sys.exc_info()[0]
                try:
                    chip.write_reg(chip.RTC_CNTL_OPTION1_REG, 0, chip.RTC_CNTL_FORCE_DOWNLOAD_BOOT_MASK); chip.watchdog_reset()
                except Exception:
                    if original is None: raise ValueError('Operation completed; normal unplug/reconnect is required')
        return 0
    except Exception as error:
        print(str(error), file=sys.stderr); return 1


if __name__ == '__main__': sys.exit(main())
