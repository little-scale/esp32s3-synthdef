/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "instrument.h"
#include <assert.h>
#include <stdio.h>
static fm_graph graph;
static fm_voice voice;
static fm_scratch scratch;
static instrument synth;
static void apply(inst_event_type type,float value)
{inst_event event={type,1,value};assert(instrument_apply(&synth,&event));}
int main(int argc,char **argv)
{
    assert(argc==3);unsigned char bytes[FM_FILE_BYTES];char error[256];
    FILE *f=fopen(argv[1],"rb");assert(f);size_t size=fread(bytes,1,sizeof bytes,f);fclose(f);
    assert(fm_load(&graph,bytes,size,error,sizeof error));
    f=fopen(argv[2],"wb");assert(f);
    const float pitch[]={0,.13f,.37f,.5f,.63f,.87f,1},frequencies[]={20,110,440,1760,20000};
    for(unsigned j=0;j<5;++j)for(unsigned p=0;p<7;++p)for(unsigned t=0;t<2;++t)for(unsigned a=0;a<2;++a)for(unsigned r=0;r<2;++r) {
        int16_t pcm[FM_BLOCK];
        assert(instrument_init(&synth,&graph,&voice,&scratch,NULL,0,44100));
        apply(INST_FREQ,frequencies[j]);apply(INST_KNOB1,pitch[p]);apply(INST_KNOB2,(float)t);
        apply(INST_KNOB3,(float)a);apply(INST_KNOB4,(float)r);apply(INST_NOTE_ON,0);
        instrument_render(&synth,pcm);assert(fwrite(pcm,1,sizeof pcm,f)==sizeof pcm);
        apply(INST_KNOB1,1-pitch[p]);apply(INST_KNOB2,1-(float)t);instrument_render(&synth,pcm);assert(fwrite(pcm,1,sizeof pcm,f)==sizeof pcm);
        apply(INST_NOTE_OFF,0);instrument_render(&synth,pcm);assert(fwrite(pcm,1,sizeof pcm,f)==sizeof pcm);
        assert(!synth.faults && !synth.nonfinite && !synth.clipped);
    }
    assert(!fclose(f));
}
