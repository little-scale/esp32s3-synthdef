#!/usr/bin/env python3
"""Compare real-control Rings voices, exercise the UI, and restore saved state."""
import argparse,hashlib,json,re,struct
from pathlib import Path
from patches import ROOT,Device
from engine_profile import generate
import profile_timing as matrix
from exercise_timing import collect_exercise

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--port',required=True);p.add_argument('--output',type=Path,required=True)
p.add_argument('--rounds',type=int,choices=range(0,11),default=1)
p.add_argument('--arena-storage',choices=('internal','PSRAM'),default='internal')
args=p.parse_args()
matrix.ENGINE=generate(ROOT/'build/host/rings-matrix/src','fm1').parent
renderer=matrix.compile_renderer()
report=dict(passed=False,status='incomplete',matrices=[],exercises=[],requested_rounds=args.rounds,expected_arena_storage=args.arena_storage,saved_patch_writes=False)
def save():args.output.write_text(json.dumps(report,indent=2)+'\n')
save();logpath=args.output.with_suffix('.log')
with logpath.open('wb') as log:
    d=Device(args.port,log);effect=None;slot=1;before=None
    def packages():
        result={}
        for item in d.request('LIST'):
            if item['slot'] and item['name']:
                d.request('LOAD',bytes([item['slot']]));graph,source,info=d.download()
                result[str(item['slot'])]=dict(graph=hashlib.sha256(graph).hexdigest(),
                    source=hashlib.sha256(source).hexdigest(),metadata=info['manifest'][152:])
        return result
    try:
        hello=d.hello();report['hello']=hello
        assert hello['policy']=='fm1-compat-v1'
        assert hello['build']==re.search(r'#define BUILD_ID "(.*?)"',(ROOT/'firmware/main/generated.h').read_text())[1]
        d.link.write(b'x');d.request('PANIC');slot=d.request('STATUS')['slot']
        effect=d.request('FX');before=d.request('LIST');report['initial_packages']=packages();save()
        for model in range(1,7):
            graph=ROOT/f'build/host/rings-voices/rings-{model}.scsyndef';offset=log.tell()
            active=d.upload(graph.read_bytes(),(ROOT/'examples/rings-benchmarks.scd').read_bytes(),f'Rings model {model}',labels=('PITCH','STRUCTURE','BRIGHTNESS','DAMPING'))
            arena=re.findall(r'Voice arena required=(\d+) capacity=(\d+) storage=(\w+)',logpath.read_bytes()[offset:].decode(errors='replace'))
            assert arena and arena[-1][2]==args.arena_storage,arena
            result=matrix.collect_matrix(d,active,graph,f'rings-{model}',renderer)
            result.update(model=model,arena=dict(required_samples=int(arena[-1][0]),capacity_samples=int(arena[-1][1]),storage=arena[-1][2]))
            result['phase_maximum_us']={key:max(case[key] for case in result['cases']) for key in ('reset','controls','prepare','dsp','pcm','total','live')}
            report['matrices'].append(result);save();print(f'Rings {model}: 280-case matrix passed',flush=True)
            if args.rounds:
                d.link.write(b'['*6);offset=log.tell()
                exercise=collect_exercise(d,logpath,hello,active,args.rounds,offset)
                exercise.update(patch=f'rings-{model}',requested_amp=.2)
                exercise['scope']='Pitch, structure, brightness and damping at 25 Hz; three master delay controls; five note starts/second; fixed 5 ms attack / 150 ms release. No physical continuity claim.'
                report['exercises'].append(exercise);save()
                print(f'Rings {model}: UI combined max {exercise["maximum"]["combined_max_us"]} us; margin passed {exercise["timing_budget_passed"]}',flush=True)
        if args.rounds:
            for name in ('filtered','phase-fm','additive'):
                active=d.install_catalog(name,diagnostic=True);d.link.write(b'['*6);offset=log.tell()
                exercise=collect_exercise(d,logpath,hello,active,args.rounds,offset)
                exercise.update(patch=name,requested_amp=.2);report['exercises'].append(exercise);save()
                print(f'{name}: UI combined max {exercise["maximum"]["combined_max_us"]} us',flush=True)
        report['final_packages']=packages();report['packages_unchanged']=report['initial_packages']==report['final_packages']
        text=logpath.read_text(errors='replace')
        report['minimum']={key:min(map(int,re.findall(r'\b'+key+r'=(\d+)',text))) for key in ('internal_min','internal_largest','stack_free_bytes','controls_stack_free_bytes')}
        report['output_checks_passed']=report['packages_unchanged'] and all(e['reported_output_checks_passed'] for e in report['exercises'])
        report['timing_margin_passed']=all(e['timing_budget_passed'] for e in report['exercises'])
        report['passed']=report['output_checks_passed'] and report['timing_margin_passed'];report['status']='complete'
    except Exception as error:report['error']=repr(error);raise
    finally:
        try:
            d.link.write(b'x');d.request('PANIC')
            if effect:d.request('FX',struct.pack('<fff',*[effect[k] for k in ('time','feedback','wet')]))
            d.request('LOAD',bytes([slot if slot>=0 else 1]));report['final_status']=d.request('STATUS')
            if before is not None:
                report['library_unchanged']=d.request('LIST')==before
                if not report['library_unchanged']:report['passed']=False
        finally:d.link.write(b'!');d.close();save()
print(json.dumps({key:report[key] for key in ('passed','status','library_unchanged')},indent=2))
raise SystemExit(0 if report['passed'] else 1)
