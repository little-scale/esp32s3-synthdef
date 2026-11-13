#!/usr/bin/env python3
"""Silent TDelay edge/state tests against an oracle and actual scsynth NRT."""
import argparse
import array
import copy
import hashlib
import json
import struct
import subprocess
from pathlib import Path
from engine_profile import ROOT, generate
from synthdef_binary import encode, decode
from test_dynamic_banks import message, wave_data

BUILD = ROOT / 'build/host/tdelay'
SC = Path('/Applications/SuperCollider.app/Contents/Resources/scsynth')
SCLANG = Path('/Applications/SuperCollider.app/Contents/MacOS/sclang')
SR, BLOCK, BLOCKS = 44100, 64, 96

def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]

def graph(rate, duration_rate, constant=None, initial_trigger=False):
    constants = [0., constant if constant is not None else 0., 1.]
    nodes = [('In', 2, [(-1, 0)], [2, 2], 0)]
    trigger = (0, 0)
    if initial_trigger:
        nodes.append(('DC', rate, [(-1, 1)], [rate], 0))
        trigger = (len(nodes)-1, 0)
    elif rate == 1:
        nodes.append(('A2K', 1, [trigger], [1], 0))
        trigger = (len(nodes)-1, 0)
    duration = (0, 1)
    if duration_rate == 0:
        duration = (-1, 1)
    elif duration_rate == 1:
        nodes.append(('A2K', 1, [duration], [1], 0))
        duration = (len(nodes)-1, 0)
    nodes.append(('TDelay', rate, [trigger, duration], [rate], 0))
    result = (len(nodes)-1, 0)
    if rate == 1:
        # K2A interpolates changing controls. Select yields the raw kr pulse
        # held over its block, without conflating that with converter ramps.
        nodes.append(('DC',2,[(-1,0)],[2],0)); zero=(len(nodes)-1,0)
        nodes.append(('DC',2,[(-1,2)],[2],0)); one=(len(nodes)-1,0)
        nodes.append(('Select', 2, [result,zero,one], [2], 0))
        result = (len(nodes)-1, 0)
    nodes.append(('Out', 2, [(-1, 0), result, result], [], 0))
    return dict(name='TDelayTest', constants=constants, controls=[], names=[], nodes=nodes)

def oracle(inputs, rate, duration_rate, constant=None, initial_trigger=False):
    result = array.array('f', [0.]) * len(inputs)
    previous, pending = 0., 0
    for block in range(BLOCKS):
        duration = f32(constant) if duration_rate == 0 else inputs[block*BLOCK*2+1]
        for j in range(BLOCK if rate == 2 else 1):
            index = (block*BLOCK+j)*2
            trigger = f32(constant) if initial_trigger else inputs[index]
            pulse = 0.
            if pending > 1:
                pending -= 1
            elif pending == 1:
                pending, pulse = 0, 1.
            elif previous <= 0 < trigger:
                pending = max(1, int(duration*(SR if rate == 2 else SR/BLOCK)+.5))
            previous = trigger
            if rate == 2:
                result[index:index+2] = array.array('f', [pulse, pulse])
            else:
                result[index:index+BLOCK*2] = array.array('f', [pulse]) * (BLOCK*2)
    return result

def reference(g, inputs, stem):
    g = copy.deepcopy(g)
    # Target bus zero is the caller's input; SC hardware inputs follow outputs.
    g['constants'].append(2.)
    g['nodes'][0] = ('In', 2, [(-1, len(g['constants'])-1)], [2, 2], 0)
    raw = encode(g)
    infile = stem.with_suffix('.input.wav')
    payload = inputs.tobytes()
    infile.write_bytes(b'RIFF'+struct.pack('<I', 36+len(payload))+b'WAVEfmt '+
                      struct.pack('<IHHIIHH',16,3,2,SR,SR*8,8,32)+b'data'+
                      struct.pack('<I',len(payload))+payload)
    events = [(0, [message('/g_new',1,0,0), message('/d_recv',raw), message('/s_new',g['name'],1000,1,1)]),
              (BLOCKS+1, [message('/g_freeAll',0)]), (BLOCKS+2, [message('/c_set',0,0)])]
    score = stem.with_suffix('.osc')
    score.write_bytes(b''.join(struct.pack('>I',len(packet))+packet for block,msgs in events
        for packet in [b'#bundle\0'+struct.pack('>Q',round(block*BLOCK/SR*2**32))+
                       b''.join(struct.pack('>I',len(m))+m for m in msgs)]))
    output = stem.with_suffix('.wav')
    r = subprocess.run([str(SC),'-U',str(SC.parent/'plugins'),'-N',str(score),str(infile),str(output),
                        str(SR),'WAV','float','-o','2','-i','2','-z',str(BLOCK)],
                       capture_output=True,text=True,timeout=30)
    stem.with_suffix('.sc.log').write_text(r.stdout+r.stderr)
    assert r.returncode == 0 and 'ERROR' not in r.stdout+r.stderr, r.stdout+r.stderr
    values = array.array('f'); values.frombytes(wave_data(output))
    assert len(values) >= len(inputs)
    return values[:len(inputs)]

