/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "instrument.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static fm_graph g;
static fm_voice v;
static fm_scratch scratch;
static instrument s;
static void load(const char *path)
{
    unsigned char bytes[65536];char error[160];FILE *f=fopen(path,"rb");assert(f);
    size_t n=fread(bytes,1,sizeof bytes,f);assert(!ferror(f));fclose(f);
    assert(fm_load(&g,bytes,n,error,sizeof error));
    assert(instrument_init(&s,&g,&v,&scratch,NULL,0,44100));
}
static unsigned values(float out[32])
{
    unsigned count=0;memset(out,0,32*sizeof(float));
    for(unsigned i=0;i<g.nodes;++i)if(g.node[i].type==FM_Rand){assert(count<32);out[count++]=v.state[i].initial_value;}
    return count;
}
int main(int argc,char **argv)
{
    assert(argc==3);load(argv[1]);float a[32],b[32],audio[128];
    assert(instrument_arm_bus(&s));assert(values(a)==15 && s.seed_active==0);
    assert(instrument_arm_bus(&s));assert(values(b)==15 && !memcmp(a,b,sizeof a));
    instrument_randomize(&s,12345);assert(instrument_arm_bus(&s));values(a);assert(s.seed_active==12345);
    assert(instrument_arm_bus(&s));values(b);assert(s.seed_active==12345u+0x9e3779b9u && memcmp(a,b,sizeof a));
    uint32_t active=s.seed_active,next=s.seed_next;
    instrument_render_stereo(&s,audio);instrument_suspend(&s);assert(instrument_resume(&s));
    values(a);assert(!memcmp(a,b,sizeof a) && s.seed_active==active && s.seed_next==next);
    /* A suspended constructor must reuse its selected seed on retry. */
    s.defer_note_render=1;assert(instrument_arm_bus(&s));values(a);active=s.seed_active;next=s.seed_next;
    instrument_suspend(&s);assert(s.suspended_restart && instrument_resume(&s));values(b);
    assert(!memcmp(a,b,sizeof a) && s.seed_active==active && s.seed_next==next);
    instrument_suspend(&s);instrument_panic(&s);assert(instrument_resume(&s) && !v.active);
    load(argv[2]);instrument_randomize(&s,9876);inst_event on={INST_NOTE_ON,1,0};
    assert(instrument_apply(&s,&on) && s.seed_active==9876);on.note_id=2;
    assert(instrument_apply(&s,&on) && s.seed_active==9876u+0x9e3779b9u);
    puts("PASS: fixed starts repeat, randomized starts choose different Rand values, notes advance seeds, maintenance/constructor retries preserve values, and Panic stays stopped.");
}
