import base64
import tempfile
from pathlib import Path
import unittest

from qualify_headless import Qualification, echo_metrics, graph_hash, pcm_channels


class QualificationTests(unittest.TestCase):
    def test_echo_spacing_and_feedback(self):
        data = [0] * 1000
        for i, value in enumerate((800,400,200,100,50)):
            data[10+i*100] = value
        self.assertEqual(echo_metrics(data,100,.5)['period_frames'],100)
        with self.assertRaises(AssertionError): echo_metrics(data,90,.5)
        with self.assertRaises(AssertionError): echo_metrics(data,100,.7)

    def test_capture_truncation(self):
        with self.assertRaises(AssertionError):
            pcm_channels(dict(format='s16le',channels=2,rate=44100,frames=2,
                              data=base64.b64encode(b'\0'*4).decode()))

    def test_wrong_target_never_backs_up_or_uploads(self):
        class Client:
            def http(self,path,payload):
                assert path == 'refresh'
                return {'hello':{'device_id':'another-board','headless':True}}
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory)/'backup.json'
            q = Qualification(Client(),'expected-board',destination)
            with self.assertRaises(AssertionError): q.save()
            self.assertFalse(destination.exists())

    def test_unrelated_package_is_never_overwritten(self):
        class Client:
            def http(self,path,payload):
                assert path == 'refresh'
                return {'hello':{'device_id':'expected-board'}}
        q = Qualification(Client(),'expected-board',Path('/unused'))
        original = {'graph':base64.b64encode(b'original').decode()}
        unrelated = {'graph':base64.b64encode(b'new user patch').decode()}
        q.backup = {'main':original}
        q.dirty.add('sound'); q.owned['sound'].add(graph_hash(original))
        q.package = lambda *args: unrelated
        q.compile = lambda *args: self.fail('Attempted to replace unrelated code')
        with self.assertRaisesRegex(AssertionError,'unrelated patch'): q.restore()


if __name__ == '__main__': unittest.main()
