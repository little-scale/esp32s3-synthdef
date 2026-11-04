"""Offline protocol validation for snapshot and deterministic target profiling."""
import unittest
import copy
from profile_ugens import collect
from qualify_seeded_dsp import compare


class Device:
    def __init__(self,mode='fixed',seed=12345,nodes=1,calls=1024,matched=1,setup=True):
        self.link=self;self.sent=[]
        self.data=[f'UGEN_PROFILE graph=Test blocks=1024 ready=2 matched={matched} normal_cycles=240000 measured_cycles=250000 audio_hash=12345678']
        if setup:self.data.append(f'UGEN_SETUP mode={mode} seed={seed} warm_blocks=128 rate=44100 frames=64 nodes={nodes} cpu_mhz=240 normal_wall_us=1000 measured_wall_us=1042 warm_sha256='+('a'*64)+' audio_sha256='+('b'*64)+' rng=12345678:12345678:12345678')
        self.data.extend([f'UGEN_NODE index=0 type=SinOsc rate=2 special=0 cycles=200000 calls={calls}','UGEN_END'])
    def request(self,op):return {'graph_sha256':'c'*64}
    def write(self,data):self.sent.append(data)
    def lines(self):data,self.data=self.data,[];return [s.encode() for s in data]


class ProfileTests(unittest.TestCase):
    def test_fixed_mode_requires_seed_and_complete_metadata(self):
        d=Device();r=collect(d,fixed=True)
        self.assertEqual(d.sent,[b'J']);self.assertEqual(r['setup']['mode'],'fixed')
        for kwargs in ({'mode':'snapshot'},{'seed':0},{'setup':False},{'nodes':2},{'calls':1000},{'matched':0}):
            with self.subTest(**kwargs),self.assertRaises(AssertionError):collect(Device(**kwargs),fixed=True)
    def test_original_snapshot_protocol_remains_supported(self):
        d=Device(setup=False);r=collect(d)
        self.assertEqual(d.sent,[b'j']);self.assertIsNone(r['setup'])
    def test_comparison_rejects_different_seed_audio_and_graph(self):
        r=collect(Device(),fixed=True)
        fixture={'graph_sha256':'c'*64,'median_us':100,'runs':[r]}
        ref=dict(passed=True,fixed_seed=True,device_id='node',fixtures={'one':fixture})
        other=copy.deepcopy(ref);other['fixtures']['one']['median_us']=90
        self.assertAlmostEqual(compare(ref,other)['one']['less_time_percent'],10)
        for key in ('seed','audio_sha256','warm_sha256','rng','cpu_mhz'):
            bad=copy.deepcopy(other);bad['fixtures']['one']['runs'][0]['setup'][key]='different'
            with self.subTest(key=key),self.assertRaises(AssertionError):compare(ref,bad)
        bad=copy.deepcopy(other);bad['fixtures']['one']['graph_sha256']='different'
        with self.assertRaises(AssertionError):compare(ref,bad)


if __name__=='__main__':unittest.main()
