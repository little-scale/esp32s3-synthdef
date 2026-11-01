/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "fm_synth.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
static fm_graph graph;static fm_voice voice;static fm_scratch scratch;
int main(int argc,char **argv)
{
    assert(argc==5);unsigned char bytes[FM_FILE_BYTES];char error[256];FILE *f=fopen(argv[1],"rb");assert(f);
    size_t n=fread(bytes,1,sizeof bytes,f);fclose(f);assert(fm_load(&graph,bytes,n,error,sizeof error));
    float rate=strtof(argv[2],NULL);unsigned seconds=(unsigned)strtoul(argv[3],NULL,10),seed=(unsigned)strtoul(argv[4],NULL,10);
    uint32_t need=fm_delay_required(&graph,rate);assert(need!=UINT32_MAX);
    float *arena=malloc(((size_t)need+2)*sizeof(float));assert(arena);arena[0]=12345.5f;arena[need+1]=-5678.25f;
    assert(fm_start(&voice,&graph,rate) && fm_bind_delay(&voice,&graph,arena+1,need) && fm_seed(&voice,seed));
    unsigned blocks=(unsigned)ceilf(seconds*rate/FM_BLOCK),failed=0;float peak=0;
    for(unsigned block=0;block<blocks;++block) {
        float out[FM_BLOCK*2]={0};fm_render(&graph,&voice,&scratch,out);
        for(unsigned i=0;i<FM_BLOCK*2;++i) {if(!isfinite(out[i]))failed=block+1;if(fabsf(out[i])>peak)peak=fabsf(out[i]);}
        if(voice.fault) {failed=block+1;break;}
        assert(arena[0]==12345.5f && arena[need+1]==-5678.25f);
    }
    free(arena);printf("{\"passed\":%s,\"rate\":%.0f,\"seconds\":%u,\"seed\":%u,\"fault_block\":%u,\"peak\":%.9g}\n",failed?"false":"true",rate,seconds,seed,failed,peak);
    return 0;
}
