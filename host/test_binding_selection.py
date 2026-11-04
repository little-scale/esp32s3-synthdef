"""Check that the narrowed hardware candidate only changes its selected kernels."""
import tempfile
from pathlib import Path
import unittest
from engine_profile import generate


class SelectionTests(unittest.TestCase):
    def test_only_delay_reverb_and_shared_binding_declarations_change(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            a=generate(root/'baseline','fm1')
            b=generate(root/'selected','fm1',candidate_binding=True,binding_families=['delay_render','render_miverb'])
            changed={p.name for p in a.iterdir() if p.suffix in ('.c','.h','.inc') and p.read_bytes()!=(b/p.name).read_bytes()}
            self.assertEqual(changed,{'fm_render.c','fm_delay.inc','fm_miverb.inc','fm_profile_render.inc'})
            for name in ('fm_extensions.inc','fm_utilities.inc','fm_modulation.inc','fm_fast.inc'):
                self.assertEqual((a/name).read_bytes(),(b/name).read_bytes())
    def test_mask_requires_binding_and_known_entries(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError,'require'):
                generate(Path(folder),'fm1',binding_families=['delay_render'])
            with self.assertRaisesRegex(ValueError,'known'):
                generate(Path(folder),'fm1',candidate_binding=True,binding_families=['not_a_renderer'])


if __name__=='__main__':unittest.main()
