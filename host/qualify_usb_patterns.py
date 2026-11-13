#!/usr/bin/env python3
"""Real sclang patterns -> isolated Studio bridge -> one backed-up USB node.

Temporary ACTIVATE only: never INSTALL/SAVE a test patch. All sound <=5%.
The normal Studio session releases USB and is reattached after restoration.
"""
import argparse
import array
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import statistics
import struct
import subprocess
import threading
import time

from control_client import schema
from ide_bridge import Bridge
from patches import ROOT
from probe_usb_lifecycle import find_port
from qualify_dsp_transient import restore, volume
from studio import Studio
from studio_client import StudioClient

SCLANG='/Applications/SuperCollider.app/Contents/MacOS/sclang'
COUNTERS=('write_fail','partial','dma_event_overflow','faults','clips','nonfinite','overflow')
GATED=r'''SynthDef(\UsbGateQA, { arg freq=440, amp=0.05, gate=0, attack=0.002, release=0.01;
    var env=EnvGen.kr(Env.asr(attack,1,release),gate);
    Out.ar(0,[SinOsc.ar(freq)*amp*env,Select.ar(gate,[DC.ar(0),SinOsc.ar(880,0,0.02)])]);
})'''
REPLACEMENT=GATED.replace('UsbGateQA','UsbGateReplacementQA').replace('freq=440','freq=660')


