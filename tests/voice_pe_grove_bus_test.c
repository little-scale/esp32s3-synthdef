/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "fm_synth.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
static fm_graph graph;
static fm_voice voices[2];
static fm_scratch scratch;
int main(int argc,char **argv)
{
    assert(argc==2);FILE *file=fopen(argv[1],"rb");assert(file);
    unsigned char bytes[FM_FILE_BYTES];size_t count=fread(bytes,1,sizeof bytes,file);fclose(file);
    char error[160];if(!fm_load(&graph,bytes,count,error,sizeof error)){fprintf(stderr,"%s\n",error);return 1;}
    const unsigned rates[]={16000,44100,48000};
    for(unsigned r=0;r<3;++r){
        float physical[FM_CONTROL_BUSES]={0};physical[44]=.75f;
        for(unsigned v=0;v<2;++v){assert(fm_start(&voices[v],&graph,rates[r]));assert(fm_bind_control_buses(&voices[v],physical,FM_CONTROL_BUSES));}
        const float normalised[]={0,.25f,1},lux[]={0,250,3157.5f};
        for(unsigned sample=0;sample<3;++sample){
            physical[42]=normalised[sample];physical[43]=lux[sample];
            for(unsigned block=0;block<8;++block)for(unsigned v=0;v<2;++v){
                if(!block)fm_prepare(&graph,&voices[v],&scratch);
                float audio[FM_BLOCK*2]={0};fm_render(&graph,&voices[v],&scratch,audio);
                assert(!voices[v].fault);
                assert(fabsf(voices[v].control_outputs[36]-normalised[sample])<.00001f);
                assert(fabsf(voices[v].control_outputs[37]-lux[sample])<.001f);
                assert(physical[42]==normalised[sample] && physical[43]==lux[sample] && physical[44]==.75f);
            }
        }
        /* Recreating a graph never mutates the externally owned sensor bank. */
        assert(fm_start(&voices[0],&graph,rates[r]));assert(physical[42]==1 && physical[43]==3157.5f);
        printf("PASS: In.kr(42,2), shared Main/FX bank, held values and graph restart at %u Hz\n",rates[r]);
    }
}
