import unittest
from studio import Problem,check_graph_limits


class SignalLimitTests(unittest.TestCase):
    def test_old_firmware_still_accepts_original_boundary(self):
        check_graph_limits(dict(nodes=160,signals=192,inputs=1024),dict(policy='fm1-compat-v1'))

    def test_new_host_rejects_expanded_graph_for_old_firmware(self):
        for field,number in (('nodes',161),('signals',193),('inputs',1025)):
            with self.assertRaisesRegex(Problem,'connected firmware'):
                check_graph_limits({field:number},dict(policy='fm1-compat-v1'))

    def test_new_limits_and_physical_buffer_boundary(self):
        hello=dict(graph_limits=dict(nodes=256,signals=512,inputs=2048,audio_buffers=192))
        check_graph_limits(dict(nodes=256,signals=512,inputs=2048,audio_buffers=192),hello)
        with self.assertRaises(Problem):check_graph_limits(dict(audio_buffers=193),hello)

    def test_invalid_device_limits(self):
        for limits in ('not a map',dict(nodes=-1),dict(nodes=True)):
            with self.assertRaises(Problem):check_graph_limits({},dict(graph_limits=limits))


if __name__=='__main__':unittest.main()
