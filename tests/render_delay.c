/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "master_delay.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
static fm_graph graph;static fm_voice voice;static fm_scratch scratch;static master_delay bus;
int main(int argc,char **argv)
{
    assert(argc==5);unsigned char bytes[FM_FILE_BYTES];char error[256];
    FILE *f=fopen(argv[1],"rb");assert(f);size_t n=fread(bytes,1,sizeof bytes,f);fclose(f);
    assert(fm_load(&graph,bytes,n,error,sizeof error));
    float *arena=malloc(MASTER_DELAY_SAMPLES*sizeof(float));assert(arena);
    assert(master_delay_init(&bus,&graph,&voice,arena,MASTER_DELAY_SAMPLES,44100,&scratch));
    int mode=atoi(argv[4]);
    assert(master_delay_set(&bus,0,mode==0?5.0f:.35f));assert(master_delay_set(&bus,1,mode==0?.35f:.8f));assert(master_delay_set(&bus,2,mode==0?1:.5f));
    assert(master_delay_reset(&bus,&scratch));
    FILE *input=fopen(argv[2],"rb"),*output=fopen(argv[3],"wb");assert(input && output);
    float in[FM_BLOCK*2],out[FM_BLOCK*2];unsigned block=0;
    while(fread(in,sizeof in,1,input)==1) {
        if(mode==2 && block==68) {assert(master_delay_set(&bus,0,.02f));assert(master_delay_set(&bus,1,0));assert(master_delay_set(&bus,2,1));}
        if(mode==2 && block==137) {assert(master_delay_set(&bus,0,5));assert(master_delay_set(&bus,1,.8f));assert(master_delay_set(&bus,2,.25f));}
        master_delay_render(&bus,&scratch,in,out);assert(!bus.faults && !voice.fault);
        assert(fwrite(out,sizeof out,1,output)==1);++block;
    }
    assert(!fclose(output));fclose(input);free(arena);
}
