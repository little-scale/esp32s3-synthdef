/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "fm_synth.h"
#include "instrument.h"
#include "voice_pe_controls.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static fm_graph graph;
static fm_voice voice;
static fm_scratch scratch;
static int load(const char *path)
{
    unsigned char bytes[FM_FILE_BYTES];char error[160];FILE *f=fopen(path,"rb");assert(f);
    size_t n=fread(bytes,1,sizeof bytes,f);assert(!ferror(f));fclose(f);
    return fm_load(&graph,bytes,n,error,sizeof error);
}
int main(int argc,char **argv)
{
    assert(argc>=4);assert(FM_CONTROL_OUTPUT_BASE==3 && FM_CONTROL_OUTPUTS==39);
    const unsigned rates[]={16000,44100,48000};
    float input[FM_CONTROL_BUSES]={0},audio[FM_BLOCK*2]={0};
    assert(load(argv[1]));
    for(unsigned pass=0;pass<3;++pass){
        unsigned rate=rates[pass];
        assert(fm_start(&voice,&graph,rate));assert(fm_bind_control_buses(&voice,input,FM_CONTROL_BUSES));
        fm_prepare(&graph,&voice,&scratch);assert(!voice.control_output_mask);
        fm_render(&graph,&voice,&scratch,audio);assert(!voice.fault);
        assert(voice.control_outputs[0]==.5f); /* Two Out.kr writers add. */
        assert(voice.control_outputs[36]==.1f && voice.control_outputs[37]==.2f && voice.control_outputs[38]==.3f);
        assert(voice.control_output_mask==(UINT64_C(1)|(UINT64_C(7)<<36)));
        input[0]=38;fm_render(&graph,&voice,&scratch,audio);assert(!voice.fault);
        assert(voice.control_outputs[0]==.25f && fabsf(voice.control_outputs[38]-.55f)<1e-6f);
        input[0]=39;fm_render(&graph,&voice,&scratch,audio);assert(voice.fault && !voice.active);
        assert(!voice.control_output_mask);
        for(unsigned i=0;i<39;++i)assert(voice.control_outputs[i]==0);
        input[0]=3;assert(fm_start(&voice,&graph,rate));assert(!voice.control_output_mask);
        assert(fm_bind_control_buses(&voice,input,FM_CONTROL_BUSES));
        input[0]=NAN;fm_render(&graph,&voice,&scratch,audio);assert(voice.fault && !voice.control_output_mask);
        input[0]=0; /* Restore input bank before next test pass. */
    }
    assert(load(argv[2]));
    for(unsigned pass=0;pass<3;++pass){
        instrument inst;unsigned rate=rates[pass];
        assert(instrument_init_definition(&inst,&graph,&voice,&scratch,NULL,0,rate,1));
        input[0]=1;input[1]=.625f;input[2]=1;inst.input_buses=input;inst.input_bus_count=FM_CONTROL_BUSES;
        assert(instrument_arm_bus(&inst));
        for(unsigned j=0;j<3;++j)instrument_render_stereo(&inst,audio);
        assert(audio[0]==1 && audio[1]==.625f && voice.control_outputs[0]==1);
        instrument_panic(&inst);assert(input[2]==1);
        assert(instrument_arm_bus(&inst));
        for(unsigned j=0;j<3;++j)instrument_render_stereo(&inst,audio);
        assert(audio[0]==1 && audio[1]==.625f && voice.control_outputs[0]==1);
    }
    for(int i=3;i<argc;++i)assert(!load(argv[i]));
    float main_rgb[39]={0},fx[39]={0},out[39];uint8_t grb[36];
    main_rgb[36]=.5f;main_rgb[37]=.25f;main_rgb[38]=1;main_rgb[0]=.8f;
    vpe_led_resolve(main_rgb,(UINT64_C(7)<<36)|1,fx,0,out);
    assert(out[0]==.8f && out[3]==.5f && out[1]==.25f && out[2]==1);
    fx[36]=.1f;fx[0]=0;
    vpe_led_resolve(main_rgb,(UINT64_C(7)<<36)|1,fx,(UINT64_C(1)<<36)|1,out);
    assert(out[0]==0 && out[3]==.1f && out[1]==.25f);
    fx[0]=NAN;main_rgb[37]=2;main_rgb[38]=-1;
    vpe_led_resolve(main_rgb,(UINT64_C(7)<<36)|1,fx,1,out);
    assert(out[0]==0 && out[1]==1 && out[2]==0);
    memset(out,0,sizeof out);out[0]=1;out[1]=.5f;out[2]=.25f;
    vpe_led_pack(out,grb);assert(grb[7*3]==26 && grb[7*3+1]==51 && grb[7*3+2]==13);
    for(unsigned i=0;i<36;++i)if(i<21 || i>23)assert(grb[i]==0);
    vpe_led_resolve(main_rgb,0,fx,0,out);vpe_led_pack(out,grb);
    for(unsigned i=0;i<36;++i)assert(grb[i]==0);
    const unsigned volumes[]={0,1,4,5,6,20,25,100,101,UINT32_MAX};
    for(unsigned i=0;i<sizeof volumes/sizeof volumes[0];++i){
        unsigned v=volumes[i];
        assert(vpe_startup_volume(v,0)==(v>5?5:v));
        assert(vpe_startup_volume(v,1)==(v>100?100:v));
    }
    puts("PASS: first unity-gain upgrade starts at <=5%; acknowledged profile preserves user levels, including mute");
    puts("PASS: Out.kr sums, first/last buses, dynamic bounds, faults/prepare/restart, separate physical inputs, broadcast RGB, explicit FX priority, GRB mapping and dark default at 16/44.1/48k");
}
