#!/usr/bin/env python3
"""Extended muted UGen/rate captures, bounded low-level UI soak and patch churn."""
import argparse,hashlib,json,re,struct,time
from pathlib import Path
from patches import ROOT,Device
from long_trace import collect,compare
from exercise_timing import collect_exercise

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--rounds',type=int,choices=range(0,31),default=6);p.add_argument('--churn',type=int,choices=range(0,101),default=10)
    p.add_argument('--resume',action='store_true');p.add_argument('--plan',type=Path,default=ROOT/'evidence/long-trace-plan.json');args=p.parse_args()
    plan=json.loads(args.plan.read_text());assert plan['passed']
    report={'passed':False,'status':'incomplete','captures':[],'exercises':[],'saved_patch_writes':False,'capture_blocks_per_graph':8192}
    if args.resume and args.output.exists():
        old=json.loads(args.output.read_text());report['captures']=old.get('captures',[])
    def save():args.output.write_text(json.dumps(report,indent=2)+'\n')
    save();logpath=args.output.with_suffix('.log')
    with logpath.open('ab' if args.resume else 'wb') as log:
        d=Device(args.port,log);effect=None;initial_slot=1;before=None
        def wait(seconds):
            until=time.monotonic()+seconds
            while time.monotonic()<until:list(d.lines())
        def packages():
            entries={}
            for item in d.request('LIST'):
                if item['slot'] and item['name']:
                    d.request('LOAD',bytes([item['slot']]));a,b,info=d.download()
                    entries[str(item['slot'])]={'graph':hashlib.sha256(a).hexdigest(),'source':hashlib.sha256(b).hexdigest(),'metadata':info['manifest'][152:]}
            return entries
        try:
            hello=d.hello();report['hello']=hello
            expected=re.search(r'#define BUILD_ID "(.*?)"',(ROOT/'firmware/main/generated.h').read_text())[1]
            assert hello['build']==expected and hello['policy']=='fm1-compat-v1'
            if args.resume:assert old.get('hello',hello)['build']==hello['build'],'Cannot combine different firmware images'
            d.link.write(b'x');d.request('PANIC');initial_slot=d.request('STATUS')['slot']
            effect=d.request('FX');before=d.request('LIST');report['initial_library']=before
            report['initial_packages']=packages();save()
            completed={r['id'] for r in report['captures']}
            for index,job in enumerate(plan['jobs']):
                if job['id'] in completed:continue
                raw=(ROOT/job['graph']).read_bytes();assert hashlib.sha256(raw).hexdigest()==job['graph_sha256']
                active=d.upload(raw,b'// Temporary long-capture diagnostic; not a musical patch.\n','Check '+job['id'][:24])
                assert active['graph_sha256']==job['graph_sha256']
                header,data=collect(d);comparison=compare(header,data,job)
                result={'id':job['id'],'graph_sha256':job['graph_sha256'],'type_rates':job['type_rates'],'device':header,'comparison':comparison}
                if 'selectors' in job:result.update(operator_selectors=job['selectors'],operator_rate=job['rate'])
                report['captures'].append(result);save()
                print(f'{index+1}/{len(plan["jobs"])} {job["id"]}: {comparison["comparison"]}; peak error {comparison["peak_error"]:.6g}; kernel max {header["max_us"]} us',flush=True)
            # Playback uses only known saved example voices, at reduced level.
            if args.churn:
                offset=log.tell()
                for cycle in range(args.churn):
                    for slot in (1,4,2,3):
                        d.request('LOAD',bytes([slot]));d.link.write(b'['*8);d.link.write(b'n');wait(.15);d.link.write(b'o');wait(.1)
                    print(f'Patch-change cycle {cycle+1}/{args.churn}',flush=True)
                d.request('PANIC');wait(1.2)
                text=logpath.read_bytes()[offset:].decode(errors='replace')
                keys=['write_fail','partial','dma_event_overflow','faults','clips','nonfinite','overflow']
                maximum={key:max(map(int,re.findall(r'\b'+key+r'=(\d+)',text)),default=0) for key in keys}
                report['patch_churn']={'cycles':args.churn,'patch_activations':args.churn*4,'fault_counters':maximum,'passed':not any(maximum.values())};save()
            if args.rounds:
                for name in ('filtered','phase-fm','additive'):
                    active=d.install_catalog(name,diagnostic=True);d.link.write(b'['*6)
                    offset=log.tell();print('Extended playback/UI soak: '+name,flush=True)
                    exercise=collect_exercise(d,logpath,hello,active,args.rounds,offset);exercise['patch']=name;exercise['requested_amp']=.2
                    report['exercises'].append(exercise);save()
            report['final_packages']=packages();report['packages_unchanged']=report['initial_packages']==report['final_packages']
            covered={tuple(pair) for result in report['captures'] if result['comparison']['passed'] for pair in result['type_rates']}
            missing=set(map(tuple,plan['expected_type_rates']))-covered
            report['type_rates_covered']=sorted(covered);report['missing_fixture_type_rates']=sorted(missing)
            report['passed']=not missing and report['packages_unchanged'] and all(r['comparison']['passed'] for r in report['captures']) and all(
                r['reported_output_checks_passed'] and r['timing_budget_passed'] for r in report['exercises']) and report.get('patch_churn',{}).get('passed',True)
            report['status']='complete'
        except Exception as error:report['error']=repr(error);raise
        finally:
            try:
                d.link.write(b'x');d.request('PANIC')
                if effect:d.request('FX',struct.pack('<fff',*[effect[k] for k in ('time','feedback','wet')]))
                d.request('LOAD',bytes([initial_slot if initial_slot>=0 else 1]));report['final_status']=d.request('STATUS')
                if before is not None:
                    report['final_library']=d.request('LIST');report['library_unchanged']=report['final_library']==before
                    if not report['library_unchanged']:report['passed']=False
            finally:d.link.write(b'!');d.close();save()
    print(json.dumps({k:report[k] for k in ('passed','status','library_unchanged')},indent=2),flush=True)
    return report['passed']

if __name__=='__main__':raise SystemExit(0 if main() else 1)
