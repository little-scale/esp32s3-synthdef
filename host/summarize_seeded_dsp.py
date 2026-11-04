#!/usr/bin/env python3
"""Audit recorded deterministic DSP comparisons; never opens hardware."""
import hashlib
import json
from pathlib import Path
import statistics
from qualify_seeded_dsp import compare
from patches import ROOT

SUITES={
 'baseline':'musical','baseline-repeat':'musical','binary':'musical',
 'binding':'musical','all':'musical','binding-full':'musical',
 'smooth-baseline':'smooth','core-baseline':'core','delay-baseline':'delay',
 'core':'core','core-musical':'musical','smooth':'smooth',
 'smooth-musical':'musical','binding-delay':'delay',
}


def main():
    metadata=json.loads((ROOT/'evidence/dsp-seeded-targeted-plan.json').read_text())['suites']
    records={};types=set();binary=set();unary=set();normal_floats=0;trials=0;clock=[]
    hashes={}
    for name,suite in SUITES.items():
        path=ROOT/('evidence/dsp-seeded-xiao-'+name+'.json');data=json.loads(path.read_text())
        assert data['passed'] and data['hardware'] and data['fixed_seed']
        assert data['device_id']=='esp32-288485ba1e48' and data['runs']==3
        assert data['restoration']['main_package_verified'] and data['restoration']['instances_restored']
        assert data['fixtures'].keys()==metadata[suite].keys()
        for fixture,row in data['fixtures'].items():
            meta=metadata[suite][fixture];assert row['graph_sha256']==meta['graph_sha256']
            assert len(row['runs'])==3 and row['nodes']==meta['nodes']
            assert row['median_us']==statistics.median(r['normal_average_us_at_240mhz'] for r in row['runs'])
            for run in row['runs']:
                h=run['header'];s=run['setup'];assert h['matched']=='1' and h['ready']=='2'
                assert s['mode']=='fixed' and s['seed']=='12345' and s['rate']=='44100' and s['frames']=='64' and s['cpu_mhz']=='240'
                ratio=int(h['normal_cycles'])/int(s['normal_wall_us']);assert 200<ratio<245
                clock.append(ratio);trials+=1;normal_floats+=int(h['blocks'])*64*2
                observed={r['type'] for r in run['by_type']};assert observed==set(meta['types'])
                types.update(observed)
            binary.update(meta['binary_selectors']);unary.update(meta['unary_selectors'])
        if data.get('comparison'):
            c=data['comparison'];assert c['passed']
            ref=json.loads((ROOT/c['reference']).read_text())
            assert compare(ref,data)==c['fixtures']
        else:assert compare(data,data)
        records[name]={'file':str(path.relative_to(ROOT)),
                       'comparison':data.get('comparison',{}).get('fixtures',{})}
        hashes[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    restored=json.loads((ROOT/'evidence/dsp-seeded-xiao-restoration.json').read_text())
    audio=json.loads((ROOT/'evidence/dsp-seeded-xiao-final-audio.json').read_text())
    assert restored['passed'] and restored['main_package_verified'] and restored['fx_package_verified'] and restored['instances_restored']
    assert restored['saved_volume_percent']==15 and audio['passed'] and audio['volume_percent']==15 and audio['fx_bypassed'] and audio['main_active']
    assert audio['original_controls_verified'] and audio['continuous']==audio['expected_continuous']
    assert all(v==0 for v in audio['settled_20s_counter_deltas'].values())
    settled=audio['settled_20s_samples'];assert settled[-1]['frame']-settled[0]['frame']>=18*44100
    defaults=json.loads((ROOT/'evidence/dsp-seeded-xiao-default-build.json').read_text())
    assert not any(defaults['engine_profile']['candidate_kernels'].values())
    assert audio['build']==defaults['build_id']
    report=dict(passed=True,date='2026-11-04',hardware=True,device_id=audio['device_id'],
        graph_count=sum(len(v) for v in metadata.values()),timing_records=len(records),
        normal_instrumented_pairs=trials,normal_output_floats=normal_floats,
        paired_output_floats=normal_floats*2,normal_warmup_floats=trials*128*64*2,
        rate=44100,block_frames=64,seed=12345,cpu_mhz_sdk=240,
        cycle_wall_mhz_range=[min(clock),max(clock)],external_clock_measurement=False,
        native_types=sorted(types),binary_selectors=sorted(binary),unary_selectors=sorted(unary),
        records=records,restoration=restored,final_audio=audio,
        production_candidates_promoted=False,record_sha256=hashes,
        scope='Selected XIAO layouts only. Each normal/instrumented pair checks audio, voice, scratch and arena. Cross-image comparisons check warm/measured audio SHA-256 and RNG, not normalized whole-voice state. Timing is normal DSP, not the full audio-task CPU meter; no isolated universal UGen speedup is claimed.')
    path=ROOT/'evidence/dsp-seeded-xiao-summary.json';path.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('passed','graph_count','timing_records','normal_instrumented_pairs','paired_output_floats','cycle_wall_mhz_range')},indent=2))


if __name__=='__main__':main()
