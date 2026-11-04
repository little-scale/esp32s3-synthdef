#!/usr/bin/env python3
"""Collect the muted, audio-owner per-node profiler; Studio must release USB first."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import time
from patches import Device

def collect(device,timeout=30,fixed=False):
    before=device.request('STATUS')
    device.link.write(b'J' if fixed else b'j')
    lines=[];until=time.monotonic()+timeout
    while time.monotonic()<until:
        for raw in device.lines():
            line=raw.rstrip(b'\r').decode(errors='replace')
            if line.startswith('UGEN_'):lines.append(line)
            if line=='UGEN_END':
                header=dict(re.findall(r'(\w+)=([^ ]+)',lines[0]))
                assert header['matched']=='1' and header['ready']=='2',lines
                setups=[dict(re.findall(r'(\w+)=([^ ]+)',line)) for line in lines if line.startswith('UGEN_SETUP ')]
                assert len(setups)<=1,'Duplicate profiler setup'
                setup=setups[0] if setups else None
                if fixed:
                    assert setup and setup['mode']=='fixed' and setup['seed']=='12345','Fixed-seed profiler required'
                    assert setup['warm_blocks']=='128' and setup['frames']=='64' and setup['rate']=='44100' and setup['cpu_mhz']=='240',setup
                    assert all(re.fullmatch('[0-9a-f]{64}',setup[k]) for k in ('warm_sha256','audio_sha256')),setup
                    assert re.fullmatch('[0-9a-f]{8}:[0-9a-f]{8}:[0-9a-f]{8}',setup['rng']),setup
                    assert all(int(setup[k])>0 for k in ('normal_wall_us','measured_wall_us')),setup
                nodes=[];group=defaultdict(int)
                for line in (line for line in lines if line.startswith('UGEN_NODE ')):
                    node=dict(re.findall(r'(\w+)=([^ ]+)',line))
                    node={k:v if k=='type' else int(v) for k,v in node.items()};nodes.append(node)
                    group[node['type']]+=node['cycles']
                assert [node['index'] for node in nodes]==list(range(len(nodes))),'Missing/duplicate/reordered nodes'
                if setup:assert len(nodes)==int(setup['nodes']),'Incomplete profiler nodes'
                assert nodes and all(node['calls']==int(header['blocks']) for node in nodes),'Incomplete profiler calls'
                total=sum(group.values());blocks=int(header['blocks'])
                return {'status':before,'header':header,'setup':setup,'nodes':nodes,'node_cycle_total':total,
                        'by_type':[{'type':name,'cycles':cycles,'share_percent':100*cycles/total,
                                    'average_us_per_block_at_240mhz':cycles/blocks/240}
                                   for name,cycles in sorted(group.items(),key=lambda x:-x[1])],
                        'normal_average_us_at_240mhz':int(header['normal_cycles'])/blocks/240,
                        'notes':'Per-node shares include probe overhead in a separate renderer. Normal DSP has no timing probes. Audio, voice-state and delay-memory digests match the normal renderer.',
                        'lines':lines}
    raise TimeoutError('No UGEN_END; this firmware must include the per-UGen diagnostic.')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',required=True)
    p.add_argument('--slot',type=int);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.with_suffix('.log').open('wb') as log:
        d=Device(a.port,log)
        try:
            hello=d.hello()
            if a.slot is not None:d.request('LOAD',bytes([a.slot]))
            result=collect(d);result['hello']=hello
            a.output.write_text(json.dumps(result,indent=2)+'\n')
            print(json.dumps({'normal_average_us':result['normal_average_us_at_240mhz'],'by_type':result['by_type'][:8]},indent=2))
        finally:d.close()
if __name__=='__main__':main()
