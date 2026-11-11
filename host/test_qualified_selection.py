"""Scope, dispatch ordering and experiment-composition guards; no hardware."""
import tempfile
import unittest
from pathlib import Path
from engine_profile import generate
REF_TYPE='typedef struct {const float *p;unsigned rate;} candidate_input_ref;'


class SelectionTests(unittest.TestCase):
    def test_only_measured_paths_change_and_fast_exits_stay_first(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);a=generate(root/'baseline','fm1');b=generate(root/'qualified','fm1',qualified_kernels=True)
            changed={p.name for p in a.iterdir() if p.suffix in ('.c','.h','.inc') and p.read_bytes()!=(b/p.name).read_bytes()}
            self.assertEqual(changed,{'fm_render.c','fm_delay.inc','fm_miverb.inc','fm_profile_render.inc','fm_build_profile.h'})
            text=(b/'fm_render.c').read_text();self.assertEqual(text.count(REF_TYPE),1)
            start=text.index('static void render_graph(');dispatch=text[start:]
            self.assertLess(dispatch.index('fast_arithmetic('),dispatch.index('qualified_smooth('))
            self.assertLess(dispatch.index('fast_sine('),dispatch.index('qualified_bank('))
            self.assertNotIn('candidate_line(',text);self.assertNotIn('candidate_lf(',text)
    def test_experimental_overlap_is_applied_once(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for families in (None,['delay_render'],['extensions']):
                b=generate(root/'mixed','fm1',qualified_kernels=True,candidate_smooth=True,candidate_core=True,candidate_binding=True,binding_families=families)
                text=(b/'fm_render.c').read_text();self.assertEqual(text.count(REF_TYPE),1)
                self.assertNotIn('qualified_smooth(',text);self.assertNotIn('qualified_bank(',text)
                for name in ('fm_delay.inc','fm_miverb.inc'):
                    self.assertEqual((b/name).read_text().count('candidate_input_ref candidate_refs['),1)
    def test_all_experiments_override_the_same_paths_without_code_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);flags=dict.fromkeys(('candidate_smooth','candidate_binary','candidate_noise','candidate_binding','candidate_routing','candidate_chaos','candidate_core'),True)
            a=generate(root/'old','fm1',**flags)
            b=generate(root/'mixed','fm1',qualified_kernels=True,**flags)
            for p in a.iterdir():
                if p.suffix in ('.c','.h','.inc') and p.name!='fm_build_profile.h':self.assertEqual(p.read_bytes(),(b/p.name).read_bytes(),p.name)


if __name__=='__main__':unittest.main()
