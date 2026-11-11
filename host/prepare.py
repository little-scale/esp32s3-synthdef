#!/usr/bin/env python3
"""Verify pinned sources and derive metadata from the engine actually compiled."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from engine_profile import generate, LIMITS, PROFILES

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_ENGINE = ROOT / 'upstream/fm1-synthdef/synthdef-engine'
ENGINE = generate(ROOT/'build/host/target-profile/src').parent
FLAGS = ['-std=c99', '-O2', '-Wall', '-Wextra', '-Werror', '-fno-fast-math', '-ffp-contract=off']

def digest(data):
    return hashlib.sha256(data).hexdigest()

def firmware_sources():
    return sorted(p for p in (ROOT/'firmware').rglob('*') if p.is_file() and
                  ('components' in p.parts or 'main' in p.parts or p.parent==ROOT/'firmware') and
                  not any(x=='managed_components' or x.startswith('build') for x in p.parts) and
                  p.name not in ('generated.h','catalog_generated.h','sdkconfig','sdkconfig.old','dependencies.lock'))

def qualification_fingerprint():
    provenance=json.loads((ROOT/'upstream/SOURCES.json').read_text())
    return digest((provenance['commit']+digest((ROOT/'host/engine_profile.py').read_bytes())+
                   digest((ROOT/'host/signal_buffers.py').read_bytes())+
                   digest((ROOT/'host/dsp_kernels.py').read_bytes())+
                   digest((ROOT/'host/dsp_candidates.py').read_bytes())+
                   digest((ROOT/'host/dsp_binding.py').read_bytes())+
                   digest((ROOT/'host/dsp_routing.py').read_bytes())+
                   digest((ROOT/'host/dsp_chaos_cache.py').read_bytes())+
                   digest((ROOT/'host/dsp_core.py').read_bytes())+
                   digest((ROOT/'host/qualified_kernels.py').read_bytes())+
                   digest((ROOT/'examples/master-delay.scsyndef').read_bytes())+
                   digest((ROOT/'examples/master-bypass.scsyndef').read_bytes())+
                   digest((ROOT/'examples/master-bypass.scd').read_bytes())+
                   ''.join(str(p.relative_to(ROOT))+digest(p.read_bytes()) for p in firmware_sources())).encode())

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    provenance = json.loads((ROOT / 'upstream/SOURCES.json').read_text())
    for name, expected in provenance['sha256'].items():
        if digest((ROOT / 'upstream/fm1-synthdef' / name).read_bytes()) != expected:
            raise RuntimeError('Modified vendored source: ' + name)
    build = ROOT / 'build/host'
    build.mkdir(parents=True, exist_ok=True)
    subprocess.run(['cc', *FLAGS, '-I'+str(ENGINE/'src'), str(ENGINE/'src/fm_load.c'),
                    str(ROOT/'host/capabilities.c'), '-lm', '-o', str(build/'capabilities')], check=True)
    compiled = json.loads(subprocess.check_output([str(build/'capabilities')], text=True))
    header = (ENGINE/'src/fm_synth.h').read_text()
    enum = re.search(r'typedef enum\s*\{(.*?)FM_TYPES', header, re.S).group(1)
    names = re.findall(r'\bFM_(\w+)\b', enum)
    if names != compiled['types']:
        raise RuntimeError('Engine enum and compiled loader table disagree')
    profile = json.loads((UPSTREAM_ENGINE/'profile.json').read_text())
    missing = sorted(set(names) - set(profile['implemented_types']))
    extra = sorted(set(profile['implemented_types']) - set(names))
    fixture = (ROOT/'examples/gated-sine.scsyndef').read_bytes()
    if fixture != (UPSTREAM_ENGINE/'fixtures/fm1_voice.scsyndef').read_bytes():
        raise RuntimeError('Factory patch differs from pinned upstream fixture')
    touch = (ROOT/'examples/touch-sine.scsyndef').read_bytes()
    effect=(ROOT/'examples/master-delay.scsyndef').read_bytes()
    subprocess.run(['cc',*FLAGS,'-I'+str(ENGINE/'src'),str(ENGINE/'src/fm_load.c'),str(ENGINE/'src/fm_render.c'),
                    str(ROOT/'host/inspect_graph.c'),'-lm','-o',str(build/'inspect-graph')],check=True)
    catalog=[]
    for entry in json.loads((ROOT/'examples/catalog.json').read_text()):
        assert entry['status'] in ('candidate','qualified','rejected')
        graph=ROOT/f'examples/{entry["id"]}.scsyndef'
        layout=json.loads(subprocess.check_output([str(build/'inspect-graph'),str(graph)],text=True))
        assert layout['nodes']<=24 and layout['signals']<=32 and layout['inputs']<=256 and not layout['delay']
        if entry['status']=='qualified':
            evidence=json.loads((ROOT/'evidence/qualified-voices.json').read_text())
            measured=next(r for r in evidence['reports'] if r['patch']==entry['id'])
            if evidence['firmware_fingerprint']!=qualification_fingerprint() or not measured['passed'] or measured['graph_sha256']!=digest(graph.read_bytes()):
                raise RuntimeError('Stale catalog qualification: mark '+entry['id']+' candidate and repeat its device checks')
        catalog.append({**entry,**layout,'graph_bytes':graph.stat().st_size,'graph_sha256':digest(graph.read_bytes())})
    catalog_header='/* Generated by host/prepare.py; do not edit. */\n#pragma once\n#include "patch_policy.h"\n'
    wire_catalog=[{k:e[k] for k in ('id','status','graph_sha256')} for e in catalog]
    catalog_header+='#define PATCH_CATALOG_JSON '+json.dumps(json.dumps(wire_catalog,separators=(',',':')))+'\n'
    catalog_header+='#ifdef PATCH_CATALOG_IMPLEMENTATION\n'
    catalog_header+='typedef struct { unsigned char hash[32]; unsigned bytes,nodes,signals,inputs,state; } patch_catalog_entry;\n'
    catalog_header+='static const patch_catalog_entry patch_catalog[]={\n'
    for e in catalog:
        state={'candidate':0,'qualified':1,'rejected':2}[e['status']]
        catalog_header+='    {{'+','.join('0x'+e['graph_sha256'][i:i+2] for i in range(0,64,2))+'},'+','.join(str(e[k]) for k in ('graph_bytes','nodes','signals','inputs'))+','+str(state)+'},\n'
    catalog_header+='};\n#endif\n'
    capability = {
        'schema': 1, 'target': 'ESP32-S3-Touch-AMOLED-1.8-V2',
        'engine_commit': provenance['commit'], 'block_frames': compiled['block_frames'],
        'compiled_types': names, 'compiled_type_count': len(names),
        'hardware_validated_types': [], 'sample_rate_requested': 44100,
        'sample_rates_hardware_validated': [], 'initial_voice_limit': 1,
        'master_effect_enabled': True, 'raw_graph_byte_limit': 65536,
        'note_preparation_blocks':1,
        'engine_target_limits':{k:int(str(new).rstrip('u')) for k,(_,new) in LIMITS.items()},
        'engine_target_header_sha256':digest((ENGINE/'src/fm_synth.h').read_bytes()),
        'engine_profile_generator_sha256':digest((ROOT/'host/engine_profile.py').read_bytes()),
        'signal_planner_sha256':digest((ROOT/'host/signal_buffers.py').read_bytes()),
        'dsp_kernels_sha256':digest((ROOT/'host/dsp_kernels.py').read_bytes()),
        'dsp_candidates_sha256':digest((ROOT/'host/dsp_candidates.py').read_bytes()),
        'dsp_binding_sha256':digest((ROOT/'host/dsp_binding.py').read_bytes()),
        'dsp_routing_sha256':digest((ROOT/'host/dsp_routing.py').read_bytes()),
        'dsp_chaos_cache_sha256':digest((ROOT/'host/dsp_chaos_cache.py').read_bytes()),
        'dsp_core_sha256':digest((ROOT/'host/dsp_core.py').read_bytes()),
        'qualified_kernels_sha256':digest((ROOT/'host/qualified_kernels.py').read_bytes()),
        'master_delay':{'kind':'embedded persistent mono SynthDef bus','max_seconds':5.0,
                        'arena_samples':262144,'arena_bytes':1048576,'storage':'PSRAM','graph_sha256':digest(effect)},
        'parser': 'fm_load remains authoritative for rates, selectors and graph layouts',
        'optional_fm1_profile':{'config':'CONFIG_SYNTHDEF_FM1_COMPAT','policy':'fm1-compat-v1',
            'nodes_max':PROFILES['fm1']['FM_NODES'][1],'signals_max':PROFILES['fm1']['FM_OUTPUTS'][1],
            'inputs_max':PROFILES['fm1']['FM_INPUTS'][1],'audio_buffers_max':192,
            'signal_storage':'Loader-planned audio reuse and one float per scalar output',
            'synth_arena_samples':262144,
            'synth_arena_bytes':1048576,'required_live_controls':['freq','amp','gate'],
            'control_buses':{'count':32,'touch':{'x':0,'y':1,'gate':2},'reader':'In.kr','bus_patches_require_legacy_controls':False},
            'types':names,'qualification':'host emulation only; ESP32 deadlines unmeasured',
            'arena_clear_samples_per_block':1024,'large_graphs_and_scratch':'PSRAM'},
        'admission': {'policy': 'catalog-voice-v2', 'legacy_family': {'policy':'simple-voice-v1','nodes_max': 20, 'signals_max': 32,
                      'inputs_max': 256, 'audio_nodes_max': 8, 'delay_samples_max': 0,
                      'required_live_controls': ['freq', 'amp', 'gate', 'knob1', 'knob2', 'knob3', 'knob4'],
                      'types': ['Control', 'Pan2', 'Out', 'MulAdd', 'DC', 'SinOsc', 'EnvGen', 'BinaryOpUGen'],
                      'binary_selectors': [0, 1, 2, 4, 12, 13], 'control_rate_pow_max': 1,
                      'SinOsc_exactly': 1, 'EnvGen_exactly': 1, 'Pan2_exactly': 1, 'Out_exactly': 1,
                      'oscillator_inputs_audio_rate': False, 'panning_audio_rate': False,
                      'envelope_segments_max': 4, 'envelope_literal_shapes': [0, 1, 5, 8, 9],
                      'envelope_literal_curve_abs_max': 20},
                      'catalog_limits':{'nodes_max':24,'signals_max':32,'inputs_max':256,'delay_samples_max':0},
                      'catalog':catalog,'candidate_admission':'explicit diagnostic builds only; rejected entries never admitted'},
        'upload': {'protocol': 1, 'chunk_bytes': 256, 'source_byte_limit': 65536, 'slots': 1,
                   'main_slot': 1, 'fx_slot': 1, 'fx_bypass_slot': 0,
                   'activation': 'explicit muted maintenance; one graph and voice active'},
        'builtin_graphs': {'gated-sine': digest(fixture), 'touch-sine': digest(touch)},
    }
    factory_source=(ROOT/'examples/touch-sine.scd').read_bytes()
    factory_pair=json.loads((ROOT/'examples/touch-sine.source.json').read_text())
    assert factory_pair=={'touch-sine.scd':digest(factory_source),'touch-sine.scsyndef':digest(touch)},'Factory source/graph pair is stale; run host/export_factory.py'
    capability['factory_source_sha256']=digest(factory_source)
    cap_hash = digest(json.dumps(capability, sort_keys=True, separators=(',', ':')).encode())
    capability['profile_sha256'] = cap_hash
    build_files = firmware_sources()
    build_id = digest((''.join(str(p.relative_to(ROOT))+digest(p.read_bytes()) for p in build_files)
                       + cap_hash + digest(fixture) + digest(touch)+digest(catalog_header.encode())).encode())
    generated = ('/* Generated by host/prepare.py; do not edit. */\n#pragma once\n'
                 f'#define ENGINE_COMMIT "{provenance["commit"]}"\n'
                 f'#define CAPABILITY_HASH "{cap_hash}"\n#define BUILD_ID "{build_id}"\n'
                 f'#define PATCH_SHA256 "{digest(fixture)}"\n'
                 'static const unsigned char embedded_patch[] = {\n' +
                 '\n'.join('    '+','.join(f'0x{v:02x}' for v in fixture[i:i+16])+',' for i in range(0,len(fixture),16)) + '\n};\n')
    generated += (f'#define TOUCH_PATCH_SHA256 "{digest(touch)}"\n'
                  'static const unsigned char touch_patch[] = {\n' +
                  '\n'.join('    '+','.join(f'0x{v:02x}' for v in touch[i:i+16])+',' for i in range(0,len(touch),16))+'\n};\n')
    effect=(ROOT/'examples/master-delay.scsyndef').read_bytes()
    generated += ('static const unsigned char touch_patch_source[]={\n'+
                  '\n'.join('    '+','.join(f'0x{v:02x}' for v in factory_source[i:i+16])+',' for i in range(0,len(factory_source),16))+'\n};\n')
    generated += (f'#define MASTER_DELAY_SHA256 "{digest(effect)}"\nstatic const unsigned char master_delay_patch[]={{\n'+
                  '\n'.join('    '+','.join(f'0x{v:02x}' for v in effect[i:i+16])+',' for i in range(0,len(effect),16))+'\n};\n')
    for name,file in [('master_bypass_patch','master-bypass.scsyndef'),('master_bypass_source','master-bypass.scd')]:
        data=(ROOT/'examples'/file).read_bytes()
        generated += ('static const unsigned char '+name+'[]={\n'+
                      '\n'.join('    '+','.join(f'0x{v:02x}' for v in data[i:i+16])+',' for i in range(0,len(data),16))+'\n};\n')
    discrepancy = {'engine_commit': provenance['commit'], 'compiled_type_count': len(names),
                   'upstream_profile_type_count': len(profile['implemented_types']),
                   'missing_from_upstream_profile': missing, 'extra_in_upstream_profile': extra,
                   'host_structure_sizes': {k:v for k,v in compiled.items() if k.endswith('_bytes')},
                   'hardware_checks': 'pending; host struct sizes are not ESP32 measurements'}
    outputs = {ROOT/'docs/capabilities.json': json.dumps(capability, indent=2)+'\n',
               ROOT/'evidence/compatibility.json': json.dumps(discrepancy, indent=2)+'\n',
               ROOT/'firmware/main/generated.h': generated}
    outputs[ROOT/'firmware/components/patches/include/catalog_generated.h']=catalog_header
    for path, content in outputs.items():
        if args.check:
            if not path.exists() or path.read_text() != content:
                raise RuntimeError('Stale generated file: '+str(path.relative_to(ROOT)))
        else:
            path.write_text(content)
    print(f'Pinned source hashes verified; {len(names)} compiled types; upstream profile missing {len(missing)}; build {build_id[:12]}')

if __name__ == '__main__':
    main()