def cases():
    # Exact edge placements exercise held-high, pending/output-tick rejection,
    # non-unit/negative triggers, boundaries and rearming after expiry.
    for rate in (1,2):
        unit = 1 if rate == 2 else BLOCK
        ticks = [0,2,4,5,7,9,63,65,127,129,254,256,258,511,513]
        for delay in (0., -1., 1., 1.49999, 1.5, 1.50001, 5., 64., 65.):
            duration = f32(delay/(SR if rate == 2 else SR/BLOCK))
            inputs = array.array('f', [0.,duration]) * (BLOCKS*BLOCK)
            for i,tick in enumerate(ticks):
                if tick*unit >= BLOCKS*BLOCK: continue
                inputs[tick*unit*2] = [3.,.25,1.][i%3]
            # A high interval must produce only a single accepted edge.
            for tick in range(32,38): inputs[tick*unit*2] = 2.
            for tick in (15,16): inputs[tick*unit*2] = -1.
            yield f'{rate}_constant_{delay:g}', graph(rate,0,duration), inputs, rate,0,duration,False
        for duration_rate in (1,2):
            inputs = array.array('f', [0.,0.]) * (BLOCKS*BLOCK)
            for b in range(BLOCKS):
                # Dramatic changes while pending must not change the countdown.
                value = [5.,65.,2.,130.,0.,-2.][b%6]/(SR if rate == 2 else SR/BLOCK)
                for j in range(BLOCK):
                    inputs[(b*BLOCK+j)*2+1] = value if j==0 else .25
                for tick in ([0,2,5,7,61,63] if rate==2 else ([0] if b%2==0 else [])):
                    inputs[(b*BLOCK+tick)*2] = 1.
            yield f'{rate}_duration_rate_{duration_rate}', graph(rate,duration_rate), inputs,rate,duration_rate,None,False
        # Constructor must reset prevtrig/counter so high input on the very
        # first render is recognized. DC makes the ctor's input high as well.
        inputs = array.array('f',[0.,0.]) * (BLOCKS*BLOCK)
        duration=1./(SR if rate==2 else SR/BLOCK)
        yield f'{rate}_initial_high',graph(rate,0,duration,True),inputs,rate,0,duration,True

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'evidence/tdelay-host.json')
    args = parser.parse_args(); BUILD.mkdir(parents=True,exist_ok=True)
    report = dict(passed=False,hardware=False,audio_playback=False,sample_rate=SR,block_frames=BLOCK,
                  sc_reference=subprocess.check_output([str(SC),'-v'],text=True).strip(),
                  state_checks=['fm_start restart','constructor previous-trigger/countdown reset',
                                'independent voices','poisoned shared scratch','fault block silence'],
                  sanitizers=['undefined','bounds','float-cast-overflow'],cases=[],rejections=[])
    flags = ['-std=c99','-O2','-fno-fast-math','-ffp-contract=off',
             '-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all']
    fixtures = list(cases()); expected = {}
    for name,g,inputs,rate,dr,constant,initial in fixtures:
        target = oracle(inputs,rate,dr,constant,initial)
        sc = reference(g,inputs,BUILD/name)
        assert sc == target, f'SC/oracle disagreement: {name}, first mismatch '+str(next((i for i,(a,b) in enumerate(zip(sc,target)) if a!=b),None))
        expected[name] = target
    for mode,reuse,qualified in [('legacy',True,False),('qualified',True,True),('dedicated',False,False)]:
        engine = generate(BUILD/mode/'src','fm1',reuse_buffers=reuse,qualified_kernels=qualified)
        exe = BUILD/mode/'test'
        subprocess.run(['cc',*flags,'-I'+str(engine),str(engine/'fm_load.c'),str(engine/'fm_render.c'),
                        str(ROOT/'tests/tdelay_test.c'),'-lm','-o',str(exe)],check=True)
        for name,g,inputs,rate,*_ in fixtures:
            stem=BUILD/name; path=stem.with_suffix('.scsyndef'); path.write_bytes(encode(g))
            data=stem.with_suffix('.f32'); data.write_bytes(inputs.tobytes()); output=stem.with_suffix('.actual')
            r=subprocess.run([str(exe),str(path),str(data),str(output),str(BLOCKS),'ok'],capture_output=True,text=True,timeout=30)
            assert r.returncode==0, r.stdout+r.stderr
            actual=array.array('f'); actual.frombytes(output.read_bytes())
            assert actual==expected[name], f'{mode}: {name}'
            report['cases'].append(dict(mode=mode,name=name,frames=BLOCKS*BLOCK,exact_sc_match=True,
                                        pulses=sum(actual[::2])/(BLOCK if rate==1 else 1),
                                        graph_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),passed=True))
        base = graph(2,2)
        for name,change in [
            ('initial_rate',lambda n: (n[0],0,n[2],[0],n[4])),
            ('missing_input',lambda n: (n[0],2,n[2][:1],n[3],n[4])),
            ('extra_input',lambda n: (n[0],2,n[2]+[(-1,0)],n[3],n[4])),
            ('extra_output',lambda n: (n[0],2,n[2],[2,2],n[4])),
            ('literal_trigger',lambda n: (n[0],2,[(-1,0),n[2][1]],n[3],n[4])),
            ('audio_trigger_into_kr',lambda n: (n[0],1,n[2],[1],n[4]))]:
            g=copy.deepcopy(base); g['nodes'][1]=change(g['nodes'][1]); path=BUILD/(name+'.scsyndef'); path.write_bytes(encode(g))
            r=subprocess.run([str(exe),str(path),'_','_','0','reject'],capture_output=True,text=True,timeout=10)
            assert r.returncode==0 and 'TDelay' in r.stdout,r.stdout+r.stderr
            report['rejections'].append(dict(mode=mode,name=name,error=r.stdout.strip(),passed=True))
        # Finite but unrepresentable delay: no undefined float-to-int cast and
        # no fault until a trigger actually attempts to latch the duration.
        for name,trigger,fault in [('huge_pending',1.,True),('huge_untriggered',0.,False),('huge_negative',1.,False)]:
            inputs=array.array('f',[trigger,1e6 if name!='huge_negative' else -1e6])*(BLOCKS*BLOCK)
            path=BUILD/(name+'.scsyndef'); path.write_bytes(encode(base)); data=BUILD/(name+'.f32');data.write_bytes(inputs.tobytes())
            r=subprocess.run([str(exe),str(path),str(data),str(BUILD/(name+'.actual')),str(BLOCKS),'fault' if fault else 'ok'],capture_output=True,text=True,timeout=10)
            assert r.returncode==0,r.stdout+r.stderr
            report['cases'].append(dict(mode=mode,name=name,passed=True,checked_fault=fault))
    # Exercise the user's real source/compiler route, not only encoded graphs.
    from studio import Compiler
    compiler=Compiler(SCLANG); report['source_compile']=[]
    for rate in ('ar','kr'):
        source='{ var t = TDelay.'+rate+'(Impulse.'+rate+'(2), 0.125); (SinOsc.ar(440) * Decay.'+rate+'(t, 0.2) * 0.1) ! 2 }.play'
        raw,original,info=compiler.compile(dict(source=source))
        assert original==source.encode() and info['fm1_admitted'] and info['continuous']
        assert 'TDelay' in [n[0] for n in decode(raw)['nodes']]
        (BUILD/f'example_{rate}.scd').write_text(source)
        (BUILD/f'example_{rate}.scsyndef').write_bytes(raw)
        report['source_compile'].append(dict(rate=rate,passed=True,studio_admitted=True,graph_sha256=hashlib.sha256(raw).hexdigest()))
    report['generator_sha256']=hashlib.sha256((ROOT/'host/engine_profile.py').read_bytes()).hexdigest()
    report['test_sources_sha256']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
                                  for p in ('host/test_tdelay.py','tests/tdelay_test.c')}
    report['passed']=True; args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(passed=True,cases=len(report['cases']),rejections=len(report['rejections']),hardware=False)))

if __name__=='__main__': main()
