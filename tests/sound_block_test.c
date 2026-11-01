/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "instrument.h"
#include "patch_format.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
static fm_graph graph;
static fm_voice voice;
static fm_scratch scratch;
static instrument synth;
int main(int argc,char **argv)
{
    assert(argc==2);unsigned char data[FM_FILE_BYTES];char error[160];
    FILE *f=fopen(argv[1],"rb");assert(f);size_t size=fread(data,1,sizeof data,f);fclose(f);
    assert(fm_load(&graph,data,size,error,sizeof error));patch_meta meta={0};
    assert(patch_validate(&graph,&meta,error));
    assert(instrument_init(&synth,&graph,&voice,&scratch,NULL,0,44100));
    assert(synth.continuous && !synth.bus_mode);
    assert(instrument_arm_bus(&synth));float out[FM_BLOCK*2];float peak=0,tail=0;
    inst_event on={INST_NOTE_ON,1,0},off={INST_NOTE_OFF,1,0};
    for(unsigned b=0;b<7700;++b){
        instrument_render_stereo(&synth,out);assert(!voice.fault);
        for(unsigned i=0;i<FM_BLOCK*2;++i){assert(isfinite(out[i]));if(fabsf(out[i])>peak)peak=fabsf(out[i]);}
    }
    assert(peak>.001f && voice.active);unsigned blocks=voice.blocks;
    assert(instrument_apply(&synth,&off));assert(instrument_apply(&synth,&on));
    assert(voice.blocks==blocks && voice.active);
    for(unsigned b=0;b<300;++b){
        instrument_render_stereo(&synth,out);assert(!voice.fault);
        for(unsigned i=0;i<FM_BLOCK*2;++i){assert(isfinite(out[i]));if(b>=200 && fabsf(out[i])>tail)tail=fabsf(out[i]);}
    }
    assert(tail>.001f && voice.active);
    blocks=voice.blocks;instrument_suspend(&synth);assert(!voice.active);
    assert(instrument_resume(&synth) && voice.active && voice.blocks==blocks);
    instrument_suspend(&synth);instrument_panic(&synth);assert(instrument_resume(&synth) && !voice.active);
    assert(instrument_apply(&synth,&on) && !voice.active);
    assert(instrument_arm_bus(&synth) && voice.active);
    instrument_panic(&synth);instrument_render_stereo(&synth,out);
    for(unsigned i=0;i<FM_BLOCK*2;++i)assert(out[i]==0);
    printf("PASS: block starts without input, keeps running past 10 seconds, ignores touch gates, resumes after maintenance, stays stopped after Panic, and restarts on reload; peak=%.9g\n",peak);
    return 0;
}
