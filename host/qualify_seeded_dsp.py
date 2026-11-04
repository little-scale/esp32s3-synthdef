#!/usr/bin/env python3
"""Prepare pinned graphs, or explicitly time them on one muted USB module."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import qualify_dsp_workloads as workloads
from patches import ROOT,compile_source
from seeded_fixtures import fixtures as target_fixtures


def prepare(directory,suite='musical'):
    directory.mkdir(parents=True,exist_ok=True)
    result={}
    for name,source in (workloads.timing.FIXTURES if suite=='musical' else target_fixtures(suite)).items():
        path=directory/(name+'.scd');path.write_text(source)
        graph=directory/(name+'.scsyndef')
        compile_source(path,graph,'/Applications/SuperCollider.app/Contents/MacOS/sclang')
        data=graph.read_bytes()
        result[name]=dict(source=source,graph=base64.b64encode(data).decode(),graph_sha256=hashlib.sha256(data).hexdigest())
    path=directory/'plan.json';path.write_text(json.dumps(result,indent=2)+'\n');return path


def compare(reference,current):
    assert reference['passed'] and current['passed'] and reference['fixed_seed'] and current['fixed_seed']
    assert reference['device_id']==current['device_id'],'Physical module changed'
    assert reference['fixtures'].keys()==current['fixtures'].keys(),'Fixture set changed'
    rows={}
    for name,ref in reference['fixtures'].items():
        new=current['fixtures'][name]
        assert ref['graph_sha256']==new['graph_sha256'],'Graph changed: '+name
        for sample in ref['runs']+new['runs']:
            setup=sample['setup'];first=ref['runs'][0]['setup']
            for key in ('mode','seed','warm_blocks','rate','frames','nodes','cpu_mhz','warm_sha256','audio_sha256','rng'):
                assert setup[key]==first[key],f'{name}: {key} differs'
        rows[name]=dict(baseline_us=ref['median_us'],candidate_us=new['median_us'],
                        less_time_percent=100*(1-new['median_us']/ref['median_us']))
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepare',type=Path)
    p.add_argument('--suite',choices=('musical','smooth','core','delay'),default='musical')
    p.add_argument('--plan',type=Path);p.add_argument('--device-id');p.add_argument('--phase')
    p.add_argument('--output',type=Path);p.add_argument('--compare',type=Path)
    p.add_argument('--runs',type=int,choices=range(1,6),default=3);a=p.parse_args()
    if a.prepare:
        if any((a.plan,a.device_id,a.phase,a.output,a.compare)):p.error('Preparation is computer-only; use separately')
        print(prepare(a.prepare,a.suite));return
    if a.suite!='musical':p.error('--suite selects computer-only preparation; timing uses --plan')
    if not all((a.plan,a.device_id,a.phase,a.output)):p.error('Timing requires --plan --device-id --phase --output')
    plan=json.loads(a.plan.read_text())
    report=workloads.timing.run(a.device_id,a.phase,a.runs,a.output,fixed=True,plan=plan)
    if a.compare:
        try:
            rows=compare(json.loads(a.compare.read_text()),report)
            report['comparison']=dict(passed=True,reference=str(a.compare),fixtures=rows)
        except (AssertionError,KeyError,ValueError) as error:
            report['passed']=False
            report['comparison']=dict(passed=False,reference=str(a.compare),error=str(error))
            raise
        finally:a.output.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report['comparison'],indent=2))


if __name__=='__main__':main()
