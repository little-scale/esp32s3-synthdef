#!/usr/bin/env python3
"""Silent Saw/Impulse oracle checks, native timings and offline Xtensa audit."""
import argparse
import hashlib
import json
import os
import re
import statistics
import subprocess

from engine_profile import ROOT, generate
from test_signal_reuse import graph

BUILD = ROOT/'build/host/dsp-oscillators'


def run(args, timeout=180):
    result = subprocess.run(list(map(str, args)), capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stdout+result.stderr)
    return result.stdout


def fixtures():
    paths = []
    c = lambda k: (-1, k)
    for kind in ('Saw', 'Impulse'):
        for rate in (1, 2):
            for frequency in ('literal', 'initial', 'dynamic', 'audio'):
                if frequency == 'audio' and (kind == 'Saw' or rate == 1):
                    continue
                for phase in ((0., -0., .25, 1., -.25, 1000.) if kind == 'Impulse' else (0.,)):
                    nodes = [('In', 1, [c(0)], 2, 0), ('In', 2, [c(0)], 2, 0)]
                    if frequency == 'initial':
                        nodes.append(('Rand', 0, [c(1), c(2)], 1, 0)); freq = (2, 0)
                    else:
                        freq = {'literal': c(1), 'dynamic': (0, 0), 'audio': (1, 0)}[frequency]
                    index = len(nodes)
                    nodes.append((kind, rate, [freq]+([c(3)] if kind == 'Impulse' else []), 1, 0))
                    output = (index, 0)
                    if rate == 1:
                        nodes.append(('K2A', 2, [output], 1, 0)); output = (len(nodes)-1, 0)
                    nodes.append(('Out', 2, [c(0), output, output], 0, 0))
                    # Keep an oscillator result live across an earlier consumer.
                    nodes += [('BinaryOpUGen', 2, [output, c(2)], 1, 2),
                              ('Out', 2, [c(0), (len(nodes), 0)], 0, 0)]
                    path = BUILD/f'{kind}_{"kr" if rate == 1 else "ar"}_{frequency}_{phase}.scsyndef'
                    path.write_bytes(graph(kind, nodes, constants=(0, 3, 5, phase)))
                    paths.append(path)
    return paths


def bank_fixture(kind):
    c = lambda k: (-1, k)
    nodes = []
    for k in range(12):
        i = len(nodes)
        nodes.append((kind, 2, [c(k+1)]+([c(0)] if kind == 'Impulse' else []), 1, 0))
        nodes.append(('Out', 2, [c(0), (i, 0), (i, 0)], 0, 0))
    path = BUILD/f'{kind}_bank12.scsyndef'
    path.write_bytes(graph(kind+'Bank', nodes, constants=(0, *[440*2**((61+k-69)/12) for k in range(12)])))
    return path


def executable(reference, target, sanitized, driver_defines=()):
    folder = BUILD/('sanitized' if sanitized else 'throughput'); folder.mkdir(exist_ok=True)
    text = (reference/'fm_render.c').read_text()+'\n'+(reference/'fm_delay.inc').read_text()
    names = sorted(set(re.findall(r'^(?:int|void|uint32_t) (fm_\w+)\(', text, re.M)))
    flags = ['cc', '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror', '-fno-fast-math', '-ffp-contract=off']
    if sanitized:
        flags += ['-fsanitize=undefined,bounds,float-cast-overflow', '-fno-sanitize-recover=all']
    objects = []
    for name, source, include, extra in (
        ('reference', reference/'fm_render.c', reference, [f'-D{x}=osc_ref_{x[3:]}' for x in names]),
        ('target', target/'fm_render.c', target, []),
        ('load', target/'fm_load.c', target, []),
        ('test', ROOT/'tests/oscillator_candidates_test.c', target, ['-D'+x for x in driver_defines]),
    ):
        obj = folder/(name+'.o')
        run([*flags, '-I'+str(include), *extra, '-c', source, '-o', obj]); objects.append(obj)
    binary = folder/'compare'; run([*flags, *objects, '-lm', '-o', binary])
    return binary


