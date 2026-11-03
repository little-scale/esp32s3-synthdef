/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "remote_control.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static fm_graph g;static fm_voice voice;static fm_scratch scratch;static instrument synth;static remote_control rc;
static fm_graph fx_graph;static fm_voice fx_voice;static master_delay fx;
static int index_of(const char *name){for(unsigned i=0;i<g.names;++i)if(!strcmp(g.control_name[i].name,name))return g.control_name[i].index;return -1;}
static rc_event message(unsigned stream,unsigned sequence,unsigned kind,uint64_t at){rc_event e={0};e.boot=rc.boot;e.revision=rc.stage[0].revision;e.stream=stream;e.sequence=sequence;e.kind=kind;e.at=at;e.duration=20000;return e;}
static void test_managed_touch(void)
{
    int freq=index_of("freq"),gate=index_of("gate"),amp=index_of("amp");
    unsigned env=0;while(env<g.nodes && g.node[env].type!=FM_EnvGen)++env;assert(env<g.nodes);
    float output[FM_BLOCK*2];
    assert(instrument_init_definition(&synth,&g,&voice,&scratch,NULL,0,44100,1));
    assert(synth.managed_definition && !voice.active); /* gate default is 1. */
    voice.control[freq]=666;voice.control[amp]=.2f;
    inst_event on={INST_NOTE_ON,20,0},off={INST_NOTE_OFF,20,0};
    assert(instrument_apply(&synth,&on) && voice.active && voice.control[gate]==1);
    assert(voice.control[freq]==666 && voice.control[amp]==.2f);
    double energy=0;
    for(unsigned b=0;b<30;++b){instrument_render_stereo(&synth,output);for(unsigned i=0;i<FM_BLOCK*2;++i)energy+=fabsf(output[i]);}
    assert(energy>1 && voice.state[env].env.previous_gate==1);
    unsigned blocks=voice.blocks;on.note_id=21;assert(instrument_apply(&synth,&on));
    assert(instrument_apply(&synth,&off) && voice.control[gate]==1); /* stale finger release */
    instrument_render_stereo(&synth,output);assert(voice.state[env].env.previous_gate==0);
    instrument_render_stereo(&synth,output);assert(voice.state[env].env.previous_gate==1 && voice.blocks==blocks+2);
    off.note_id=21;assert(instrument_apply(&synth,&off) && voice.control[gate]==0 && synth.buses[2]==0);
    for(unsigned b=0;b<200;++b)instrument_render_stereo(&synth,output);
    assert(!voice.active);on.note_id=22;assert(instrument_apply(&synth,&on) && voice.active && voice.control[freq]==666);
    instrument_panic(&synth);instrument_render_stereo(&synth,output);
    for(unsigned i=0;i<FM_BLOCK*2;++i)assert(output[i]==0);

    assert(instrument_init_definition(&synth,&g,&voice,&scratch,NULL,0,44100,1));
    rc_init(&rc,910);rc_bind(&rc,0,&g,&voice);
    rc_event e=message(50,1,1,0);assert(rc_enqueue(&rc,&e,1000));rc_tick(&rc,&synth,1000);
    instrument_render_stereo(&synth,output);assert(voice.control[gate]==1);
    on.note_id=30;assert(instrument_apply(&synth,&on));rc_tick(&rc,&synth,1500);
    assert(!rc.stage[0].owner && !rc.stage[0].release);
    instrument_render_stereo(&synth,output);instrument_render_stereo(&synth,output);
    e=message(50,2,2,0);assert(rc_enqueue(&rc,&e,50000));rc_tick(&rc,&synth,50000);
    assert(voice.control[gate]==1); /* Old SC cancellation/release cannot cut touch. */
    e=message(51,1,1,60000);assert(rc_enqueue(&rc,&e,50000));rc_tick(&rc,&synth,60000);
    assert(!synth.note_id && voice.control[gate]==0);instrument_render_stereo(&synth,output);
    off.note_id=30;assert(instrument_apply(&synth,&off) && synth.buses[2]==0);
    rc_tick(&rc,&synth,61500);instrument_render_stereo(&synth,output);
    assert(voice.control[gate]==1 && voice.state[env].env.previous_gate==1);
    rc_tick(&rc,&synth,80000);assert(voice.control[gate]==0);
    on.note_id=40;assert(instrument_apply(&synth,&on));rc_tick(&rc,&synth,81000);
    instrument_render_stereo(&synth,output);instrument_render_stereo(&synth,output);
    e=message(52,1,0,0);e.count=1;e.index[0]=gate;e.value[0]=.5f;
    assert(rc_enqueue(&rc,&e,82000));rc_tick(&rc,&synth,82000);
    off.note_id=40;assert(instrument_apply(&synth,&off));instrument_render_stereo(&synth,output);
    assert(voice.control[gate]==.5f && synth.buses[2]==0); /* explicit SC set owns gate */

    assert(instrument_init_definition(&synth,&g,&voice,&scratch,NULL,0,44100,1));
    inst_event tap[]={{INST_NOTE_ON,41,0},{INST_NOTE_OFF,41,0}};
    instrument_apply_batch(&synth,tap,2);assert(!voice.active && !synth.held);
    synth.defer_note_render=1;on.note_id=42;off.note_id=42;
    assert(instrument_apply(&synth,&on) && voice.active);
    assert(instrument_apply(&synth,&off) && !voice.active); /* release before deferred first block */
    puts("PASS: managed touch starts/retriggers/releases without resetting a live voice, preserves controls, handles Panic and quick taps, and transfers gate ownership between touch and SC notes/sets.");
}
static void test_deltas(void)
{
    static remote_control reduced;static instrument other;static fm_voice other_voice;static fm_scratch other_scratch;
    int freq=index_of("freq"),amp=index_of("amp");assert(freq>=0 && amp>=0);
    unsigned char wire[RC_HEADER]={0};rc_event decoded;wire[0]=wire[4]=wire[8]=wire[12]=1;wire[31]=RC_DELTA;
    assert(rc_decode(&decoded,wire,sizeof wire) && decoded.flags==RC_DELTA);wire[31]=2;assert(!rc_decode(&decoded,wire,sizeof wire));
    wire[31]=RC_DELTA;wire[28]=2;assert(!rc_decode(&decoded,wire,sizeof wire));
    assert(instrument_init(&synth,&g,&voice,&scratch,NULL,0,44100));
    assert(instrument_init(&other,&g,&other_voice,&other_scratch,NULL,0,44100));
    rc_init(&rc,777);rc_bind(&rc,0,&g,&voice);rc_init(&reduced,777);rc_bind(&reduced,0,&g,&other_voice);
    for(unsigned n=0;n<3;++n){
        rc_event full=message(70,n+1,1,100000+n*200000);full.count=2;
        full.index[0]=freq;full.value[0]=n?440:330;full.index[1]=amp;full.value[1]=.4f;
        assert(rc_enqueue(&rc,&full,0)==1);
        rc_event delta=full;if(n){delta.flags=RC_DELTA;delta.count=n==1?1:0;}
        assert(rc_enqueue(&reduced,&delta,0)==1);
    }
    /* These arrive after all three notes were queued but execute between them.
     * A host cache of live values would play the later notes at the wrong amp. */
    for(unsigned n=0;n<2;++n){
        rc_event set=message(71,n+1,0,n?450000:200000);set.count=1;set.index[0]=amp;set.value[0]=n?.1f:.9f;
        assert(rc_enqueue(&rc,&set,0)==1 && rc_enqueue(&reduced,&set,0)==1);
    }
    float a[FM_BLOCK*2],b[FM_BLOCK*2];
    for(uint64_t frame=0;frame<44100;frame+=FM_BLOCK){
        uint64_t now=frame*1000000/44100;rc_tick(&rc,&synth,now);rc_tick(&reduced,&other,now);
        instrument_render_stereo(&synth,a);instrument_render_stereo(&other,b);
        assert(!memcmp(a,b,sizeof a));assert(!memcmp(voice.control,other_voice.control,sizeof voice.control));
    }
    assert(rc.applied==5 && reduced.applied==5 && !reduced.rejected && !reduced.late);
    rc_event e=message(72,1,0,0);e.flags=RC_DELTA;
    assert(rc_enqueue(&rc,&e,1000000)==RC_NEED_FULL && !rc.count);
    e.flags=0;e.count=2;e.index[0]=freq;e.value[0]=220;e.index[1]=amp;e.value[1]=.3f;
    assert(rc_enqueue(&rc,&e,1000000)==1);rc_tick(&rc,&synth,1000000);
    e.sequence=2;e.flags=RC_DELTA;e.count=0;
    rc.stage[0].trigger[amp]=1;voice.control[amp]=0; /* DSP reset a trigger. */
    assert(rc_enqueue(&rc,&e,1000000)==1);rc_tick(&rc,&synth,1000000);assert(voice.control[amp]==.3f);
    e.sequence=3;e.flags=0;e.count=1;assert(rc_enqueue(&rc,&e,1000000)==1);rc_tick(&rc,&synth,1000000);
    voice.control[amp]=.8f;e.sequence=4;e.flags=RC_DELTA;e.count=0;
    assert(rc_enqueue(&rc,&e,1000000)==1);rc_tick(&rc,&synth,1000000);assert(voice.control[amp]==.8f); /* Removed field stays removed. */
    e.sequence=5;e.count=1;e.index[0]=amp;e.value[0]=.5f;assert(!rc_enqueue(&rc,&e,1000000)); /* Cannot add fields to a delta. */
    e.count=0;assert(rc_enqueue(&rc,&e,1000000)==1);rc_tick(&rc,&synth,1000000); /* Rejection did not consume sequence. */
    rc_bind(&rc,1,&g,&fx_voice);e.sequence++;assert(rc_enqueue(&rc,&e,1000000)==1);rc_tick(&rc,&synth,1000000); /* Other stage preserved. */
    rc_bind(&rc,0,&g,&voice);e.revision=rc.stage[0].revision;e.sequence++;
    assert(rc_enqueue(&rc,&e,1000000)==RC_NEED_FULL);e.flags=0;assert(rc_enqueue(&rc,&e,1000000)==1);rc_tick(&rc,&synth,1000000);
    /* A full queue must not consume sequence or advance the baseline. */
    e=message(73,1,0,1100000);e.count=1;e.index[0]=amp;e.value[0]=.2f;
    for(unsigned n=0;n<RC_EVENTS;++n){e.sequence=n+1;assert(rc_enqueue(&rc,&e,1000000)==1);}
    e.sequence++;e.flags=RC_DELTA;e.value[0]=.9f;assert(!rc_enqueue(&rc,&e,1000000));rc_tick(&rc,&synth,1100000);
    e.count=0;assert(rc_enqueue(&rc,&e,1100000)==1);rc_tick(&rc,&synth,1100000);assert(voice.control[amp]==.2f);
    e.sequence++;e.kind=2;e.flags=0;assert(rc_enqueue(&rc,&e,1100000)==1);
    e.sequence++;e.kind=0;e.flags=RC_DELTA;assert(!rc_enqueue(&rc,&e,1100000));
}
int main(int argc,char **argv){
    assert(argc==3);FILE *f=fopen(argv[1],"rb");assert(f);unsigned char data[65536];size_t size=fread(data,1,sizeof data,f);fclose(f);char error[160];assert(fm_load(&g,data,size,error,sizeof error));
    test_deltas();assert(instrument_init(&synth,&g,&voice,&scratch,NULL,0,44100));rc_init(&rc,123);rc_bind(&rc,0,&g,&voice);
    int freq=index_of("freq"),gate=index_of("gate"),amp=index_of("amp");assert(freq>=0 && gate>=0 && amp>=0);
    rc_event e=message(1,1,0,1000);e.count=2;e.index[0]=freq;e.value[0]=.1f;e.index[1]=amp;e.value[1]=2;
    assert(rc_enqueue(&rc,&e,1000));rc_tick(&rc,&synth,1000);assert(voice.control[freq]==.1f && voice.control[amp]==2);
    assert(!rc_enqueue(&rc,&e,1000));e.sequence++;e.value[0]=NAN;unsigned char bad[32]={0};assert(!rc_decode(&e,bad,sizeof bad));
    e=message(2,1,1,2000);assert(rc_enqueue(&rc,&e,1000));rc_tick(&rc,&synth,2000);assert(voice.active && voice.control[gate]==1);
    float output[FM_BLOCK*2];instrument_render_stereo(&synth,output);
    e=message(3,2,1,3000);e.duration=50000;assert(rc_enqueue(&rc,&e,3000));rc_tick(&rc,&synth,3000);assert(voice.control[gate]==0);
    instrument_render_stereo(&synth,output);rc_tick(&rc,&synth,4500);assert(voice.control[gate]==1);
    rc_tick(&rc,&synth,23000);assert(voice.control[gate]==1); /* old note's release cannot cut the new note */
    e=message(2,3,2,0);e.duration=0;assert(rc_enqueue(&rc,&e,24000));assert(voice.control[gate]==1);
    e=message(3,4,2,0);e.duration=0;assert(rc_enqueue(&rc,&e,25000));assert(voice.control[gate]==0);
    e=message(3,5,1,40000);assert(!rc_enqueue(&rc,&e,26000)); /* stopped stream cannot resurrect */
    e=message(4,1,1,27000);assert(rc_enqueue(&rc,&e,26000));rc_tick(&rc,&synth,27000);
    e=message(5,1,0,28000);e.count=1;e.index[0]=gate;e.value[0]=1;assert(rc_enqueue(&rc,&e,28000));rc_tick(&rc,&synth,28000);
    rc_tick(&rc,&synth,49000);assert(voice.control[gate]==1); /* explicit gate set takes ownership */
    for(unsigned i=0;i<RC_EVENTS;++i){e=message(10,i+1,0,100000+i);assert(rc_enqueue(&rc,&e,30000));}
    e.sequence++;assert(!rc_enqueue(&rc,&e,30000));
    rc_bind(&rc,0,&g,&voice);assert(!rc.count);assert(!rc_enqueue(&rc,&e,30000));
    e=message(12,1,1,40000);assert(rc_enqueue(&rc,&e,30000));rc_clear(&rc);assert(!rc.count && !rc_enqueue(&rc,&e,30000));
    rc_status status;char json[4000];assert(rc_snapshot(&rc,0,50000,&status));assert(rc_info(&status,0,json,sizeof json));assert(strstr(json,"66726571"));
    assert(!rc_info(&status,0,json,4));
    /* Default legato .8 * dur .125 equals delta .1. A release and the
     * following note can share one audio tick; the envelope must see low. */
    assert(instrument_init(&synth,&g,&voice,&scratch,NULL,0,44100));rc_init(&rc,456);rc_bind(&rc,0,&g,&voice);
    e=message(30,1,1,100000);e.duration=100000;assert(rc_enqueue(&rc,&e,100000));
    rc_tick(&rc,&synth,100000);instrument_render_stereo(&synth,output);assert(voice.control[gate]==1);
    e=message(30,2,1,200000);e.duration=100000;assert(rc_enqueue(&rc,&e,150000));
    rc_tick(&rc,&synth,200000);assert(voice.control[gate]==0 && rc.stage[0].retrigger);
    instrument_render_stereo(&synth,output);
    rc_tick(&rc,&synth,201500);assert(voice.control[gate]==1 && !rc.stage[0].retrigger);
    /* Render real 64-frame blocks: count edges actually observed by EnvGen,
     * not merely accepted network events. Cover gaps, exact joins and overlap. */
    unsigned env=0;while(env<g.nodes && g.node[env].type!=FM_EnvGen)++env;assert(env<g.nodes);
    const unsigned durations[]={80000,100000,100001};
    for(unsigned mode=0;mode<3;++mode){
        assert(instrument_init(&synth,&g,&voice,&scratch,NULL,0,44100));rc_init(&rc,789);rc_bind(&rc,0,&g,&voice);
        unsigned sent=0,edges=0;float previous=0;
        for(uint64_t frame=0;frame<44100u*11u;frame+=FM_BLOCK){
            uint64_t now=frame*1000000u/44100u;
            while(sent<100 && 100000u+sent*100000u<=now+250000u){
                e=message(31,sent+1,1,100000u+sent*100000u);e.duration=durations[mode];
                assert(rc_enqueue(&rc,&e,now));++sent;
            }
            rc_tick(&rc,&synth,now);instrument_render_stereo(&synth,output);
            float current=voice.state[env].env.previous_gate;
            if(previous<=0 && current>0)++edges;
            previous=current;
        }
        assert(sent==100 && edges==100 && rc.applied==100 && !rc.rejected && !rc.late);
    }
    /* A definition with gate=1 must remain uninstantiated and silent. Creation
     * arguments precede constructors; stop invalidates queued instance events. */
    g.defaults[gate]=1;
    assert(instrument_init_definition(&synth,&g,&voice,&scratch,NULL,0,44100,1));
    assert(!voice.active && !voice.prepared);rc_init(&rc,900);rc_bind(&rc,0,&g,&voice);
    e=message(40,1,0,0);e.count=3;e.index[0]=freq;e.value[0]=330;e.index[1]=amp;e.value[1]=.3f;e.index[2]=gate;e.value[2]=1;
    assert(rc_instance(&rc,&synth,NULL,1,&e));assert(voice.active && voice.prepared && voice.control[freq]==330 && voice.control[gate]==1);
    assert(!rc_instance(&rc,&synth,NULL,1,&e)); /* old revision cannot recreate */
    e=message(40,2,1,100000);assert(rc_enqueue(&rc,&e,0));
    e=message(40,3,0,0);assert(rc_instance(&rc,&synth,NULL,0,&e));assert(!voice.active && !voice.prepared && !rc.count);
    assert(rc_snapshot(&rc,0,0,&status));assert(!status.active && !status.prepared);
    test_managed_touch();
    f=fopen(argv[2],"rb");assert(f);size=fread(data,1,sizeof data,f);fclose(f);assert(fm_load(&fx_graph,data,size,error,sizeof error));
    assert(master_effect_define(&fx,&fx_graph,&fx_voice,NULL,0,44100,&scratch));assert(!fx_voice.active && !fx_voice.prepared);
    rc_bind(&rc,1,&fx_graph,&fx_voice);float input[FM_BLOCK*2];for(unsigned i=0;i<FM_BLOCK*2;++i)input[i]=1;
    master_delay_render(&fx,&scratch,input,output);assert(output[0]==1);
    memset(&e,0,sizeof e);e.boot=rc.boot;e.stage=1;e.revision=rc.stage[1].revision;e.count=1;e.index[0]=0;e.value[0]=.25f;
    assert(rc_instance(&rc,&synth,&fx,1,&e));master_delay_render(&fx,&scratch,input,output);assert(output[0]==.25f && output[1]==.25f);
    e.revision=rc.stage[1].revision;e.count=0;assert(rc_instance(&rc,&synth,&fx,0,&e));
    assert(master_delay_reset(&fx,&scratch) && !fx_voice.active);master_delay_render(&fx,&scratch,input,output);assert(output[0]==1);
    printf("PASS: delta/full PCM identity with interleaved future events, trigger replay, field removal, baseline recovery, queue rollback and stage invalidation; definition silence, explicit instance creation/free and stale creation rejection; atomic controls, scheduling, release ownership, cancellation, revisions, Panic and queue bounds; 300 rendered EnvGen retriggers; state=%zu bytes, snapshot=%zu bytes\n",sizeof rc,sizeof status);return 0;
}
