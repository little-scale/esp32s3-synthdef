#!/usr/bin/env python3
"""Prepare guarded Rings regressions and six real-control voice traces."""
import hashlib,json,struct,subprocess
from pathlib import Path
from long_trace import ROOT,WINDOWS,BLOCKS,compile_renderer,wrap_fixture
from synthdef_binary import decode,encode

exe=compile_renderer();jobs=[];build=ROOT/'build/host/rings-voices'
assert all((build/f'rings-{model}.scsyndef').exists() for model in range(1,7)),'Run host/export_rings.py first'
for original in sorted((ROOT/'upstream/fm1-synthdef/synthdef-engine/fixtures').glob('m13_MiRings*.scsyndef')):
    if not original.stem.endswith(('_live','_forced','_bypass')):continue
    raw,events=wrap_fixture(original);g=decode(raw)
    path=build/original.name;path.write_bytes(raw);samples=path.with_suffix('.f32')
    run=subprocess.run([str(exe),str(path),str(samples)],check=True,capture_output=True,text=True)
    summary=json.loads(run.stdout);assert summary['passed'] and not summary['rejected']
    jobs.append(dict(id=original.stem,graph=str(path.relative_to(ROOT)),samples=str(samples.relative_to(ROOT)),
        graph_sha256=hashlib.sha256(raw).hexdigest(),type_rates=sorted({(n,r) for n,r,refs,rates,s in g['nodes']}),
        host=summary,source=str(original.relative_to(ROOT)),events=events))
for model in range(1,7):
    original=build/f'rings-{model}.scsyndef'
    g=decode(original.read_bytes())
    # Keep the real seven-control interface; alias gate for the existing trace
    # event protocol and release after ten seconds to check the final silence.
    g['names'].append(('src_gate',2))
    index=len(g['controls']);g['controls'].append(0)
    g['names'].append(('trace_ev_007540',index))
    g['nodes'].append(('Control',0,[],[0],index))
    g['name']=f'rings-{model}-long-release'
    path=build/f'rings-{model}-trace.scsyndef';raw=encode(g);path.write_bytes(raw)
    samples=path.with_suffix('.f32')
    run=subprocess.run([str(exe),str(path),str(samples)],check=True,capture_output=True,text=True)
    summary=json.loads(run.stdout);assert summary['passed'] and summary['updates']==1 and not summary['rejected']
    assert not any(struct.unpack('<128f',samples.read_bytes()[-512:])),'Release must finish in silence'
    jobs.append(dict(id=g['name'],graph=str(path.relative_to(ROOT)),samples=str(samples.relative_to(ROOT)),
        graph_sha256=hashlib.sha256(raw).hexdigest(),type_rates=sorted({(n,r) for n,r,refs,rates,s in g['nodes']}),
        host=summary,source=str(original.relative_to(ROOT)),events=[(7540*64/44100,0)],final_window_exactly_silent=True))
identity=ROOT/'evidence/rings-clear-identity.json'
if identity.exists():
    previous={row['id']:row['baseline_sha256'] for row in json.loads(identity.read_text())['results']}
    for job in jobs:
        if job['id'] in previous:
            actual=hashlib.sha256((ROOT/job['samples']).read_bytes()).hexdigest()
            assert actual==previous[job['id']],job['id']+' changed from the pre-optimization waveform'
            job['byte_identical_to_preoptimization_capture']=True
expected=sorted({tuple(pair) for job in jobs for pair in job['type_rates']})
assert len(jobs)==24
report=dict(passed=True,blocks=BLOCKS,seconds_per_graph=BLOCKS*64/44100,windows=WINDOWS,
    expected_type_rates=expected,jobs=jobs,
    scope='Six original live models, twelve forced/bypass fixtures, six playable voices with release. Native traces use guarded PSRAM-equivalent arenas; normal playback tests internal arena selection separately.')
(ROOT/'evidence/rings-regression-plan.json').write_text(json.dumps(report,indent=2)+'\n')
print(f'Prepared {len(jobs)} guarded Rings traces')
