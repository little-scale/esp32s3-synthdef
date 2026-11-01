#!/usr/bin/env python3
"""Run the 30-second on-board control/retrigger/UI exercise, then restore slot 1."""
import argparse
import json
from pathlib import Path
import re
import struct
import time
from patches import Device, ROOT

OUTPUT_COUNTERS=('write_fail','partial','dma_event_overflow','faults','clips','nonfinite','overflow')
def output_counter_delta(text,previous=''):
    def values(source,key):return list(map(int,re.findall(r'\b'+key+r'=(\d+)',source)))
    baseline={key:(values(previous,key) or [0])[-1] for key in OUTPUT_COUNTERS}
    delta={key:max(values(text,key) or [0])-baseline[key] for key in OUTPUT_COUNTERS}
    return baseline,delta

def collect_exercise(d,log_path,hello,active,rounds,offset=0):
    for round_number in range(rounds):
        d.request('PANIC');d.link.write(b't')
        until=time.monotonic()+32
        while time.monotonic()<until:list(d.lines())
        d.link.write(b'x');d.request('PANIC')
        print(f'Completed exercise round {round_number+1}/{rounds}',flush=True)
    until=time.monotonic()+1.2
    while time.monotonic()<until:list(d.lines())
    status=d.request('STATUS')
    raw=log_path.read_bytes();text=raw[offset:].decode(errors='replace')
    baseline,output_delta=output_counter_delta(text,raw[:offset].decode(errors='replace'))
    assert 'EXERCISE_BEGIN' in text and 'active=1' in text
    assert re.findall(r'active=(\d+)',text)[-1]=='0'
    keys=['render_max_us','prep_max_us','combined_max_us','budget70_exceeded','write_fail','partial',
          'dma_event_overflow','faults','clips','nonfinite','overflow','coalesced']
    maximum={key:max(map(int,re.findall(r'\b'+key+r'=(\d+)',text))) for key in keys}
    cumulative_maximum=dict(maximum)
    epochs=set(map(int,re.findall(r'EXERCISE_BEGIN epoch=(\d+)',text)))
    windows=[dict(re.findall(r'(\w+)=([\d.]+)',line)) for line in text.splitlines() if 'PROFILE epoch=' in line]
    windows=[w for w in windows if int(w['epoch']) in epochs]
    assert len(epochs)==rounds and {int(w['epoch']) for w in windows}==epochs
    for key in ['render_max_us','prep_max_us','combined_max_us','budget70_exceeded']:
        maximum[key]=max(int(w[key]) for w in windows)
    minimum={key:min(map(int,re.findall(r'\b'+key+r'=(\d+)',text))) for key in ['internal_min','internal_largest','stack_free_bytes']}
    fatal=bool(re.search('watchdog got triggered|Guru Meditation|Stack canary|assert failed',text,re.I))
    output_ok=not fatal and all(value==0 for value in output_delta.values())
    worst=max(windows,key=lambda w:int(w['combined_max_us']))
    report={'test':'30-second normal-UI control and note exercise','rounds':rounds,'hello':hello,'status':status,'active':active,
            'maximum':maximum,'minimum':minimum,'worst_phases':{k:worst[k] for k in ['reset','controls','prepare','dsp','pcm']},
            'cumulative_maximum':cumulative_maximum,'epochs':sorted(epochs),
            'output_counter_baseline':baseline,'output_counter_delta':output_delta,
            'max_combined_fraction_of_block':maximum['combined_max_us']/(64/44100*1e6),
            'reported_output_checks_passed':output_ok,'timing_budget_passed':maximum['budget70_exceeded']==0,
            'scope':'four synth controls and three master delay controls at 25 Hz; delay 20 ms to 5 s, feedback 0 to 0.8, wet 0 to 1; seven pitch positions, attack/release extremes, five note starts/second; no physical continuity claim'}
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--rounds',type=int,choices=range(1,11),default=1)
    parser.add_argument('--catalog-entry',help='Exercise one unsaved catalog entry, then restore Mac Sine')
    args=parser.parse_args()
    args.output.write_text(json.dumps({'reported_output_checks_passed':False,'timing_budget_passed':False,'status':'incomplete'})+'\n')
    with args.output.with_suffix('.log').open('wb') as log:
        d=Device(args.port,log);original_effect=None
        try:
            hello=d.hello()
            if hello.get('effects'):original_effect=d.request('FX')
            expected=re.search(r'#define BUILD_ID "(.*?)"',(ROOT/'firmware/main/generated.h').read_text())[1]
            assert hello['build']==expected
            active=d.install_catalog(args.catalog_entry,diagnostic=True) if args.catalog_entry else d.request('LOAD',b'\1')
            report=collect_exercise(d,args.output.with_suffix('.log'),hello,active,args.rounds)
            args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
            if not report['reported_output_checks_passed'] or not report['timing_budget_passed']:raise SystemExit(1)
        finally:
            try:
                d.link.write(b'x');d.request('PANIC')
                if original_effect:d.request('FX',struct.pack('<fff',original_effect['time'],original_effect['feedback'],original_effect['wet']))
                d.request('LOAD',b'\1')
            finally:d.link.write(b'!');d.close()

if __name__=="__main__":main()
