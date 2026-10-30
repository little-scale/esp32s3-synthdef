/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "fm_synth.h"
#include <assert.h>
#include <stdio.h>
static fm_graph graph;
int main(int argc,char **argv)
{
    assert(argc==2);unsigned char bytes[FM_FILE_BYTES];char error[256];
    FILE *f=fopen(argv[1],"rb");assert(f);size_t size=fread(bytes,1,sizeof bytes,f);fclose(f);
    if(!fm_load(&graph,bytes,size,error,sizeof error)) {fprintf(stderr,"%s\n",error);return 1;}
    printf("{\"nodes\":%u,\"signals\":%u,\"inputs\":%u,\"delay\":%u,\"types\":[",graph.nodes,graph.outputs,graph.inputs,fm_delay_required(&graph,44100));
    for(unsigned n=0;n<graph.nodes;++n)printf("%s\"%s\"",n?",":"",fm_type_name(graph.node[n].type));
    puts("]}");
}
