import unittest
from studio import Problem,check_graph_limits,admission_for_device
from patches import Device
from unittest.mock import Mock


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

    def test_led_outputs_require_advertised_hardware(self):
        for hello in ({},dict(control_outputs=dict(base=32,count=36))):
            with self.assertRaises(Problem):check_graph_limits(dict(requires_control_outputs=True),hello)
        check_graph_limits(dict(requires_control_outputs=True),dict(control_outputs=dict(base=3,count=39)))

    def test_voice_pe_identity_and_rate_admission(self):
        d=Device.__new__(Device)
        d.request=Mock(return_value=dict(protocol=1,model='Home Assistant Voice PE',policy='fm1-compat-v1',chunk=256,rate=48000))
        hello=d.hello()
        rows={'44100':dict(fm1_admitted=True),'48000':dict(fm1_admitted=False)}
        info=dict(fm1_admitted=True,admission_rates=rows)
        self.assertFalse(admission_for_device(info,hello)['fm1_admitted'])
        self.assertTrue(info['fm1_admitted'])
        self.assertTrue(admission_for_device(info,{})['fm1_admitted'])
        with self.assertRaises(Problem):admission_for_device(dict(fm1_admitted=True),hello)
        for rate in (True,32000,'48000'):
            with self.assertRaises(Problem):admission_for_device(info,dict(rate=rate))


if __name__=='__main__':unittest.main()
