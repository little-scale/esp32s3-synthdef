"""Exercise the actual firmware program service with fake clocks/audio on macOS."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from engine_profile import generate
from patches import ROOT
from pattern_program import compile_pattern

@unittest.skipUnless(sys.platform=='darwin','native SHA adapter uses macOS CommonCrypto')
class PatternStorage(unittest.TestCase):
 def test_real_service_transactions_and_power_restart(self):
  folder=ROOT/'build/host/pattern-service';folder.mkdir(parents=True,exist_ok=True)
  engine=generate(folder/'engine','fm1');binary=folder/'service'
  with tempfile.TemporaryDirectory(prefix='pg-',dir='/tmp') as storage:
   subprocess.run(['cc','-std=c99','-O2','-Wall','-Wextra','-Werror','-Wno-deprecated-declarations',
    '-fno-fast-math','-ffp-contract=off','-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all',
    '-DPATCH_FM1_COMPAT=1','-Daccess=pg_test_access','-DPG_STORAGE_DIRECTORY="'+storage+'"',
    '-I'+str(engine),'-I'+str(ROOT/'firmware/components/instrument/include'),
    '-I'+str(ROOT/'firmware/components/patches/include'),'-I'+str(ROOT/'tests/pattern_stubs'),
    str(ROOT/'firmware/components/instrument/pattern_vm.c'),str(ROOT/'firmware/components/instrument/pattern_player.c'),
    str(ROOT/'firmware/components/patches/pattern_service.c'),str(ROOT/'firmware/components/patches/patch_format.c'),
    str(engine/'fm_load.c'),str(engine/'fm_render.c'),str(ROOT/'tests/pattern_service_test.c'),
    '-lm','-o',str(binary)],check=True)
   raw,_=compile_pattern(dict(op='Pbind',args=['freq',440,'dur',.25]),'12'*32,tempo=2,autostart=True)
   path=folder/'program.espp';path.write_bytes(raw)
   def run(mode):
    result=subprocess.run([str(binary),str(path),mode],capture_output=True,text=True)
    self.assertEqual(result.returncode,0,result.stderr)
   run('install');run('boot');run('mismatch');run('delete');run('empty');run('install')
   # Tear the newest bank: startup falls back to the intact previous bank.
   Path(storage,'program_b.bin').write_bytes(b'PGs1 broken')
   run('boot')
   Path(storage,'program_a.bin').write_bytes(b'PGs1 broken')
   run('empty')

if __name__=='__main__':unittest.main()
