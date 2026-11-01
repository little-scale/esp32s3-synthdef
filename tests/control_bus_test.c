/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "fm_synth.h"
#include "instrument.h"
#include "patch_format.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static fm_graph graph;
static fm_voice voice;
static fm_scratch scratch;
static instrument synth;
static void load(const char *path)
{
    unsigned char bytes[FM_FILE_BYTES];char error[192];
    FILE *f=fopen(path,"rb");assert(f);size_t n=fread(bytes,1,sizeof bytes,f);fclose(f);
    if(!fm_load(&graph,bytes,n,error,sizeof error)){fprintf(stderr,"%s\n",error);abort();}
}
static void event(inst_event_type type,unsigned id,float value)
{
    inst_event e={type,id,value};assert(instrument_apply(&synth,&e));
}
int main(int argc,char **argv)
{
    assert(argc>=4);float bank[FM_CONTROL_BUSES]={0},output[FM_BLOCK*2];char error[192];
    load(argv[2]);assert(fm_start(&voice,&graph,44100));
    assert(!fm_bind_control_buses(&voice,NULL,1) && !fm_bind_control_buses(&voice,bank,FM_CONTROL_BUSES+1));
    memset(output,0,sizeof output);fm_render(&graph,&voice,&scratch,output);
    for(unsigned i=0;i<FM_BLOCK*2;++i)assert(output[i]==0);
    bank[0]=.125f;bank[1]=-.25f;bank[2]=1;
    assert(fm_bind_control_buses(&voice,bank,2));
    memset(output,0,sizeof output);fm_render(&graph,&voice,&scratch,output);
    memset(output,0,sizeof output);fm_render(&graph,&voice,&scratch,output); /* K2A settles over one block. */
    assert(output[0]==.125f && output[1]==-.25f && !voice.fault);
    assert(fm_set(&voice,&graph,"hwBus",29));bank[29]=.75f;bank[30]=.5f;bank[31]=1;
    assert(fm_bind_control_buses(&voice,bank,FM_CONTROL_BUSES));
    memset(output,0,sizeof output);fm_render(&graph,&voice,&scratch,output);
    memset(output,0,sizeof output);fm_render(&graph,&voice,&scratch,output);
    assert(output[0]==.75f && output[1]==.5f && !voice.fault);
    assert(fm_set(&voice,&graph,"hwBus",30));fm_render(&graph,&voice,&scratch,output);assert(voice.fault);
    assert(fm_start(&voice,&graph,44100));assert(!voice.control_buses && !voice.control_bus_count);
    assert(fm_bind_control_buses(&voice,bank,FM_CONTROL_BUSES));bank[0]=NAN;
    fm_render(&graph,&voice,&scratch,output);assert(voice.fault);
    for(int i=4;i<argc;++i){
        unsigned char bytes[FM_FILE_BYTES];FILE *f=fopen(argv[i],"rb");assert(f);size_t n=fread(bytes,1,sizeof bytes,f);fclose(f);
        assert(!fm_load(&graph,bytes,n,error,sizeof error));
    }
    puts("PASS: control bus default zeros, partial binding, last valid range, dynamic index, invalid ranges/count/rates, nonfinite data and restart binding");
    /* Compare the raw graph with SC; no adapter fade or mono conversion. */
    load(argv[1]);assert(fm_start(&voice,&graph,44100));assert(fm_bind_control_buses(&voice,bank,FM_CONTROL_BUSES));
    memset(bank,0,sizeof bank);bank[0]=.25f;bank[1]=.7f;bank[2]=1;
    FILE *f=fopen(argv[3],"wb");assert(f);
    for(unsigned b=0;b<448;++b){
        if(b==64)bank[0]=.8f;if(b==128)bank[1]=.2f;if(b==192)bank[2]=0;
        if(b==256){bank[0]=.5f;bank[1]=.7f;bank[2]=1;}if(b==320)bank[2]=0;
        memset(output,0,sizeof output);fm_render(&graph,&voice,&scratch,output);assert(!voice.fault);
        assert(fwrite(output,sizeof(float),FM_BLOCK*2,f)==FM_BLOCK*2);
    }assert(!fclose(f));
    patch_meta meta={0};assert(patch_validate(&graph,&meta,error));
    /* Touch gates preserve DSP state and tails; Panic still stops it. */
    assert(instrument_init(&synth,&graph,&voice,&scratch,NULL,0,44100));assert(synth.bus_mode);
    assert(instrument_arm_bus(&synth));assert(voice.active && synth.buses[2]==0 && !synth.held);
    for(unsigned b=0;b<8;++b){instrument_render_stereo(&synth,output);for(unsigned i=0;i<FM_BLOCK*2;++i)assert(output[i]==0);}
    event(INST_TOUCH_X,0,.25f);event(INST_TOUCH_Y,0,.7f);event(INST_NOTE_ON,1,0);
    for(unsigned i=0;i<80;++i)instrument_render_stereo(&synth,output);
    unsigned blocks=voice.blocks;event(INST_NOTE_OFF,999,0);assert(synth.buses[2]==1);
    event(INST_NOTE_OFF,1,0);assert(!synth.held && synth.buses[2]==0);
    instrument_render_stereo(&synth,output);assert(voice.blocks==blocks+1 && voice.active);
    event(INST_NOTE_ON,2,0);instrument_render_stereo(&synth,output);assert(voice.blocks==blocks+2);
    /* Release/retrigger inside one block emits a low block before the rise. */
    event(INST_NOTE_OFF,2,0);event(INST_NOTE_ON,3,0);
    instrument_render_stereo(&synth,output);assert(synth.rendered_gate==0 && synth.buses[2]==1);
    instrument_render_stereo(&synth,output);assert(synth.rendered_gate==1);
    event(INST_NOTE_OFF,3,0);
    for(unsigned i=0;i<7000;++i)instrument_render_stereo(&synth,output);
    assert(voice.active && !voice.fault && !synth.held);
    for(unsigned i=0;i<FM_BLOCK*2;++i)assert(fabsf(output[i])<1e-12f);
    instrument_panic(&synth);assert(!voice.active && synth.buses[2]==0);
    synth.defer_note_render=1;event(INST_NOTE_ON,4,0);event(INST_NOTE_OFF,4,0);
    assert(!voice.active && synth.buses[2]==0);
    puts("PASS: bus-only patch admission, X/Y/gate, stale releases, persistent state after release, same-block retrigger, silence after tail, Panic and early cancellation");
    return 0;
}