def xtensa(reference, target):
    from pathlib import Path
    roots = sorted((Path.home()/'.espressif/tools/xtensa-esp-elf').glob('*/xtensa-esp-elf/bin'))
    if not roots: return {'available': False}
    prefix = str(roots[-1]/'xtensa-esp32s3-elf-')
    flags = ['-std=gnu99', '-O2', '-mlongcalls', '-mtext-section-literals', '-ffunction-sections',
             '-fdata-sections', '-fno-jump-tables', '-fno-tree-switch-conversion', '-fno-fast-math', '-ffp-contract=off']
    report = {'available': True, 'hardware_timing': False, 'compiler': run([prefix+'gcc', '--version']).splitlines()[0], 'flags': flags}
    for name, folder in (('reference', reference), ('candidate', target)):
        obj = BUILD/(name+'-xtensa.o')
        run([prefix+'gcc', *flags, '-I'+str(folder), '-c', folder/'fm_render.c', '-o', obj])
        asm = run([prefix+'objdump', '-dr', obj]); (BUILD/(name+'-xtensa.asm')).write_text(asm)
        report[name] = {'size': run([prefix+'size', obj]).strip(), 'object_sha256': hashlib.sha256(obj.read_bytes()).hexdigest()}
        for function in ('candidate_saw', 'candidate_impulse') if name == 'candidate' else ('bandlimited', 'extensions'):
            section = re.search(r'Disassembly of section \.text\.'+function+r'(?:[.$][^:\n]*)?:\n(.*?)(?=\nDisassembly of section|\Z)', asm, re.S)
            assert section, function
            report[name][function] = {'float_division_relocations': section[1].count('__divsf3'),
                'double_arithmetic_relocations': len(re.findall(r'__(?:add|sub|mul|div)df3', section[1]))}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-supercollider', action='store_true', help='Also compile and time the supplied 12-voice LED/Splay patches silently')
    args = parser.parse_args()
    BUILD.mkdir(parents=True, exist_ok=True)
    reference = generate(BUILD/'reference/src', 'fm1', qualified_kernels=True)
    target = generate(BUILD/'target/src', 'fm1', qualified_kernels=True, candidate_saw=True, candidate_impulse=True)
    paths = fixtures()
    report = {'passed': False, 'hardware': False, 'device_access': False, 'production_enabled': False,
        'sample_rates': [8000, 44100, 48000, 192000], 'blocks_per_case': 2048, 'restarts_per_rate': 3,
        'comparison': 'Byte-identical audio, full scratch and voice state except Saw b1/total setup cache; RNG, flags, compensated phase and constructor behaviour retained.',
        'sanitizers': ['undefined', 'bounds', 'float-cast-overflow']}
    try:
        binary = executable(reference, target, True)
        report['edges'] = json.loads(run([binary, *paths])); print(json.dumps(report['edges']), flush=True)
        # Both switches are independently selectable and compose with broad input binding.
        for saw, impulse, binding in ((True, False, False), (False, True, False), (True, True, True)):
            variant = generate(BUILD/f'variant-{saw}-{impulse}-{binding}/src', 'fm1', qualified_kernels=True,
                               candidate_saw=saw, candidate_impulse=impulse, candidate_binding=binding)
            binary = executable(reference, variant, True)
            result = json.loads(run([binary, *paths])); assert result['passed']
            report.setdefault('switch_combinations', []).append({'saw': saw, 'impulse': impulse, 'binding': binding, **result})
            print('Combination', saw, impulse, binding, 'passed', flush=True)
        binary = executable(reference, target, False)
        report['native_benchmarks'] = {}
        workloads = [(kind, bank_fixture(kind)) for kind in ('Saw', 'Impulse')]
        if args.with_supercollider:
            from patches import compile_source
            for kind in ('Saw', 'SinOsc'):
                source = BUILD/(kind+'_user12.scd')
                source.write_text('{ arg rate=1, decay=0.5; var size=12, env, sig; env=Decay.kr(Dust.kr(rate!size),decay); Out.kr(3,env.collect { |e| [e,e*0.5,0] }.flat); sig=Splay.ar('+kind+'.ar((60+(1..size)).midicps)*env); }')
                path = source.with_suffix('.scsyndef')
                compile_source(source, path, '/Applications/SuperCollider.app/Contents/MacOS/sclang')
                workloads.append((kind+'_user12', path))
        for kind, path in workloads:
            runs = [json.loads(run([binary, '--benchmark', path])) for _ in range(3)]
            report['native_benchmarks'][kind] = {'runs': runs,
                'median_time_reduction_percent': statistics.median(100*(1-r['candidate_seconds']/r['reference_seconds']) for r in runs),
                'scope': 'Desktop full LED/Splay graph; not an ESP32 CPU prediction.' if kind.endswith('_user12') else 'Desktop 12-oscillator bank; not an ESP32 CPU prediction or the complete LED/Splay graph.'}
            print(kind, report['native_benchmarks'][kind]['median_time_reduction_percent'], flush=True)
        import test_dsp_candidates as inventory
        inventory.BUILD = BUILD
        broad = sorted((ROOT/'upstream/fm1-synthdef/synthdef-engine/fixtures').glob('*.scsyndef'))
        broad += sorted((ROOT/'examples').glob('*.scsyndef'))
        binary = inventory.executable(reference, target, True, inventory=True,
            defines=('DSP_STRICT_COMPARISON', 'DSP_OSCILLATORS_COMPARISON'))
        report['inventory'] = json.loads(inventory.run([binary, *broad],
            env={**os.environ, 'DSP_TEST_BLOCKS': '64', 'DSP_TEST_RATE': '48000'}))
        print('Inventory', report['inventory'], flush=True)
        report['xtensa'] = xtensa(reference, target)
        report['source_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (ROOT/'host/dsp_oscillators.py', ROOT/'tests/oscillator_candidates_test.c', ROOT/'host/test_dsp_oscillators.py')}
        report['graphs'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        report['passed'] = True
    finally:
        (ROOT/'evidence/dsp-oscillators-host-20261115.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: report[k] for k in ('passed', 'edges', 'native_benchmarks', 'xtensa')}, indent=2))


if __name__ == '__main__': main()
