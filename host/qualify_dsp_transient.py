#!/usr/bin/env python3
"""Single-USB DSP checks using temporary graphs, including an empty saved FX.

Requires a private Studio snapshot made before the session. Never saves a test
patch; reloads and verifies the original packages and restores live controls.
Profiling is muted. All further output is limited to 5% main volume.
"""
import argparse
import array
import base64
import hashlib
import json
from pathlib import Path
import statistics
import secrets
import time

from capture import capture
from control_client import instance_packet, packet, schema
from patches import Device, ROOT
from profile_ugens import collect
from studio import AudioTelemetry, Compiler


def volume(device, percent, save=False):
    assert type(percent) is int and 0 <= percent <= 5
    assert device.request('VOLUME', bytes([percent]))['percent'] == percent
    if save:
        assert device.request('VOLSAVE')['percent'] == percent


def restore(device, backup, percent=0, save=False):
    """Reload storage; temporary ACTIVATE never changes its generations."""
    volume(device, 0)
    device.request('FXLOAD', b'\0')
    device.request('LOAD', bytes([backup['state']['status']['slot']]))
    graph, source, _ = device.download()
    assert graph == base64.b64decode(backup['main']['graph'])
    assert source == backup['main']['source'].encode()
    assert device.request('LIST') == backup['state']['slots']
    assert device.request('FXLIST') == backup['state']['masters']
    for stage, key in ((1, 'fx_info'), (0, 'main_info')):
        old = backup[key]
        current = schema(device, stage)
        args = [value for control in old['controls'] if not control['name'].startswith('__esp32_')
                for value in (control['name'], control['values'])]
        device.request('START' if old['active'] else 'STOP',
                       instance_packet(current, stage, args if old['active'] else []))
        assert schema(device, stage)['active'] == old['active']
    volume(device, percent, save)
    return dict(main_package_verified=True, saved_main_fx_lists_unchanged=True,
                instance_controls_restored=True, volume_percent=percent, volume_saved=save)


def install(device, raw, source, name, master=False):
    status = device.upload(raw, source.encode(), name[:31], mapping=0, master=master)
    if not master:
        assert status['graph_sha256'] == hashlib.sha256(raw).hexdigest()
    assert device.request('VOLUME')['percent'] <= 5


def profile(device, phase, qualified, runs):
    fixtures = {}
    for folder in ('seeded-dsp-plan', 'seeded-smooth-plan', 'seeded-core-plan', 'seeded-delay-plan'):
        plan = json.loads((ROOT/'build/host'/folder/'plan.json').read_text())
        assert not fixtures.keys() & plan.keys()
        fixtures.update(plan)
    result = dict(fixtures={}, fixed_seed=True, phase=phase, runs=runs)
    for name, item in fixtures.items():
        raw = base64.b64decode(item['graph'], validate=True)
        assert hashlib.sha256(raw).hexdigest() == item['graph_sha256']
        install(device, raw, item['source'], 'DSP '+name)
        trials = []
        for _ in range(runs):
            sample = collect(device, fixed=True)
            assert sample['setup']['qualified'] == str(int(qualified)), 'Wrong kernel mode'
            if trials:
                for key in ('warm_sha256', 'audio_sha256', 'rng'):
                    assert trials[0]['setup'][key] == sample['setup'][key]
            trials.append({k: sample[k] for k in ('header', 'setup', 'by_type', 'normal_average_us_at_240mhz')})
        us = statistics.median(t['normal_average_us_at_240mhz'] for t in trials)
        result['fixtures'][name] = dict(graph_sha256=item['graph_sha256'],
            nodes=int(trials[0]['setup']['nodes']), median_us=us, runs=trials)
        print(f'{phase}: {name}: {us:.2f} us/block', flush=True)
    return result


def compile_install(compiler, device, source, name, master=False):
    raw, original, info = compiler.compile(dict(source=source, target='master' if master else 'sound'))
    assert info['admitted'] and (master or info['continuous'])
    install(device, raw, original.decode(), name, master)
    return info


