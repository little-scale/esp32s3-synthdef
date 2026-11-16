"""Computer-only Voice PE migration/update guards; no USB access."""
import hashlib,json,struct,tempfile,unittest,zlib,sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,MagicMock,patch
import voice_pe_firmware as vpe
import firmware_upload as uploader


def table(rows):
    data=b''.join(struct.pack('<HBBII16sI',0x50aa,t,s,o,n,label.encode().ljust(16,b'\0'),0) for label,t,s,o,n in rows)
    return (data+b'\xeb\xeb'+b'\xff'*14+hashlib.md5(data).digest()).ljust(0xc00,b'\xff')


def app(name='waveshare_synthdef',marker=b'Home Assistant Voice PE'):
    header=bytearray(24);header[0:2]=b'\xe9\x01';header[23]=1
    payload=bytearray(512);struct.pack_into('<I',payload,0,0xabcd5432)
    payload[48:80]=name.encode().ljust(32,b'\0');payload[256:256+len(marker)]=marker
    return bytes(header)+struct.pack('<II',0x3c000020,len(payload))+payload+b'\0'*16+b'\0'*32


class Chip:
    def __init__(self,migration=False):
        self.memory=bytearray(b'\xff'*vpe.FLASH_BYTES);self.writes=[];self.sync_stub_detected=True
        self.memory[:4]=b'\xe9\x03\x02\x4f'
        self.memory[0x8000:0x9000]=table(vpe.STOCK if migration else vpe.PROJECT).ljust(4096,b'\xff')
        old=app('home-assistant-voice' if migration else 'waveshare_synthdef')
        self.memory[0x10000:0x10000+len(old)]=old
        self.memory[0xf90000:0xf90008]=b'USER NVS'
    def read_flash(self,offset,size):return bytes(self.memory[offset:offset+size])
    def flash_md5sum(self,offset,size):return hashlib.md5(self.read_flash(offset,size)).hexdigest()
    def sync(self):pass
    def write(self,command,esp):
        assert esp is self
        args=command[command.index('--flash_size')+2:]
        for offset,file in zip(args[::2],args[1::2],strict=True):
            at=int(offset,0);data=Path(file).read_bytes();self.writes.append(at)
            end=(at+len(data)+4095)&~4095
            self.memory[at:end]=b'\xff'*(end-at);self.memory[at:at+len(data)]=data


class VoiceFirmwareTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.table=self.root/'part.bin';self.table.write_bytes(table(vpe.PROJECT))
        self.app=self.root/'app.bin';self.app.write_bytes(app())
        self.valid=patch.object(vpe,'verified_image');self.valid.start()
    def tearDown(self):self.valid.stop();self.tmp.cleanup()
    def run_install(self,chip):
        esptool=SimpleNamespace(main=Mock(side_effect=chip.write))
        return vpe.install(chip,esptool,self.table.read_bytes(),self.app.read_bytes(),self.table,self.app,self.root/'private','1020ba0697d4')
    def test_stock_migration_is_backed_up_before_selective_writes(self):
        chip=Chip(True);before=bytes(chip.memory)
        result=self.run_install(chip)
        self.assertEqual(chip.writes,[0x8000,0x9000,0x10000])
        backup=next((self.root/'private').rglob('esp-flash-before.bin'))
        self.assertEqual(backup.read_bytes(),before)
        self.assertEqual(backup.stat().st_mode&0o777,0o600)
        self.assertEqual(vpe.partitions(chip.read_flash(0x8000,4096)),vpe.PROJECT)
        self.assertEqual(chip.read_flash(0x9000,8192),b'\xff'*8192)
        self.assertEqual(chip.memory[:0x8000],before[:0x8000])
        self.assertEqual(chip.memory[0xf90000:],before[0xf90000:])
        self.assertEqual(result['status'],'installed_verified')
    def test_newer_stock_migration_preserves_all_settings_pages(self):
        chip=Chip(True);chip.memory[0x8000:0x9000]=table(vpe.STOCK_LATEST).ljust(4096,b'\xff')
        chip.memory[-8:]=b'LAST NVS';before=bytes(chip.memory[0xf90000:])
        result=self.run_install(chip)
        self.assertEqual(vpe.partitions(chip.read_flash(0x8000,4096)),vpe.PROJECT_LATEST)
        self.assertEqual(chip.memory[0xf90000:],before)
        self.assertEqual(result['nvs_preserved_bytes'],0x70000)

    def test_newer_project_update_preserves_its_partition_table(self):
        chip=Chip();chip.memory[0x8000:0x9000]=table(vpe.PROJECT_LATEST).ljust(4096,b'\xff')
        before=bytes(chip.memory[:0x10000]);self.run_install(chip)
        self.assertEqual(chip.writes,[0x10000]);self.assertEqual(chip.memory[:0x10000],before)

    def test_project_update_writes_only_app_preserving_storage_and_ota(self):
        chip=Chip();before=bytes(chip.memory);result=self.run_install(chip)
        self.assertEqual(chip.writes,[0x10000]);self.assertEqual(result['installation'],'application update')
        self.assertEqual(chip.memory[:0x10000],before[:0x10000]);self.assertEqual(chip.memory[0x7d0000:],before[0x7d0000:])
        self.assertTrue(next((self.root/'private').rglob('application-before.bin')).exists())
    def test_rnbo_conversion_backs_up_old_app_and_preserves_other_regions(self):
        for layout in (vpe.PROJECT,vpe.PROJECT_LATEST):
            with self.subTest(layout=layout):
                chip=Chip();old=app('rnbo_s3_voice-pe')
                chip.memory[0x8000:0x9000]=table(layout).ljust(4096,b'\xff')
                chip.memory[0x10000:0x10000+len(old)]=old
                chip.memory[0xb90000:0xb90008]=b'RNBO FS!'
                before=bytes(chip.memory);result=self.run_install(chip)
                self.assertEqual(chip.writes,[0x10000])
                self.assertEqual(result['previous_project'],'rnbo_s3_voice-pe')
                self.assertEqual(result['status'],'installed_verified')
                self.assertEqual(chip.memory[:0x10000],before[:0x10000])
                self.assertEqual(chip.memory[0x7d0000:],before[0x7d0000:])
                saved=list((self.root/'private').rglob('application-before.bin'))
                self.assertTrue(any(p.read_bytes().startswith(old) for p in saved))
    def test_rnbo_name_does_not_bypass_board_marker_or_digest_checks(self):
        for problem in ('marker','digest'):
            with self.subTest(problem=problem):
                chip=Chip();old=app('rnbo_s3_voice-pe',b'Another board' if problem=='marker' else b'Home Assistant Voice PE')
                chip.memory[0x10000:0x10000+len(old)]=old
                before=bytes(chip.memory)
                if problem=='digest':
                    def validate(data):
                        if vpe.project_name(data)=='rnbo_s3_voice-pe':raise ValueError('Invalid application digest')
                    with patch.object(vpe,'verified_image',side_effect=validate):
                        with self.assertRaisesRegex(ValueError,'digest'):self.run_install(chip)
                else:
                    with self.assertRaisesRegex(ValueError,'different board'):self.run_install(chip)
                self.assertEqual(chip.writes,[]);self.assertEqual(chip.memory,before)
    def test_unrecognized_project_with_voice_pe_marker_still_rejected(self):
        chip=Chip();old=app('unreviewed_voice_pe')
        chip.memory[0x10000:0x10000+len(old)]=old
        with self.assertRaisesRegex(ValueError,'app0'):self.run_install(chip)
        self.assertEqual(chip.writes,[]);self.assertFalse((self.root/'private').exists())
    def test_unknown_layout_and_bad_table_rejected_before_write(self):
        for corrupt in (0,1):
            chip=Chip();changed=list(vpe.PROJECT);changed[-1]=('nvs',1,2,0xf80000,0x6d000)
            blob=bytearray(table(changed))
            if corrupt:blob[50]^=1
            chip.memory[0x8000:0x9000]=blob.ljust(4096,b'\xff')
            with self.assertRaises(ValueError):self.run_install(chip)
            self.assertEqual(chip.writes,[])
    def test_other_stock_model_rejected_before_backup_or_write(self):
        chip=Chip(True);other=app('other-board',b'Other device');chip.memory[0x10000:0x10000+len(other)]=other
        with self.assertRaisesRegex(ValueError,'identify stock'):self.run_install(chip)
        self.assertEqual(chip.writes,[]);self.assertFalse((self.root/'private').exists())
    def test_other_project_model_never_written(self):
        chip=Chip();other=app(marker=b'Waveshare AMOLED');chip.memory[0x10000:0x10000+len(other)]=other
        with self.assertRaisesRegex(ValueError,'different board'):self.run_install(chip)
        self.assertEqual(chip.writes,[])
    def test_app1_ota_selection_rejected_for_project_updates(self):
        for name in ('waveshare_synthdef','rnbo_s3_voice-pe'):
            with self.subTest(name=name):
                chip=Chip();old=app(name);chip.memory[0x10000:0x10000+len(old)]=old
                ota=bytearray(b'\xff'*32);struct.pack_into('<I',ota,0,2);struct.pack_into('<I',ota,24,2)
                struct.pack_into('<I',ota,28,zlib.crc32(ota[:4],0xffffffff));chip.memory[0x9000:0x9020]=ota
                with self.assertRaisesRegex(ValueError,'app0'):self.run_install(chip)
                self.assertEqual(chip.writes,[])
    def test_failed_backup_never_calls_programmer(self):
        chip=Chip()
        with patch.object(chip,'flash_md5sum',return_value='bad'):
            with self.assertRaisesRegex(ValueError,'Backup verification failed'):self.run_install(chip)
        self.assertEqual(chip.writes,[])
    def test_partial_backup_never_calls_programmer(self):
        chip=Chip();read=chip.read_flash
        def short(offset,size):return b'' if size>=4096 and offset==0x10000 else read(offset,size)
        with patch.object(chip,'read_flash',side_effect=short):
            with self.assertRaisesRegex(ValueError,'Incomplete backup'):self.run_install(chip)
        self.assertEqual(chip.writes,[])
    def test_overlarge_or_wrong_new_app_rejected(self):
        chip=Chip()
        for data in (app(marker=b'wrong-board'),app('rnbo_s3_voice-pe'),b'Home Assistant Voice PE'+b'\0'*0x3c0000):
            self.app.write_bytes(data)
            with self.assertRaisesRegex(ValueError,'Voice PE application'):self.run_install(chip)
            self.assertEqual(chip.writes,[])
    def test_device_write_failure_retains_verified_backup(self):
        chip=Chip()
        with patch.object(chip,'write',side_effect=RuntimeError('USB lost')):
            with self.assertRaisesRegex(RuntimeError,'USB lost'):self.run_install(chip)
        saved=next((self.root/'private').rglob('backup.json'))
        record=json.loads(saved.read_text())
        self.assertEqual(record['status'],'writing')
        self.assertTrue(all(row['verified'] for row in record['files']))
        self.assertTrue((saved.parent/'application-before.bin').exists())

    def test_rom_security_and_identity_fail_before_install(self):
        for problem in ('wrong_chip','wrong_mac','secure_download','secure_boot','encrypted','reset_failure'):
            with self.subTest(problem=problem):
                chip=MagicMock();chip.CHIP_NAME='ESP32-S3';chip.secure_download_mode=False
                chip.read_mac.return_value=bytes.fromhex('1020ba0697d4')
                security=dict(parsed_flags=dict(SECURE_BOOT_EN=False,SECURE_DOWNLOAD_ENABLE=False),flash_crypt_cnt=0)
                if problem=='wrong_chip':chip.CHIP_NAME='ESP32'
                if problem=='wrong_mac':chip.read_mac.return_value=b'wrong!'
                if problem=='secure_download':chip.secure_download_mode=True
                if problem in ('secure_boot','reset_failure'):security['parsed_flags']['SECURE_BOOT_EN']=True
                if problem=='encrypted':security['flash_crypt_cnt']=1
                if problem=='reset_failure':chip.watchdog_reset.side_effect=OSError('reset unavailable')
                chip.get_security_info.return_value=security
                tool=SimpleNamespace(detect_chip=Mock(return_value=chip))
                serial=SimpleNamespace(open_port=MagicMock())
                args=SimpleNamespace(mac='1020ba0697d4',flash_size='16MB',mode='dio',frequency='80m',port='fake',images=['unused',self.table,self.app])
                with patch.dict(sys.modules,serial_port=serial),patch.object(vpe,'install') as install:
                    with self.assertRaises(ValueError):vpe.flash(args,tool)
                    install.assert_not_called();chip.run_stub.assert_not_called()

    def test_incomplete_native_identity_never_opens_usb(self):
        args=SimpleNamespace(mac=None,flash_size='16MB',mode='dio',frequency='80m')
        serial=SimpleNamespace(open_port=MagicMock())
        with patch.dict(sys.modules,serial_port=serial):
            with self.assertRaisesRegex(ValueError,'exact native USB identity'):vpe.flash(args,SimpleNamespace())
        serial.open_port.assert_not_called()

    def test_active_slot_and_crc(self):
        self.assertEqual(vpe.active_slot(b'\xff'*8192),0)
        with self.assertRaises(ValueError):vpe.active_slot(b'\0'*8192)
        for seq,state in ((1,2),(2,2),(3,2),(1,1)):
            data=bytearray(b'\xff'*8192);struct.pack_into('<I',data,0,seq);struct.pack_into('<I',data,24,state)
            struct.pack_into('<I',data,28,zlib.crc32(data[:4],0xffffffff))
            if state==1:
                with self.assertRaisesRegex(ValueError,'pending'):vpe.active_slot(data)
            else:self.assertEqual(vpe.active_slot(data),(seq-1)%2)


class VoiceBuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.target=uploader.TARGETS['voice-pe'];self.folder=self.root/'firmware'/self.target.folder
        (self.folder/'config').mkdir(parents=True);(self.folder/'bootloader').mkdir();(self.folder/'partition_table').mkdir()
        self.config=dict(SYNTHDEF_HEADLESS=False,SYNTHDEF_VOICE_PE=True,SYNTHDEF_NO_DISPLAY=True,SYNTHDEF_TOUCH_UI=False,ESPTOOLPY_FLASHSIZE='16MB',SYNTHDEF_FM1_COMPAT=True)
        self.manifest=dict(flash_settings=dict(flash_mode='dio',flash_freq='80m',flash_size='16MB'),extra_esptool_args=dict(chip='esp32s3'),flash_files=dict(uploader.FILES,**{'0x9000':'ota_data_initial.bin'}))
        self.manifest.update({k:dict(encrypted='false') for k in ('bootloader','partition-table','app','otadata')})
        (self.folder/'project_description.json').write_text(json.dumps(dict(project_name='waveshare_synthdef',target='esp32s3')))
        (self.folder/'bootloader/bootloader.bin').write_bytes(b'\xe9\x00')
        (self.folder/'partition_table/partition-table.bin').write_bytes(table(vpe.PROJECT))
        (self.folder/'waveshare_synthdef.bin').write_bytes(app())
        (self.folder/'ota_data_initial.bin').write_bytes(b'\xff'*8192)
        self.patch=patch.object(uploader,'ROOT',self.root);self.patch.start()
    def tearDown(self):self.patch.stop();self.tmp.cleanup()
    def load(self):
        (self.folder/'config/sdkconfig.json').write_text(json.dumps(self.config));(self.folder/'flasher_args.json').write_text(json.dumps(self.manifest));return uploader.load_image('voice-pe')
    def test_qualified_build(self):self.assertTrue(self.load().target.voice_pe)
    def test_wrong_board_or_rate_configuration(self):
        for key,value in (('SYNTHDEF_HEADLESS',True),('SYNTHDEF_TOUCH_UI',True),('SYNTHDEF_VOICE_PE',False),('SYNTHDEF_VOICE_PE_LOW_RATE',True),('SYNTHDEF_VOICE_PE_NATIVE_16K',True),('SYNTHDEF_FM1_COMPAT',False),('SYNTHDEF_DIAGNOSTICS',True)):
            old=dict(self.config);self.config[key]=value
            with self.assertRaises(ValueError):self.load()
            self.config=old
    def test_native_16k_has_separate_build_and_rejects_stock_configuration(self):
        native=uploader.TARGETS['voice-pe-native-16k'];folder=self.root/'firmware'/native.folder
        self.folder.rename(folder);self.folder=folder
        (folder/'config/sdkconfig.json').write_text(json.dumps(self.config));(folder/'flasher_args.json').write_text(json.dumps(self.manifest))
        with self.assertRaises(ValueError):uploader.load_image('voice-pe-native-16k')
        self.config['SYNTHDEF_VOICE_PE_NATIVE_16K']=True
        (folder/'config/sdkconfig.json').write_text(json.dumps(self.config))
        image=uploader.load_image('voice-pe-native-16k');self.assertEqual(image.target.rate,16000);self.assertTrue(image.target.native16)
    def test_unknown_flash_files_and_layout(self):
        self.manifest['flash_files']['0xf90000']='nvs.bin'
        with self.assertRaises(ValueError):self.load()
        del self.manifest['flash_files']['0xf90000']
        (self.folder/'partition_table/partition-table.bin').write_bytes(table(vpe.STOCK))
        with self.assertRaises(ValueError):self.load()
    def test_snapshot_command_selects_guarded_writer(self):
        image=self.load()
        with patch.object(uploader.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='verified')) as run:
            uploader.write_image('python',image,'usb','10:20:BA:06:97:D4')
        args,kwargs=run.call_args;self.assertIn('--board',args[0]);self.assertIn('voice-pe',args[0]);self.assertEqual(kwargs['timeout'],600)


if __name__=='__main__':unittest.main()
