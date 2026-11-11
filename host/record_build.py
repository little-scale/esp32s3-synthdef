#!/usr/bin/env python3
"""Record build provenance, verified compile options and target structure sizes."""
import hashlib
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess

ROOT = Path(__file__).resolve().parents[1]
from engine_profile import generate
from prepare import qualification_fingerprint
parser=argparse.ArgumentParser()
parser.add_argument('--build-dir',default='build-esp32s3')
parser.add_argument('--output',default='esp32-build.json')
options=parser.parse_args()
BUILD = ROOT/'firmware'/options.build_dir
entries = json.loads((BUILD/'compile_commands.json').read_text())
engine = [e for e in entries if e['file'].endswith(('/src/fm_load.c', '/src/fm_render.c'))]
assert len(engine) == 2
verified = []
for entry in engine:
    args = shlex.split(entry['command'])
    assert '-fno-fast-math' in args and '-ffp-contract=off' in args
    assert [a for a in args if a.startswith('-std=')][-1] == '-std=c99'
    assert not any('device_include' in a or 'fm1-base' in a for a in args)
    assert '-ffast-math' not in args
    verified.append({'source': str(Path(entry['file']).relative_to(ROOT)),
                     'math': ['-fno-fast-math', '-ffp-contract=off'], 'language': 'c99',
                     'fm1_platform_includes': False})
compiler = shlex.split(engine[0]['command'])[0]
profile=BUILD/'esp-idf/synthdef_engine/target-profile/src'
profile_manifest=json.loads((profile.parent/'profile.json').read_text())
candidate_flags={('candidate_'+name):value for name,value in profile_manifest.get('candidate_kernels',{}).items() if name!='production_default'}
expected_profile=generate(ROOT/'build/host/verified-profile'/profile_manifest['profile']/'src',profile_manifest['profile'],binding_families=profile_manifest.get('candidate_binding_families'),qualified_kernels=profile_manifest.get('qualified_kernels',{}).get('enabled',False),**candidate_flags)
for source in expected_profile.iterdir():
    assert (profile/source.name).read_bytes()==source.read_bytes(),'Target engine copy differs from audited profile: '+source.name
probe = ROOT/'build/host/target_sizes.c'
probe.write_text('#include "fm_synth.h"\nchar target_graph[sizeof(fm_graph)];\n'
                 'char target_voice[sizeof(fm_voice)];\nchar target_scratch[sizeof(fm_scratch)];\n')
obj = probe.with_suffix('.o')
subprocess.run([compiler, '-I'+str(profile),
                '-c', str(probe), '-o', str(obj)], check=True)
nm = Path(compiler).with_name('xtensa-esp-elf-nm')
sizes = {}
for line in subprocess.check_output([str(nm), '-S', str(obj)], text=True).splitlines():
    match = re.match(r'\S+\s+(\S+)\s+\w\s+target_(\w+)$', line)
    if match: sizes[match[2]+'_bytes'] = int(match[1], 16)
description = json.loads((BUILD/'project_description.json').read_text())
idf_path = Path(description['idf_path'])
generated = (ROOT/'firmware/main/generated.h').read_text()
main_source = (ROOT/'firmware/main/main.c').read_text()
task_stacks = {name:int(re.search(r'^#define '+name+r' (\d+)$',main_source,re.M)[1])
               for name in ('CONTROL_STACK_BYTES','AUDIO_STACK_BYTES')}
app = BUILD/'waveshare_synthdef.bin'
build_id=re.search(r'#define BUILD_ID "(.*?)"', generated)[1]
assert build_id.encode() in app.read_bytes(), 'Binary is stale relative to the generated source identity'
config_path=Path(description['config_file'])
config=config_path.read_text()
compat='CONFIG_SYNTHDEF_FM1_COMPAT=y' in config
assert profile_manifest['profile']==('fm1' if compat else 'compact')
if 'CONFIG_SYNTHDEF_TOUCH_UI=y' in config:
    assert int(re.search(r'CONFIG_LV_MEM_SIZE_KILOBYTES=(\d+)', config)[1]) >= 64, 'Expanded library needs a 64 KiB LVGL heap'
    assert 'CONFIG_LV_THEME_DEFAULT_TRANSITION_TIME=0' in config
    lv_entry=next(e for e in entries if e['file'].endswith('/src/misc/lv_mem.c'))
    lv_args=shlex.split(lv_entry['command'])
    assert '-DLV_MEM_POOL_ALLOC=synthdef_lvgl_pool_alloc' in lv_args, 'UI heap must leave internal RAM available for Wi-Fi'
    lv_obj=next((BUILD/'esp-idf/lvgl__lvgl').rglob('lv_mem.c.obj'))
    lv_symbols=subprocess.check_output([str(nm),'-S',str(lv_obj)],text=True)
    assert 'heap_caps_malloc' in lv_symbols and 'work_mem_int' not in lv_symbols, 'LVGL fixed pool placement was not applied'
