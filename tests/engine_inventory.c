/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "fm_synth.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static fm_graph graph;
static fm_voice voice;
static fm_scratch scratch;
static unsigned char bytes[FM_FILE_BYTES+1];
static void quoted(const char *p)
{
    putchar('"');
    for(;*p;++p) {
        unsigned c=(unsigned char)*p;
        if(c=='"' || c=='\\')putchar('\\');
        if(c<32)printf("\\u%04x",c);else putchar((int)c);
    }
    putchar('"');
}
int main(void)
{
    char path[4096],error[256];
    while(fgets(path,sizeof path,stdin)) {
        path[strcspn(path,"\r\n")]=0;
        FILE *file=fopen(path,"rb");
        if(!file)return 2;
        size_t size=fread(bytes,1,sizeof bytes,file);fclose(file);
        int loaded=fm_load(&graph,bytes,size,error,sizeof error);
        printf("{\"path\":");quoted(path);printf(",\"loaded\":%s",loaded?"true":"false");
        if(!loaded) {printf(",\"error\":");quoted(error);puts("}");continue;}
        uint32_t need=fm_delay_required(&graph,44100);
        float *arena=need && need!=UINT32_MAX?calloc(need,sizeof(float)):NULL;
        int rendered=need!=UINT32_MAX && fm_start(&voice,&graph,44100) && fm_bind_delay(&voice,&graph,arena,need);
        /* Silent finite-output smoke test. Reference/oracle suites separately
         * check numerical agreement, live changes and longer state evolution. */
        for(unsigned block=0;rendered && block<16;++block) {
            float out[FM_BLOCK*2]={0};
            fm_render(&graph,&voice,&scratch,out);
            for(unsigned i=0;i<FM_BLOCK*2;++i)if(!isfinite(out[i]))rendered=0;
            if(voice.fault)rendered=0;
        }
        free(arena);
        printf(",\"nodes\":%u,\"signals\":%u,\"inputs\":%u,\"arena_samples\":%u,\"smoke_passed\":%s,\"ugens\":[",graph.nodes,graph.outputs,graph.inputs,need,rendered?"true":"false");
        for(unsigned i=0;i<graph.nodes;++i) {
            const fm_node *n=&graph.node[i];
            if(i)putchar(',');
            printf("{\"name\":\"%s\",\"rate\":%u,\"selector\":%d}",fm_type_name(n->type),n->rate,n->special);
        }
        puts("]}");
    }
    return ferror(stdin)?2:0;
}
