#!/usr/bin/env python3
"""Build-only native-16k XMOS companion; never accesses USB or flashes hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import os
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REVISION = '1a1df7c2b3e578431b1550a8defe8ae2c8b54d93'
IMAGE = 'ghcr.io/xmos/xcore_builder@sha256:cb301ec2c847d622a4a779a7fbbb131eba0c8f1931f53b938516b09529065e16'
WORK = ROOT / 'build/host/voice-pe-native16/xmos-src'
PATCHES = ROOT / 'ports/voice_pe/xmos/native16'
CHANGES = (
    ('application', '', REVISION, ['src/ffva/ffva_int.cmake', 'src/ffva/src/usb/usb_descriptors.c']),
    ('rtos', 'modules/rtos', '656e31cc784254d7f404f915a1663438ac46356c', ['modules/rtos_support/src/rtos_interrupt_impl.h']),
    ('microphone-array', 'modules/io/modules/mic_array', '28cc9b13ea73c9301ee6c786cb64218d773bc43e', ['etc/vanilla/mic_array_vanilla.cpp']),
)


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def prepare():
    if not WORK.exists():
        WORK.parent.mkdir(parents=True, exist_ok=True)
        run('git', 'clone', '--no-checkout', 'https://github.com/esphome/voice-kit-xmos-firmware.git', str(WORK))
        run('git', '-C', str(WORK), 'checkout', '--detach', REVISION)
    actual = subprocess.check_output(['git', '-C', str(WORK), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != REVISION:
        raise ValueError('Unexpected source revision; use a separate clean build directory.')
    run('git', '-C', str(WORK), '-c', 'url.https://github.com/.insteadOf=git@github.com:',
        'submodule', 'update', '--init', '--recursive', '--depth', '1', '--jobs', '4')
    verify(apply=True)


def verify(apply=False):
    records = []
    for name, folder, revision, files in CHANGES:
        repo = WORK / folder
        actual = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != revision:
            raise ValueError('Unexpected dependency revision: ' + name)
        patch = PATCHES / (name + '.patch')
        diff = subprocess.check_output(['git', '-C', str(repo), 'diff', '--', *files])
        if not diff and apply:
            run('git', '-C', str(repo), 'apply', '--check', str(patch))
            run('git', '-C', str(repo), 'apply', str(patch))
            diff = subprocess.check_output(['git', '-C', str(repo), 'diff', '--', *files])
        if diff != patch.read_bytes():
            raise ValueError('Source does not match reviewed native-16k patch: ' + name)
        records.append(dict(name=name, revision=revision, patch_sha256=hashlib.sha256(diff).hexdigest()))
    # Also reject changes outside the explicitly reviewed files in any submodule.
    expected = {folder: set(files) for _, folder, _, files in CHANGES}
    for folder, files in expected.items():
        changed = set(subprocess.check_output(['git', '-C', str(WORK / folder),
            'diff', '--name-only', '--ignore-submodules=all'], text=True).splitlines())
        if changed != files:
            raise ValueError('Unreviewed tracked changes: ' + (folder or 'application'))
    return records


def build():
    records = verify()
    run('docker', 'run', '--rm', '--platform', 'linux/amd64', '--network', 'none',
        '-e', 'LC_ALL=C', '-u', str(os.getuid()) + ':' + str(os.getgid()),
        '-v', str(WORK) + ':/sln_voice', '-w', '/sln_voice', IMAGE, 'bash', '-lc',
        'cmake -B build-native16 --toolchain xmos_cmake_toolchain/xs3a.cmake && '
        'cmake --build build-native16 --target create_upgrade_img_example_ffva_int_fixed_delay -j4 && '
        'cd build-native16 && xflash --factory-version 15.2 --upgrade 0 '
        'example_ffva_int_fixed_delay.xe -o example_ffva_int_fixed_delay_upgrade_factory15_2.bin')
    binary = WORK / 'build-native16/example_ffva_int_fixed_delay_upgrade.bin'
    data = binary.read_bytes()
    if not data or len(data) % 4096:
        raise ValueError('Expected a sector-aligned XMOS upgrade image.')
    if binary.with_name('example_ffva_int_fixed_delay_upgrade_factory15_2.bin').read_bytes() != data:
        raise ValueError('Factory 15.2/15.3 packaging differs; inspect the installed factory version before selecting an image.')
    record = dict(source_revision=REVISION, patches=records, container=IMAGE,
                  compiler='XTC 15.3.0', i2c_version='1.3.116', usb_bcd_device='0x1610',
                  i2s_rate=16000, bclk_hz=1024000, mclk_hz=24576000,
                  factory_15_2_and_15_3_packaging_byte_identical=True,
                  sha256=hashlib.sha256(data).hexdigest(), bytes=len(data),
                  image=str(binary.relative_to(ROOT)), hardware_testing_performed_by_build=False)
    (WORK.parent / 'xmos-build.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'verify', 'build'))
    action = parser.parse_args().action
    if action == 'prepare': prepare()
    elif action == 'verify': print(json.dumps(verify(), indent=2))
    else: build()
