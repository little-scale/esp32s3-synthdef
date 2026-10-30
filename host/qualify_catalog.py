#!/usr/bin/env python3
"""Combine recorded reference, ESP32 numerical and normal-UI timing checks.

Run after all three candidates have matrix/exercise reports. --promote changes
the local catalog only; it neither flashes firmware nor writes device storage.
"""
import argparse
import hashlib
import json
from prepare import ROOT,qualification_fingerprint
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--promote',action='store_true');args=p.parse_args()
read=lambda name:json.loads((ROOT/'evidence'/name).read_text())
build=read('qualified-candidate-build.json');reference=read('qualified-host-reference.json')
catalog_path=ROOT/'examples/catalog.json';catalog=json.loads(catalog_path.read_text());reports=[]
for entry in catalog:
    name=entry['id'];graph_hash=hashlib.sha256((ROOT/f'examples/{name}.scsyndef').read_bytes()).hexdigest()
    matrix=read(name+'-matrix.json');exercise=read(name+'-exercise.json')
    assert matrix.get('checks_passed') and 'maximum' in exercise,'Incomplete checks: '+name
    numerical=matrix['reports'][0];ref=next(r for r in reference['reports'] if r['patch']==name)
    assert matrix['hello']['build']==exercise['hello']['build']==build['build_id']
    assert numerical['active']['graph_sha256']==exercise['status']['graph_sha256']==ref['graph_sha256']==graph_hash
    assert int(numerical['header']['cases'])==280 and exercise['rounds']>=3
    passed=bool(ref['passed'] and numerical['numerical']['passed'] and exercise['timing_budget_passed'] and exercise['reported_output_checks_passed'])
    reports.append({'patch':name,'graph_sha256':graph_hash,'passed':passed,'combined_max_us':exercise['maximum']['combined_max_us'],
                    'block_fraction':exercise['max_combined_fraction_of_block'],'max_pcm_step_error':numerical['numerical']['max_pcm_step_error'],
                    'reference':'qualified-host-reference.json','matrix':name+'-matrix.json','exercise':name+'-exercise.json'})
    if args.promote:entry['status']='qualified' if passed else 'rejected'
report={'firmware_fingerprint':qualification_fingerprint(),'measured_build':build['build_id'],
        'measured_configuration_sha256':build['sha256']['firmware/build-ui/sdkconfig'],
        'reports':reports,'sample_rate':44100,'block_frames':64,'voices':1,
        'listening':'pending user review of new sounds','extended_soak':'pending',
        'scope':'exact compiled graph hashes on the measured configuration; no general multi-oscillator/filter admission'}
(ROOT/'evidence/qualified-voices.json').write_text(json.dumps(report,indent=2)+'\n')
if args.promote:catalog_path.write_text(json.dumps(catalog,indent=2)+'\n')
print(json.dumps(report,indent=2))
