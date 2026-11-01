#!/usr/bin/env python3
"""Independent SuperCollider NRT comparisons for the extended trace graphs."""
import array,json,math,os,struct,subprocess
from pathlib import Path
from long_trace import ROOT,WINDOWS,BLOCKS,BUILD
from synthdef_binary import decode,encode
SC=Path(os.environ.get('SCSYNTH','/Applications/SuperCollider.app/Contents/Resources/scsynth'))

def string(value):
    raw=value.encode()+b'\0';return raw+b'\0'*((-len(raw))%4)
def message(address,*args):
    tags=',';data=b''
    for value in args:
        if isinstance(value,str):tags+='s';data+=string(value)
        elif isinstance(value,bytes):tags+='b';data+=struct.pack('>I',len(value))+value+b'\0'*((-len(value))%4)
        elif isinstance(value,int):tags+='i';data+=struct.pack('>i',value)
        else:tags+='f';data+=struct.pack('>f',value)
    return string(address)+string(tags)+data
def score(job,path):
    raw=(ROOT/job['graph']).read_bytes();g=decode(raw)
    input_role=any(n=='In' for n,r,refs,rates,s in g['nodes'])
    if input_role:
        # Native input is immutable and separate from the output accumulator.
        # Isolate SC's output from the provider already on bus 0, as in the
        # existing persistent-delay oracle. DSP equations are unchanged.
        g['nodes']=[('ReplaceOut' if n=='Out' else n,r,refs,rates,s) for n,r,refs,rates,s in g['nodes']]
        raw=encode(g)
    events={0:[message('/g_new',1,0,0),message('/d_recv',raw)]}
    def at(block,msg):events.setdefault(block,[]).append(msg)
    if input_role:
        provider=dict(name='trace-input',constants=[0],controls=[.25],names=[('amp',0)],nodes=[
            ('Control',1,[],[1],0),('Impulse',2,[(-1,0),(-1,0)],[2],0),
            ('BinaryOpUGen',2,[(1,0),(0,0)],[2],2),('Out',2,[(-1,0),(2,0),(2,0)],[],0)])
        at(0,message('/d_recv',encode(provider)));at(0,message('/s_new','trace-input',1001,0,1))
        at(1722,message('/s_new','trace-input',1002,0,1,'amp',.125))
    at(0,message('/s_new',g['name'],1000,1,1))
    if g['name'].startswith('rate-probe-'):
        for block in (4,8,16,64,344):
            value=.5 if block==8 else .25 if block in (16,344) else .75
            # n_set updates control-rate values for a whole block. Place the
            # timestamp inside that block so OSC fixed-point rounding cannot
            # accidentally deliver it one block early at an exact boundary.
            at(block+.25,message('/n_set',1000,'probe_live',value,'probe_initial',value))
        at(4096,message('/n_free',1000));at(4096,message('/s_new',g['name'],1000,1,1,'probe_initial',.75,'probe_live',.75))
    for when,value in job.get('events',[]):at(int(when*44100)//64+.25,message('/n_set',1000,'src_gate',float(value)))
    at(BLOCKS+.25,message('/g_freeAll',0));at(BLOCKS+1,message('/c_set',0,0))
    data=b''
    for block,messages in sorted(events.items()):
        packet=b'#bundle\0'+struct.pack('>Q',round(block*64/44100*2**32))
        packet+=b''.join(struct.pack('>I',len(m))+m for m in messages)
        data+=struct.pack('>I',len(packet))+packet
    path.write_bytes(data)

def read_wave(path):
    data=path.read_bytes();pos=12
    while pos+8<=len(data):
        tag,n=struct.unpack_from('<4sI',data,pos);pos+=8
        if tag==b'data':
            a=array.array('f');a.frombytes(data[pos:pos+n]);return a
        pos+=n+n%2
    raise RuntimeError('No WAV samples')

def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,default=ROOT/'evidence/long-trace-plan.json')
    p.add_argument('--output',type=Path,default=ROOT/'evidence/long-trace-sc.json');args=p.parse_args()
    plan=json.loads(args.plan.read_text());results=[]
    folder=BUILD/'sc';folder.mkdir(exist_ok=True)
    plugin=ROOT/'build/host/fm1-parity/reference-engine/build/reverb-plugins'
    assert all((plugin/(n+'.scx')).exists() for n in ('MiVerb','MiMu','FM1RingsReference'))
    version=subprocess.check_output([str(SC),'-v'],text=True).strip();assert '3.14.1' in version
    for index,job in enumerate(plan['jobs']):
        name=job['id'];osc=folder/(name+'.osc');wav=folder/(name+'.wav');score(job,osc)
        run=subprocess.run([str(SC),'-U',str(SC.parent/'plugins')+os.pathsep+str(plugin),'-N',str(osc),'_',str(wav),'44100','WAV','float','-o','2','-i','0','-z','64'],capture_output=True,text=True,timeout=60)
        if run.returncode or 'FAILURE' in run.stdout or 'ERROR' in run.stdout+run.stderr:
            result=dict(id=name,passed=False,error=run.stdout+run.stderr,returncode=run.returncode)
        else:
            full=read_wave(wav);assert len(full)>=BLOCKS*128
            ref=array.array('f');ref.frombytes((ROOT/job['samples']).read_bytes())
            actual=array.array('f')
            for block in WINDOWS:actual.extend(full[block*128:(block+1)*128])
            peak=max(abs(a-b) for a,b in zip(actual,ref));rms=math.sqrt(sum((a-b)**2 for a,b in zip(actual,ref))/len(ref))
            finite=all(math.isfinite(x) for x in actual)
            # Preserve the saturation envelope already declared by the pinned
            # reference suite; quantized MiVerb feedback amplifies input ULPs.
            peak_limit,rms_limit=(.0002,.00002) if name=='m7_MiVerb_saturation' else (.0001,.00003)
            strict=finite and peak<=peak_limit and rms<=rms_limit
            # Keep divergent chaotic trajectories explicit. These are not
            # converted into waveform passes or silent tolerance changes.
            chaotic=any(n.startswith(('Gendy','Henon','Cusp','Latoocarfian','Lorenz','FBSine','Standard','Crackle')) or n=='SinOscFB' for n,r in job['type_rates'])
            full_rms=math.sqrt(sum(x*x for x in full[:BLOCKS*128])/(BLOCKS*128));ratio=full_rms/job['host']['rms'] if job['host']['rms'] else 1 if not full_rms else math.inf
            result=dict(id=name,passed=strict,comparison='waveform' if strict else 'chaotic-divergence' if chaotic and finite else 'failed',peak_error=peak,rms_error=rms,peak_limit=peak_limit,rms_limit=rms_limit,rms_ratio=ratio,finite=finite)
        results.append(result)
        if not index%10 or not result['passed']:print(f'{index+1}/{len(plan["jobs"])} {name}: {result.get("comparison", "reference-error")}',flush=True)
        report={'passed':all(r['passed'] for r in results),'status':'complete' if len(results)==len(plan['jobs']) else 'incomplete','reference':version,'blocks':BLOCKS,'results':results,
            'scope':'Independent SC NRT sparse waveform comparison over 11.89 s, with full-duration RMS; chaotic divergence remains separate from a waveform pass'}
        args.output.write_text(json.dumps(report,indent=2)+'\n')
    return report['passed']

if __name__=='__main__':raise SystemExit(0 if main() else 1)
