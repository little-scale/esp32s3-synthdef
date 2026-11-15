"""Guard opt-in selection, unchanged ABI and candidate composition."""
import json
from pathlib import Path
import tempfile
import unittest

from engine_profile import generate


class OscillatorSelectionTests(unittest.TestCase):
    def test_default_is_off_and_abi_is_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for profile in ('compact', 'fm1'):
                for reuse in (False, True):
                    for qualified in (False, True):
                        reference = generate(root/'reference/src', profile, reuse_buffers=reuse, qualified_kernels=qualified)
                        baseline = json.loads((reference.parent/'profile.json').read_text())
                        self.assertFalse(baseline['candidate_kernels']['saw'])
                        self.assertFalse(baseline['candidate_kernels']['impulse'])
                        for saw, impulse in ((True, False), (False, True), (True, True)):
                            target = generate(root/'target/src', profile, reuse_buffers=reuse, qualified_kernels=qualified,
                                              candidate_saw=saw, candidate_impulse=impulse)
                            for name in ('fm_synth.h', 'fm_load.c', 'fm_tables.inc'):
                                self.assertEqual((reference/name).read_bytes(), (target/name).read_bytes())
                            for filename, enabled, function in (('fm_bandlimited.inc', saw, 'candidate_saw'), ('fm_extensions.inc', impulse, 'candidate_impulse')):
                                self.assertNotIn(function, (reference/filename).read_text())
                                if enabled:
                                    self.assertIn('void '+function+'(', (target/filename).read_text())
                                else:
                                    self.assertEqual((reference/filename).read_bytes(), (target/filename).read_bytes())

    def test_composes_with_all_other_candidates(self):
        with tempfile.TemporaryDirectory() as folder:
            flags = dict.fromkeys(('candidate_smooth', 'candidate_binary', 'candidate_noise',
                'candidate_binding', 'candidate_routing', 'candidate_chaos', 'candidate_core',
                'candidate_mix', 'candidate_saw', 'candidate_impulse'), True)
            source = generate(Path(folder)/'src', 'fm1', qualified_kernels=True, **flags)
            self.assertEqual((source/'fm_extensions.inc').read_text().count('void candidate_impulse('), 1)
            self.assertEqual((source/'fm_bandlimited.inc').read_text().count('void candidate_saw('), 1)


if __name__ == '__main__': unittest.main()
