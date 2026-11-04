#!/usr/bin/env python3
"""Run the explicit muted, embedded replay on one identified USB XIAO.

No firmware flashing or package writes. Studio must release USB first.
"""
import argparse
import json
from pathlib import Path
import re
import time
from patches import Device,ROOT


def collect(device,expected,timeout=180):
    device.link.write(b'q');lines=[];until=time.monotonic()+timeout
    while time.monotonic()<until:
        for raw in device.lines():
            line=raw.decode(errors='replace').strip()
            if not line.startswith('DSPQA_'):continue
            lines.append(line)
            if line=='DSPQA_END':
                header=dict(re.findall(r'(\w+)=([^ ]+)',lines[0]))
                rows=[dict(re.findall(r'(\w+)=([^ ]+)',line)) for line in lines if line.startswith('DSPQA_CASE ')]
                assert header['candidates']==expected,('Wrong candidate image',header)
                assert int(header['cases'])==int(header['complete'])==len(rows)==50,header
                assert re.fullmatch('[0-9a-f]{64}',header['pack']),'Invalid pack identity'
                assert [int(row['index']) for row in rows]==list(range(50)),'Missing/duplicate/reordered QA cases'
                for row in rows:
                    assert int(row['blocks']) in (32,256)
                    assert 0<=int(row['fault_blocks'])<=int(row['blocks'])
                    assert 0<=int(row['arena_samples'])<=262144
                    assert int(row['constructors'])==int(row['blocks'])//128+(int(row['blocks'])<128)
                    assert all(re.fullmatch('[0-9a-f]{64}',row['h'+str(k)]) for k in range(4)),'Invalid digest'
                return dict(header=header,cases=rows,passed=True,lines=lines)
    raise TimeoutError('DSPQA_END not received')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',required=True)
    p.add_argument('--device-id',required=True);p.add_argument('--candidates',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--compare',type=Path)
    a=p.parse_args();report=dict(passed=False,hardware=True,device_id=a.device_id,candidates=a.candidates,package_writes=False)
    log=ROOT/'build/host/private'/('dsp-qa-'+str(time.time_ns())+'.log');log.parent.mkdir(parents=True,exist_ok=True)
    try:
        with log.open('wb') as stream:
            d=Device(a.port,stream)
            try:
                hello=d.request('HELLO',timeout=20,retries=0);assert hello['device_id']==a.device_id
                report['hello']=hello;d.request('PANIC');d.request('VOLUME',b'\0')
                report.update(collect(d,a.candidates))
                if a.compare:
                    baseline=json.loads(a.compare.read_text());assert baseline['device_id']==a.device_id
                    assert baseline['header']['pack']==report['header']['pack'],'Replay pack changed'
                    mismatches=[]
                    for ref,row in zip(baseline['cases'],report['cases']):
                        for key in ('index','blocks','arena_samples','fault_blocks','constructors','h0','h1','h2','h3'):
                            if ref[key]!=row[key]:mismatches.append(dict(index=row['index'],field=key,before=ref[key],after=row[key]))
                    report['comparison']=dict(reference=str(a.compare),mismatches=mismatches,passed=not mismatches)
                    report['passed']=not mismatches
            finally:d.close()
    except BaseException as error:
        report['passed']=False;report['error']=str(error);raise
    finally:
        a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('hello','cases','lines')},indent=2))
    return report['passed']


if __name__=='__main__':raise SystemExit(0 if main() else 1)
