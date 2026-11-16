"""No USB access: rate selection, real adapter with fake IDF I/O, build admission."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import firmware_upload as uploader

ROOT = Path(__file__).resolve().parents[1]
INSTRUMENT = ROOT/'firmware/components/instrument/include'


class RateTests(unittest.TestCase):
    def test_all_existing_profiles_and_invalid_xiao_combination(self):
        cases = [({}, 44100, 44100), ({'HEADLESS':1},44100,44100),
                 ({'HEADLESS':1,'XIAO_NATIVE_16K':1},16000,16000),
                 ({'VOICE_PE':1},48000,48000),
                 ({'VOICE_PE':1,'VOICE_PE_NATIVE_16K':1},16000,16000),
                 ({'VOICE_PE':1,'VOICE_PE_LOW_RATE':1},16000,48000)]
        for defines, dsp, output in cases:
            with self.subTest(defines=defines):
                source = '#include "synthdef_rate.h"\n'
                source += f'_Static_assert(SYNTHDEF_SAMPLE_RATE=={dsp},"DSP rate");\n'
                source += f'_Static_assert(SYNTHDEF_OUTPUT_SAMPLE_RATE=={output},"wire rate");\n'
                subprocess.run(['cc','-std=c11','-fsyntax-only','-x','c','-I'+str(INSTRUMENT),
                    *['-DCONFIG_SYNTHDEF_'+key for key in defines],'-'],input=source,text=True,check=True,capture_output=True)
        for defines in (['XIAO_NATIVE_16K'],['HEADLESS','XIAO_NATIVE_16K','VOICE_PE'],
                        ['VOICE_PE','VOICE_PE_LOW_RATE','VOICE_PE_NATIVE_16K']):
            result=subprocess.run(['cc','-fsyntax-only','-x','c','-I'+str(INSTRUMENT),
                *['-DCONFIG_SYNTHDEF_'+key for key in defines],'-'],
                input='#include "synthdef_rate.h"\n',text=True,capture_output=True)
            self.assertNotEqual(result.returncode,0)

    def test_i2s_clock_pcm_capture_boundaries_and_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            (folder/'driver').mkdir()
            for header in ('driver/i2s_std.h','driver/gpio.h','esp_err.h','esp_check.h','esp_heap_caps.h','esp_random.h'):
                (folder/header).write_text('#include "fake_idf.h"\n')
            (folder/'fake_idf.h').write_text((ROOT/'tests/xiao_i2s_fake.h').read_text())
            for rate in (44100,16000):
                with self.subTest(rate=rate):
                    (folder/'sdkconfig.h').write_text('#define CONFIG_SYNTHDEF_HEADLESS 1\n#define CONFIG_SYNTHDEF_NO_DISPLAY 1\n'
                        '#define CONFIG_SYNTHDEF_I2S_BCLK 7\n#define CONFIG_SYNTHDEF_I2S_WS 8\n#define CONFIG_SYNTHDEF_I2S_DOUT 9\n'
                        + ('#define CONFIG_SYNTHDEF_XIAO_NATIVE_16K 1\n' if rate==16000 else ''))
                    binary=folder/'test'
                    subprocess.run(['cc','-std=c11','-O1','-Wall','-Wextra','-Werror',
                        '-fsanitize=undefined,bounds','-fno-sanitize-recover=all','-I'+str(folder),'-I'+str(INSTRUMENT),
                        '-I'+str(ROOT/'firmware/components/board_audio/include'),
                        str(ROOT/'tests/xiao_i2s_test.c'),'-o',str(binary)],check=True,capture_output=True)
                    subprocess.run([str(binary),str(rate)],check=True,capture_output=True)


class BuildAdmissionTests(unittest.TestCase):
    def test_installer_refuses_wrong_rate_and_fixed_rate_diagnostics(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(uploader,'ROOT',Path(temporary)):
            for board in ('xiao','xiao-native-16k'):
                target=uploader.TARGETS[board]; folder=Path(temporary)/'firmware'/target.folder
                (folder/'config').mkdir(parents=True)
                (folder/'bootloader').mkdir();(folder/'partition_table').mkdir()
                (folder/'project_description.json').write_text(json.dumps(dict(project_name='waveshare_synthdef',target='esp32s3')))
                manifest=dict(flash_settings=dict(flash_mode='qio',flash_freq='80m',flash_size='8MB'),
                    extra_esptool_args=dict(chip='esp32s3'),flash_files=uploader.FILES,
                    **{part:dict(encrypted='false') for part in ('bootloader','partition-table','app')})
                (folder/'flasher_args.json').write_text(json.dumps(manifest))
                for name,data in zip(uploader.FILES.values(),(b'\xe9boot',b'\xaa\x50table',b'\xe9app')):
                    (folder/name).write_bytes(data)
                config=dict(SYNTHDEF_HEADLESS=True,ESPTOOLPY_FLASHSIZE='8MB',
                    SYNTHDEF_XIAO_NATIVE_16K=target.native16)
                def load():
                    (folder/'config/sdkconfig.json').write_text(json.dumps(config))
                    return uploader.load_image(board)
                self.assertEqual(load().target.rate,target.rate)
                config['SYNTHDEF_XIAO_NATIVE_16K']=not target.native16
                with self.assertRaisesRegex(ValueError,'metadata'):load()
                config['SYNTHDEF_XIAO_NATIVE_16K']=target.native16
                if target.native16:
                    config['SYNTHDEF_DIAGNOSTICS']=True
                    with self.assertRaisesRegex(ValueError,'diagnostic'):load()
                    config['SYNTHDEF_DIAGNOSTICS']=False
                config['SYNTHDEF_VOICE_PE_NATIVE_16K']=True
                with self.assertRaisesRegex(ValueError,'metadata'):load()


if __name__=='__main__':unittest.main(verbosity=2)
