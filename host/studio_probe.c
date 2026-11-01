/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Browser compiler inspection uses the same generated loader and FM1 policy. */
#include "patch_format.h"
#include "../firmware/components/instrument/include/playback_mode.h"
#include <string.h>
#include <stdlib.h>
static fm_graph graph;
static unsigned char bytes[FM_FILE_BYTES + 1];
static void hex(const char *s)
{
    putchar('"');for(;*s;++s)printf("%02x",(unsigned char)*s);putchar('"');
}
int main(int argc,char **argv)
{
    if(argc!=2 && argc!=3)return 2;
    FILE *f=fopen(argv[1],"rb");if(!f)return 2;
    size_t size=fread(bytes,1,sizeof bytes,f);int failed=ferror(f);fclose(f);if(failed)return 2;
    char error[160]={0};int loaded=fm_load(&graph,bytes,size,error,sizeof error);
    printf("{\"loaded\":%s",loaded?"true":"false");
    if(loaded){
        patch_meta meta={0};meta.graph_bytes=(uint32_t)size;meta.flags=(argc==3 && atoi(argv[2]))?PATCH_DEFINITION:0;
        int admitted=patch_validate(&graph,&meta,error);
        char master_error[160]={0};int master=patch_validate_master(&graph,&meta,master_error);
        printf(",\"fm1_admitted\":%s,\"continuous\":%s,\"name_hex\":",admitted?"true":"false",graph_continuous_mode(&graph)==1?"true":"false");hex(graph.name);
        printf(",\"nodes\":%u,\"signals\":%u,\"inputs\":%u,\"delay_samples\":%u,\"touch_buses\":",
               graph.nodes,graph.outputs,graph.inputs,fm_delay_required(&graph,44100));
        int touch=0;for(unsigned n=0;n<graph.nodes;++n)if(graph.node[n].type==FM_In && graph.node[n].rate==1)touch=1;
        printf("%s,\"ugens\":[",touch?"true":"false");
        for(unsigned n=0;n<graph.nodes;++n)printf("%s\"%s\"",n?",":"",fm_type_name(graph.node[n].type));
        printf("],\"controls\":[");
        for(unsigned n=0;n<graph.names;++n){
            unsigned index=graph.control_name[n].index,count=graph.controls-index,rate=1,trigger=0;
            for(unsigned j=0;j<graph.names;++j)if(graph.control_name[j].index>index && (unsigned)(graph.control_name[j].index-index)<count)count=graph.control_name[j].index-index;
            for(unsigned j=0;j<graph.nodes;++j){const fm_node *u=&graph.node[j];
                if((u->type==FM_Control || u->type==FM_LagControl || u->type==FM_TrigControl) && u->special>=0 && index>=(unsigned)u->special && index<(unsigned)u->special+u->outputs){if(!u->rate)rate=0;if(u->type==FM_TrigControl)trigger=1;}}
            printf("%s{\"name_hex\":",n?",":"");hex(graph.control_name[n].name);
            printf(",\"default\":%.9g,\"index\":%u,\"count\":%u,\"rate\":%u,\"trigger\":%s,\"writable\":%s}",(double)graph.defaults[index],index,count,rate,trigger?"true":"false",rate && strncmp(graph.control_name[n].name,"__esp32_",8)?"true":"false");
        }
        putchar(']');
        printf(",\"master_admitted\":%s,\"master_error_hex\":",master?"true":"false");hex(master_error);
    }
    printf(",\"error_hex\":");hex(error);puts("}");return 0;
}
