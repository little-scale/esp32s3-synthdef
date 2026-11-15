"""Simulated DFU backup guards. Never enumerates or opens USB hardware."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import voice_pe_xmos_dfu as dfu


def listing(path='20-1', version='0131', names=None, number=9):
    return '\n'.join(f'Found DFU: [2886:0019] ver={version}, devnum={number}, cfg=1, intf=0, '
        f'path="{path}", alt={alt}, name="{name}", serial="0000000001"'
        for alt,name in (names or dfu.NAMES).items())


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'private'
        self.calls=[];self.uploads=0
    def tearDown(self):self.temp.cleanup()
    def process(self, command, **kwargs):
        self.calls.append(command)
        self.assertFalse(set(command)&{'--download','--detach','--reset','-D','-e','-R','--dfuse-address'})
        if '--list' in command:return subprocess.CompletedProcess(command,0,listing(),'')
        self.assertIn('--upload',command);self.assertEqual(command[command.index('--path')+1],'20-1')
        self.assertNotIn('--upload-size',command)
        self.assertIs(kwargs['preexec_fn'],dfu.upload_file_limit)
        alternate=int(command[command.index('--alt')+1]);self.uploads+=1
        Path(command[-1]).write_bytes(bytes([alternate+1])*4096)
        return subprocess.CompletedProcess(command,0,'Upload done.','')
    def execute(self, process=None):
        with patch.object(dfu.subprocess,'run',side_effect=process or self.process):
            return dfu.backup('/test/dfu-util','20-1',self.root)
    def test_unique_device_all_named_alternates(self):
        row=dfu.inventory('banner\n'+listing());self.assertEqual(row['path'],'20-1')
        for data in ('',listing()+'\n'+listing('20-2'),listing(names={0:'DFU FACTORY',1:'WRONG',2:'DFU DATAPARTITION'}),listing()+'\n'+listing()):
            with self.subTest(data=data),self.assertRaises(ValueError):dfu.inventory(data)
    def test_backup_reads_every_partition_twice_and_keeps_it_private(self):
        record=self.execute();self.assertEqual(record['status'],'repeat_verified');self.assertFalse(record['flash_written'])
        self.assertEqual(self.uploads,6);self.assertEqual(len(record['partitions']),3)
        for p in self.root.rglob('*'):
            self.assertEqual(p.stat().st_mode&0o777,0o700 if p.is_dir() else 0o600)
        self.assertTrue(all(x['verified'] for x in record['partitions']))
    def test_wrong_path_stops_before_creating_backup(self):
        with patch.object(dfu.subprocess,'run',side_effect=self.process),self.assertRaises(ValueError):
            dfu.backup('/test/dfu-util','99-9',self.root)
        self.assertEqual(self.uploads,0);self.assertFalse(self.root.exists())
    def test_changed_identity_stops_before_reading_partition(self):
        def process(command,**kwargs):
            if self.calls:return subprocess.CompletedProcess(command,0,listing(number=10),'')
            return self.process(command,**kwargs)
        with self.assertRaises(ValueError):self.execute(process)
        self.assertEqual(self.uploads,0)
        self.assertEqual(json.loads(next(self.root.rglob('backup.json')).read_text())['status'],'failed')
    def test_mismatched_repeats_are_not_verified(self):
        def process(command,**kwargs):
            result=self.process(command,**kwargs)
            if '--upload' in command and self.uploads==2:Path(command[-1]).write_bytes(b'x'*4096)
            return result
        with self.assertRaises(ValueError):self.execute(process)
        self.assertEqual(self.uploads,2)
        self.assertEqual(json.loads(next(self.root.rglob('backup.json')).read_text())['status'],'failed')
    def test_transfer_error_keeps_failure_journal(self):
        def process(command,**kwargs):
            result=self.process(command,**kwargs)
            if '--upload' in command:result.returncode=1
            return result
        with self.assertRaises(subprocess.CalledProcessError):self.execute(process)
        self.assertEqual(json.loads(next(self.root.rglob('backup.json')).read_text())['status'],'failed')
    def test_truncated_or_safety_bound_read_is_rejected(self):
        for size in (1,dfu.MAX_BYTES):
            destination=Path(self.temp.name)/f'read-{size}.bin'
            def process(command,**kwargs):
                if '--list' in command:return subprocess.CompletedProcess(command,0,listing(),'')
                with Path(command[-1]).open('wb') as f:f.truncate(size)
                return subprocess.CompletedProcess(command,0,'','')
            with patch.object(dfu.subprocess,'run',side_effect=process),self.assertRaises(ValueError):
                dfu.read_partition('/test/dfu-util',dfu.inventory(listing()),0,destination)
    def test_existing_backup_is_never_overwritten(self):
        p=Path(self.temp.name)/'read.bin';p.write_bytes(b'KEEP')
        with patch.object(dfu.subprocess,'run') as run,self.assertRaises(ValueError):
            dfu.read_partition('/test/dfu-util',dfu.inventory(listing()),0,p)
        run.assert_not_called();self.assertEqual(p.read_bytes(),b'KEEP')
    def test_unused_upgrade_and_absent_data_are_recorded_without_claiming_flash_contents(self):
        def process(command,**kwargs):
            result=self.process(command,**kwargs)
            if '--upload' in command and command[command.index('--alt')+1]!='0':Path(command[-1]).write_bytes(b'')
            return result
        record=self.execute(process)
        self.assertEqual(record['status'],'repeat_verified')
        self.assertEqual([p['availability'] for p in record['partitions']],
            ['nonempty','not_exposed_or_absent','not_exposed_or_absent'])
    def test_empty_factory_is_rejected(self):
        def process(command,**kwargs):
            result=self.process(command,**kwargs)
            if '--upload' in command:Path(command[-1]).write_bytes(b'')
            return result
        with self.assertRaises(ValueError):self.execute(process)
    def test_child_file_bound_is_an_actual_resource_limit(self):
        # Run a harmless child against a much smaller limit; do not allocate a
        # large file or alter the test runner's own process resource limits.
        import sys
        destination=Path(self.temp.name)/'bounded.bin'
        def limit():dfu.resource.setrlimit(dfu.resource.RLIMIT_FSIZE,(4096,4096))
        result=subprocess.run([sys.executable,'-c',
            'import pathlib,sys;pathlib.Path(sys.argv[1]).write_bytes(b"x"*8192)',str(destination)],
            preexec_fn=limit,capture_output=True)
        self.assertNotEqual(result.returncode,0);self.assertLessEqual(destination.stat().st_size,4096)


if __name__=='__main__':unittest.main()
