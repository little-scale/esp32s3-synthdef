#!/usr/bin/env python3
"""Reversible USB checks of expanded graph limits on a signal-reuse XIAO.

Uses the running Studio connection. Never flashes firmware. Backups and restores
both saved packages using the same ownership guards as qualify_headless.py.
"""
import argparse
import base64
import json
from pathlib import Path
import struct
import time
import wave

from patches import ROOT
from qualify_headless import Qualification, levels, require
from studio_client import StudioClient
from test_signal_reuse import capacity_cases, graph


def install_binary(q, data):
    artifact=q.compile('',graph=base64.b64encode(data).decode())
    q.install(artifact);q.rpc('prepare',stage='main')
    return {k:artifact[k] for k in ('nodes','signals','inputs','audio_buffers','scalar_values','signal_workspace_bytes','graph_sha256')}


def measure(q, seconds=6, silent=False, wav=None):
    q.rpc('play',stage='main');time.sleep(1.2)
    samples=[];start=time.monotonic()
    channels=q.capture(.25);result=levels(channels)
    require(result['peak']==0 if silent else min(result['rms'])>10,'Unexpected silence/signal in capacity capture')
    require(result['peak']<32767,'Capacity graph clipped')
    if wav:
        wav.parent.mkdir(parents=True,exist_ok=True)
        data=[v for frame in zip(*channels) for v in frame]
        with wave.open(str(wav),'wb') as f:
            f.setparams((2,2,44100,0,'NONE','not compressed'))
            f.writeframes(struct.pack('<'+str(len(data))+'h',*data))
    while time.monotonic()-start<seconds:
        sample=q.client.http('audio');samples.append(sample)
        if sample.get('peak_x10',0)>950:
            q.rpc('stop',stage='main')
            raise RuntimeError('Measured audio peak exceeded 95%; capacity is not a CPU guarantee')
        time.sleep(.25)
    q.rpc('stop',stage='main')
    result.update(average_cpu_max_percent=max(s.get('average_x10',0) for s in samples)/10,
                  peak_cpu_max_percent=max(s.get('peak_x10',0) for s in samples)/10,
                  memory={k:min(s[k] for s in samples if k in s) for k in
                          ('internal_free','internal_largest','psram_free','stack_free_bytes','controls_stack_free_bytes')
                          if any(k in s for s in samples)})
    return result


