#!/usr/bin/env python3
"""Embed the bounded, muted QA pack and exact host replay schedule. No device I/O."""
import argparse
import hashlib
import json
from pathlib import Path
from plan_dsp_hardware import ROOT, build_plan


def prepare(folder):
    plan=build_plan();folder.mkdir(parents=True,exist_ok=True)
    text=(ROOT/'tests/dsp_kernels_test.c').read_text()
    start=text.index('    static const float freq[]=')
    end=text.index('    float oa[FM_BLOCK*2]',start)
    body='\n'.join(line for line in text[start:end].splitlines() if not line.lstrip().startswith('#'))
    body=body.replace('set("','fm_set(v,g,"')
    initial=text[text.index('     if(strstr(argv[file],"core_dynamic_Blip"))'):text.index('     assert(fm_start(')]
    initial='\n'.join(line for line in initial.splitlines() if not line.lstrip().startswith('#'))
    initial=initial.replace('argv[file]','file')
    body=body.replace('argv[file]','file')
    schedule='/* Extracted verbatim arithmetic/control schedules from tests/dsp_kernels_test.c. */\n'
    schedule+='static void qa_initial(const char *file,float sr,float *bank){\n'+initial+'\n}\n'
    schedule+='static void qa_controls(const char *file,unsigned block,float sr,float *bank,fm_voice *v,const fm_graph *g){\n'+body+'\n}\n'
    (folder/'qa_schedule_generated.h').write_text(schedule)
    rows=[];data=[]
    for i,name in enumerate(plan['fixture_sets']['first_session']):
        raw=(ROOT/plan['fixtures'][name]['path']).read_bytes()
        data.append('static const unsigned char qa_data_%u[]={%s};'%(i,','.join(map(str,raw))))
        blocks=32 if 'Binary_signed_zero_' in name else 256
        rows.append('{"%s",qa_data_%u,sizeof qa_data_%u,%u}'%(name,i,i,blocks))
    pack='\n'.join(data)+'\nstatic const qa_fixture qa_fixtures[]={\n'+',\n'.join(rows)+'\n};\n'
    pack_hash=hashlib.sha256((pack+schedule).encode()).hexdigest()
    (folder/'qa_pack_generated.h').write_text('#define QA_PACK_SHA256 "'+pack_hash+'"\n'+pack)
    (folder/'qa_pack.json').write_text(json.dumps(dict(pack_sha256=pack_hash,fixtures={name:plan['fixtures'][name]['sha256'] for name in plan['fixture_sets']['first_session']},schedule_sha256=hashlib.sha256(schedule.encode()).hexdigest()),indent=2)+'\n')
    print('Prepared',len(rows),'muted QA fixtures; pack',pack_hash[:12])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    prepare(p.parse_args().output)
