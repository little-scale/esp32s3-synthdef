"""Protocol completeness checks with fake lines; no device I/O."""
import unittest
from run_dsp_qa import collect


class Device:
    def __init__(self,missing=False,duplicate=False,qualified=None):
        self.link=self;self.sent=[]
        lines=['DSPQA_BEGIN cases=50 complete=50 pack='+('a'*64)+' candidates=all']
        if qualified is not None:lines[0]+=' qualified='+str(qualified)
        for i in range(49 if missing else 50):
            lines.append('DSPQA_CASE index=%u blocks=32 arena_samples=0 fault_blocks=0 constructors=1 render_us=1 '%(0 if duplicate else i)+
                         ' '.join('h%u=%s'%(k,'b'*64) for k in range(4)))
        self.data=[s.encode() for s in lines+['DSPQA_END']]
    def write(self,data):self.sent.append(data)
    def lines(self):data,self.data=self.data,[];return data


class ReplayTests(unittest.TestCase):
    def test_complete_pack_is_accepted(self):
        d=Device();r=collect(d,'all');self.assertTrue(r['passed']);self.assertEqual(d.sent,[b'q'])
    def test_wrong_image_is_rejected(self):
        with self.assertRaisesRegex(AssertionError,'Wrong candidate image'):collect(Device(),'none')
    def test_missing_case_is_rejected(self):
        with self.assertRaises(AssertionError):collect(Device(missing=True),'all')
    def test_duplicate_cases_are_rejected(self):
        with self.assertRaisesRegex(AssertionError,'duplicate'):collect(Device(duplicate=True),'all')
    def test_selected_build_cannot_be_mistaken_for_legacy(self):
        with self.assertRaisesRegex(AssertionError,'Wrong qualified-kernel mode'):collect(Device(qualified=1),'all')
        self.assertTrue(collect(Device(qualified=1),'all',expected_qualified=True)['passed'])


if __name__=='__main__':unittest.main()
