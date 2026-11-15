/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "master_delay.h"
#include "patch_format.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static fm_graph graph;
static fm_voice voice;
static fm_scratch scratch;
static void load(const char *path,patch_meta *meta)
{
    unsigned char bytes[FM_FILE_BYTES];char error[160];
    FILE *f=fopen(path,"rb");assert(f);
    size_t n=fread(bytes,1,sizeof bytes,f);assert(!ferror(f));fclose(f);
    assert(fm_load(&graph,bytes,n,error,sizeof error));
    memset(meta,0,sizeof *meta);meta->graph_bytes=(uint32_t)n;meta->flags=PATCH_DEFINITION;
}
int main(int argc,char **argv)
{
    assert(argc==4);patch_meta meta;load(argv[1],&meta);
    assert(fm_delay_required(&graph,44100)==262144);
    assert(fm_delay_required(&graph,16000)==131072);
    assert(fm_delay_required(&graph,48000)==UINT32_MAX);
    char error[160];
    assert(patch_validate_at_rate(&graph,&meta,44100,error));
    assert(patch_validate_at_rate(&graph,&meta,16000,error));
    assert(!patch_validate_at_rate(&graph,&meta,48000,error));
    assert(patch_validate_master_at_rate(&graph,&meta,44100,error));
    assert(patch_validate_master_at_rate(&graph,&meta,16000,error));
    assert(!patch_validate_master_at_rate(&graph,&meta,48000,error));
    assert(!patch_validate_at_rate(&graph,&meta,32000,error));
    /* The bounded engine reports overflow, rather than an allocatable 2 MiB
     * requirement. Use a smaller maximum for the separate timing check. */
    graph.constant[1]=.2f;
    const unsigned rates[]={16000,44100,48000};
    for(unsigned pass=0;pass<3;++pass){
        unsigned rate=rates[pass],capacity=fm_delay_required(&graph,(float)rate);
        float *arena=calloc(capacity,sizeof *arena);assert(arena);
        master_delay fx;
        assert(master_effect_init(&fx,&graph,&voice,arena,capacity,rate,&scratch));
        float input[FM_BLOCK*2]={0},output[FM_BLOCK*2];
        unsigned peak_frame[2]={0};float peak[2]={0};
        for(unsigned frame=0;frame<rate/5;frame+=FM_BLOCK){
            memset(input,0,sizeof input);if(!frame){input[0]=1;input[1]=.5f;}
            master_delay_render(&fx,&scratch,input,output);
            assert(!fx.faults);
            for(unsigned j=0;j<FM_BLOCK;++j)for(unsigned ch=0;ch<2;++ch){
                assert(isfinite(output[j*2+ch]));
                if(fabsf(output[j*2+ch])>peak[ch]){peak[ch]=fabsf(output[j*2+ch]);peak_frame[ch]=frame+j;}
            }
        }
        for(unsigned ch=0;ch<2;++ch){
            assert(abs((int)peak_frame[ch]-(int)(rate/10))<=1);
            assert(peak[ch]>(ch?.49f:.99f));
        }
        printf("%u Hz: stereo 100ms delay peaks at %u/%u; arena=%u\n",rate,peak_frame[0],peak_frame[1],capacity);
        free(arena);
    }
    load(argv[2],&meta);
    for(unsigned pass=0;pass<3;++pass){
        unsigned rate=rates[pass];float buses[FM_CONTROL_BUSES]={0};master_delay fx;
        assert(!master_effect_init_buses(&fx,&graph,&voice,NULL,0,rate,&scratch,buses,0,false));
        assert(!master_effect_init_buses(&fx,&graph,&voice,NULL,0,rate,&scratch,NULL,1,false));
        assert(!master_effect_init_buses(&fx,&graph,&voice,NULL,0,rate,&scratch,buses,FM_CONTROL_BUSES+1,false));
        buses[8]=.25f;
        assert(master_effect_init_buses(&fx,&graph,&voice,NULL,0,rate,&scratch,buses,FM_CONTROL_BUSES,false));
        float input[FM_BLOCK*2],output[FM_BLOCK*2];
        for(unsigned i=0;i<FM_BLOCK*2;++i)input[i]=i%2?-.5f:1;
        for(unsigned iteration=0;iteration<3;++iteration){
            if(iteration==1)buses[8]=.75f;
            if(iteration==2)assert(master_delay_reset(&fx,&scratch));
            master_delay_render(&fx,&scratch,input,output);assert(!fx.faults);
            /* Audio binary operators interpolate a changed kr operand across
             * the block, preserving SuperCollider's smooth control transition. */
            for(unsigned i=0;i<FM_BLOCK*2;++i){
                float gain=iteration==1?.25f+.5f*(float)(i/2)/FM_BLOCK:buses[8];
                assert(fabsf(output[i]-input[i]*gain)<1e-6f);
            }
        }
        assert(master_effect_init_buses(&fx,&graph,&voice,NULL,0,rate,&scratch,buses,FM_CONTROL_BUSES,true));
        assert(fx.suppressed && !voice.active);
        assert(master_effect_start(&fx,&scratch,NULL));
        master_delay_render(&fx,&scratch,input,output);
        for(unsigned i=0;i<FM_BLOCK*2;++i){if(fabsf(output[i]-input[i]*buses[8])>=1e-6f)fprintf(stderr,"bus mismatch: rate=%u sample=%u got=%g wanted=%g\n",rate,i,output[i],input[i]*buses[8]);assert(fabsf(output[i]-input[i]*buses[8])<1e-6f);}
        printf("%u Hz: FX bus updates, reset and definition start retain bus binding\n",rate);
    }
    load(argv[3],&meta);
    assert(!patch_validate_at_rate(&graph,&meta,16000,error));
    assert(strstr(error,"MiRings requires at least 32000 Hz"));
    assert(!patch_validate_master_at_rate(&graph,&meta,16000,error));
    assert(strstr(error,"MiRings requires at least 32000 Hz"));
    assert(patch_validate_at_rate(&graph,&meta,48000,error));
    puts("PASS: rate-specific admission, stereo delay timing, FX control-bus lifetime, 16k Rings rejection");
}
