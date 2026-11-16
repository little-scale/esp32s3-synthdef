"""Computer-only preservation and interruption checks for XIAO/AMOLED pairing."""
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import dual_apps as dual
from firmware_upload import reject_dual_app_overwrite
from runtime_routing import compact_layout
from voice_pe_firmware import encode_partitions, partitions, project_name, active_slot
from test_voice_pe_firmware import Chip, app


class MigrationTests(unittest.TestCase):
    def test_xiao_16k_cannot_be_paired_with_44100_rnbo(self):
        with tempfile.TemporaryDirectory() as root:
            synth = Path(root) / 'synth'; (synth/'config').mkdir(parents=True)
            (synth/'project_description.json').write_text(json.dumps(dict(project_name='waveshare_synthdef',target='esp32s3')))
            (synth/'config/sdkconfig.json').write_text(json.dumps(dict(ESPTOOLPY_FLASHSIZE='8MB',
                SYNTHDEF_HEADLESS=True,SYNTHDEF_XIAO_NATIVE_16K=True)))
            rnbo=Path(root)/'rnbo';rnbo.mkdir()
            (rnbo/'build-report.json').write_text(json.dumps(dict(board='xiao',player=True,sample_rate=44100,block_frames=256)))
            # Rate rejection precedes image loading or device access.
            with self.assertRaisesRegex(ValueError,'matching sample rate'):
                dual.load_targets('xiao',synth,rnbo)

    def test_rate_markers_and_unknown_old_images(self):
        self.assertEqual(dual.image_rate(b'old firmware','xiao'),44100)
        self.assertEqual(dual.image_rate(b'S3_NATIVE_RATE=16000u\0','xiao'),16000)
        for data,board in ((b'S3_NATIVE_RATE=16000u\0','amoled-v2'),
                           (b'S3_NATIVE_RATE=22050u\0','xiao'),
                           (b'S3_NATIVE_RATE=invalid\0','xiao'),
                           (b'S3_NATIVE_RATE=48000u\0','xiao'),
                           (b'S3_NATIVE_RATE=16000u\0S3_NATIVE_RATE=44100u\0','xiao')):
            with self.assertRaises(ValueError):dual.image_rate(data,board)

    def test_mixed_rate_update_blocks_auto_inventory_until_both_match(self):
        chip,tool,synth,rnbo,_,_=self.setup_pair('xiao')
        synth16=app('waveshare_synthdef',b'XIAO ESP32-S3\0S3_NATIVE_RATE=16000u\0')
        rnbo16=app('rnbo_s3_xiao',b'XIAO ESP32-S3\0S3_NATIVE_RATE=16000u\0')
        dual.update(chip,tool,'xiao','synthdef',synth16,self.root,'001122334455')
        inventory=self.root/'001122334455/installed-apps.json'
        self.assertIsNone(json.loads(inventory.read_text())['rate'])
        self.assertEqual(dual.inspect(chip,'xiao')['rate'],16000)
        dual.update(chip,tool,'xiao','rnbo',rnbo16,self.root,'001122334455')
        self.assertEqual(json.loads(inventory.read_text())['rate'],16000)

    def test_filesystem_format_mismatch_rejects_before_loading_images(self):
        with tempfile.TemporaryDirectory() as root:
            synth, rnbo = Path(root) / 'synth', Path(root) / 'rnbo'
            for folder in (synth, rnbo): (folder / 'config').mkdir(parents=True)
            (synth / 'project_description.json').write_text(json.dumps(dict(project_name='waveshare_synthdef', target='esp32s3')))
            sdk = dict(ESPTOOLPY_FLASHSIZE='8MB', SYNTHDEF_HEADLESS=True,
                       SYNTHDEF_TOUCH_UI=False, SPIFFS_PAGE_SIZE=256)
            (synth / 'config/sdkconfig.json').write_text(json.dumps(sdk))
            (rnbo / 'config/sdkconfig.json').write_text(json.dumps(dict(SPIFFS_PAGE_SIZE=512)))
            (rnbo / 'build-report.json').write_text(json.dumps(dict(board='xiao', player=True,
                sample_rate=44100, block_frames=256)))
            with self.assertRaisesRegex(ValueError, 'filesystem formats'):
                dual.load_targets('xiao', synth, rnbo)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.verify = patch.object(dual, 'verified_image'); self.verify.start()
        self.verify_selection = patch('voice_pe_apps.verified_image'); self.verify_selection.start()

    def tearDown(self):
        self.verify.stop(); self.verify_selection.stop(); self.tmp.cleanup()

    def fixture(self, board):
        chip = Chip(); size = 0x800000 if board == 'xiao' else 0x1000000
        chip.memory = bytearray(b'\xff' * size)
        chip.memory[:4] = b'\xe9\x03\x02' + bytes([0x3f if board == 'xiao' else 0x4f])
        chip.memory[0x8000:0x9000] = encode_partitions(dual.legacy_layout(board)).ljust(4096, b'\xff')
        model = dual.MODELS[board].encode()
        synth = app('waveshare_synthdef', model)
        rnbo = app(dual.identities(board)['rnbo'], model)
        chip.memory[0x10000:0x10000 + len(synth)] = synth
        chip.memory[0x9000:0x9008] = b'USER NVS'
        chip.memory[0x310000:0x310010] = b'SAVED PATCH DATA'
        return chip, synth, rnbo

    def setup_pair(self, board):
        chip, synth, rnbo = self.fixture(board)
        tool = SimpleNamespace(main=Mock(side_effect=chip.write))
        before = bytes(chip.memory)
        result = dual.setup(chip, tool, board, synth, rnbo, self.root, '001122334455')
        return chip, tool, synth, rnbo, before, result

    def test_migration_preserves_boot_settings_and_exact_storage_on_both_boards(self):
        for board in ('xiao', 'amoled-v2'):
            with self.subTest(board=board):
                chip, tool, synth, rnbo, before, result = self.setup_pair(board)
                self.assertEqual(chip.memory[:0x8000], before[:0x8000])
                self.assertEqual(chip.memory[0x9000:0x10000], before[0x9000:0x10000])
                self.assertEqual(chip.memory[0x310000:], before[0x310000:])
                self.assertEqual(partitions(chip.read_flash(0x8000, 4096)), dual.dual_layout(board, result['layout']))
                self.assertEqual(active_slot(chip.read_flash(0x300000, 8192)), 0)
                self.assertEqual(chip.read_flash(0x10000, len(synth)), synth)
                self.assertEqual(chip.read_flash(result['layout']['app1']['offset'], len(rnbo)), rnbo)
                saved = Path(result['backup']) / 'full-flash-before.bin'
                self.assertEqual(saved.read_bytes(), before)
                self.assertEqual(saved.stat().st_mode & 0o777, 0o600)

    def test_switch_both_directions_changes_only_ota_records(self):
        chip, tool, _, _, _, result = self.setup_pair('xiao')
        for role in ('rnbo', 'synthdef'):
            before = bytes(chip.memory); chip.writes.clear()
            selected = dual.select(chip, tool, 'xiao', role, self.root, '001122334455')
            self.assertTrue(selected['changed'])
            self.assertEqual(len(chip.writes), 1)
            self.assertIn(chip.writes[0], (0x300000, 0x301000))
            self.assertEqual(chip.memory[:0x300000], before[:0x300000])
            self.assertEqual(chip.memory[0x302000:], before[0x302000:])

    def test_unknown_layout_wrong_board_bad_images_and_failed_backup_never_write(self):
        for issue in ('layout', 'board', 'digest', 'backup'):
            with self.subTest(issue=issue):
                chip, synth, rnbo = self.fixture('xiao'); tool = SimpleNamespace(main=Mock(side_effect=chip.write))
                if issue == 'layout': chip.memory[0x8000] ^= 1
                if issue == 'board': rnbo = app('rnbo_s3_amoled', b'Waveshare AMOLED 1.8 V2')
                before = bytes(chip.memory)
                validator = patch.object(dual, 'verified_image', side_effect=ValueError('digest')) if issue == 'digest' else patch.object(dual, 'verified_image')
                backup = patch.object(chip, 'flash_md5sum', return_value='bad') if issue == 'backup' else patch.object(chip, 'flash_md5sum', wraps=chip.flash_md5sum)
                with validator, backup, self.assertRaises(ValueError):
                    dual.setup(chip, tool, 'xiao', synth, rnbo, self.root, '001122334455')
                self.assertEqual(chip.writes, []); self.assertEqual(chip.memory, before)

    def test_power_interruption_after_table_keeps_rnbo_available(self):
        chip, synth, rnbo = self.fixture('xiao'); original = chip.write
        def fail_synth(command, esp):
            args = command[command.index('--flash_size') + 2:]
            if int(args[0], 0) == 0x10000: raise OSError('power interrupted')
            return original(command, esp)
        tool = SimpleNamespace(main=Mock(side_effect=fail_synth))
        with self.assertRaisesRegex(OSError, 'power interrupted'):
            dual.setup(chip, tool, 'xiao', synth, rnbo, self.root, '001122334455')
        plan = dual.validate_dual_layout('xiao', partitions(chip.read_flash(0x8000, 4096)))
        self.assertEqual(active_slot(chip.read_flash(0x300000, 8192)), 1)
        self.assertEqual(chip.read_flash(plan['app1']['offset'], len(rnbo)), rnbo)

    def test_existing_pair_cannot_be_repartitioned_as_a_first_install(self):
        chip, tool, synth, rnbo, _, _ = self.setup_pair('xiao'); chip.writes.clear()
        with self.assertRaisesRegex(ValueError, 'First setup'):
            dual.setup(chip, tool, 'xiao', synth, rnbo, self.root, '001122334455')
        self.assertEqual(chip.writes, [])

    def test_legacy_synthdef_uploader_refuses_both_dual_board_layouts(self):
        for board in ('xiao', 'amoled-v2'):
            plan = compact_layout(board, 1407392, 937376)
            with self.assertRaisesRegex(ValueError, 'Dual applications detected'):
                reject_dual_app_overwrite(encode_partitions(dual.dual_layout(board, plan)))
            reject_dual_app_overwrite(encode_partitions(dual.legacy_layout(board)))
        reject_dual_app_overwrite(b'\xff' * 4096)

    def test_each_runtime_update_preserves_companion_settings_storage_and_selection(self):
        for role in ('synthdef', 'rnbo'):
            with self.subTest(role=role):
                chip, tool, synth, rnbo, _, _ = self.setup_pair('xiao')
                before = bytes(chip.memory)
                updated = app(dual.identities('xiao')[role], b'XIAO ESP32-S3 updated')
                result = dual.update(chip, tool, 'xiao', role, updated, self.root, '001122334455')
                info = dual.inspect(chip, 'xiao'); other = info['apps']['rnbo' if role == 'synthdef' else 'synthdef']
                self.assertEqual(chip.memory[other['offset']:other['offset'] + other['capacity']], before[other['offset']:other['offset'] + other['capacity']])
                self.assertEqual(chip.memory[:0x10000], before[:0x10000])
                self.assertEqual(chip.memory[0x310000:], before[0x310000:])
                self.assertEqual(result['selected'], 'synthdef'); self.assertTrue(result['verified'])


if __name__ == '__main__': unittest.main()
