/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "master_delay.h"
#include "instrument.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static fm_graph graph,note_graph;static fm_voice voice,note_voice;static fm_scratch scratch;static master_delay bus;static instrument note;
int main(int argc,char **argv)
{
    assert(argc==3);unsigned char bytes[FM_FILE_BYTES];char error[160];
    FILE *f=fopen(argv[1],"rb");assert(f);size_t n=fread(bytes,1,sizeof bytes,f);fclose(f);assert(fm_load(&graph,bytes,n,error,sizeof error));
    f=fopen(argv[2],"rb");assert(f);n=fread(bytes,1,sizeof bytes,f);fclose(f);assert(fm_load(&note_graph,bytes,n,error,sizeof error));
    float *arena=malloc((MASTER_DELAY_SAMPLES+16)*sizeof(float));assert(arena);
    for(unsigned i=0;i<16;++i)arena[MASTER_DELAY_SAMPLES+i]=12345;
    assert(!master_delay_init(&bus,&graph,&voice,arena,65536,44100,&scratch));
    assert(master_delay_init(&bus,&graph,&voice,arena,MASTER_DELAY_SAMPLES,44100,&scratch));
    assert(!master_delay_set(&bus,0,NAN) && !master_delay_set(&bus,1,INFINITY) && !master_delay_set(&bus,0,5.01f) && !master_delay_set(&bus,1,.81f));
    assert(master_delay_set(&bus,0,5) && master_delay_set(&bus,1,.35f) && master_delay_set(&bus,2,1));
    assert(master_delay_reset(&bus,&scratch));
    assert(instrument_init(&note,&note_graph,&note_voice,&scratch,NULL,0,44100));
    unsigned first=0,second=0;float in[FM_BLOCK*2]={0},out[FM_BLOCK*2];
    for(unsigned base=0;base<441000+64;base+=FM_BLOCK) {
        memset(in,0,sizeof in);if(!base)in[0]=in[1]=.25f;
        if(base==640) {uint32_t count=voice.blocks;inst_event event={INST_NOTE_ON,1,0};assert(instrument_apply(&note,&event));assert(voice.blocks==count);}
        master_delay_render(&bus,&scratch,in,out);
        for(unsigned i=0;i<FM_BLOCK;++i) {
            unsigned frame=base+i;assert(isfinite(out[2*i]) && out[2*i]==out[2*i+1]);
            if(frame<220500)assert(fabsf(out[2*i])<1e-7f);
            if(fabsf(out[2*i]-.1625f)<1e-5f && frame==220500)++first;
            if(fabsf(out[2*i]-.056875f)<1e-5f && frame==441000)++second;
        }
    }
    assert(first==1 && second==1 && !bus.faults);
    master_delay_panic(&bus);memset(in,0,sizeof in);master_delay_render(&bus,&scratch,in,out);
    for(unsigned i=0;i<FM_BLOCK*2;++i)assert(out[i]==0);
    assert(master_delay_reset(&bus,&scratch));
    for(unsigned i=0;i<MASTER_DELAY_SAMPLES;++i)assert(arena[i]==0);
    assert(master_delay_set(&bus,0,.02f) && master_delay_set(&bus,1,.8f));assert(master_delay_reset(&bus,&scratch));
    for(unsigned b=0;b<16000;++b) {
        for(unsigned i=0;i<FM_BLOCK*2;++i)in[i]=.125f;
        master_delay_render(&bus,&scratch,in,out);
        for(unsigned i=0;i<FM_BLOCK*2;++i)assert(isfinite(out[i]) && fabsf(out[i])<.126f);
    }
    assert(master_delay_set(&bus,2,0));assert(master_delay_reset(&bus,&scratch));
    for(unsigned b=0;b<100;++b) {
        for(unsigned i=0;i<FM_BLOCK*2;++i)in[i]=(float)((int)(i+b)%127-63)/128;
        master_delay_render(&bus,&scratch,in,out);int16_t expected[FM_BLOCK],actual[FM_BLOCK];uint64_t c=0,z=0;
        instrument_pcm(in,expected,.8f,&z,&c);instrument_pcm(out,actual,.8f,&z,&c);assert(!memcmp(expected,actual,sizeof expected));
    }
    for(unsigned i=0;i<16;++i)assert(arena[MASTER_DELAY_SAMPLES+i]==12345);
    free(arena);puts("PASS: 5-second echo timing, feedback decay, new-note tail preservation, panic/reset, sustained feedback bound, dry PCM identity, invalid controls and arena canaries");
}
