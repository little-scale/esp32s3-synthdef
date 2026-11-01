/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "fm_synth.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern int fm_ref_start(fm_voice *,const fm_graph *,float);
extern int fm_ref_bind_delay(fm_voice *,const fm_graph *,float *,uint32_t);
extern int fm_ref_set(fm_voice *,const fm_graph *,const char *,float);
extern void fm_ref_render(const fm_graph *,fm_voice *,fm_scratch *,float *);
static fm_graph graph;
static fm_voice a,b;
static fm_scratch sa,sb;
static unsigned char data[65536];
static void set(const char *name,float value)
{
    int x=fm_set(&a,&graph,name,value),y=fm_ref_set(&b,&graph,name,value);assert(x==y);
}
int main(int argc,char **argv)
{
    assert(argc>1);uint64_t samples=0;
    const unsigned rates[]={8000,44100,48000,192000};
    for(int file=1;file<argc;++file){
        FILE *f=fopen(argv[file],"rb");assert(f);size_t bytes=fread(data,1,sizeof data,f);assert(!ferror(f));fclose(f);
        char error[160];if(!fm_load(&graph,data,bytes,error,sizeof error)){fprintf(stderr,"%s: %s\n",argv[file],error);return 1;}
        /* Existing instrument presets are qualified at 44.1 kHz; the targeted
         * kernel fixtures exercise the full supported sample-rate range. */
        int legacy=strstr(argv[file],"/examples/")!=NULL;
        for(unsigned rate=0;rate<(legacy?1u:4u);++rate){
            unsigned sr=legacy?44100:rates[rate],need=fm_delay_required(&graph,(float)sr);assert(need!=UINT32_MAX);
            float *ma=calloc(need?need:1,sizeof(float)),*mb=calloc(need?need:1,sizeof(float));assert(ma&&mb);
            assert(fm_start(&a,&graph,(float)sr)&&fm_ref_start(&b,&graph,(float)sr));
            assert(fm_bind_delay(&a,&graph,ma,need)&&fm_ref_bind_delay(&b,&graph,mb,need));
            set("gate",1);set("amp",.5f);
            for(unsigned block=0;block<8192;++block){
                if(block%31==0){
                    static const float freq[]={330,-330,0,.1f,44101,1000000};
                    static const float phase[]={0,.1f,-.5f,6.2831853f,100000};
                    static const float density[]={0,1,-1,100,44100,88200};
                    static const float attack[]={0,.01f,.1f,1};
                    static const float decay[]={0,.1f,2,10};
                    static const float legacy_freq[]={55,110,220,440,880,1760};
                    unsigned k=block/31;set("freq",legacy?legacy_freq[k%6]:freq[k%6]);set("phase",phase[k%5]);
                    set("density",density[k%6]);set("attack",attack[k%4]);set("decay",decay[(k/4)%4]);
                }
                float oa[FM_BLOCK*2]={0},ob[FM_BLOCK*2]={0};
                fm_render(&graph,&a,&sa,oa);fm_ref_render(&graph,&b,&sb,ob);
                if(a.fault || b.fault || a.active!=b.active || memcmp(oa,ob,sizeof oa) ||
                   memcmp(a.random,b.random,sizeof a.random) || memcmp(ma,mb,need*sizeof(float))){
                    fprintf(stderr,"Mismatch: %s rate=%u block=%u faults=%d/%d\n",argv[file],sr,block,a.fault,b.fault);return 1;
                }
                samples+=FM_BLOCK*2;
            }
            free(ma);free(mb);
        }
    }
    printf("PASS: %d graphs, four rates for kernel fixtures / 44.1 kHz for legacy presets, %llu bit-identical output samples; delay memory and shared random sequence also match under changing controls.\n",argc-1,(unsigned long long)samples);
}
