/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "patch_format.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>
static fm_graph graph;
int main(int argc,char **argv)
{
    assert(argc==4);unsigned char bytes[FM_FILE_BYTES];char error[160];
    FILE *f=fopen(argv[1],"rb");assert(f);size_t size=fread(bytes,1,sizeof bytes,f);fclose(f);
    assert(fm_load(&graph,bytes,size,error,sizeof error));
    patch_meta meta={0};meta.graph_bytes=(uint32_t)size;
    for(unsigned i=0;i<32;++i) {char pair[3]={argv[2][2*i],argv[2][2*i+1],0};meta.graph_hash[i]=(unsigned char)strtoul(pair,NULL,16);}
    int expected=atoi(argv[3]);assert(!!patch_validate(&graph,&meta,error)==expected);
    meta.graph_hash[0]^=1;assert(!patch_validate(&graph,&meta,error));meta.graph_hash[0]^=1;
    --meta.graph_bytes;assert(!patch_validate(&graph,&meta,error));++meta.graph_bytes;
    --graph.nodes;assert(!patch_validate(&graph,&meta,error));
    puts("PASS: exact catalog admission, changed digest/size/structure rejection");
}
