/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Raw engine feasibility only: no production wrapper or output converter. */
#include "fm_synth.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
static fm_graph graph;
static fm_voice voice;
static fm_scratch scratch;
int main(int argc,char **argv)
{
    assert(argc==2);FILE *f=fopen(argv[1],"rb");assert(f);
    unsigned char bytes[FM_FILE_BYTES];size_t n=fread(bytes,1,sizeof bytes,f);assert(!ferror(f));fclose(f);
    char error[160];assert(fm_load(&graph,bytes,n,error,sizeof error));
    for(unsigned pass=0;pass<2;++pass){
        unsigned rate=pass?48000:16000;
        assert(fm_start(&voice,&graph,rate));assert(fm_bind_delay(&voice,&graph,NULL,0));assert(fm_seed(&voice,12345));
        float previous=0,peak=0;unsigned crossings=0,frames=0;
        for(unsigned at=0;at<rate;at+=FM_BLOCK){
            float audio[FM_BLOCK*2]={0};fm_render(&graph,&voice,&scratch,audio);assert(!voice.fault);
            for(unsigned i=0;i<FM_BLOCK && frames<rate;++i,++frames){
                float value=audio[i*2];assert(isfinite(value) && value==audio[i*2+1]);
                if(fabsf(value)>peak)peak=fabsf(value);
                if(frames>=rate/4 && previous<=0 && value>0)++crossings;
                previous=value;
            }
        }
        assert(frames==rate && crossings>=329 && crossings<=331 && peak>.01f && peak<.11f);
        printf("Raw core %u Hz: %u frames, %u positive crossings in final 750ms, peak %.8f\n",rate,frames,crossings,peak);
    }
    puts("PASS: 16k core feasibility. Production wrappers, 48k output conversion and ESP32 CPU gains remain unqualified.");
}