def tdelay(device, compiler):
    result = []
    # Capture both the trigger and the delayed output, then reconstruct the
    # expected countdown from the physical output's trigger channel. Anchor on
    # the first output pulse: a running delay's pending state is unknown when
    # capture starts, and periodic ignored triggers never force it to resync.
    for rate, frequency, ticks in (('ar',100,0), ('ar',100,5), ('ar',2000,64),
                                   ('kr',20,0), ('kr',20,5), ('kr',100,12)):
        sr = 44100 if rate == 'ar' else 44100/64
        duration = ticks/sr
        if rate == 'ar':
            source = f'{{ var t=Impulse.ar({frequency}); [t,TDelay.ar(t,{duration!r})]*0.1 }}'
        else:
            source = f'{{ var t=Impulse.kr({frequency}), d=TDelay.kr(t,{duration!r}); [Select.ar(t,[DC.ar(0),DC.ar(0.1)]),Select.ar(d,[DC.ar(0),DC.ar(0.1)])] }}'
        compiled=compile_install(compiler, device, source, 'TDelay '+rate)
        volume(device, 5)
        time.sleep(.15)
        pcm, info = capture(device, .4)
        volume(device, 0)
        values = array.array('h'); values.frombytes(pcm)
        left, right = values[::2], values[1::2]
        assert max(left) > 100 and max(right) > 100 and max(map(abs, values)) < 32767
        assert max(left)==max(right), 'Delayed trigger amplitude differs'
        step = 1 if rate == 'ar' else 64
        # Recover control-block alignment from a rising trigger plateau.
        origin = 0 if step == 1 else next(i for i in range(1,len(left)) if left[i]>0 and left[i-1]==0)
        anchor=next(i for i in range(origin,len(left)-step+1,step) if right[i]>0)
        previous, pending = int(left[anchor]>0), 0
        checked, pulses = 0, 0
        for index in range(anchor+step,len(left)-step+1,step):
            current = int(left[index] > 0); expected = 0
            if pending > 1: pending -= 1
            elif pending == 1: pending, expected = 0, 1
            elif previous <= 0 < current: pending = max(1,ticks)
            previous = current
            assert all(int(v>0)==expected for v in right[index:index+step]), (rate,ticks,index)
            checked += step; pulses += expected
        assert pulses > 0
        result.append(dict(rate=rate,trigger_hz=frequency,delay_ticks=ticks,checked_frames=checked,
                           pulses=pulses,graph_sha256=compiled['graph_sha256'],passed=True))
        print(f'TDelay.{rate}: delay={ticks} ticks, {checked} captured frames match',flush=True)
    return result


def listen(device, compiler, results=None):
    tests = results if results is not None else {}
    volume(device, 0)
    # finish() runs the soak first, which leaves its separate MiVerb active.
    # These Main fixtures already include their intended effects: do not stack
    # the soak FX on them and accidentally test an over-budget double reverb.
    device.request('FXLOAD', b'\0')
    for name,file,seconds in (('eight_saw','module-audio-check',10),
                              ('comb_kr','comb-cloud-kr',12),
                              ('triggered_harmonics','triggered-harmonics',12)):
        source = (ROOT/f'examples/{file}.scd').read_text()
        info = compile_install(compiler,device,source,name)
        volume(device,5); print('PLAYING '+name+' (5% main volume)',flush=True)
        time.sleep(2)
        pcm,_ = capture(device,.5); values=array.array('h');values.frombytes(pcm)
        assert max(map(abs,values)) < 32767
        tests[name] = dict(graph_sha256=info['graph_sha256'],pcm_peak=max(map(abs,values)))
        time.sleep(seconds-2); volume(device,0)
    # Temporary FX does not populate the user's empty saved FX slot.
    source = '{ MiVerb.ar(In.ar(0,2),0.85,1,0.5,0.05) }'
    compile_install(compiler,device,source,'Temporary MiVerb',master=True)
    # Keep charging the FX while the first recording downloads. A one-shot
    # burst could have decayed completely before a slow USB download finishes.
    source = '{ (SinOsc.ar(440)*0.1)!2 }'
    compile_install(compiler,device,source,'Tone and FX tail')
    volume(device,5);print('PLAYING tone and separate MiVerb tail (5% main volume)',flush=True)
    time.sleep(.2);pcm,_=capture(device,.5);values=array.array('h');values.frombytes(pcm)
    rms=math_rms(values);assert rms>.1, 'FX pre-stop capture was silent'
    current=schema(device,0);device.request('STOP',instance_packet(current,0,[]))
    # Exclude the Main fade and the 6x128-frame DMA queue from the tail check.
    time.sleep(.05)
    pcm,_=capture(device,.3);values=array.array('h');values.frombytes(pcm)
    after=math_rms(values);assert after>.02, 'FX tail was silent after Main stop'
    time.sleep(2);device.request('PANIC');pcm,_=capture(device,.1)
    assert not any(pcm), 'Panic capture was not silent'
    tests['reverb']=dict(playing_rms=rms,tail_after_main_stop_rms=after,panic_silence=True)
    volume(device,0)
    return tests


def math_rms(values):
    return (sum(float(v)*v for v in values)/len(values))**.5


