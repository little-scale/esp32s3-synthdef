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
    if(argc<2 || argc>4)return 2;
    if(argc==4 && strcmp(argv[3],"16000") && strcmp(argv[3],"44100") && strcmp(argv[3],"48000"))return 2;
    unsigned rate=argc==4?(unsigned)strtoul(argv[3],NULL,10):44100;
    if(rate!=16000 && rate!=44100 && rate!=48000)return 2;
    FILE *f=fopen(argv[1],"rb");if(!f)return 2;
    size_t size=fread(bytes,1,sizeof bytes,f);int failed=ferror(f);fclose(f);if(failed)return 2;
    char error[160]={0};int loaded=fm_load(&graph,bytes,size,error,sizeof error);
    printf("{\"loaded\":%s",loaded?"true":"false");
    if(loaded){
        patch_meta meta={0};meta.graph_bytes=(uint32_t)size;meta.flags=(argc>=3 && atoi(argv[2]))?PATCH_DEFINITION:0;
        int admitted=patch_validate_at_rate(&graph,&meta,rate,error);
        char master_error[160]={0};int master=patch_validate_master_at_rate(&graph,&meta,rate,master_error);
        printf(",\"fm1_admitted\":%s,\"continuous\":%s,\"name_hex\":",admitted?"true":"false",graph_continuous_mode(&graph)==1?"true":"false");hex(graph.name);
        printf(",\"nodes\":%u,\"signals\":%u,\"inputs\":%u,\"delay_samples\":%u,\"touch_buses\":",
               graph.nodes,graph.outputs,graph.inputs,fm_delay_required(&graph,(float)rate));

        int touch=0;for(unsigned n=0;n<graph.nodes;++n)if(graph.node[n].type==FM_In && graph.node[n].rate==1)touch=1;
        printf("%s,\"rate\":%u",touch?"true":"false",rate);
        unsigned physical_outputs=0;
        for(unsigned i=0;i<graph.nodes;++i)if(graph.node[i].type==FM_Out && graph.node[i].rate==1)physical_outputs=1;
        printf(",\"requires_control_outputs\":%s",physical_outputs?"true":"false");
#ifdef FM_SIGNAL_REUSE
        printf(",\"audio_buffers\":%u,\"scalar_values\":%u,\"signal_workspace_bytes\":%u",
               graph.audio_buffers,graph.scalar_values,(graph.audio_buffers*FM_BLOCK+graph.scalar_values)*4u);
#endif
        printf(",\"ugens\":[");
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
        printf(",\"admission_rates\":{");
        const unsigned rates[]={16000,44100,48000};
        for(unsigned i=0;i<3;++i){
            char main_error[160]={0},fx_error[160]={0};
            int main_ok=patch_validate_at_rate(&graph,&meta,rates[i],main_error);
            int fx_ok=patch_validate_master_at_rate(&graph,&meta,rates[i],fx_error);
            printf("%s\"%u\":{\"fm1_admitted\":%s,\"master_admitted\":%s,\"delay_samples\":",
                   i?",":"",rates[i],main_ok?"true":"false",fx_ok?"true":"false");
            uint32_t need=fm_delay_required(&graph,(float)rates[i]);
            if(need==UINT32_MAX)printf("null");else printf("%u",need);
            printf(",\"error_hex\":");
            hex(main_error);printf(",\"master_error_hex\":");hex(fx_error);putchar('}');
        }
        putchar('}');
    }
    printf(",\"error_hex\":");hex(error);puts("}");return 0;
}
