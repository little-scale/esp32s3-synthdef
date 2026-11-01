/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "fm_synth.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
extern int fm_ref_start(fm_voice *,const fm_graph *,float);
extern int fm_ref_bind_delay(fm_voice *,const fm_graph *,float *,uint32_t);
extern int fm_ref_set(fm_voice *,const fm_graph *,const char *,float);
extern void fm_ref_render(const fm_graph *,fm_voice *,fm_scratch *,float *);
extern void miverb_probe(uint32_t,uint32_t,unsigned,unsigned,uint32_t[4]);
extern void miverb_ref_probe(uint32_t,uint32_t,unsigned,unsigned,uint32_t[4]);
static fm_graph g;static fm_voice a,b;static fm_scratch sa,sb;
static void set(const char *name,float value){assert(fm_set(&a,&g,name,value)==fm_ref_set(&b,&g,name,value));}
int main(int argc,char **argv){
 assert(argc>1);
 uint32_t probes=0,word=1;
 static const uint32_t special[]={0,0x80000000u,0x3f800000u,0xbf800000u,0x3f7ffe00u,0x3f7ffdffu,0x3f7ffe01u,0xbf800001u,0xbf7fffffu,0x7f800000u,0xff800000u,0x7fc00001u,0x7f800001u,1,0x80000001u,0x7f7fffffu,0xff7fffffu};
 for(unsigned i=0;i<100000;++i){word=word*1664525u+1013904223u;uint32_t bits=i<sizeof special/sizeof *special?special[i]:word;
  static const uint32_t scales[]={0x3f800000u,0xbf200000u,0x40000000u,0};
  for(unsigned j=0;j<4;++j){uint32_t x[4],y[4];miverb_probe(bits,scales[j],i*31u,i*919u,x);miverb_ref_probe(bits,scales[j],i*31u,i*919u,y);assert(!memcmp(x,y,sizeof x));++probes;}
 }
 unsigned char data[65536];unsigned rates[]={8000,44100,48000,192000};unsigned long long samples=0;
 clock_t start=clock();
 for(int file=1;file<argc;++file){FILE *f=fopen(argv[file],"rb");assert(f);size_t bytes=fread(data,1,sizeof data,f);fclose(f);char error[160];assert(fm_load(&g,data,bytes,error,sizeof error));
 for(unsigned rate=0;rate<4;++rate){unsigned sr=rates[rate],need=fm_delay_required(&g,sr);assert(need!=UINT32_MAX);float *ma=calloc(need?need:1,4),*mb=calloc(need?need:1,4);assert(ma&&mb);
 memset(&sa,0,sizeof sa);memset(&sb,0,sizeof sb);assert(fm_start(&a,&g,sr)&&fm_ref_start(&b,&g,sr));assert(fm_bind_delay(&a,&g,ma,need)&&fm_ref_bind_delay(&b,&g,mb,need));
 for(unsigned block=0;block<4096;++block){if(block%127==0){unsigned k=block/127;static const float t[]={-.1f,0,.7f,.99f,1.25f,2},w[]={-1,0,.5f,1,2},d[]={-1,0,.01f,.5f,1,2},h[]={-1,0,.05f,.5f,1,2},diff[]={-1,0,.625f,.95f,2},level[]={0,.01f,.4f,4,16};
 set("time",t[k%6]);set("wet",w[(k/2)%5]);set("damp",d[(k/3)%6]);set("hp",h[(k/4)%6]);set("diff",diff[(k/5)%5]);set("freeze",(k%7)==0);set("level",level[(k/3)%5]);set("freq",55.f*(1+k%12));}
 float oa[FM_BLOCK*2]={0},ob[FM_BLOCK*2]={0};fm_render(&g,&a,&sa,oa);fm_ref_render(&g,&b,&sb,ob);
 fm_voice shadow=a;shadow.delay_memory=b.delay_memory;
 if(a.fault || b.fault || memcmp(oa,ob,sizeof oa) || memcmp(&shadow,&b,sizeof b) || memcmp(ma,mb,need*4)){
 fprintf(stderr,"Mismatch file=%s sr=%u block=%u fault=%d/%d output=%d state=%d memory=%d\n",argv[file],sr,block,a.fault,b.fault,memcmp(oa,ob,sizeof oa),memcmp(&shadow,&b,sizeof b),memcmp(ma,mb,need*4));return 1;}
 samples+=FM_BLOCK*2;
 }free(ma);free(mb);}}
 printf("{\"passed\":true,\"samples\":%llu,\"clamp_probes\":%u,\"process_seconds\":%.6f}\n",samples,probes,(double)(clock()-start)/CLOCKS_PER_SEC);
}