def soak(device, compiler, telemetry, seconds=60, controls=True, recordings=True):
    # The saved Main may already contain MiVerb. Replace it with the light
    # fixture before enabling test FX, even while output volume is muted.
    device.request('FXLOAD', b'\0')
    compile_install(compiler,device,(ROOT/'examples/comb-cloud-kr.scd').read_text(),'Soak Comb Cloud')
    compile_install(compiler,device,'{ MiVerb.ar(In.ar(0,2),0.85,0.35,0.5,0.05) }','Soak MiVerb',master=True)
    info=schema(device,0);volume(device,5)
    setup=telemetry.snapshot()
    # Logs are asynchronous. Read through several complete telemetry windows
    # after constructors/activation before attributing counters to playback.
    settling=time.monotonic()+3
    while time.monotonic()<settling:
        device.request('VOLUME');time.sleep(.125)
    # Replay protection survives graph rebinds. A new invocation must not reuse
    # a previous run's stream with its sequence restarted at one.
    stream=secrets.randbits(32) or 1
    before=telemetry.snapshot();captures=[];sent=0;start=time.monotonic();next_capture=start+5
    while time.monotonic()-start<seconds:
        if controls:
            sent+=1
            wire=packet(info,0,stream,sent,['freq',[220,330,440,550][sent%4]])
            assert device.request('RCEVENT',wire)['queued']
        else:device.request('VOLUME')
        if recordings and time.monotonic()>=next_capture:
            pcm,_=capture(device,.2);values=array.array('h');values.frombytes(pcm)
            peak=max(map(abs,values));assert peak<32767
            captures.append(dict(elapsed=round(time.monotonic()-start,2),peak=peak,rms=math_rms(values)))
            next_capture+=10
        time.sleep(.125)
    finished=time.monotonic();settling=finished+2
    while time.monotonic()<settling:
        device.request('VOLUME');time.sleep(.125)
    after=telemetry.snapshot();volume(device,0)
    keys=('faults','clips','nonfinite','write_fail','partial','dma_event_overflow','overflow')
    for key in keys:
        assert key in before and key in after, 'Missing telemetry: '+key
    delta={key:after[key]-before[key] for key in keys}
    good_signal=not recordings or any(row['peak']>100 for row in captures)
    stable_memory=(after['internal_free']>=before['internal_free']-1024 and
                   after['psram_free']>=before['psram_free']-1024)
    return dict(passed=not any(delta.values()) and good_signal and stable_memory,
                seconds=round(finished-start,2),controls_enabled=controls,recordings_enabled=recordings,
                controls_sent=sent,control_stream=stream,captures=captures,diagnostic_deltas=delta,
                setup=setup,before=before,after=after,stable_memory=stable_memory)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True);p.add_argument('--device-id',required=True)
    p.add_argument('--backup',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--phase',choices=('baseline','qualified','tdelay','soak','listen','finish','restore'),required=True)
    p.add_argument('--runs',type=int,choices=range(1,6),default=3)
    p.add_argument('--soak-seconds',type=int,choices=range(10,601),default=60)
    p.add_argument('--no-controls',action='store_true');p.add_argument('--no-capture',action='store_true')
    args=p.parse_args();backup=json.loads(args.backup.read_text())
    assert backup['state']['hello']['device_id']==args.device_id
    assert next(e['slot'] for e in backup['state']['masters'] if e['selected'])==0, 'This session requires original FX bypass'
    report=dict(passed=False,hardware=True,device_id=args.device_id,phase=args.phase,
                saved_patch_writes=False,volume_limit_percent=5)
    telemetry=AudioTelemetry();device=Device(args.port,telemetry)
    identified=False
    try:
        hello=device.hello();assert hello['device_id']==args.device_id and hello['headless']
        identified=True
        report['build']=hello['build']
        if args.phase=='finish':volume(device,5,save=True)
        volume(device,0)
        if args.phase in ('baseline','qualified'):
            report.update(profile(device,args.phase,args.phase=='qualified',args.runs))
        elif args.phase=='tdelay':
            report['tests']=tdelay(device,Compiler('/Applications/SuperCollider.app/Contents/MacOS/sclang'))
        elif args.phase=='listen':
            report['tests']={}
            listen(device,Compiler('/Applications/SuperCollider.app/Contents/MacOS/sclang'),report['tests'])
            report['listening']='pending user assessment'
        elif args.phase=='soak':
            report['tests']=soak(device,Compiler('/Applications/SuperCollider.app/Contents/MacOS/sclang'),telemetry,
                                 args.soak_seconds,not args.no_controls,not args.no_capture)
            assert report['tests']['passed'],report['tests']['diagnostic_deltas']
        elif args.phase=='finish':
            compiler=Compiler('/Applications/SuperCollider.app/Contents/MacOS/sclang')
            report['tests']={}
            report['tests']['soak']=soak(device,compiler,telemetry,args.soak_seconds)
            print('SOAK '+('PASS' if report['tests']['soak']['passed'] else 'FAILED')+'; starting listening sequence',flush=True)
            report['tests']['listening']={}
            listen(device,compiler,report['tests']['listening'])
            report['listening']='pending user assessment'
            assert report['tests']['soak']['passed'],report['tests']['soak']['diagnostic_deltas']
        report['passed']=True
    except BaseException as error:
        report['error_type']=type(error).__name__
        report['error']=str(error) or type(error).__name__;raise
    finally:
        try:
            final=args.phase in ('finish','restore')
            if identified:
                report['restoration']=restore(device,backup,min(5,round(backup['volume']*100)) if final else 0,save=final)
            else:
                report['restoration']=dict(skipped='Physical module identity was not verified')
        except BaseException as error:
            report['restoration_error']=str(error);report['passed']=False;raise
        finally:
            report['audio_telemetry']=telemetry.snapshot()
            device.close();args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS '+args.phase+'; original packages and live controls restored',flush=True)


if __name__=='__main__':main()
