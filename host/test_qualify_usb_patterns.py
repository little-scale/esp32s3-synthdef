"""Offline capture analysis and wrong-device guards for the pattern pack."""
import argparse
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

import qualify_usb_patterns as tool


class PatternQualificationTests(unittest.TestCase):
    def wave(self,rate,overlap=False,jitter=False):
        count=44100;period=44100/rate
        data=[]
        for index in range(count):
            if overlap:
                phase=index%round(period);active=phase>=64
            else:
                phase=index%round(period);active=phase<period*.7
            if jitter and 18000<=index<23000:active=False
            data.append(round(32*math.sin(2*math.pi*880*index/44100)) if active else 0)
        return data

    def test_marker_recovers_notes_without_counting_sine_zero_crossings(self):
        for rate in (8,16):
            with self.subTest(rate=rate):
                result=tool.period_stats(self.wave(rate),rate)
                self.assertAlmostEqual(result['mean_period_seconds'],1/rate,delta=.00005)
                self.assertGreaterEqual(result['transitions'],rate-2)
        edges,gaps=tool.gate_edges([round(32*math.sin(2*math.pi*880*i/44100)) for i in range(44100)])
        self.assertEqual((edges,gaps),([],[]))

    def test_overlapping_notes_have_single_block_retrigger_gaps(self):
        result=tool.period_stats(self.wave(16,overlap=True),16)
        self.assertGreaterEqual(result['zero_gap_min_samples'],64)
        self.assertLessEqual(result['zero_gap_max_samples'],66)

    def test_missing_and_displaced_gates_cannot_pass_timing(self):
        with self.assertRaisesRegex(AssertionError,'Too few'):tool.period_stats([0]*44100,16)
        with self.assertRaisesRegex(AssertionError,'period error'):tool.period_stats(self.wave(16,jitter=True),16)

    def test_wrong_device_or_changed_saved_state_does_not_disconnect_or_mutate(self):
        target='esp32-1c29043eeb84'
        backup=dict(state=dict(hello=dict(device_id=target),masters=[dict(slot=0,selected=True)],
                               status=dict(graph_sha256='original'),slots=[]))
        for wrong_id,changed in ((True,False),(False,True)):
            client=Mock();client.http.return_value=dict(hello=dict(device_id='other' if wrong_id else target),
                volume_percent=5,status=dict(graph_sha256='different' if changed else 'original'),slots=[],masters=backup['state']['masters'])
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder);(path/'backup.json').write_text(json.dumps(backup))
                args=argparse.Namespace(device_id=target,backup=path/'backup.json',output=path/'result.json',soak_seconds=60)
                with patch.object(tool,'StudioClient',return_value=client),patch.object(tool,'Studio') as studio:
                    with self.assertRaises(AssertionError):tool.run(args)
                self.assertEqual([c.args[0] for c in client.http.call_args_list],['refresh'])
                studio.assert_not_called();self.assertFalse(json.loads((path/'result.json').read_text())['passed'])

    def test_soak_monitor_rejects_a_dead_stream_or_diagnostic_failure(self):
        for fault in ('stalled','rejected','audio'):
            qa=tool.Qualification.__new__(tool.Qualification)
            qa.failure=None;qa.done=Mock();qa.done.wait.return_value=False
            counters=dict.fromkeys(tool.COUNTERS,0)
            remote=dict(boot=1,revision=2,applied=10,rejected=0,late=0)
            qa.report=dict(soak=dict(before=counters,remote_before=remote,samples=[]))
            audio=dict(counters,internal_free=10000,psram_free=10000)
            current=dict(remote,queued=0,applied=10 if fault=='stalled' else 11)
            if fault=='rejected':current['rejected']=1
            if fault=='audio':audio['write_fail']=1
            qa.audio=Mock(return_value=audio);qa.info=Mock(return_value=current)
            qa.watch()
            expected={'stalled':'stopped advancing','rejected':'rejected/late','audio':'counter increased'}[fault]
            self.assertIn(expected,qa.failure)


if __name__=='__main__':unittest.main()
