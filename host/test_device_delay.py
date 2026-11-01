#!/usr/bin/env python3
"""Check target delay impulses, control validation, persistent tails and settings."""
import argparse,json,re,struct,subprocess,time,zlib
from pathlib import Path
from patches import Device,ROOT
from prepare import ENGINE,FLAGS
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
report={'passed':False,'status':'incomplete'};args.output.write_text(json.dumps(report)+'\n')
exe=ROOT/'build/host/delay-matrix';reference=ROOT/'build/host/delay-matrix.f32'
subprocess.run(['cc',*FLAGS,'-I'+str(ENGINE/'src'),'-I'+str(ROOT/'firmware/components/instrument/include'),str(ENGINE/'src/fm_load.c'),str(ENGINE/'src/fm_render.c'),str(ROOT/'firmware/components/instrument/master_delay.c'),str(ROOT/'tests/delay_matrix.c'),'-lm','-o',str(exe)],check=True)
subprocess.run([str(exe),str(ROOT/'examples/master-delay.scsyndef'),str(reference)],check=True)
log_path=args.output.with_suffix('.log')
with log_path.open('wb') as log:
    d=Device(args.port,log);original=None;verification_complete=False
    def wait(seconds):
        until=time.monotonic()+seconds
        while time.monotonic()<until:list(d.lines())
    def set_fx(values):return d.request('FX',struct.pack('<fff',*values))
    try:
        hello=d.hello();report['hello']=hello
        assert hello['build']==re.search(r'#define BUILD_ID "(.*?)"',(ROOT/'firmware/main/generated.h').read_text())[1]
        original=d.request('FX');report['original']=original
        d.request('LOAD',b'\1');d.link.write(b'e');lines=[];end=False;until=time.monotonic()+35
        while time.monotonic()<until and not end:
            for raw in d.lines():
                line=raw.rstrip(b'\r')
                if line.startswith(b'DELAY_BENCH_'):lines.append(line.decode())
                if line==b'DELAY_BENCH_END':end=True;break
        assert end and len(lines)==6,lines[-2:]
        header=dict(re.findall(r'(\w+)=(\d+)',lines[0]));assert header['failures']=='0' and header['cases']=='4'
        actual=b''
        for i,line in enumerate(lines[1:-1]):
            _,index,checksum,hexdata=line.split();raw=bytes.fromhex(hexdata)
            assert int(index)==i and len(raw)==1024 and zlib.crc32(raw)==int(checksum,16);actual+=raw
        a=struct.unpack('<1024f',actual);b=struct.unpack('<1024f',reference.read_bytes())
        peak=max(abs(x-y) for x,y in zip(a,b));assert peak<=1e-6,peak
        report['numerical']={'passed':True,'max_float_error':peak,'limit':1e-6,'samples':1024,'times':[.02,.35,1,5],'scope':'first/second echo windows and post-panic zeros from the actual parked audio owner'}
        baseline=d.request('FX')
        for values in [(0,.35,.25),(5.01,.35,.25),(.35,.81,.25),(.35,.35,1.01),(float('nan'),.35,.25)]:
            try:set_fx(values)
            except RuntimeError:pass
            else:raise AssertionError('Invalid effect controls accepted')
            assert d.request('FX')==baseline
        report['invalid_controls_retain_previous']=True
        set_fx([.5,.5,1]);wait(1.2)
        offset=log.tell();d.link.write(b'n');wait(.08);d.link.write(b'o');wait(.4)
        d.link.write(b'n');wait(.08);d.link.write(b'o');wait(3)
        text=log_path.read_bytes()[offset:].decode(errors='replace')
        tails=list(map(int,re.findall(r'tail_blocks=(\d+)',text)));resets=list(map(int,re.findall(r'\bresets=(\d+)',text)))
        assert tails and tails[-1]>tails[0] and len(set(resets))==1
        report['tail_across_retrigger']={'passed':True,'tail_blocks':tails[-1]-tails[0],'resets_during_notes':0}
        d.request('PANIC');wait(1.5)
        recent=log_path.read_text(errors='replace')
        assert re.findall(r'\bpcm_peak=(\d+)',recent)[-1]=='0'
        assert int(re.findall(r'\bresets=(\d+)',recent)[-1])>resets[-1]
        report['panic_cleared_tail']=True
        for key in ['write_fail','partial','dma_event_overflow','faults','clips','nonfinite','overflow']:
            values=list(map(int,re.findall(r'\b'+key+r'=(\d+)',recent)));assert values and max(values)==0,(key,values[-3:])
        saved=set_fx([5,.75,.5]);d.request('FXSAVE');d.close()
        restart_offset=log.tell();d=Device(args.port,log);d.hello();loaded=d.request('FX')
        assert loaded==saved
        report['saved_settings_readback']=loaded
        report['restart_observed']=b'ESP-ROM:' in log_path.read_bytes()[restart_offset:]
        verification_complete=True
    except Exception as error:
        report['error']=repr(error);raise
    finally:
        try:
            d.request('PANIC')
            if original:set_fx([original['time'],original['feedback'],original['wet']]);d.request('FXSAVE')
            d.request('LOAD',b'\1');report['final_effect']=d.request('FX')
            if verification_complete:report['passed']=True;report['status']='complete'
        finally:
            d.close();args.output.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
