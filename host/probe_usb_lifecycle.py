#!/usr/bin/env python3
"""Read-only native USB reopen/backpressure probe for one identified module.

No firmware writes, reset requests, patch uploads or volume changes. Opening
uses the selected modem-line policy; the boot-ID checks detect unintended resets.
Studio releases USB during the probe and reattaches only after a healthy final
handshake. Raw console bytes stay in a private log; public reports contain only
identity, boot/revision, timing and byte counts.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time

from patches import Device, ROOT, frame
from studio_client import StudioClient


def serial_id(target):
    if not target.startswith('esp32-'):
        raise ValueError('Use a permanent esp32-<12 hex digits> ID')
    value=target[6:]
    if len(value)!=12 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('Use a permanent esp32-<12 lowercase hex digits> ID')
    return value


def find_port(target, inventory=None):
    if inventory is None:
        from serial.tools import list_ports
        inventory=list_ports.comports()
    expected=serial_id(target)
    matches=[p.device for p in inventory
             if p.vid==0x303a and p.pid==0x1001 and
             (p.serial_number or '').replace(':','').lower()==expected]
    if len(matches)!=1:
        raise RuntimeError('Exact target USB port is absent or ambiguous')
    return matches[0]


class PrivateLog:
    def __init__(self,path):
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        self.file=os.fdopen(fd,'wb');self.bytes=0;self.pending=b'';self.resets=[]
    def write(self,data):
        self.bytes+=len(data);self.file.write(data);self.pending+=data
        while b'\n' in self.pending:
            line,_,self.pending=self.pending.partition(b'\n')
            match=re.search(rb'rst:0x([0-9a-fA-F]+) \(([A-Z0-9_]+)\)',line)
            if match:self.resets.append(dict(reason_hex=match[1].decode(),name=match[2].decode()))
        if len(self.pending)>16384:self.pending=b''
    def flush(self):self.file.flush()
    def close(self):self.file.close()


def snapshot(device,target,startup=False):
    started=time.monotonic()
    # macOS may reset native USB hardware during open. Allow that boot to
    # complete on the SAME handle; only repeat the idempotent HELLO query.
    hello=device.request('HELLO',timeout=2,retries=4 if startup else 0)
    if hello.get('device_id')!=target:
        raise RuntimeError('Physical USB identity changed')
    remote=device.request('RCINFO',bytes([0,0]),timeout=2,retries=0)
    status=device.request('STATUS',timeout=2,retries=0)
    volume=device.request('VOLUME',timeout=2,retries=0)
    return dict(device_id=target,build=hello['build'],boot=remote['boot'],
                revision=remote['revision'],uptime_us=remote['now_us'],
                active=remote['active'],graph_sha256=status['graph_sha256'],
                volume_percent=volume['percent'],elapsed_ms=round((time.monotonic()-started)*1000,3))


def pause(seconds):
    # Deliberately do not read serial: distinguish an open, unread port from a
    # closed port. Keep long waits visible without monopolising a tool call.
    end=time.monotonic()+seconds;next_notice=time.monotonic()+20
    while time.monotonic()<end:
        time.sleep(max(0,min(.25,end-time.monotonic())))
        if time.monotonic()>=next_notice:
            print('USB idle observation continues',flush=True);next_notice+=20


def probe_case(device,target,mode,gap,log,open_policy='auto'):
    before=snapshot(device,target);start_bytes=log.bytes
    if mode=='closed':
        device.close();device=None;pause(gap)
        device=Device(find_port(target),log,open_policy=open_policy)
    elif mode=='unread':pause(gap)
    elif mode=='partial':
        # Leave an unfinished read-only frame, like a host leaving mid-command.
        # A new @-prefixed frame must resynchronise the firmware parser.
        device.link.write(frame(123456,'HELLO',b'')[:9]);pause(gap)
    else:raise ValueError('Unknown probe mode')
    try:
        after=snapshot(device,target,startup=mode=='closed')
        assert before['boot']==after['boot'],'MCU rebooted during a no-reset probe'
        assert before['revision']==after['revision'],'Instance binding changed'
        assert before['graph_sha256']==after['graph_sha256'],'Active graph changed'
        assert before['volume_percent']==after['volume_percent'],'Volume changed'
        assert before['active']==after['active'],'Instance activity changed'
        assert after['uptime_us']>before['uptime_us'],'Device uptime did not advance'
    except BaseException:
        if mode=='closed':device.close()
        raise
    return device,dict(mode=mode,gap_seconds=gap,before=before,after=after,
                       rx_bytes=log.bytes-start_bytes,passed=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--device-id',required=True)
    p.add_argument('--gaps',default='0.2,2,5,15')
    p.add_argument('--modes',default='unread,partial,closed')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--open-policy',choices=('auto','legacy','atomic'),default='auto')
    p.add_argument('--repeat',type=int,choices=range(1,101),default=1)
    args=p.parse_args();serial_id(args.device_id)
    gaps=[float(x) for x in args.gaps.split(',')];modes=args.modes.split(',')
    if not gaps or any(not 0<=x<=300 for x in gaps):p.error('Use idle gaps from 0 to 300 seconds')
    if not modes or any(m not in ('unread','partial','closed') for m in modes):p.error('Use unread,partial,closed modes')
    # Refuse absence before disconnecting Studio or creating a hardware report.
    port=find_port(args.device_id)
    client=StudioClient();device=None;log=None;healthy=False;released=False
    report=dict(passed=False,hardware=True,device_id=args.device_id,
                date_utc=datetime.now(timezone.utc).isoformat(),saved_patch_writes=False,
                volume_changes=False,firmware_writes=False,reset_requests=False,open_policy=args.open_policy,
                repeats=args.repeat,cases=[])
    from serial_port import select_policy
    report['effective_open_policy']=select_policy(port,args.open_policy)
    try:
        state=client.http('config')
        if state['connected']:
            state=client.http('refresh',{})
            if state['hello']['device_id']!=args.device_id:
                raise RuntimeError('Studio is connected to another module; leave it unchanged')
            client.http('disconnect',{});released=True
        log=PrivateLog(ROOT/'build/host/private'/f'usb-probe-{time.time_ns()}.log')
        device=Device(port,log,open_policy=args.open_policy);report['initial']=snapshot(device,args.device_id,startup=True);healthy=True
        if report['initial']['volume_percent']>5:
            raise RuntimeError('Set the module volume to at most 5% before this read-only probe')
        for repeat in range(args.repeat):
            for mode in modes:
                for gap in gaps:
                    healthy=False
                    report['active_case']=dict(mode=mode,gap_seconds=gap,iteration=repeat+1,rx_bytes_before=log.bytes)
                    device,row=probe_case(device,args.device_id,mode,gap,log,args.open_policy)
                    row['iteration']=repeat+1
                    healthy=True;report['cases'].append(row)
                    print(f'PASS {mode}: {gap:g}s; same boot and patch; {row["rx_bytes"]} RX bytes',flush=True)
        report['passed']=True
    except BaseException as error:
        report['error_type']=type(error).__name__;report['error']=str(error)
        if 'active_case' in report and log is not None:
            report['failed_case']=dict(report['active_case'],rx_bytes_after=log.bytes)
        try:report['port_still_present']=bool(find_port(args.device_id))
        except RuntimeError:report['port_still_present']=False
        raise
    finally:
        if device is not None:device.close()
        if log is not None:
            report['rx_bytes_total']=log.bytes;report['usb_reset_boot_messages']=log.resets;log.close()
        try:
            if healthy:
                state=client.http('connect',dict(port=find_port(args.device_id)))
                assert state['hello']['device_id']==args.device_id
                info=client.rpc('info',dict(target=args.device_id,stage='main'))['results'][0]
                assert info['boot']==report['initial']['boot'],'Studio reattachment rebooted the module'
                report['studio_final_boot']=info['boot']
                report['studio_reattached']=True
            elif released:
                report['studio_reattached']=False
        except Exception as error:
            report['studio_error']=str(error);report['passed']=False
        finally:
            client.close();args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(report,indent=2)+'\n')
    print('USB lifecycle probes complete; no reset or patch/volume writes',flush=True)


if __name__=='__main__':main()
