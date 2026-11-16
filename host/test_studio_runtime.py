"""No-board tests for Studio's runtime review/lease/job boundary."""
import base64
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import dual_upload as dual
from studio_runtime import RuntimeUploads, MAX_FILE


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.row = dict(port='/usb', usb_id=(0x303a, 0x1001, '10:20:BA:06:97:D4', 'here'))
        self.device = SimpleNamespace(link=SimpleNamespace(port='/usb'))
        self.studio = SimpleNamespace(device_lock=threading.Lock(), device=self.device, usb_monitor=None,
            device_info=dict(device_id='esp32-1020ba0697d4'), device_port='/usb',
            compiler=SimpleNamespace(sclang=Path('/fake-sclang')),
            firmware_port=Mock(side_effect=lambda port: dict(self.row)))
        def disconnect():
            self.studio.device = self.studio.device_info = self.studio.device_port = None
        def connect(port):
            self.studio.device=self.device;self.studio.device_port=port
            self.studio.device_info=dict(device_id='esp32-1020ba0697d4')
        self.studio.disconnect=Mock(side_effect=disconnect)
        self.studio.connect=Mock(side_effect=connect)
        self.manager=RuntimeUploads(self.studio)
        self.reply=dict(version=1,engine='synthdef',model='Home Assistant Voice PE',rate=16000,busy=False)
        self.patches=[patch.object(dual,'probe_connection',side_effect=lambda owner: dict(self.reply)),
                      patch.object(dual,'probe',side_effect=lambda *args: dict(self.reply)),
                      patch.object(dual,'installed_pair',return_value={'synthdef','rnbo'}),
                      patch.object(dual,'wait_port',return_value='/usb')]
        for item in self.patches:item.start()
        self.artifact=dual.Artifact('synthdef',16000,b'validated',b'original source',dict(name='Test'))

    def tearDown(self):
        self.manager.close()
        for item in reversed(self.patches):item.stop()

    def test_xiao_native16_is_identified_and_checks_verified_pair_inventory(self):
        self.reply.update(model='XIAO ESP32-S3',rate=16000)
        result=self.manager.inspect(dict(port='/usb'))
        self.assertEqual(result['board'],'xiao')
        self.assertEqual(result['rate'],16000)
        self.assertTrue(result['ready'])
        dual.installed_pair.assert_called_once_with('xiao','1020ba0697d4',16000)

    def review(self):
        inspection=self.manager.inspect(dict(port='/usb'))
        with patch.object(dual,'prepare',return_value=self.artifact):
            return self.manager.review(dict(inspection=inspection['inspection'],source='{ Silent.ar(2) }'))

    def rnbo_hint(self):
        self.reply['engine']='rnbo';self.studio.device=self.studio.device_info=self.studio.device_port=None
        self.manager.inspect(dict(port='/usb'))
        return self.manager.usb_hint()

    def test_rnbo_hint_never_probes_and_is_invalidated_by_replug(self):
        row=self.rnbo_hint();self.assertEqual(row['runtime'],'rnbo')
        dual.probe.reset_mock()
        self.assertEqual(self.manager.usb_hint()['device_id'],'esp32-1020ba0697d4')
        dual.probe.assert_not_called()
        self.row['usb_id']=(0x303a,0x1001,'00:11:22:33:44:55','here')
        self.assertIsNone(self.manager.usb_hint())

    def test_sc_main_uses_the_normal_sender_once_under_the_connection_lease(self):
        row=self.rnbo_hint()
        artifact=SimpleNamespace(graph=b'compiled graph',source=b'original source',
            info=dict(target='sound',admission_rates={'16000':dict(fm1_admitted=True)}))
        def deliver():
            self.assertFalse(self.studio.device_lock.acquire(blocking=False))
            return dict(device_id=row['device_id'],verified=True,active=False)
        callback=Mock(side_effect=deliver)
        def route(payload,*args,**kwargs):
            self.assertEqual(payload.data,artifact.graph);self.assertEqual(payload.source,artifact.source)
            return kwargs['sender'](payload,'1020ba0697d4',16000,None)
        with patch.object(dual,'route',side_effect=route) as routed:
            result=self.manager.send_from_sc(row,artifact,callback)
            routed.assert_called_once();callback.assert_called_once()
        self.assertTrue(result['verified']);self.assertFalse(result['active'])
        self.studio.connect.assert_called_once_with('/usb')
        self.assertIsNone(self.manager.usb_hint())
        self.assertEqual(self.manager.snapshot()['state'],'complete')

    def test_sc_invalid_rate_and_fx_never_begin_a_switch(self):
        row=self.rnbo_hint()
        for info in [dict(target='master'),dict(target='sound',admission_rates={'16000':dict(fm1_admitted=False)})]:
            artifact=SimpleNamespace(graph=b'compiled',source=b'source',info=info)
            with patch.object(dual,'route') as route:
                with self.assertRaises(ValueError):self.manager.send_from_sc(row,artifact,Mock())
                route.assert_not_called()
        self.assertEqual(self.manager.snapshot(),dict(active=False))

    def test_sc_voice_led_graph_does_not_switch_a_headless_node(self):
        row=self.rnbo_hint()
        self.manager.last_target.update(board='xiao',rate=44100)
        artifact=SimpleNamespace(graph=b'compiled',source=b'source',info=dict(target='sound',requires_control_outputs=True,fm1_admitted=True))
        with patch.object(dual,'route') as route:
            with self.assertRaisesRegex(ValueError,'LED buses'):
                self.manager.send_from_sc(row,artifact,Mock())
            route.assert_not_called()

    def test_owned_usb_identification_does_not_disconnect_or_open_again(self):
        result=self.manager.inspect(dict(port='/usb'))
        self.assertTrue(result['ready']);self.assertEqual(result['rate'],16000)
        dual.probe.assert_not_called();self.studio.disconnect.assert_not_called()
        self.assertEqual(self.studio.device,self.device)

    def test_missing_pair_or_busy_state_prevents_ready(self):
        with patch.object(dual,'installed_pair',side_effect=ValueError('not commissioned')):
            result=self.manager.inspect(dict(port='/usb'))
        self.assertFalse(result['ready']);self.assertEqual(result['error'],'not commissioned')
        self.reply['busy']=True
        self.assertFalse(self.manager.inspect(dict(port='/usb'))['ready'])

    def test_legacy_probe_does_not_request_a_maintenance_restart(self):
        with patch.object(dual,'probe_connection',return_value=None),patch.object(dual,'boot') as boot:
            with self.assertRaisesRegex(ValueError,'identification'):
                self.manager.inspect(dict(port='/usb'))
            boot.assert_not_called()

    def test_other_usb_owner_gets_a_clear_recoverable_error(self):
        self.studio.device=None
        with patch.object(dual,'probe',side_effect=OSError('exclusive lock')):
            with self.assertRaisesRegex(ValueError,'owned by another app'):
                self.manager.inspect(dict(port='/usb'))

    def test_connection_wait_timeout_preserves_the_existing_session(self):
        self.studio.device_lock=Mock()
        self.studio.device_lock.acquire.return_value=False
        self.manager.job={'active':True}
        self.manager.run('unused',{},self.artifact)
        result=self.manager.snapshot()
        self.assertFalse(result['active']);self.assertTrue(result['studio_connected'])
        self.studio.disconnect.assert_not_called()
        self.studio.device_lock.release.assert_not_called()

    def test_invalid_inputs_fail_before_compile_or_new_usb_access(self):
        token=self.manager.inspect(dict(port='/usb'))['inspection']
        for data in [dict(data='!',filename='test.rnbopkg'),dict(data='',filename='../escape'),
                     dict(data='',filename='..'),dict(data='A'*(((MAX_FILE+2)//3)*4+1),filename='a'),
                     dict(source=''),dict(source='\0'),dict(source='x'*65537),dict(source='x',definition=1)]:
            with self.subTest(data=str(data)[:50]),patch.object(dual,'prepare') as prepare,patch.object(dual,'probe_connection') as probe:
                with self.assertRaises(ValueError):self.manager.review(dict(inspection=token,**data))
                prepare.assert_not_called();probe.assert_not_called()

    def test_replugged_identity_is_rejected_after_validation_and_before_job(self):
        token=self.manager.inspect(dict(port='/usb'))['inspection']
        self.row['usb_id']=(0x303a,0x1001,'00:11:22:33:44:55','here')
        with patch.object(dual,'prepare',return_value=self.artifact):
            with self.assertRaisesRegex(ValueError,'USB module changed'):
                self.manager.review(dict(inspection=token,source='{}'))
        self.assertEqual(self.manager.snapshot(),dict(active=False))

    def test_used_and_expired_reviews_do_not_upload_twice(self):
        plan=self.review()
        with patch.object(dual,'route',return_value=dict(engine='synthdef',verified=True)) as route:
            self.manager.start(dict(plan=plan['plan']));self.manager.worker.join(2)
            with self.assertRaisesRegex(ValueError,'expired or was used'):self.manager.start(dict(plan=plan['plan']))
            route.assert_called_once()
        self.assertEqual(self.manager.snapshot()['state'],'complete')
        self.studio.connect.assert_called_once_with('/usb')
        plan=self.review()
        with patch('studio_runtime.time.monotonic',return_value=10**15):
            with self.assertRaisesRegex(ValueError,'expired'):self.manager.start(dict(plan=plan['plan']))

    def test_busy_job_keeps_connection_mutex_and_rejects_a_second_job(self):
        first=self.review();second=self.review();started=threading.Event();finish=threading.Event()
        def route(*args,**kwargs):
            self.assertFalse(self.studio.device_lock.acquire(blocking=False))
            kwargs['progress']('Waiting for reboot');started.set();finish.wait(2)
            return dict(engine='synthdef',verified=True)
        with patch.object(dual,'route',side_effect=route):
            self.manager.start(dict(plan=first['plan']));self.assertTrue(started.wait(1))
            self.assertEqual(self.manager.snapshot()['progress'],'Waiting for reboot')
            with self.assertRaisesRegex(ValueError,'already in progress'):self.manager.start(dict(plan=second['plan']))
            finish.set();self.manager.worker.join(2)
        self.assertEqual(self.manager.snapshot()['state'],'complete')

    def test_job_failure_is_reported_without_replaying_the_payload(self):
        plan=self.review()
        with patch.object(dual,'route',side_effect=ValueError('USB lost after activation')) as route:
            self.manager.start(dict(plan=plan['plan']));self.manager.worker.join(2)
            route.assert_called_once()
        result=self.manager.snapshot();self.assertFalse(result['active']);self.assertEqual(result['state'],'failed')
        self.assertIn('USB lost',result['error']);self.assertFalse(result['studio_connected'])

    def test_rnbo_completion_leaves_classic_synthdef_connection_closed(self):
        self.artifact=dual.Artifact('rnbo',16000,b'package',b'',{})
        plan=self.review()
        with patch.object(dual,'route',return_value=dict(engine='rnbo',verified=True)):
            self.manager.start(dict(plan=plan['plan']));self.manager.worker.join(2)
        self.assertIsNone(self.studio.device);self.studio.connect.assert_not_called()
        self.assertFalse(self.manager.snapshot()['studio_connected'])

    def test_identity_change_after_review_never_disconnects_or_routes(self):
        plan=self.review();self.row['usb_id']=(0x303a,0x1001,'00:11:22:33:44:55','here')
        with patch.object(dual,'route') as route:
            self.manager.start(dict(plan=plan['plan']));self.manager.worker.join(2)
            route.assert_not_called();self.studio.disconnect.assert_not_called()
        self.assertEqual(self.manager.snapshot()['state'],'failed')


if __name__=='__main__':unittest.main()
