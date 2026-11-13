#!/usr/bin/env python3
"""Silent exactness checks for narrow mixing candidates; no board access."""
import hashlib
import itertools
import json
import os
from pathlib import Path
import subprocess

from dsp_mix import prepare
from engine_profile import ROOT, generate
from test_signal_reuse import graph
import test_dsp_candidates as suite

BUILD = ROOT/'build/host/dsp-mix'


def fixtures():
    paths = []
    c = lambda k: (-1, k)
    for typ, size in (('Sum3', 3), ('Sum4', 4)):
        for rate in range(3):
            for rates in itertools.product(range(rate+1), repeat=size):
                nodes = [('In', 2, [c(0)], 2, 0), ('In', 1, [c(0)], 4, 0)]
                refs = [c(k+1) if r == 0 else (1 if r == 1 else 0, k % (4 if r == 1 else 2))
                        for k, r in enumerate(rates)]
                nodes.append((typ, rate, refs, 1, 0))
                output = (2, 0)
                if rate != 2:
                    nodes.append(('K2A', 2, [output], 1, 0)); output = (3, 0)
                nodes.append(('Out', 2, [c(0), output, output], 0, 0))
                path = BUILD/(typ+'_'+str(rate)+'_'+''.join(map(str, rates))+'.scsyndef')
                path.write_bytes(graph(typ, nodes, constants=(0, -0., .125, -.25, 1e-30)))
                paths.append(path)
        # Duplicate references and signed zeros reach the all-audio shortcut.
        # Follow with atan2 to make any zero-sign difference observable.
        for value in (0., -0., 1e-30, -1e-30, 1e12, -1e12, 3e38):
            nodes = [('DC', 2, [c(1)], 1, 0), (typ, 2, [(0, 0)]*size, 1, 0),
                     ('BinaryOpUGen', 2, [(1, 0), c(2)], 1, 22),
                     ('Out', 2, [c(0), (1, 0), (2, 0)], 0, 0)]
            path = BUILD/(typ+'_edge_'+str(len(paths))+'.scsyndef')
            path.write_bytes(graph(typ, nodes, constants=(0, value, -1)))
            paths.append(path)
    for rate in (1, 2):
        for rates in itertools.product(range(rate+1), repeat=3):
            if rates[2] == 2:
                continue  # The loader requires initial/control-rate level.
            nodes = [('In', 2, [c(0)], 2, 0), ('In', 1, [c(0)], 3, 0)]
            refs = [c(k+1) if r == 0 else (1 if r == 1 else 0, k % (3 if r == 1 else 2))
                    for k, r in enumerate(rates)]
            nodes.append(('Pan2', rate, refs, 2, 0))
            if rate == 1:
                nodes += [('K2A', 2, [(2, 0)], 1, 0), ('K2A', 2, [(2, 1)], 1, 0)]
                left, right = (3, 0), (4, 0)
            else:
                left, right = (2, 0), (2, 1)
            nodes.append(('Out', 2, [c(0), left, right], 0, 0))
            # Reuse both Pan outputs after the first consumer to exercise the
            # lifetimes of the two independently mapped output buffers.
            nodes += [('BinaryOpUGen', 2, [left, right], 1, 0),
                      ('Out', 2, [c(0), (len(nodes), 0)], 0, 0)]
            path = BUILD/('Pan2_'+str(rate)+'_'+''.join(map(str, rates))+'.scsyndef')
            path.write_bytes(graph('Pan2', nodes, constants=(0, .125, -.5, .75)))
            paths.append(path)
    return paths


def main():
    BUILD.mkdir(parents=True, exist_ok=True)
    suite.BUILD = BUILD
    reference = generate(BUILD/'reference/src', 'fm1', qualified_kernels=True)
    target = generate(BUILD/'target/src', 'fm1', qualified_kernels=True, candidate_mix=True)
    paths = fixtures()
    binary = suite.executable(reference, target, True, inventory=True,
                              defines=('DSP_STRICT_COMPARISON',))
    report = dict(passed=False, hardware=False, device_access=False, production_enabled=False,
        comparison='Byte-identical output, constructor/render scratch, Pan/Sum state, flags, RNG and arena. Arithmetic order unchanged.',
        sanitizers=['undefined', 'bounds', 'float-cast-overflow'],
        source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (
            ROOT/'host/dsp_mix.py', ROOT/'host/test_dsp_mix.py', ROOT/'tests/dsp_kernels_test.c')})
    try:
        report['four_rate_edges'] = json.loads(suite.run([binary, *paths],
            env={**os.environ, 'DSP_TEST_BLOCKS': '512'}))
        print('Four-rate edges:', len(paths), flush=True)
        broad = paths+sorted((ROOT/'upstream/fm1-synthdef/synthdef-engine/fixtures').glob('*.scsyndef'))
        broad += sorted((ROOT/'examples').glob('*.scsyndef'))
        report['inventory'] = json.loads(suite.run([binary, *broad],
            env={**os.environ, 'DSP_TEST_BLOCKS': '64', 'DSP_TEST_RATE': '44100'}))
        report['graphs'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in broad}
        report['passed'] = True
    finally:
        (ROOT/'evidence/dsp-mix-host-20261113.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: report[k] for k in ('passed', 'four_rate_edges', 'inventory')}, indent=2))


if __name__ == '__main__': main()