capabilities = json.loads((ROOT/'docs/capabilities.json').read_text())
loader_obj = next((BUILD/'esp-idf/synthdef_engine').rglob('fm_load.c.obj'))
strings = set(subprocess.check_output(['strings', '-n', '2', str(loader_obj)], text=True).splitlines())
assert all(name in strings for name in capabilities['compiled_types'])
instrument_obj=next((BUILD/'esp-idf/instrument').rglob('instrument.c.obj'))
undefined=subprocess.check_output([str(nm),'-u',str(instrument_obj)],text=True)
assert not re.search(r'\blrintf\b',undefined), 'Per-sample library conversion has returned'
symbols={}
for line in subprocess.check_output([str(nm),'-S',str(BUILD/'waveshare_synthdef.elf')],text=True).splitlines():
    match=re.match(r'([0-9a-f]+) ([0-9a-f]+) \w (\S+)$',line)
    if match:symbols[match[3]]={'address':int(match[1],16),'bytes':int(match[2],16)}
hot=['render_graph','fast_arithmetic','fast_sine','fast_envelope','fast_pan','fast_filter','fast_lag','fast_unary','binary',
     'envelope','envelope_init','segment','sine_control_step','fm_start','fm_seed','fm_set',
     'fm_prepare','fm_render_input','fm_render','delay_render','unary']
internal_kernels='CONFIG_SYNTHDEF_INTERNAL_KERNELS=y' in config
optional={'fm_render_input','fm_set','delay_render','unary'} # unused wrappers or helpers inlined into render_graph
assert all(name in symbols for name in hot if name not in optional), 'Required rendering symbol absent'
hot_retained=[name for name in hot if name in symbols]
internal_rings='CONFIG_SYNTHDEF_INTERNAL_RINGS=y' in config
rings_hot=['rg_process','rings_render','rg_hermite','rg_fx_write']
if internal_rings:
    assert all(name in symbols for name in rings_hot),'Expected Rings routine missing'
    assert all(0x40370000<=symbols[name]['address']<0x403e0000 for name in rings_hot),'Rings routine escaped internal instruction RAM'
if internal_kernels:
    assert all(0x40370000<=symbols[name]['address']<0x403e0000 for name in hot_retained), 'Hot kernel escaped internal instruction RAM'
internal_sine='CONFIG_SYNTHDEF_INTERNAL_SINE=y' in config
internal_adapter='CONFIG_SYNTHDEF_INTERNAL_ADAPTER=y' in config
adapter_hot=['instrument_apply','instrument_apply_batch','instrument_render','instrument_pcm']
adapter_hot+=['instrument_render_stereo','master_delay_render','master_delay_set']
if 'CONFIG_SYNTHDEF_HEADLESS=y' in config:adapter_hot.append('instrument_pcm_stereo')
assert all(name in symbols for name in adapter_hot)
if internal_adapter:
    assert all(0x40370000<=symbols[name]['address']<0x403e0000 for name in adapter_hot),'Audio adapter escaped internal instruction RAM'
assert (0x3fc80000<=symbols['fm_sine']['address']<0x3fd00000)==internal_sine
sections=subprocess.check_output([str(Path(compiler).with_name('xtensa-esp-elf-objdump')),
                                  '-h',str(BUILD/'waveshare_synthdef.elf')],text=True)
elf=(BUILD/'waveshare_synthdef.elf').read_bytes()
for name,length,start,offset in re.findall(r'^\s*\d+\s+(\S+)\s+([0-9a-f]+)\s+([0-9a-f]+)\s+[0-9a-f]+\s+([0-9a-f]+)',sections,re.M):
    length,start,offset=[int(value,16) for value in (length,start,offset)]
    address=symbols['fm_sine']['address'];size=symbols['fm_sine']['bytes']
    if start<=address and address+size<=start+length:
        sine_hash=hashlib.sha256(elf[offset+address-start:offset+address-start+size]).hexdigest()
        break
