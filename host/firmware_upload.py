"""Review and flash the local ESP-IDF builds supported by SynthDef Studio."""

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from patches import ROOT


@dataclass(frozen=True)
class Target:
    label: str
    folder: str
    flash_size: str
    headless: bool


TARGETS = {
    'xiao': Target('Seeed XIAO ESP32-S3', 'build-xiao', '8MB', True),
    'amoled-v2': Target('Waveshare AMOLED 1.8 V2', 'build-instrument', '16MB', False),
}
FILES = {
    '0x0': 'bootloader/bootloader.bin',
    '0x8000': 'partition_table/partition-table.bin',
    '0x10000': 'waveshare_synthdef.bin',
}
SCRIPT = Path(__file__).resolve()


@dataclass(frozen=True)
class Image:
    target: Target
    mode: str
    frequency: str
    binaries: tuple[bytes, ...]

    @property
    def app_hash(self):
        return hashlib.sha256(self.binaries[-1]).hexdigest()

    @property
    def signature(self):
        return self.mode, self.frequency, tuple(hashlib.sha256(data).digest() for data in self.binaries)


def load_image(board):
    if not isinstance(board, str) or board not in TARGETS:
        raise ValueError('Choose the exact board model.')
    target = TARGETS[board]
    folder = ROOT / 'firmware' / target.folder
    try:
        description = json.loads((folder / 'project_description.json').read_text())
        config = json.loads((folder / 'config/sdkconfig.json').read_text())
        manifest = json.loads((folder / 'flasher_args.json').read_text())
        settings = manifest['flash_settings']
        mode, frequency = settings['flash_mode'], settings['flash_freq']
        valid = (
            description.get('project_name') == 'waveshare_synthdef'
            and description.get('target') == 'esp32s3'
            and config.get('SYNTHDEF_HEADLESS', False) is target.headless
            and config.get('SYNTHDEF_TOUCH_UI', False) is (not target.headless)
            and config.get('ESPTOOLPY_FLASHSIZE') == settings['flash_size'] == target.flash_size
            and manifest['extra_esptool_args']['chip'] == 'esp32s3'
            and manifest['flash_files'] == FILES
            and all(manifest[part]['encrypted'] == 'false' for part in ('bootloader', 'partition-table', 'app'))
            and mode in ('dio', 'dout', 'qio', 'qout')
            and frequency in ('20m', '26m', '40m', '80m')
        )
        if not valid:
            raise ValueError('Build metadata does not match the selected board.')
        binaries = tuple((folder / name).read_bytes() for name in FILES.values())
        boot, partitions, app = binaries
        if not (boot.startswith(b'\xe9') and partitions.startswith(b'\xaa\x50') and app.startswith(b'\xe9')):
            raise ValueError('Invalid ESP-IDF bootloader, partition table, or application image.')
        if len(boot) > 0x8000 or len(partitions) > 0x1000 or len(app) > 0x300000:
            raise ValueError('A firmware image exceeds its flash region.')
        return Image(target, mode, frequency, binaries)
    except FileNotFoundError as error:
        raise ValueError(f'Build {target.label} first. Studio needs a complete build in firmware/{target.folder}.') from error
    except (OSError, KeyError, AttributeError, TypeError, ValueError) as error:
        raise ValueError(f'Cannot use firmware/{target.folder}. {error}') from error


def programmer_python():
    candidates = [Path(sys.executable)]
    if os.environ.get('IDF_PYTHON_ENV_PATH'):
        environment = Path(os.environ['IDF_PYTHON_ENV_PATH'])
        candidates.extend((environment / 'bin/python', environment / 'Scripts/python.exe'))
    candidates.extend(sorted(Path.home().glob('.espressif/python_env/idf5.5*/bin/python')))
    for candidate in dict.fromkeys(candidates):
        if not candidate.is_file():
            continue
        try:
            result = subprocess.run([str(candidate), str(SCRIPT), '--check'],
                                    capture_output=True, timeout=8)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0:
            return candidate
    raise ValueError('Firmware flashing needs esptool 4.9–4.x. Install it in the Studio Python environment or use the ESP-IDF 5.5 Python environment.')


def write_image(python, image, port, serial_number):
    # Flash a private snapshot of the reviewed files even if another build starts.
    with tempfile.TemporaryDirectory(prefix='studio-firmware-') as folder:
        command = [str(python), '-u', str(SCRIPT), '--port', port,
                   '--flash-size', image.target.flash_size, '--mode', image.mode,
                   '--frequency', image.frequency]
        mac = (serial_number or '').replace(':', '').replace('-', '').lower()
        if re.fullmatch(r'[0-9a-f]{12}', mac) and int(mac, 16):
            command.extend(('--mac', mac))
        command.append('--images')
        for index, data in enumerate(image.binaries):
            path = Path(folder) / f'{index}.bin'
            path.write_bytes(data)
            command.append(str(path))
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, errors='replace', timeout=180)
    log = result.stdout.replace('\r', '\n').strip()
    if result.returncode:
        raise ValueError(f'Firmware flashing failed.\n{log[-5000:]}')
    return log[-5000:]


def flash(args, esptool):
    with esptool.detect_chip(port=args.port, connect_attempts=3) as chip:
        if chip.CHIP_NAME != 'ESP32-S3' or chip.secure_download_mode:
            raise ValueError('Expected an ESP32-S3 with standard serial download mode.')
        try:
            if args.mac and bytes(chip.read_mac()).hex() != args.mac:
                raise ValueError('The ESP32 MAC does not match the selected USB device.')
            if not chip.IS_STUB:
                chip.flash_spi_attach(0)
            detected = esptool.cmds.detect_flash_size(chip)
            if detected != args.flash_size:
                raise ValueError(f'Flash size is {detected or "unknown"}. The selected build requires {args.flash_size}.')
        except ValueError:
            try:
                chip.watchdog_reset()
            except (OSError, esptool.FatalError):
                pass
            raise

        # Reuse the open connection so another device cannot be selected between
        # the ROM checks and the write. esptool verifies each written image.
        command = ['--chip', 'esp32s3', '--port', args.port, '--baud', '460800',
                   '--after', 'watchdog_reset', 'write_flash', '--flash_mode', args.mode,
                   '--flash_freq', args.frequency, '--flash_size', args.flash_size]
        for offset, path in zip(FILES, args.images, strict=True):
            command.extend((offset, path))
        esptool.main(command, esp=chip)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--port')
    parser.add_argument('--flash-size')
    parser.add_argument('--mode')
    parser.add_argument('--frequency')
    parser.add_argument('--mac')
    parser.add_argument('--images', nargs=3)
    args = parser.parse_args()
    try:
        import esptool
        version = re.match(r'4\.(\d+)', esptool.__version__)
        if not version or int(version[1]) < 9:
            raise ValueError('This programmer requires esptool 4.9–4.x.')
        if not args.check:
            flash(args, esptool)
    except Exception as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