def pcm_stats(pcm):
    values=array.array('h');values.frombytes(pcm)
    if not values or len(values)%2:raise ValueError('Expected nonempty stereo PCM')
    peak=max(map(abs,values))
    return values,dict(frames=len(values)//2,peak=peak,rms=math.sqrt(sum(float(v)*v for v in values)/len(values)))


def gate_edges(right,min_zero=16):
    """Ignore isolated sine/quantisation zero crossings; keep actual low gates."""
    edges=[];gaps=[];start=None
    for index,value in enumerate(right):
        if value==0:
            if start is None:start=index
        elif start is not None:
            if start>0 and index-start>=min_zero:edges.append(index);gaps.append(index-start)
            start=None
    return edges,gaps


def period_stats(right,rate,sample_rate=44100):
    edges,gaps=gate_edges(right)
    periods=[(b-a)/sample_rate for a,b in zip(edges,edges[1:])]
    if len(periods)<2 or len(edges)<max(3,int(len(right)*rate/sample_rate)-2):
        raise AssertionError('Too few gate transitions in capture')
    expected=1/rate
    error=max(abs(value-expected) for value in periods)
    if error>.010:raise AssertionError(f'Gate period error {error:.6f}s exceeds 10 ms')
    return dict(transitions=len(edges),mean_period_seconds=statistics.mean(periods),
                max_period_error_seconds=error,zero_gap_min_samples=min(gaps),zero_gap_max_samples=max(gaps))


def empty_note_delta_stats(wires):
    notes=[row for row in wires if row['kind']==1 and row.get('queued') is True]
    assert len(notes)>=3,'Too few acknowledged repeated notes'
    assert all(row['delta'] and row['pairs']==0 and row['bytes']==32 for row in notes), 'Repeated notes did not use empty 32-byte deltas'
    return dict(acknowledged_notes=len(notes),empty_delta_notes=len(notes),bytes_per_event=32)


SCRIPT=r'''
Routine({
    var target=%TARGET%,p,mk,ask,s1,s2,future;
    try {
        ESP32.connect(%CONFIG%).wait;ESP32.latency=0.25;
        ask={|name,extra|ESP32.request(\qa,(name:name).putAll(extra ? ())).wait};
        mk={|rate,overlap=false,repeated=false|
            Pbind(\type,\esp32Note,\module,target,
                \freq,Pfunc({~sent=~sent+1;if(repeated){440}{[220,330,440,550].wrapAt(~sent)}}),
                \amp,0.05,\attack,0.002,\release,0.01,
                \dur,1/rate,\sustain,if(overlap){0.2}{0.7/rate}).playESP32;
        };
        ESP32.prepare(target).wait;ask.value("definition_silent");
        ESP32.play(target,[\gate,0]).wait;ask.value("created_silent");
        ESP32.stop(target).wait;ESP32.prepare(target).wait;
        ~sent=0;p=mk.value(8);0.6.wait;ask.value("rate8",(rate:8,sent:~sent));
        p.stop;0.5.wait;ask.value("cancel_silent");
        p.play;0.6.wait;ask.value("replay8",(rate:8,sent:~sent));p.stop;0.5.wait;ask.value("cancel_silent");
        ~sent=0;p=mk.value(16);0.6.wait;ask.value("rate16",(rate:16,sent:~sent));p.stop;0.5.wait;ask.value("cancel_silent");
        ~sent=0;p=mk.value(16,false,true);0.6.wait;ask.value("same_pitch16",(rate:16,sent:~sent));p.stop;0.5.wait;ask.value("cancel_silent");
        ~sent=0;p=mk.value(16,true);0.6.wait;ask.value("overlap16",(rate:16,sent:~sent));p.stop;0.5.wait;ask.value("cancel_silent");
        ask.value("finite_before");
        p=Pbind(\type,\esp32Note,\module,target,\freq,Pseq([220,330,440],1),\amp,0.05,\dur,0.125).playESP32;
        1.0.wait;ask.value("finite_ended");
        future=UniqueID.next;
        ESP32.request(\control,(kind:\note,target:target,stream:future,args:[\freq,330,\amp,0.05],lead:0.5,sustain:0.2)).wait;
        ask.value("queued_future");ESP32.cancel(future).wait;ask.value("future_canceled");
        s1=UniqueID.next;s2=UniqueID.next;
        ESP32.request(\control,(kind:\note,target:target,stream:s1,args:[\freq,330,\amp,0.05],lead:0.15,sustain:0.4)).wait;
        ESP32.request(\control,(kind:\note,target:target,stream:s2,args:[\freq,660,\amp,0.05],lead:0.25,sustain:1.5)).wait;
        0.7.wait;ESP32.cancel(s1).wait;ask.value("new_owner_survives");ESP32.cancel(s2).wait;0.1.wait;ask.value("cancel_silent");
        future=UniqueID.next;
        ESP32.request(\control,(kind:\note,target:target,stream:future,args:[\freq,330,\amp,0.05],lead:0.5,sustain:0.2)).wait;
        ask.value("queued_future");ESP32.module(target).main.panic.wait;ask.value("panic_silent");
        ESP32.prepare(target).wait;
        ~sent=0;p=mk.value(16);0.5.wait;ask.value("replace_while_queued");
        0.5.wait;if(p.isPlaying){Error("Old pattern continued after definition replacement").throw};ask.value("changed_silent");
        ESP32.prepare(target).wait;~sent=0;p=mk.value(8);0.6.wait;ask.value("new_definition8",(rate:8,sent:~sent));p.stop;0.5.wait;ask.value("cancel_silent");
        ~sent=0;p=mk.value(8);0.5.wait;ESP32.cmdPeriod;0.5.wait;ask.value("cmdperiod_hook_silent");
        ask.value("soak_install");ESP32.prepare(target).wait;
        ~sent=0;p=Pbind(\type,\esp32Set,\module,target,
            \freq,Pfunc({~sent=~sent+1;[220,220,330,330,440,440,550,550].wrapAt(~sent)}),\dur,1/16).playESP32;
        0.5.wait;ask.value("soak_begin");%SECONDS%.wait;
        if(p.isPlaying.not){Error("Soak pattern stopped early").throw};
        p.stop;0.6.wait;ask.value("soak_end",(sent:~sent));
        ESP32.disconnect;"PASS: USB patterns and DSP/control soak".postln;0.exit;
    } {|error|p.tryPerform(\stop);ESP32.disconnect;error.reportError;1.exit};
}).play(SystemClock);
'''


class Qualification:
    def __init__(self,app,bridge,plan,report,seconds):
        self.app,self.bridge,self.plan,self.report,self.seconds=app,bridge,plan,report,seconds
        self.phase='setup';self.wires=[];self.lock=threading.Lock();self.failure=None
        self.done=threading.Event();self.monitor=None;self.expect_stale=False
        original=app.device.request
        def request(operation,payload=b'',*args,**kwargs):
            started=time.monotonic();row=None
            if operation=='RCEVENT':
                row=dict(phase=self.phase,kind=payload[28],delta=bool(payload[31]),pairs=payload[30],bytes=len(payload),stream=struct.unpack_from('<I',payload,8)[0])
            try:
                result=original(operation,payload,*args,**kwargs)
                if row is not None:row['queued']=result.get('queued');row['need_full']=result.get('need_full',False)
                return result
            except Exception as error:
                if row is not None:row['error']=str(error)
                raise
            finally:
                if row is not None:
                    row['ack_ms']=round((time.monotonic()-started)*1000,3)
                    with self.lock:self.wires.append(row)
        app.device.request=request
        self.original_dispatch=bridge.hub.dispatch
        bridge.hub.dispatch=self.dispatch

    def info(self):
        with self.app.device_lock:return schema(self.app.device,0)

    def capture(self,seconds):
        result=self.app.capture_audio(dict(device_id=self.report['device_id'],seconds=seconds))
        pcm=base64.b64decode(result['data'])
        folder=ROOT/'build/host/private/usb-pattern-qa'
        (folder/(self.phase+'-'+str(result['frames'])+'.pcm')).write_bytes(pcm)
        return pcm_stats(pcm)

    def audio(self):
        value=self.app.telemetry.snapshot()
        assert all(k in value and value.get('ages',{}).get(k,99)<3 for k in COUNTERS),'Stale/missing telemetry'
        return value

    def install(self,key,master=False):
        item=self.plan[key]
        with self.app.device_lock:
            d=self.app.device
            assert d.hello()['device_id']==self.report['device_id']
            result=d.upload(item['graph'],item['source'],key,mapping=0,master=master,definition=key in ('gated','replacement'))
            assert d.request('VOLUME')['percent']<=5
            if not master:assert result['graph_sha256']==item['info']['graph_sha256']

    def silent(self,seconds=.25):
        info=self.info();assert info['queued']==0,'Pending notes remain after cleanup'
        values,pcm=self.capture(seconds);assert not any(values),'Cleanup left audible PCM'
        return dict(queued=0,active=info['active'],pcm=pcm)

    def dispatch(self,action,p,source,graph,client,sequence):
        if action!='qa':
            try:result=self.original_dispatch(action,p,source,graph,client,sequence)
            except Exception as error:
                if action=='control' and not self.expect_stale:self.failure='SC control failed: '+str(error)
                raise
            if action=='control' and result.get('queued') is False and not self.expect_stale:
                self.failure='Unexpected rejected SC control: '+str(result)
            return result
        name=p['name'];self.phase=name;row=dict(name=name,passed=False)
        self.report['cases'].append(row)
        print('CHECK '+name,flush=True)
        try:
            if name in ('definition_silent','created_silent','cancel_silent','cmdperiod_hook_silent','changed_silent'):
                row.update(self.silent());info=self.info()
                assert next(c['values'][0] for c in info['controls'] if c['name']=='gate')==0
                if name in ('definition_silent','changed_silent'):assert not info['active']
            elif name in ('rate8','replay8','rate16','same_pitch16','overlap16','new_definition8'):
                values,pcm=self.capture(.8);assert 0<pcm['peak']<32767
                row.update(pcm=pcm,timing=period_stats(values[1::2],int(p['rate'])),sc_sent=int(p['sent']))
                if name=='overlap16':assert row['timing']['zero_gap_max_samples']<=192,'Overlap produced an unexpectedly long gate gap'
                if name=='same_pitch16':
                    with self.lock:wires=[v.copy() for v in self.wires if v['phase']==name]
                    row['wire_deltas']=empty_note_delta_stats(wires)
                if name=='new_definition8':self.expect_stale=False
            elif name=='finite_before':self.finite=self.info()['applied']
            elif name=='finite_ended':
                row.update(self.silent());row['notes_applied']=self.info()['applied']-self.finite;assert row['notes_applied']==3
            elif name=='queued_future':
                info=self.info();assert info['queued']>=1;row['queued']=info['queued']
            elif name in ('future_canceled','panic_silent'):
                row.update(self.silent(.8))
            elif name=='new_owner_survives':
                info=self.info();controls={c['name']:c['values'][0] for c in info['controls']}
                assert controls['gate']==1 and controls['freq']==660
                values,pcm=self.capture(.2);edges,_=gate_edges(values[1::2]);assert not edges and pcm['peak']>0
                row.update(pcm=pcm,gate=1,freq=660)
            elif name=='replace_while_queued':
                before=self.info();self.expect_stale=True;self.install('replacement');after=self.info()
                assert before['boot']==after['boot'] and before['revision']!=after['revision'] and after['queued']==0
                row.update(old_revision=before['revision'],new_revision=after['revision'],queue_flushed=True)
            elif name=='soak_install':
                self.expect_stale=False
                with self.app.device_lock:self.app.device.request('FXLOAD',b'\0')
                self.install('cloud');self.install('fx',True)
            elif name=='soak_begin':
                self.report['soak']=dict(seconds=self.seconds,rate_hz=16,before=self.audio(),remote_before=self.info(),samples=[])
                self.monitor=threading.Thread(target=self.watch,daemon=True);self.monitor.start()
            elif name=='soak_end':
                self.done.set();self.monitor.join(6);assert not self.monitor.is_alive()
                if self.failure:raise AssertionError(self.failure)
                info=self.info();assert info['queued']==0
                held=next(c['values'][0] for c in info['controls'] if c['name']=='freq');time.sleep(.4)
                again=self.info();assert next(c['values'][0] for c in again['controls'] if c['name']=='freq')==held
                values,pcm=self.capture(.2);assert 0<pcm['peak']<32767,'Control cancellation stopped continuous audio'
                soak=self.report['soak'];soak.update(after=self.audio(),remote_after=again,sc_sent=int(p['sent']),continuous_after_cancel=True)
                soak['diagnostic_deltas']={k:soak['after'][k]-soak['before'][k] for k in COUNTERS}
                assert not any(soak['diagnostic_deltas'].values()),soak['diagnostic_deltas']
                assert again['late']==soak['remote_before']['late'] and again['rejected']==soak['remote_before']['rejected']
                assert soak['sc_sent']>=self.seconds*16*.99
                soak['stable_memory']=all(soak['after'][k]>=soak['before'][k]-1024 for k in ('internal_free','psram_free'));assert soak['stable_memory']
                soak['passed']=True
            else:raise ValueError('Unknown QA phase')
            row['passed']=True;return dict(ok=True)
        except BaseException as error:
            row['error']=str(error) or type(error).__name__;self.failure=row['error'];raise

    def watch(self):
        started=time.monotonic();next_capture=started+10;last_notice=started
        last_applied=self.report['soak']['remote_before']['applied']
        try:
            while not self.done.wait(5):
                if self.failure:return
                audio=self.audio();base=self.report['soak']['before']
                assert not any(audio[k]-base[k] for k in COUNTERS),'Audio diagnostic counter increased'
                info=self.info();remote=self.report['soak']['remote_before']
                assert (info['boot'],info['revision'])==(remote['boot'],remote['revision'])
                assert info['rejected']==remote['rejected'] and info['late']==remote['late'],'Remote event rejected/late'
                assert info['applied']>last_applied,'SC control stream stopped advancing'
                last_applied=info['applied']
                sample=dict(seconds=round(time.monotonic()-started,2),queued=info['queued'],applied=info['applied'],average_x10=audio.get('average_x10'),peak_x10=audio.get('peak_x10'),internal_free=audio['internal_free'],psram_free=audio['psram_free'])
                if time.monotonic()>=next_capture:
                    values,pcm=self.capture(.2);assert 0<pcm['peak']<32767
                    sample['pcm']=pcm;next_capture+=30
                self.report['soak']['samples'].append(sample)
                if time.monotonic()-last_notice>=30:
                    print(f'SOAK {sample["seconds"]:.0f}s: applied={info["applied"]}; no new audio or remote errors',flush=True);last_notice=time.monotonic()
        except BaseException as error:self.failure=str(error) or type(error).__name__


def run(args):
    target=args.device_id;backup=json.loads(args.backup.read_text());assert backup['state']['hello']['device_id']==target
    assert next(r['slot'] for r in backup['state']['masters'] if r['selected'])==0,'This pack requires initial FX bypass'
    normal=StudioClient();app=None;bridge=None;child=None;qa=None;mutated=False;borrowed=False
    private=ROOT/'build/host/private/usb-pattern-qa';private.mkdir(parents=True,exist_ok=True,mode=0o700)
    report=dict(passed=False,hardware=True,device_id=target,volume_limit_percent=5,saved_patch_writes=False,firmware_writes=False,cases=[])
    try:
        state=normal.http('refresh',{});assert state['hello']['device_id']==target and state['volume_percent']==5
        assert state['status']['graph_sha256']==backup['state']['status']['graph_sha256'] and state['slots']==backup['state']['slots'] and state['masters']==backup['state']['masters'],'Saved state changed since backup'
        compiler=Studio(SCLANG).compiler;plan={}
        for key,source,master,definition in (('gated',GATED,False,True),('replacement',REPLACEMENT,False,True),('cloud',(ROOT/'examples/comb-cloud-kr.scd').read_text(),False,False),('fx','{ MiVerb.ar(In.ar(0,2),0.85,0.35,0.5,0.05) }',True,False)):
            graph,original,info=compiler.compile(dict(source=source,target='master' if master else 'sound',definition=definition));assert info['admitted']
            plan[key]=dict(graph=graph,source=original,info=info)
        report['graphs']={k:dict(graph_sha256=v['info']['graph_sha256'],source_sha256=v['info']['source_sha256'],nodes=v['info']['nodes']) for k,v in plan.items()}
        normal.http('disconnect',{});borrowed=True
        app=Studio(SCLANG);app.connect(find_port(target));app.start_reader()
        assert app.device_info['device_id']==target and app.device_info.get('headless')
        report['build']=app.device_info['build']
        with app.device_lock:
            initial=schema(app.device,0)
            assert initial['active']==backup['main_info']['active']
            assert {v['name']:v['values'] for v in initial['controls']}=={v['name']:v['values'] for v in backup['main_info']['controls']},'Live controls changed since backup'
            report['initial_boot']=initial['boot']
        config=private/'connection.json';bridge=Bridge(app,secrets.token_urlsafe(32),config=config)
        qa=Qualification(app,bridge,plan,report,args.soak_seconds)
        mutated=True
        with app.device_lock:volume(app.device,0);app.device.request('FXLOAD',b'\0')
        qa.install('gated')
        with app.device_lock:volume(app.device,5)
        installed=Path.home()/'Library/Application Support/SuperCollider/Extensions/ESP32Studio'
        same=installed.is_symlink() and installed.resolve()==ROOT/'supercollider'
        language=private/'language.yaml';language.write_text(json.dumps(dict(includePaths=[] if same else [str(ROOT/'supercollider')],excludePaths=[str(installed),str(installed.resolve())] if installed.exists() and not same else [],postInlineWarnings=False)))
        script=private/'patterns.scd';script.write_text(SCRIPT.replace('%TARGET%',json.dumps(target)).replace('%CONFIG%',json.dumps(str(config))).replace('%SECONDS%',str(args.soak_seconds)))
        log=private/'sclang.log'
        with log.open('w') as output:
            child=subprocess.Popen([SCLANG,'-l',str(language),'-D',str(script)],stdout=output,stderr=subprocess.STDOUT)
            deadline=time.monotonic()+args.soak_seconds+240
            while child.poll() is None:
                if qa.failure:raise AssertionError(qa.failure)
                if time.monotonic()>deadline:raise TimeoutError('SC hardware qualification deadline exceeded')
                time.sleep(.2)
        text=log.read_text();report['sclang_exit_code']=child.returncode
        warnings=[line for line in text.splitlines() if 'WARNING: ESP32' in line]
        report['sc_warnings']=warnings
        assert child.returncode==0,'sclang failed; inspect private qualification log'
        assert len(warnings)==1 and 'pattern stopped:' in warnings[0],'Expected one stale-pattern warning and no warning flood'
        assert report['soak']['passed'] and not qa.failure
        report['passed']=True
    except BaseException as error:report['error']=str(error) or type(error).__name__;raise
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:child.wait(3)
            except subprocess.TimeoutExpired:child.kill();child.wait(3)
        if qa:
            qa.done.set()
            if qa.monitor:qa.monitor.join(6)
        if bridge:bridge.server_close()
        try:
            if app and mutated:
                with app.device_lock:
                    app.device.request('PANIC');report['restoration']=restore(app.device,backup,5,save=True)
                    assert schema(app.device,0)['boot']==report['initial_boot'],'Board rebooted during qualification'
                    for stage,key in ((0,'main_info'),(1,'fx_info')):
                        current=schema(app.device,stage)
                        assert {v['name']:v['values'] for v in current['controls']}=={v['name']:v['values'] for v in backup[key]['controls']}
            if qa:
                with qa.lock:wires=list(qa.wires)
                delays=[r['ack_ms'] for r in wires if r.get('queued')]
                report['wire_summary']=dict(requests=len(wires),accepted=sum(r.get('queued') is True for r in wires),errors=[r for r in wires if 'error' in r],delta_packets=sum(r['delta'] for r in wires),empty_delta_notes=sum(r['delta'] and r['kind']==1 and r['pairs']==0 for r in wires),ack_ms_median=statistics.median(delays) if delays else None,ack_ms_max=max(delays) if delays else None)
        except BaseException as error:report['restoration_error']=str(error) or type(error).__name__;report['passed']=False;raise
        finally:
            if app:app.close()
            try:
                if borrowed:
                    state=normal.http('connect',dict(port=find_port(target)));assert state['hello']['device_id']==target and state['volume_percent']==5
                    report['studio_connected']=True
            except BaseException as error:report['studio_error']=str(error);report['passed']=False
            normal.close();args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
    print('PASS: hardware USB patterns and soak; original sound and 5% restored',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device-id',required=True);parser.add_argument('--backup',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--soak-seconds',type=int,choices=range(60,901),default=600)
    run(parser.parse_args())


if __name__=='__main__':main()
