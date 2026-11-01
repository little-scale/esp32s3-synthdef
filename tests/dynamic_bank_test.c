/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "fm_synth.h"
#include "patch_format.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
static fm_graph g;
static fm_voice v;
static fm_scratch scratch;
int main(int argc,char **argv)
{
    assert(argc==4);unsigned char data[65536];char error[160];
    FILE *f=fopen(argv[1],"rb");assert(f);size_t size=fread(data,1,sizeof data,f);assert(!ferror(f));fclose(f);
    if(!fm_load(&g,data,size,error,sizeof error)){fprintf(stderr,"%s\n",error);return 1;}
    patch_meta meta={0};meta.graph_bytes=(uint32_t)size;
    if(!patch_validate(&g,&meta,error)){fprintf(stderr,"%s\n",error);return 1;}
    assert(fm_delay_required(&g,44100)==0 && fm_start(&v,&g,44100) && fm_bind_delay(&v,&g,NULL,0) && fm_seed(&v,0));
    f=fopen(argv[2],"wb");assert(f);unsigned blocks=(unsigned)strtoul(argv[3],NULL,10);float peak=0;
    for(unsigned b=0;b<blocks;++b){
        float out[FM_BLOCK*2]={0};fm_render(&g,&v,&scratch,out);assert(v.active && !v.fault);
        for(unsigned i=0;i<FM_BLOCK*2;++i){assert(isfinite(out[i]));if(fabsf(out[i])>peak)peak=fabsf(out[i]);}
        assert(fwrite(out,sizeof(float),FM_BLOCK*2,f)==FM_BLOCK*2);
    }
    assert(!fclose(f) && peak>1e-7f);
    printf("{\"passed\":true,\"nodes\":%u,\"signals\":%u,\"peak\":%.9g}\n",g.nodes,g.outputs,peak);
}