else:raise AssertionError('Sine table section not found')
assert size==32772 and sine_hash=='3264f07efa6217955d24e1756a7887972ef7fce7ad6709e99eec1dc9331232fd', 'Pinned sine table bytes changed'
report = {
    'status': 'cross-compiled; physical runtime results are recorded separately',
    'build_id': build_id,
    'firmware_fingerprint':qualification_fingerprint(),
    'touch_ui_enabled': 'CONFIG_SYNTHDEF_TOUCH_UI=y' in config,
    'lvgl_pool_storage': 'PSRAM; fixed pool retained across LVGL reinitialization' if 'CONFIG_SYNTHDEF_TOUCH_UI=y' in config else 'not linked',
    'quad_flash_enabled': 'CONFIG_ESPTOOLPY_FLASHMODE_QIO=y' in config,
    'pcm_conversion': 'bounded nearest/even; no lrintf call in target instrument object',
    'engine_commit': capabilities['engine_commit'],
    'profile_sha256': capabilities['profile_sha256'],
    'idf_version': subprocess.check_output(['git', '-C', str(idf_path), 'describe', '--tags', '--always'], text=True).strip(),
    'idf_commit': subprocess.check_output(['git', '-C', str(idf_path), 'rev-parse', 'HEAD'], text=True).strip(),
    'compiler': subprocess.check_output([compiler, '--version'], text=True).splitlines()[0],
    'target': 'esp32s3',
    'board_revision': 'XIAO ESP32-S3 (headless profile)' if 'CONFIG_SYNTHDEF_HEADLESS=y' in config else 'V2 (user confirmed; not physically probed)',
    'output_channels': 2 if 'CONFIG_SYNTHDEF_HEADLESS=y' in config else 1,
    'compiled_loader_types_checked_in_target_object': len(capabilities['compiled_types']),
    'engine_compile_options_verified': verified, 'target_structure_sizes': sizes,
    'engine_fixed_allocation_bytes': 4*sizes['graph_bytes']+2*sizes['voice_bytes']+sizes['scratch_bytes'],
    'engine_fixed_internal_bytes':sizes['voice_bytes'] if compat else 4*sizes['graph_bytes']+2*sizes['voice_bytes']+sizes['scratch_bytes'],
    'master_voice_storage':'PSRAM' if compat else 'internal',
    'engine_fixed_psram_bytes':4*sizes['graph_bytes']+sizes['scratch_bytes']+sizes['voice_bytes'] if compat else 0,
    'synth_arena_psram_bytes':1048576 if compat else 0,
    'synth_fast_arena_internal_bytes':int(re.search(r'CONFIG_SYNTHDEF_INTERNAL_VOICE_ARENA_SAMPLES=(\d+)',config)[1])*4 if 'CONFIG_SYNTHDEF_INTERNAL_VOICE_ARENA_SAMPLES=' in config else 0,
    'cache':{key:int(re.search(r'^CONFIG_'+option+r'=(\w+)$',config,re.M)[1],0) for key,option in (
        ('instruction_bytes','ESP32S3_INSTRUCTION_CACHE_SIZE'),('data_bytes','ESP32S3_DATA_CACHE_SIZE'),
        ('data_line_bytes','ESP32S3_DATA_CACHE_LINE_SIZE'))},
    'admission_policy':'fm1-compat-v1' if compat else 'catalog-voice-v2',
    'fm1_compat_hardware_qualified':False,
    'one_voice_without_effect_fixed_bytes':2*sizes['graph_bytes']+sizes['voice_bytes']+sizes['scratch_bytes'],
    'graph_buffers': 4, 'voice_instances':2,'shared_scratch_instances':1,
    'master_delay_arena_psram_bytes':1048576,
    'engine_profile':json.loads((profile.parent/'profile.json').read_text()),
    'package_buffers_psram_bytes': 3*131072,
    'diagnostics_enabled': 'CONFIG_SYNTHDEF_DIAGNOSTICS=y' in config,
    'internal_render_kernels': internal_kernels,
    'internal_rings_kernels':internal_rings,
    'rings_hot_symbols':{name:symbols[name] for name in rings_hot if name in symbols},
    'internal_audio_adapter':internal_adapter,
    'adapter_hot_symbols':{name:symbols[name] for name in adapter_hot},
    'hot_kernel_symbols': {name:symbols[name] for name in hot_retained},
    'optional_wrapper_not_retained': [name for name in hot if name not in symbols],
    'sine_table_internal': internal_sine,
    'sine_table_symbol': symbols['fm_sine'],
    'sine_table_sha256': sine_hash,
    'console_patch_task_stack_bytes': task_stacks['CONTROL_STACK_BYTES'],
    'audio_task_stack_bytes': task_stacks['AUDIO_STACK_BYTES'], 'event_queue_capacity': 16,
    'dma_descriptors': 6, 'dma_frames_per_descriptor': 128,
    'app_bytes': app.stat().st_size,
    'sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
               [app, BUILD/'bootloader/bootloader.bin', BUILD/'partition_table/partition-table.bin',
                config_path, ROOT/('host/xiao.defaults' if 'CONFIG_SYNTHDEF_HEADLESS=y' in config else 'firmware/sdkconfig.defaults'),
                ROOT/'firmware'/re.search(r'^CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="([^"]+)"$',config,re.M)[1],
                ROOT/'firmware/dependencies.lock']},
    'runtime_heap_and_clocks': 'see runtime logs; actual clocks still require external measurement',
}
(ROOT/'evidence'/options.output).write_text(json.dumps(report, indent=2)+'\n')
print(f'ESP32 binary: {app.stat().st_size} bytes; target sizes: {sizes}; compile flags verified')
