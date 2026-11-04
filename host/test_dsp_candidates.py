#!/usr/bin/env python3
"""Offline next-batch equivalence, native throughput and Xtensa object analysis.

No serial, device, network, flashing or audio playback code is used here.
Candidates remain disabled in the production generator defaults.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
from engine_profile import ROOT, generate
from test_signal_reuse import graph
from dsp_candidates import BINARY_EXPRESSIONS, BINARY_SCALAR_SELECTORS, SMOOTH_TYPES, NOISE_TYPES

BUILD = ROOT / 'build/host/dsp-candidates-next'
SMOOTH = SMOOTH_TYPES


def fixture(kind, rate=2, arate=2, brate=1, selector=0, bank=False):
    c = lambda i: (-1, i)
    nodes = [('In', 2, [c(0)], 2, 0), ('In', 1, [c(0)], 3, 0)]
    source = lambda r, k: c(k+1) if r == 0 else (1 if r == 1 else 0, k)
    for _ in range(32 if bank else 1):
        refs = [source(arate, 0)]
        if kind in ('WhiteNoise','PinkNoise'):
            refs=[]
        elif kind in NOISE_TYPES:
            refs=[(1,2)]
        elif kind == 'BinaryOpUGen':
            refs.append(source(brate, 1))
        elif kind not in ('LPZ1', 'HPZ1'):
            refs.append((1, 2))
        index = len(nodes)
        nodes.append((kind, rate, refs, 1, selector))
        if rate != 2:
            nodes.append(('K2A', 2, [(index, 0)], 1, 0))
            index += 1
        nodes.append(('Out', 2, [c(0), (index, 0), (index, 0)], 0, 0))
    # The two unused input providers deliberately precede every node, including
    # initial-rate operators. Out still consumes the converted audio result.
    return graph(kind, nodes, constants=(0, .25, .5))


def fixtures():
    paths = []
    for kind in SMOOTH:
        for rate in (1, 2):
            for arate in range(rate+1):
                for suffix in ('normal', 'fault') if kind not in ('LPZ1', 'HPZ1') else ('normal',):
                    path = BUILD / f'{kind}_{rate}_{arate}_{suffix}.scsyndef'
                    path.write_bytes(fixture(kind, rate, arate))
                    paths.append(path)
    for kind in NOISE_TYPES:
        for rate in (1,2):
            path=BUILD/f'{kind}_{rate}.scsyndef'
            path.write_bytes(fixture(kind,rate));paths.append(path)
    # Shared RNG, constructors and a mid-graph RandSeed change must agree even
    # when candidate generators are interleaved with unchanged stochastic nodes.
    nodes=[('In',1,[(-1,0)],3,0)]
    for k,kind in enumerate(('WhiteNoise','PinkNoise','Dust','LFNoise0','GrayNoise','LFNoise1','LFNoise2','PinkNoise')):
        if k==3:nodes.append(('RandSeed',1,[(0,1),(-1,1)],1,0))
        i=len(nodes);nodes.append((kind,2,[(0,2)] if kind in ('Dust','LFNoise0','LFNoise1','LFNoise2') else [],1,0))
        nodes.append(('Out',2,[(-1,0),(i,0),(i,0)],0,0))
    path=BUILD/'Noise_interleaved_seed.scsyndef';path.write_bytes(graph('NoiseShared',nodes,constants=(0,12345)));paths.append(path)
    inventory = json.loads((ROOT/'evidence/fm1-fixed-inventory.json').read_text())
    for selector in map(int, inventory['operators']['BinaryOpUGen']):
        for rate in range(3):
            for arate in range(rate+1):
                for brate in range(rate+1):
                    path = BUILD/f'Binary_{selector}_{rate}_{arate}_{brate}.scsyndef'
                    path.write_bytes(fixture('BinaryOpUGen', rate, arate, brate, selector))
                    paths.append(path)
    for op in (3,5,17,18,19,20,21,39,42,43,44,45):
        for swapped in (False,True):
            refs=[(-1,1),(-1,2)]
            if swapped:refs.reverse()
            path=BUILD/f'Binary_signed_zero_{op}_{int(swapped)}.scsyndef'
            path.write_bytes(graph('SignedZero',[
                ('BinaryOpUGen',2,refs,1,op),('BinaryOpUGen',2,[(0,0),(-1,3)],1,22),
                ('Out',2,[(-1,0),(1,0),(1,0)],0,0)],constants=(0,-0.0,.5,-1)))
            paths.append(path)
    return paths


def run(command, timeout=120, env=None):
    result = subprocess.run(list(map(str, command)), capture_output=True, text=True, timeout=timeout, env=env)
    if result.returncode:
        raise RuntimeError(f'{command[0]} failed:\n{result.stdout}\n{result.stderr}')
    return result.stdout


def executable(reference, target, sanitized, inventory=False, defines=(), address=False):
    folder = BUILD / ('inventory' if inventory else 'sanitized' if sanitized else 'throughput')
    folder.mkdir(exist_ok=True)
    text = (reference/'fm_render.c').read_text()+'\n'+(reference/'fm_delay.inc').read_text()
    names = sorted(set(re.findall(r'^(?:int|void|uint32_t) (fm_\w+)\(', text, re.M)))
    flags = ['cc', '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror', '-fno-fast-math', '-ffp-contract=off']
    flags += ['-D'+name for name in defines]
    if not inventory and 'candidate_noise(' in (target/'fm_dsp_candidates.inc').read_text():
        flags += ['-DFM_CANDIDATE_TEST','-DFM_CANDIDATE_NOISE']
    prefix = 'dsp_ref_' if inventory else 'candidate_ref_'
    if inventory:
        flags.append('-DDSP_CANDIDATE_COMPARISON')
    if sanitized:
        flags += ['-fsanitize=undefined,bounds,float-cast-overflow', '-fno-sanitize-recover=all']
        if address:flags.append('-fsanitize=address')
    objects = []
    for name, source, include, extra in [
        ('reference', reference/'fm_render.c', reference, [f'-D{x}={prefix}{x[3:]}' for x in names]),
        ('target', target/'fm_render.c', target, []),
        ('load', target/'fm_load.c', target, []),
        ('test', ROOT/('tests/dsp_kernels_test.c' if inventory else 'tests/dsp_candidates_test.c'), target, []),
    ]:
        obj = folder / (name+'.o')
        run([*flags, '-I'+str(include), *extra, '-c', source, '-o', obj])
        objects.append(obj)
    binary = folder/'compare'
    run([*flags, *objects, '-lm', '-o', binary])
    return binary


def xtensa(reference, target):
    roots = sorted((Path.home()/'.espressif/tools/xtensa-esp-elf').glob('*/xtensa-esp-elf/bin'))
    if not roots:
        return {'available': False, 'scope': 'No cross compiler installed; no target timing claimed.'}
    prefix = str(roots[-1]/'xtensa-esp32s3-elf-')
    flags = ['-std=gnu99', '-Os', '-mlongcalls', '-mtext-section-literals', '-ffunction-sections',
             '-fdata-sections', '-fno-jump-tables', '-fno-tree-switch-conversion',
             '-fno-fast-math', '-ffp-contract=off']
    report = {'available': True, 'flags': flags, 'compiler':run([prefix+'gcc','--version']).splitlines()[0], 'timing_measured': False,
              'scope': 'Offline renderer objects only, not linked firmware or a hardware speed prediction.'}
    for name, source in [('reference', reference), ('candidate', target)]:
        obj = BUILD/(name+'-xtensa.o')
        run([prefix+'gcc', *flags, '-I'+str(source), '-c', source/'fm_render.c', '-o', obj])
        size = run([prefix+'size', obj])
        symbols = run([prefix+'nm', '-S', '--size-sort', obj])
        asm = run([prefix+'objdump', '-dr', obj])
        (BUILD/(name+'-xtensa.asm')).write_text(asm)
        report[name] = {'size_output': size.strip(), 'object_sha256': hashlib.sha256(obj.read_bytes()).hexdigest(),
                        'object_text_bytes':int(size.splitlines()[-1].split()[0]),
                        'selected_symbol_sizes_hex': [line for line in symbols.splitlines() if re.search(r'\b(candidate_smooth|candidate_noise|fast_arithmetic|extensions|utilities)$', line)],
                        'software_float_division_relocations': asm.count('__divsf3'),
                        'software_double_relocations': len(re.findall(r'__(?:add|sub|mul|div)df3', asm))}
        if name == 'candidate':
            section = re.search(r'Disassembly of section \.text\.candidate_smooth:\n(.*?)(?=\nDisassembly of section|\Z)', asm, re.S)
            assert section
            report[name]['candidate_smooth_direct_division_helper_references'] = section.group(1).count('__divsf3')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--benchmark', action='store_true', help='Also run silent native throughput trials')
    parser.add_argument('--inventory', action='store_true', help='Also compare all pinned graphs, examples and kernel fixtures')
    parser.add_argument('--variants', action='store_true', help='Also verify independent smooth-only and binary-only switches')
    parser.add_argument('--all-operator-benchmarks',action='store_true',help='Time each of the 36 new audio binary specialisations')
    parser.add_argument('--output',type=Path,default=ROOT/'evidence/dsp-candidates-next-host.json')
    parser.add_argument('--build-dir',type=Path)
    args = parser.parse_args()
    global BUILD
    if args.build_dir:BUILD=args.build_dir
    if not BUILD.is_absolute():BUILD=ROOT/BUILD
    if not args.output.is_absolute():args.output=ROOT/args.output
    BUILD.mkdir(parents=True, exist_ok=True)
    paths = fixtures()
    reference = generate(BUILD/'reference/src', 'fm1')
    target = generate(BUILD/'candidate/src', 'fm1', candidate_smooth=True, candidate_binary=True,candidate_noise=True)
    binary = executable(reference, target, True)
    result = json.loads(run([binary, *paths]))
    report = dict(result, hardware=False, audio_playback=False, device_access=False,
                  production_enabled=False, rates=[8000, 44100, 48000, 192000],
                  candidate_ugens=list(SMOOTH)+list(NOISE_TYPES), candidate_binary_selectors=sorted(BINARY_SCALAR_SELECTORS),
                  candidate_audio_binary_selectors=sorted(BINARY_EXPRESSIONS),
                  pink_index_probes_per_noise_variant=200000,
                  comparison='Bit-identical output, recursive voice/RNG/flags, constructor scratch; only caller-owned control-bank pointers and the new otherwise-unused Lag2/3 freq cache normalized.',
                  sanitizers=['undefined', 'bounds', 'float-cast-overflow'],
                  candidate_source_sha256=hashlib.sha256((ROOT/'host/dsp_candidates.py').read_bytes()).hexdigest(),
                  graphs={p.stem: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    report['graph_count'] = len(paths)
    report['source_sha256'] = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in (
        'host/dsp_candidates.py', 'host/engine_profile.py', 'host/test_dsp_candidates.py',
        'tests/dsp_candidates_test.c', 'tests/dsp_kernels_test.c')}
    report['native_compiler'] = run(['cc','--version']).splitlines()[0]
    if args.variants:
        report['independent_variants'] = {}
        for name, smooth, arithmetic, noise in [('smooth-only',True,False,False), ('binary-only',False,True,False),('noise-only',False,False,True)]:
            variant=generate(BUILD/name/'src','fm1',candidate_smooth=smooth,candidate_binary=arithmetic,candidate_noise=noise)
            variant_binary=executable(reference,variant,True)
            report['independent_variants'][name]=json.loads(run([variant_binary,*paths]))
    if args.inventory:
        broad = sorted((ROOT/'upstream/fm1-synthdef/synthdef-engine/fixtures').glob('*.scsyndef'))
        broad += sorted((ROOT/'examples').glob('*.scsyndef'))
        broad += sorted((ROOT/'build/host/dsp-kernels').glob('*.scsyndef'))
        inventory_binary = executable(reference, target, True, inventory=True)
        report['inventory'] = dict(json.loads(run([inventory_binary, *broad], env={**os.environ, 'DSP_TEST_BLOCKS':'32', 'DSP_TEST_RATE':'44100'})),
                                   scope='All pinned fixtures and current local example/kernel fixtures; 32 blocks each at 44.1 kHz with full recursive state, RNG and arena comparison.',
                                   graphs_sha256=hashlib.sha256(b''.join(hashlib.sha256(p.read_bytes()).digest() for p in broad)).hexdigest())
    if args.benchmark:
        native = executable(reference, target, False)
        timings = {}
        banks=[(k,k,0) for k in (*SMOOTH,*NOISE_TYPES)]+[('comparisons','BinaryOpUGen',8), ('ring4','BinaryOpUGen',33), ('min','BinaryOpUGen',12)]
        if args.all_operator_benchmarks:banks += [(f'Binary_{op}','BinaryOpUGen',op) for op in sorted(BINARY_EXPRESSIONS)]
        for name, kind, selector in banks:
            path = BUILD/f'bank-{name}.scsyndef'
            path.write_bytes(fixture(kind, selector=selector, bank=True))
            trials = [json.loads(run([native, '--benchmark', path])) for _ in range(3 if name.startswith('Binary_') else 5)]
            timings[name] = {'trials': trials, 'median_reference_seconds': statistics.median(t['reference_seconds'] for t in trials),
                             'median_candidate_seconds': statistics.median(t['candidate_seconds'] for t in trials)}
        report['native_throughput'] = {'scope': 'Desktop-only bank throughput; not ESP32 speed estimates.', 'fixtures': timings}
    report['xtensa'] = xtensa(reference, target)
    output = args.output
    output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'passed':report['passed'],'graphs':report['graph_count'],
                      'samples':report['samples'],'inventory':report.get('inventory'),
                      'independent_variants':report.get('independent_variants'),
                      'hardware':False,'production_enabled':False,'report':str(output.relative_to(ROOT))}, indent=2))


if __name__ == '__main__':
    main()
