#!/usr/bin/env python3
"""Muted full-arena comparison, plus explicitly requested short playback/cancellation."""
import argparse,json,re,struct,time
from pathlib import Path
from engine_profile import generate
from patches import ROOT,Device
from synthdef_binary import decode,encode
import profile_timing as matrix

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',required=True)
p.add_argument('--output',type=Path,required=True);p.add_argument('--playback',action='store_true');args=p.parse_args()
report={'passed':False,'status':'incomplete','playback_authorized':args.playback,'arena_bytes':1048576}
def save():args.output.write_text(json.dumps(report,indent=2)+'\n')
save();build=ROOT/'build/host/device-fm1-memory';build.mkdir(parents=True,exist_ok=True)
matrix.ENGINE=generate(build/'src','fm1').parent;renderer=matrix.compile_renderer()
g=decode((ROOT/'examples/touch-sine.scsyndef').read_bytes());g['name']='full-arena-diagnostic'
def constant(value):
    if value not in g['constants']:g['constants'].append(value)
    return (-1,g['constants'].index(value))
out=g['nodes'].pop();assert out[0]=='Out';source=out[2][1];index=len(g['nodes'])
# A 5-second maximum reserves the full arena. A short effective delay makes
# all three captured blocks nontrivial, instead of comparing only silence.
g['nodes'].append(('CombL',2,[source,constant(5),constant(.0005),constant(.001)],[2],0))
g['nodes'].append(('Out',2,[out[2][0],(index,0),(index,0)],[],0))
raw=encode(g);path=build/'full-arena.scsyndef';path.write_bytes(raw);report['diagnostic_graph_hex']=raw.hex()
with args.output.with_suffix('.log').open('wb') as log:
    d=Device(args.port,log);effect=None;slot=1;before=None
    def wait(seconds):
        until=time.monotonic()+seconds
        while time.monotonic()<until:list(d.lines())
    def text(offset):return args.output.with_suffix('.log').read_bytes()[offset:].decode(errors='replace')
    try:
        hello=d.hello();report['hello']=hello;assert hello['policy']=='fm1-compat-v1'
        assert hello['build']==re.search(r'#define BUILD_ID "(.*?)"',(ROOT/'firmware/main/generated.h').read_text())[1]
        d.request('PANIC');slot=d.request('STATUS')['slot'];before=d.request('LIST');effect=d.request('FX')
        active=d.upload(raw,b'// Temporary full-arena diagnostic derived from touch-sine.\n','Full-arena diagnostic')
        report['matrix']=matrix.collect_matrix(d,active,path,'full-arena',renderer);save()
        print('PASS: full 1 MiB synth arena, muted 280-case matrix',flush=True)
        if args.playback:
            d.request('FX',struct.pack('<fff',effect['time'],effect['feedback'],0));d.link.write(b'['*6)
            d.request('PANIC');wait(.5);offset=log.tell()
            d.link.write(b'n');wait(.06);d.link.write(b'o');wait(1.5)
            cancelled=text(offset);peaks=list(map(int,re.findall(r'\bpcm_peak=(\d+)',cancelled)))
            active_flags=list(map(int,re.findall(r'\bactive=(\d+)',cancelled)))
            assert peaks and max(peaks)==0 and active_flags and active_flags[-1]==0
            report['cancel_before_construction']={'passed':True,'requested_release_delay_seconds':.06,'pcm_peaks':peaks}
            print('PASS: early release cancels pending construction without output',flush=True)
            offset=log.tell();d.link.write(b'n');wait(1.8);d.link.write(b'o');wait(1.8)
            played=text(offset);peaks=list(map(int,re.findall(r'\bpcm_peak=(\d+)',played)))
            active_flags=list(map(int,re.findall(r'\bactive=(\d+)',played)))
            assert peaks and max(peaks)>0 and peaks[-1]==0 and active_flags[-1]==0
            failures={key:max(map(int,re.findall(r'\b'+key+r'=(\d+)',played))) for key in ['write_fail','partial','dma_event_overflow','faults','clips','nonfinite','overflow']}
            assert not any(failures.values()),failures
            report['incremental_start_and_release']={'passed':True,'max_pcm_peak':max(peaks),'last_pcm_peak':peaks[-1],'last_active':active_flags[-1],'fault_counters':failures,
                'scope':'Normal DMA path with incremental clearing; startup latency inferred from code, not measured externally'}
            print('PASS: incremental construction plays, releases and remains fault-free',flush=True)
        report['status']='complete';report['passed']=True
    except Exception as error:report['error']=repr(error);raise
    finally:
        try:
            d.request('PANIC')
            if effect:d.request('FX',struct.pack('<fff',*[effect[k] for k in ('time','feedback','wet')]))
            d.request('LOAD',bytes([slot if slot>=0 else 1]));report['final_status']=d.request('STATUS')
            if before is not None:
                report['library_unchanged']=d.request('LIST')==before
                if not report['library_unchanged']:report['passed']=False
        finally:d.link.write(b'!');d.close();save()
print(json.dumps({k:report[k] for k in ('passed','status','library_unchanged')},indent=2))
