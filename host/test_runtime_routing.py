"""No-device tests for all-board routing and data-preserving layout admission."""
import unittest
from runtime_routing import Upload, compact_layout, plan_upload


class RoutingTests(unittest.TestCase):
    def test_both_directions_on_each_board_and_matching_rates(self):
        for board, rates in [('voice-pe', (16000, 48000)), ('xiao', (16000,44100)), ('amoled-v2', (44100,))]:
            for rate in rates:
                for source, target in [('synthdef', 'rnbo'), ('rnbo', 'synthdef')]:
                    with self.subTest(board=board, rate=rate, source=source):
                        result = plan_upload(Upload(target, rate, 'validated-sha'), board=board,
                                             current_engine=source, device_rate=rate, installed={'synthdef', 'rnbo'})
                        self.assertTrue(result['switch']); self.assertTrue(result['reconnect'])

    def test_matching_engine_does_not_reboot(self):
        result = plan_upload(Upload('synthdef', 16000, 'sha'), board='voice-pe',
                             current_engine='synthdef', device_rate=16000, installed={'synthdef'})
        self.assertFalse(result['switch'])

    def test_notes_controls_discovery_cannot_switch(self):
        for action in ('note', 'set', 'volume', 'discover', 'identify'):
            with self.subTest(action=action):
                with self.assertRaisesRegex(ValueError, 'must not switch'):
                    plan_upload(Upload('rnbo', 16000, 'sha'), board='voice-pe', current_engine='synthdef',
                                device_rate=16000, installed={'synthdef', 'rnbo'}, action=action)

    def test_wrong_rate_missing_image_and_unvalidated_payload_reject(self):
        args = dict(board='voice-pe', current_engine='synthdef', device_rate=16000, installed={'synthdef'})
        for artifact in (Upload('rnbo', 16000, 'sha'), Upload('synthdef', 48000, 'sha'), b'garbage'):
            with self.assertRaises(ValueError): plan_upload(artifact, **args)

    def test_wrong_board_rate_is_not_a_request_to_reconfigure_clocks(self):
        with self.assertRaises(ValueError):
            plan_upload(Upload('rnbo', 16000, 'sha'), board='amoled-v2', current_engine='synthdef',
                        device_rate=16000, installed={'synthdef', 'rnbo'})


class LayoutTests(unittest.TestCase):
    def test_storage_and_settings_stay_at_existing_addresses_on_both_boards(self):
        for board, flash in [('xiao', 0x800000), ('amoled-v2', 0x1000000)]:
            result = compact_layout(board, 1255472, 986768)
            self.assertEqual(result['storage']['offset'], 0x310000)
            self.assertEqual(sum(result['storage'].values()), flash)
            self.assertEqual(result['nvs'], dict(offset=0x9000, bytes=0x6000))
            self.assertEqual(result['app1']['offset'] % 0x10000, 0)
            self.assertEqual(result['app1']['offset'] + result['app1']['capacity'], 0x300000)
            self.assertLessEqual(result['otadata']['offset'] + result['otadata']['bytes'], 0x310000)

    def test_oversized_images_never_silently_shrink_storage(self):
        for sizes in [(0x200000, 0x200000), (0, 1), (-1, 1), (True, 1), (1, 0x300000)]:
            with self.assertRaises(ValueError): compact_layout('xiao', *sizes)


if __name__ == '__main__': unittest.main()
