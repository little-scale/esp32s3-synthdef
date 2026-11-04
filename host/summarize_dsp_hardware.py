#!/usr/bin/env python3
"""Summarize recorded XIAO results without contacting hardware."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def read(name):return json.loads((ROOT/'evidence'/name).read_text())


def main():
    pack=read('dsp-qa-pack.json');plan=json.loads((ROOT/'docs/dsp_hardware_plan.json').read_text())
    names=list(pack['fixtures'])
    for name,sha in pack['fixtures'].items():assert plan['fixtures'][name]['sha256']==sha
    coverage={tuple(t) for name in names for t in plan['fixtures'][name]['coverage']}
    replay={key:read('dsp-qa-xiao-'+key+'.json') for key in ('baseline','all','selected')}
    for key,r in replay.items():
        assert r['passed'] and r['device_id']=='esp32-288485ba1e48'
        assert r['header']['pack']==pack['pack_sha256']
        assert [int(row['index']) for row in r['cases']]==list(range(50))
        if key!='baseline':assert r['comparison']['passed'] and not r['comparison']['mismatches']
    timing={key:read('dsp-qa-xiao-'+key+'-timing.json') for key in ('baseline','all','selected')}
    workloads={}
    for name,before in timing['baseline']['fixtures'].items():
        values={}
        for key,r in timing.items():
            assert r['passed'] and r['restoration']['instances_restored']
            row=r['fixtures'][name];assert row['graph_sha256']==before['graph_sha256']
            trials=[run['normal_average_us_at_240mhz'] for run in row['runs']]
            values[key]=dict(median_us=row['median_us'],trials_us=trials,
                less_time_percent=(1-row['median_us']/before['median_us'])*100)
        workloads[name]=dict(graph_sha256=before['graph_sha256'],measurements=values)
    listening=read('dsp-qa-xiao-listening.json');final=read('dsp-qa-xiao-final-smoke.json')
    installed=read('dsp-qa-xiao-restored-build.json')
    assert listening['passed'] and listening['listening']['user_confirmed']
    assert final['passed'] and final['build']==installed['build_id']
    assert final['restoration']['main_package_verified'] and final['restoration']['instances_restored']
    assert not any(installed['engine_profile']['candidate_kernels'].values())
    report=dict(passed=True,date='2026-11-04',hardware=True,device_id=final['device_id'],board='XIAO ESP32-S3 / PCM5102A',
        rate=44100,block_frames=64,configured_cpu_mhz=240,external_clock_measurement=False,
        backup=dict(private_full_flash=True,bytes=8388608,private_package_settings_backup=True),
        replay=dict(record='evidence/dsp-qa-pack.json',cases=50,rendered_samples_per_variant=950272,
            candidate_comparison_samples=1900544,method='SHA-256 of serialized float output, normalized voice state, raw scratch and allocated arena, including constructors',
            variants=['baseline','all','selected'],all_candidates_matched=True,selected_matched=True,
            expected_fault_case='edges/Binary_signed_zero_3_1',expected_fault_blocks=32,
            native_types=sorted({t[1] for t in coverage if t[0]=='type'}),
            binary_selectors=sorted({int(t[1]) for t in coverage if t[0]=='BinaryOpUGen'}),
            unary_selectors=[],scope='Selected cases only; not every supported rate, input layout, UGen or selector.'),
        timing=dict(workloads=workloads,trials=3,blocks_per_trial=1024,warm_blocks=128,
            scope='Uninstrumented renderer cycles converted at configured 240 MHz. Per-node probes are separate and checked against the normal renderer.',
            limitation='Live voice snapshots are deterministic within each normal/probed pair, but stochastic starting states are not fixed across firmware variants. Small timing differences need fixed-seed A/B confirmation.'),
        selected_binding_entry_points=['delay_render','render_miverb'],
        listening=listening['listening'],listening_record='evidence/dsp-qa-xiao-listening.json',
        final_installed=dict(record='evidence/dsp-qa-xiao-restored-build.json',build=final['build'],app_bytes=installed['app_bytes'],
            experimental_flags_enabled=False,large_replay_pack_enabled=False,smoke_record='evidence/dsp-qa-xiao-final-smoke.json',
            original_main_fx_verified=True,volume=.25,fx_bypassed=True),
        decision='No production promotion. Mixed target timing results retained; standard headless firmware installed and original saved setup restored.',
        not_run=['AMOLED hardware qualification','all 154 UGens and 73 operators on current target','full 324-graph coverage sweep','10-minute soak','long-run memory and stack headroom','externally scheduled SC pattern','dedicated Main replacement fade capture','fixed-seed performance A/B','multi-module Wi-Fi tests'],
        startup_notes=['Initial application HELLO checks timed out; ROM loader identified the exact MAC and full flash was backed up before writing.',
            'An interrupted slow backup was replaced by a complete 921600-baud backup.',
            'The replay result buffer was moved from static internal RAM to on-demand PSRAM before the qualified baseline/candidate runs.',
            'Paused-audio telemetry warnings during the parked replay are maintenance observations, not realtime dropout measurements.'])
    (ROOT/'evidence/dsp-qa-xiao-summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS: three replay variants, mixed timings, listening confirmation and restored standard firmware; records consistent.')


if __name__=='__main__':main()
