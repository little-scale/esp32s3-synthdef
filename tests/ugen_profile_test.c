/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "fm_synth.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern void fm_ugen_render(const fm_graph *,fm_voice *,fm_scratch *,float *);
extern uint64_t fm_ugen_cycles[FM_NODES];
extern uint32_t fm_ugen_calls[FM_NODES];
uint32_t fm_ugen_clock(void){static uint32_t clock;return ++clock;}
static fm_graph graph;
static fm_voice a,b;
static fm_scratch sa,sb;
static unsigned char bytes[65536];
int main(int argc,char **argv)
{
    assert(argc==2);FILE *f=fopen(argv[1],"rb");assert(f);
    size_t size=fread(bytes,1,sizeof bytes,f);assert(!ferror(f));fclose(f);
    char error[160];assert(fm_load(&graph,bytes,size,error,sizeof error));
    unsigned need=fm_delay_required(&graph,44100);float *ma=calloc(need?need:1,sizeof(float)),*mb=calloc(need?need:1,sizeof(float));assert(ma&&mb);
    assert(fm_start(&a,&graph,44100)&&fm_start(&b,&graph,44100));
    assert(fm_bind_delay(&a,&graph,ma,need)&&fm_bind_delay(&b,&graph,mb,need));
    for(unsigned block=0;block<1024;++block){
        float oa[FM_BLOCK*2]={0},ob[FM_BLOCK*2]={0};
        fm_render(&graph,&a,&sa,oa);fm_ugen_render(&graph,&b,&sb,ob);
        assert(!a.fault && !b.fault && a.active && b.active);
        assert(!memcmp(oa,ob,sizeof oa));assert(!memcmp(a.state,b.state,sizeof a.state));
        assert(!memcmp(ma,mb,need*sizeof(float)));
    }
    for(unsigned i=0;i<graph.nodes;++i)assert(fm_ugen_calls[i]==1025 && fm_ugen_cycles[i]==1025);
    free(ma);free(mb);puts("PASS: instrumented renderer matches all audio samples, node states and delay memory over 1024 blocks; every dispatch (including cached nodes) is counted.");
}
