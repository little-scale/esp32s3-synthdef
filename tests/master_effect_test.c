/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "master_delay.h"
#include "patch_format.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
static fm_graph graph;static fm_voice voice;static fm_scratch scratch;
static float arena[MASTER_DELAY_SAMPLES];
static void load(const char *path)
{
    unsigned char bytes[FM_FILE_BYTES];char error[160];FILE *f=fopen(path,"rb");assert(f);
    size_t count=fread(bytes,1,sizeof bytes,f);fclose(f);assert(fm_load(&graph,bytes,count,error,sizeof error));
    patch_meta meta={0};assert(patch_validate_master(&graph,&meta,error));
}
int main(int argc,char **argv)
{
    assert(argc==3);master_delay effect;float input[FM_BLOCK*2],output[FM_BLOCK*2];
    for(unsigned i=0;i<FM_BLOCK*2;++i)input[i]=sinf((float)i*.12f)*.7f;
    load(argv[1]);assert(master_effect_init(&effect,&graph,&voice,arena,MASTER_DELAY_SAMPLES,44100,&scratch));assert(effect.bypass);
    master_delay_render(&effect,&scratch,input,output);assert(!memcmp(input,output,sizeof input));
    assert(master_delay_reset(&effect,&scratch));master_delay_render(&effect,&scratch,input,output);assert(!memcmp(input,output,sizeof input));
    load(argv[2]);assert(master_effect_init(&effect,&graph,&voice,arena,MASTER_DELAY_SAMPLES,44100,&scratch));assert(!effect.bypass);
    for(unsigned b=0;b<20;++b){master_delay_render(&effect,&scratch,input,output);
        for(unsigned i=0;i<FM_BLOCK*2;++i)assert(output[i]==input[i]*.5f);assert(!voice.fault);}
    master_delay_panic(&effect);master_delay_render(&effect,&scratch,input,output);assert(!memcmp(input,output,sizeof input));
    assert(master_delay_reset(&effect,&scratch));master_delay_render(&effect,&scratch,input,output);
    for(unsigned i=0;i<FM_BLOCK*2;++i)assert(output[i]==input[i]*.5f);
    puts("PASS: exact stereo bypass, generic uploaded master processing, Panic bypass and reset");return 0;
}
