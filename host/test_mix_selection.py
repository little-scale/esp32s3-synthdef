"""Ensure mixer experiments remain explicit and compose with both profiles."""
import json
from pathlib import Path
import tempfile
import unittest

from engine_profile import generate


class MixSelectionTests(unittest.TestCase):
    def test_mixer_is_off_by_default_and_declares_its_effective_flag(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for profile in ('compact', 'fm1'):
                for reuse in (False, True):
                    a = generate(root/'baseline/src', profile, reuse_buffers=reuse, qualified_kernels=True)
                    b = generate(root/'candidate/src', profile, reuse_buffers=reuse,
                                 qualified_kernels=True, candidate_mix=True)
                    baseline = json.loads((a.parent/'profile.json').read_text())
                    candidate = json.loads((b.parent/'profile.json').read_text())
                    self.assertFalse(baseline['candidate_kernels']['mix'])
                    self.assertTrue(candidate['candidate_kernels']['mix'])
                    self.assertIn('#define FM_MIX_KERNELS_ENABLED 0', (a/'fm_build_profile.h').read_text())
                    self.assertIn('#define FM_MIX_KERNELS_ENABLED 1', (b/'fm_build_profile.h').read_text())
                    self.assertEqual((a/'fm_synth.h').read_bytes(), (b/'fm_synth.h').read_bytes())
                    self.assertEqual((a/'fm_load.c').read_bytes(), (b/'fm_load.c').read_bytes())
                    self.assertNotIn('goto arithmetic_done;\n }\n /* Resolve', (a/'fm_fast.inc').read_text())
                    self.assertIn('const float *e=x[3].p', (b/'fm_fast.inc').read_text())

    def test_mixer_composes_with_the_other_candidates(self):
        with tempfile.TemporaryDirectory() as folder:
            flags = dict.fromkeys(('candidate_smooth', 'candidate_binary', 'candidate_noise',
                                  'candidate_binding', 'candidate_routing', 'candidate_chaos',
                                  'candidate_core', 'candidate_mix'), True)
            source = generate(Path(folder)/'src', 'fm1', qualified_kernels=True, **flags)
            text = (source/'fm_fast.inc').read_text()
            self.assertEqual(text.count('float *out_left='), 1)
            self.assertEqual(text.count('const float *e=x[3].p'), 1)


if __name__ == '__main__': unittest.main()
