#!/usr/bin/env python3
"""Capture the raw, unclamped contact-count register during a muted touch test."""
import argparse,json,re,time
from pathlib import Path
from patches import Device

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',required=True);p.add_argument('--output',type=Path,required=True)
args=p.parse_args();report={'complete':False,'audio_parked_during_capture':True,'register_configuration_writes':False,'physical_sequence_confirmed':None}
def save():args.output.write_text(json.dumps(report,indent=2)+'\n')
save()
with args.output.with_suffix('.log').open('wb') as log:
    d=Device(args.port,log)
    try:
        report['hello']=d.hello();d.request('PANIC')
        initial={'status':d.request('STATUS'),'library':d.request('LIST'),'effect':d.request('FX')};report['initial']=initial;save()
        d.link.write(b'q');deadline=time.monotonic()+80;events=[];summary=None
        while time.monotonic()<deadline and summary is None:
            for line in d.lines():
                text=line.decode(errors='replace').strip()
                if text.startswith('TOUCH_BEGIN '):report['begin']=text;save();print(text,flush=True)
                match=re.fullmatch(r'TOUCH_RAW ms=(\d+) contacts=(\d+) x=(\d+) y=(\d+) raw=([0-9a-f]+)',text)
                if match:
                    ms,contacts,x,y=map(int,match.groups()[:4]);events.append(dict(ms=ms,contacts=contacts,x=x,y=y,raw=match[5]))
                if text.startswith('TOUCH_END '):summary=text;print(text,flush=True);break
        assert summary is not None,'No complete raw capture'
        report.update(complete=True,summary=summary,changed_reports=events,observed_contact_counts=sorted({e['contacts'] for e in events}))
        d.request('PANIC');report['final_status']=d.request('STATUS')
        report['saved_library_unchanged']=d.request('LIST')==initial['library']
        report['effect_unchanged']=d.request('FX')==initial['effect']
        assert report['saved_library_unchanged'] and report['effect_unchanged'] and not report['final_status']['reset_required']
        assert report['final_status']['slot']==initial['status']['slot'];save()
        print(json.dumps({k:report[k] for k in ('complete','summary','observed_contact_counts','saved_library_unchanged','effect_unchanged')},indent=2),flush=True)
    finally:d.close()
