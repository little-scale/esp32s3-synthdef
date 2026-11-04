"""Validate the hardware plan locally; no board, network, compiler or audio I/O."""
import hashlib
import json
import math
import unittest

from dsp_binding import TYPE_FAMILIES
from plan_dsp_hardware import ROOT, build_plan, required_tokens, select_cover
from synthdef_binary import decode


class HardwarePlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.plan=build_plan()

    def test_first_session_is_bounded_and_requires_only_two_variants(self):
        p=self.plan;first=p['fixture_sets']['first_session']
        self.assertEqual(len(first),50)
        session=p['timeboxed_sessions']['first']
        self.assertEqual(session['variants'],['baseline','all-candidates'])
        self.assertEqual(session['minutes'],30)
        signs=[name for name in first if 'Binary_signed_zero_' in name]
        self.assertEqual(len(signs),24)
        blocks=len(signs)*session['signed_zero_blocks']+(len(first)-len(signs))*session['raw_blocks']
        self.assertLess(blocks*64/44100,11)
        self.assertLess(len(first),len(p['fixture_sets']['extended_structural_cover']))

    def test_fast_pack_exercises_every_changed_binding_entry_and_candidate_family(self):
        p=self.plan;first=p['fixture_sets']['first_session']
        types={t[1] for name in first for t in p['fixtures'][name]['coverage'] if t[0]=='type'}
        for entry,names in TYPE_FAMILIES.items():
            with self.subTest(entry=entry):self.assertTrue(types.intersection(names))
        for group,row in p['candidate_groups'].items():
            with self.subTest(group=group):self.assertTrue(types.intersection(row['types']))

    def test_extended_cover_contains_all_required_rates_and_selectors(self):
        p=self.plan
        register=json.loads((ROOT/'docs/dsp_optimizations.json').read_text())
        inventory=json.loads((ROOT/'evidence/fm1-fixed-inventory.json').read_text())
        covered={tuple(t) for name in p['fixture_sets']['extended_structural_cover'] for t in p['fixtures'][name]['coverage']}
        self.assertFalse(required_tokens(register,inventory)-covered)
        self.assertEqual(len(p['ugen_coverage']),154)
        self.assertEqual(len(p['operator_coverage']['unary']),33)
        self.assertEqual(len(p['operator_coverage']['binary']),40)

    def test_prepared_graphs_are_intact_and_signed_zero_survives(self):
        for name,row in self.plan['fixtures'].items():
            data=(ROOT/row['path']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(),row['sha256'],name)
            g=decode(data)
            self.assertEqual(len(g['nodes']),row['nodes'],name)
            if 'Binary_signed_zero_' in name:
                self.assertTrue(any(x==0 and math.copysign(1,x)<0 for x in g['constants']),name)
        for row in self.plan['musical_cases'].values():
            self.assertEqual(hashlib.sha256((ROOT/row['source']).read_bytes()).hexdigest(),row['sha256'])

    def test_nothing_is_marked_as_hardware_passed_or_enabled(self):
        p=self.plan
        self.assertFalse(p['hardware_tested']);self.assertFalse(p['device_access'])
        self.assertFalse(p['firmware_written']);self.assertFalse(p['production_defaults_changed'])
        self.assertEqual(p['hardware_results'],[])
        self.assertFalse(any(p['firmware_variants']['baseline'].values()))
        for key,flags in p['firmware_variants'].items():
            expected=0 if key=='baseline' else 7 if key=='all-candidates' else 1
            self.assertEqual(sum(flags.values()),expected,key)
        self.assertTrue(all(row['hardware_status']=='planned' for row in p['fixtures'].values()))

    def test_missing_coverage_is_an_error_not_a_silent_skip(self):
        with self.assertRaisesRegex(ValueError,'No fixture covers'):
            select_cover({'one':(b'',{('type','One',2)})},{('type','Missing',1)})


if __name__=='__main__':unittest.main()
