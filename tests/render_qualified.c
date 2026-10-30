/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "fm_synth.h"
#include <assert.h>
#include <stdio.h>
static fm_graph graph;
static fm_voice voice;
static fm_scratch scratch;
int main(int argc,char **argv)
{
    assert(argc==3);unsigned char bytes[FM_FILE_BYTES];char error[256];
    FILE *f=fopen(argv[1],"rb");assert(f);size_t size=fread(bytes,1,sizeof bytes,f);fclose(f);
    if(!fm_load(&graph,bytes,size,error,sizeof error)) {fprintf(stderr,"%s\n",error);return 1;}
    printf("nodes=%u signals=%u inputs=%u delay=%u\n",graph.nodes,graph.outputs,graph.inputs,fm_delay_required(&graph,44100));
    for(unsigned n=0;n<graph.nodes;++n)printf("%s:%u ",fm_type_name(graph.node[n].type),graph.node[n].rate);
    puts("");assert(fm_start(&voice,&graph,44100));assert(fm_bind_delay(&voice,&graph,NULL,0));assert(fm_seed(&voice,0));
    f=fopen(argv[2],"wb");assert(f);
    for(unsigned b=0;b<345;++b) {
        float stereo[FM_BLOCK*2]={0};
        if(b==68) {assert(fm_set(&voice,&graph,"knob1",.75f));assert(fm_set(&voice,&graph,"knob2",.7f));}
        if(b==137) {assert(fm_set(&voice,&graph,"knob1",.13f));assert(fm_set(&voice,&graph,"knob2",.2f));}
        if(b==172)assert(fm_set(&voice,&graph,"gate",0));
        fm_render(&graph,&voice,&scratch,stereo);assert(!voice.fault);
        assert(fwrite(stereo,1,sizeof stereo,f)==sizeof stereo);
    }
    assert(!fclose(f));
}
