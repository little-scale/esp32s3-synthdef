#!/usr/bin/env python3
"""Summarize one bounded physical control run without claiming underrun coverage."""
import argparse
import json
from pathlib import Path
import re
ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('log', type=Path)
parser.add_argument('--output', default='realtime-summary.json')
parser.add_argument('--ui-redraw', action='store_true')
args = parser.parse_args()
text = args.log.read_text(errors='replace')
build_id = re.findall(r'build=([0-9a-f]{64})', text)[-1]
expected = re.search(r'#define BUILD_ID "(.*?)"', (ROOT/'firmware/main/generated.h').read_text())[1]
assert build_id == expected, 'Runtime evidence belongs to another source build'
keys = ['render_max_us','prep_max_us','combined_max_us','budget70_exceeded','write_fail',
        'partial','dma_event_overflow','faults','clips','nonfinite','queue_high','overflow',
        'pcm_peak_max','stack_free_bytes','internal_min','internal_largest','psram_free']
values = {key: [int(v) for v in re.findall(r'\b'+key+r'=(\d+)', text)] for key in keys}
assert all(values.values()), 'Incomplete runtime telemetry'
observations = [(int(f),int(a)) for f,a in re.findall(r'frame=(\d+) active=(\d+)', text)]
assert observations and any(a for _,a in observations), 'No active note observed'
assert observations[-1][1] == 0 and values['pcm_peak_max'][-1] > 0
fatal = re.findall(r'Guru Meditation|assert failed|Stack canary|Brownout detector|watchdog got triggered', text)
assert not fatal, fatal
maximum = {key:max(data) for key,data in values.items() if key not in
           ['stack_free_bytes','internal_min','internal_largest','psram_free']}
minimum = {key:min(values[key]) for key in ['stack_free_bytes','internal_min','internal_largest','psram_free']}
output_ok = all(maximum[key] == 0 for key in ['write_fail','partial','faults','clips','nonfinite'])
fraction = maximum['combined_max_us']/(64/44100*1e6)
report = {'test': 'short ESP32 control/playback run', 'build_id': build_id,
          'active_graph': (re.findall(r'Active graph=(\S+)',text) or ['legacy gated sine'])[-1],
          'source_log': str(args.log), 'last_logical_frame': observations[-1][0],
          'last_note_active': False, 'maximum': maximum, 'minimum': minimum,
          'block_us': 64/44100*1e6, 'max_combined_fraction_of_block': fraction,
          'reported_output_checks_passed': output_ok,
          'observed_70_percent_budget_passed': maximum['budget70_exceeded'] == 0,
          'ui_redraw_stress_requested': args.ui_redraw,
          'scope': ('short run with touch UI and requested 25 Hz redraw stress; no radio/storage'
                    if args.ui_redraw else 'short run, no UI/radio/storage') +
                   '; driver counters do not prove zero physical underruns',
          'release_soak_30_minutes': 'not run', 'external_recording_and_latency': 'pending'}
(ROOT/'evidence'/args.output).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
if not output_ok: raise SystemExit(1)
