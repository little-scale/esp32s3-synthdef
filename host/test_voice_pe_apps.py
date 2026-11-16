"""Portable dual-app selection and preservation checks; no physical USB."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zlib

import voice_pe_apps as apps
from test_voice_pe_firmware import Chip, app


def record(seq, state=0xffffffff):
    data = bytearray(b'\xff' * 4096)
    struct.pack_into('<I', data, 0, seq)
    struct.pack_into('<I', data, 24, state)
    struct.pack_into('<I', data, 28, zlib.crc32(data[:4], 0xffffffff))
    return bytes(data)


class SelectionTests(unittest.TestCase):
    def test_alternating_boot_records_keep_previous_valid_sector(self):
        ota = b'\xff' * 8192
        for target in (1, 0, 1, 0, 0, 1):
            old = ota
            offset, data = apps.ota_selection(ota, target)
            self.assertEqual(len(data), 4096)
            ota = old[:offset] + data + old[offset + 4096:]
            other = 4096 - offset
            self.assertEqual(old[other:other + 4096], ota[other:other + 4096])
            self.assertEqual(apps.active_slot(ota), target)

    def test_torn_new_record_keeps_previous_valid_selection(self):
        old = record(2) + b'\xff' * 4096
        offset, data = apps.ota_selection(old, 0)
        damaged = bytearray(data); damaged[0] ^= 1
        ota = old[:offset] + bytes(damaged) + old[offset + 4096:]
        self.assertEqual(apps.active_slot(ota), 1)

    def test_pending_corrupt_exhausted_and_bad_slot_reject(self):
        cases = [(record(1, 1) + b'\xff' * 4096, 1),
                 (b'\0' * 8192, 1), (record(0xfffffffe) + b'\xff' * 4096, 0),
                 (b'\xff' * 8192, 2)]
        for ota, target in cases:
            with self.subTest(target=target, prefix=ota[:4]):
                with self.assertRaises(ValueError): apps.ota_selection(ota, target)


class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.chip = Chip()
        self.tool = SimpleNamespace(main=Mock(side_effect=self.chip.write))
        self.valid = patch.object(apps, 'verified_image'); self.valid.start()
        self.rnbo = app('rnbo_s3_voice-pe', b'Home Assistant Voice PE voice-pe-16000-256-v1')
        self.synth_hash = hashlib.sha256(app()).hexdigest()
        self.local = patch('firmware_upload.load_image', return_value=SimpleNamespace(app_hash=self.synth_hash))
        self.local.start()

    def tearDown(self):
        self.local.stop(); self.valid.stop(); self.tmp.cleanup()

    def install(self, data=None):
        return apps.install_rnbo(self.chip, self.tool, self.rnbo if data is None else data,
                                 16000, self.root, '1020ba0697d4')

    def test_install_changes_only_second_app_slot_and_preserves_selection(self):
        before = bytes(self.chip.memory)
        result = self.install()
        self.assertEqual(self.chip.writes, [0x7d0000])
        self.assertEqual(self.chip.memory[:0x7d0000], before[:0x7d0000])
        self.assertEqual(self.chip.memory[0xb90000:], before[0xb90000:])
        self.assertEqual(result['selected'], 'synthdef')
        self.assertEqual(apps.active_slot(self.chip.read_flash(0x9000, 8192)), 0)
        journal = json.loads(next(self.root.rglob('operation.json')).read_text())
        self.assertEqual(journal['status'], 'installed_verified')
        backup = next(self.root.rglob('app1-before.bin'))
        self.assertEqual(backup.read_bytes(), before[0x7d0000:0xb90000])
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)

    def test_switch_both_directions_changes_only_one_ota_sector(self):
        self.install(); self.chip.writes.clear()
        for role in ('rnbo', 'synthdef'):
            before = bytes(self.chip.memory)
            result = apps.switch(self.chip, self.tool, role, self.root, '1020ba0697d4')
            self.assertTrue(result['changed'])
            self.assertEqual(self.chip.writes[-1], 0x9000 if role == 'rnbo' else 0xa000)
            self.assertEqual(self.chip.memory[:0x9000], before[:0x9000])
            self.assertEqual(self.chip.memory[0xb000:], before[0xb000:])
            self.assertEqual(apps.active_slot(self.chip.read_flash(0x9000, 8192)), apps.SLOTS[role][0])

    def test_already_selected_does_not_write(self):
        self.install(); self.chip.writes.clear()
        result = apps.switch(self.chip, self.tool, 'synthdef', self.root, '1020ba0697d4')
        self.assertFalse(result['changed']); self.assertEqual(self.chip.writes, [])

    def test_cached_images_require_exact_device_digest_and_stale_cache_rechecks(self):
        self.install()
        cache = json.loads(next(self.root.rglob('installed-apps.json')).read_text())['apps']
        original = self.chip.read_flash
        sizes = []
        def read(offset, count):
            sizes.append(count); return original(offset, count)
        with patch.object(self.chip, 'read_flash', side_effect=read):
            _, _, _, found = apps.inspect(self.chip, cache)
        self.assertIsNone(found['rnbo']['data'])
        cache['rnbo']['md5'] = '0' * 32
        _, _, _, found = apps.inspect(self.chip, cache)
        self.assertEqual(found['rnbo']['data'], self.rnbo)

    def test_missing_second_image_rejects_switch(self):
        with self.assertRaisesRegex(ValueError, 'Install both'):
            apps.switch(self.chip, self.tool, 'rnbo', self.root, '1020ba0697d4')
        self.assertEqual(self.chip.writes, [])

    def test_hidden_nonempty_tail_of_unused_slot_is_not_overwritten(self):
        self.chip.memory[0xb8ff00] = 0
        before = bytes(self.chip.memory)
        with self.assertRaisesRegex(ValueError, 'not wholly erased'): self.install()
        self.assertEqual(self.chip.writes, []); self.assertEqual(self.chip.memory, before)

    def test_unknown_slot_identity_and_wrong_profile_reject(self):
        unknown = app('other_board')
        self.chip.memory[0x7d0000:0x7d0000 + len(unknown)] = unknown
        with self.assertRaisesRegex(ValueError, 'unrecognized application'): self.install()
        self.assertEqual(self.chip.writes, [])
        self.chip = Chip(); self.tool.main.side_effect = self.chip.write
        for image in (app('rnbo_s3_voice-pe'), app('rnbo_s3_voice-pe', b'Home Assistant Voice PE voice-pe-48000-256-v1')):
            with self.assertRaisesRegex(ValueError, 'clock profile'): self.install(image)
        self.assertEqual(self.chip.writes, [])

    def test_different_synth_build_and_failed_backup_prevent_writes(self):
        with patch('firmware_upload.load_image', return_value=SimpleNamespace(app_hash='wrong')):
            with self.assertRaisesRegex(ValueError, 'matching-rate'): self.install()
        with patch.object(self.chip, 'flash_md5sum', return_value='wrong'):
            with self.assertRaisesRegex(ValueError, 'Backup verification'): self.install()
        self.assertEqual(self.chip.writes, [])

    def test_image_validation_failure_prevents_writes(self):
        with patch.object(apps, 'verified_image', side_effect=ValueError('Bad digest')):
            with self.assertRaisesRegex(ValueError, 'Bad digest'): self.install()
        self.assertEqual(self.chip.writes, [])


if __name__ == '__main__':
    unittest.main()
