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
probe = ROOT/'build/host/target_sizes.c'
probe.write_text('#include "fm_synth.h"\nchar target_graph[sizeof(fm_graph)];\n'
                 'char target_voice[sizeof(fm_voice)];\nchar target_scratch[sizeof(fm_scratch)];\n')
obj = probe.with_suffix('.o')
subprocess.run([compiler, '-I'+str(ROOT/'upstream/fm1-synthdef/synthdef-engine/src'),
                '-c', str(probe), '-o', str(obj)], check=True)
nm = Path(compiler).with_name('xtensa-esp-elf-nm')
sizes = {}
for line in subprocess.check_output([str(nm), '-S', str(obj)], text=True).splitlines():
    match = re.match(r'\S+\s+(\S+)\s+\w\s+target_(\w+)$', line)
    if match: sizes[match[2]+'_bytes'] = int(match[1], 16)
description = json.loads((BUILD/'project_description.json').read_text())
idf_path = Path(description['idf_path'])
generated = (ROOT/'firmware/main/generated.h').read_text()
app = BUILD/'waveshare_synthdef.bin'
build_id=re.search(r'#define BUILD_ID "(.*?)"', generated)[1]
assert build_id.encode() in app.read_bytes(), 'Binary is stale relative to the generated source identity'
config_path=Path(description['config_file'])
config=config_path.read_text()
if 'CONFIG_SYNTHDEF_TOUCH_UI=y' in config:
    assert int(re.search(r'CONFIG_LV_MEM_SIZE_KILOBYTES=(\d+)', config)[1]) >= 64, 'Expanded library needs a 64 KiB LVGL heap'
    assert 'CONFIG_LV_THEME_DEFAULT_TRANSITION_TIME=0' in config
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
hot=['render_graph','fast_arithmetic','fast_sine','fast_envelope','fast_pan','binary',
     'envelope','envelope_init','segment','sine_control_step','fm_start','fm_seed','fm_set',
     'fm_prepare','fm_render_input','fm_render']
internal_kernels='CONFIG_SYNTHDEF_INTERNAL_KERNELS=y' in config
optional={'fm_render_input','fm_set'} # wrappers/name lookup can be unused and discarded
assert all(name in symbols for name in hot if name not in optional), 'Required rendering symbol absent'
hot_retained=[name for name in hot if name in symbols]
if internal_kernels:
    assert all(0x40370000<=symbols[name]['address']<0x403e0000 for name in hot_retained), 'Hot kernel escaped internal instruction RAM'
internal_sine='CONFIG_SYNTHDEF_INTERNAL_SINE=y' in config
internal_adapter='CONFIG_SYNTHDEF_INTERNAL_ADAPTER=y' in config
adapter_hot=['instrument_apply','instrument_apply_batch','instrument_render','instrument_pcm']
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
    'touch_ui_enabled': 'CONFIG_SYNTHDEF_TOUCH_UI=y' in config,
    'quad_flash_enabled': 'CONFIG_ESPTOOLPY_FLASHMODE_QIO=y' in config,
    'pcm_conversion': 'bounded nearest/even; no lrintf call in target instrument object',
    'engine_commit': capabilities['engine_commit'],
    'profile_sha256': capabilities['profile_sha256'],
    'idf_version': subprocess.check_output(['git', '-C', str(idf_path), 'describe', '--tags', '--always'], text=True).strip(),
    'idf_commit': subprocess.check_output(['git', '-C', str(idf_path), 'rev-parse', 'HEAD'], text=True).strip(),
    'compiler': subprocess.check_output([compiler, '--version'], text=True).splitlines()[0],
    'target': 'esp32s3', 'board_revision': 'V2 (user confirmed; not physically probed)',
    'compiled_loader_types_checked_in_target_object': len(capabilities['compiled_types']),
    'engine_compile_options_verified': verified, 'target_structure_sizes': sizes,
    'engine_fixed_allocation_bytes': sum(sizes.values())+sizes['graph_bytes'],
    'graph_buffers': 2, 'package_buffers_psram_bytes': 3*131072,
    'diagnostics_enabled': 'CONFIG_SYNTHDEF_DIAGNOSTICS=y' in config,
    'internal_render_kernels': internal_kernels,
    'internal_audio_adapter':internal_adapter,
    'adapter_hot_symbols':{name:symbols[name] for name in adapter_hot},
    'hot_kernel_symbols': {name:symbols[name] for name in hot_retained},
    'optional_wrapper_not_retained': [name for name in hot if name not in symbols],
    'sine_table_internal': internal_sine,
    'sine_table_symbol': symbols['fm_sine'],
    'sine_table_sha256': sine_hash,
    'console_patch_task_stack_bytes': 16384,
    'audio_task_stack_bytes': 16384, 'event_queue_capacity': 16,
    'dma_descriptors': 6, 'dma_frames_per_descriptor': 128,
    'app_bytes': app.stat().st_size,
    'sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
               [app, BUILD/'bootloader/bootloader.bin', BUILD/'partition_table/partition-table.bin',
                config_path, ROOT/'firmware/sdkconfig.defaults', ROOT/'firmware/partitions.csv',
                ROOT/'firmware/dependencies.lock']},
    'runtime_heap_and_clocks': 'see runtime logs; actual clocks still require external measurement',
}
(ROOT/'evidence'/options.output).write_text(json.dumps(report, indent=2)+'\n')
print(f'ESP32 binary: {app.stat().st_size} bytes; target sizes: {sizes}; compile flags verified')