def run(q):
    hello=q.save()
    require(hello.get('signal_reuse')==1,'Install signal-reuse firmware first')
    require(hello.get('graph_limits')==dict(nodes=256,signals=512,inputs=2048,audio_buffers=192),'Unexpected firmware limits')
    report=q.report=dict(build=hello['build'],device_id=q.target,tests={})
    before=q.client.http('audio');tests=report['tests']
    q.rpc('meta',args=['volume',1]);q.rpc('bypass',bypassed=True)

    print('Loading exact 256-node audio graph without starting its CPU workload',flush=True)
    tests['nodes_256_admission']=install_binary(q,capacity_cases()['nodes-256'][0])
    require(not q.info()['active'],'Definition upload unexpectedly started audio')

    print('Rendering a 256-node control/audio graph',flush=True)
    c=lambda i:(-1,i)
    nodes=[('DC',1,[c(0)],1,0)]
    nodes += [('UnaryOpUGen',1,[(i-1,0)],1,0) for i in range(1,254)]
    nodes += [('K2A',2,[(253,0)],1,0),('Out',2,[c(0),(254,0),(254,0)],0,0)]
    tests['nodes_256_render']=install_binary(q,graph('ControlChain',nodes))
    tests['nodes_256_render'].update(measure(q,silent=True))

    print('Rendering the complete 512-scalar output bank',flush=True)
    tests['outputs_512']=install_binary(q,capacity_cases()['scalar-bank-1'][0])
    tests['outputs_512'].update(measure(q,silent=True))

    print('Rendering the exact 2048-reference boundary',flush=True)
    tests['inputs_2048']=install_binary(q,capacity_cases()['inputs-2048'][0])
    tests['inputs_2048'].update(measure(q,silent=True))

    print('Checking admission of 192 simultaneously live audio buffers without playback',flush=True)
    data=bytearray(capacity_cases()['live-192'][0])
    # Rewrite constant 1 (.1 -> 0) without changing graph topology or lifetimes.
    start=11+data[10];count=struct.unpack_from('>i',data,start)[0];require(count==4,'Unexpected fixture')
    struct.pack_into('>f',data,start+4+4,0)
    tests['live_192']=install_binary(q,bytes(data))
    require(not q.info()['active'],'Memory-boundary definition unexpectedly started')
    tests['live_192']['playback_qualified']=False
    tests['live_192']['scope']='Memory admission only; this deliberately wide fixture can exceed the audio CPU budget.'

    previous=None
    for count in (16,32,48,64):
        print(f'Compiling and admitting real {count}-oscillator stereo Splay graph',flush=True)
        source=f'SynthDef(\\ReuseDense{count}, {{ Out.ar(0, Splay.ar(SinOsc.ar(Array.series({count}, 80, 7)), 1, 0.05)) }})'
        artifact=q.compile(source);q.install(artifact);q.rpc('prepare',stage='main')
        tests['dense_'+str(count)]={k:artifact[k] for k in ('nodes','signals','inputs','audio_buffers','scalar_values','signal_workspace_bytes','graph_sha256')}
        if previous is not None and previous[1]*count/previous[0]>70:
            tests['dense_'+str(count)].update(playback_qualified=False,scope='Playback skipped: lower-density measurement projects beyond the 70% test budget.')
            print('  Playback skipped by projected CPU budget',flush=True)
            continue
        print('  Rendering and capturing audio',flush=True)
        result=measure(q,wav=ROOT/f'build/host/xiao-signal-reuse-dense{count}.wav')
        tests['dense_'+str(count)].update(result,playback_qualified=True)
        previous=(count,result['average_cpu_max_percent'])

    print('Rendering expanded graph with eight oscillators and deep control-rate phase modulation',flush=True)
    source=r'''SynthDef(\ReuseModulation, {
        var frequencies=Array.fill(8, { |i|
            var modulation=0;
            20.do { |j| modulation=SinOsc.kr(0.1+(i*0.01)+(j*0.001),modulation) };
            110*(i+1)+(modulation*2)
        });
        Out.ar(0,Splay.ar(SinOsc.ar(frequencies),1,0.04));
    })'''
    artifact=q.compile(source);q.install(artifact);q.rpc('prepare',stage='main')
    tests['expanded_modulation']={k:artifact[k] for k in ('nodes','signals','inputs','audio_buffers','scalar_values','signal_workspace_bytes','graph_sha256')}
    tests['expanded_modulation'].update(measure(q,wav=ROOT/'build/host/xiao-signal-reuse-modulation.wav'))

    print('Checking Main/FX sharing with different stereo tones and a swap effect',flush=True)
    q.load(r'SynthDef(\ReuseStereo, { Out.ar(0, SinOsc.ar([330,660]) * Rand(0.03,0.03)) })')
    q.load(r'SynthDef(\ReuseSwap, { arg gain=0.5; Out.ar(0, In.ar(0,2).reverse * gain) })','master')
    q.rpc('play',stage='fx');q.rpc('play',stage='main');time.sleep(.1)
    channels=q.capture(.5);frequencies=[]
    for channel in channels:
        crossings=sum(a<=0<b for a,b in zip(channel,channel[1:]))
        frequencies.append(crossings*44100/len(channel))
    require(abs(frequencies[0]-660)<=4 and abs(frequencies[1]-330)<=4,'Shared scratch corrupted stereo routing')
    tests['main_fx']=dict(frequencies_hz=frequencies,**levels(channels))
    require(100<tests['main_fx']['peak']<1000,'FX control storage overwrote the cached initial-rate Main amplitude')
    q.rpc('panic');time.sleep(.1)
    require(levels(q.capture(.2))['peak']==0,'Panic did not silence both graphs')
    tests['main_fx']['panic_silence']=True
    after=q.client.http('audio')
    report['diagnostic_deltas']={k:after.get(k,0)-before.get(k,0) for k in
        ('faults','clips','nonfinite','overflow','write_fail','partial','dma_event_overflow')}
    require(not any(report['diagnostic_deltas'].values()),'Audio fault counters changed')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--device-id',required=True)
    parser.add_argument('--report',type=Path,default=ROOT/'build/host/signal-reuse-device.json')
    args=parser.parse_args()
    q=Qualification(StudioClient(),args.device_id,ROOT/'build/host/private'/('signal-reuse-'+time.strftime('%Y%m%d-%H%M%S')+'.json'))
    error=None;report={}
    try:report=run(q)
    except BaseException as exc:error=exc;report=q.report;report['error']=str(exc)
    finally:
        print('Restoring original Main/FX and settings',flush=True)
        try:report['restored']=q.restore()
        except Exception as exc:
            report['restore_error']=str(exc)
            if error is None:error=exc
        q.client.close();report['passed']=error is None
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,indent=2)+'\n')
    if error:raise error
    print('PASS: expanded graph hardware checks; original packages restored',flush=True)


if __name__=='__main__':main()
