/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "fm_synth.h"
#include <assert.h>
#include <stdio.h>
#include <math.h>
#include <string.h>
extern int fm_ref_start(fm_voice*,const fm_graph*,float);
extern int fm_ref_set(fm_voice*,const fm_graph*,const char*,float);
extern void fm_ref_render(const fm_graph*,fm_voice*,fm_scratch*,float*);
static fm_graph g;static fm_voice a,b;static fm_scratch sa,sb;
int main(int argc,char**argv){assert(argc>1);unsigned char data[65536];unsigned rates[]={8000,44100,48000,192000};unsigned long long samples=0;
 for(int f=1;f<argc;++f){FILE*file=fopen(argv[f],"rb");assert(file);size_t n=fread(data,1,sizeof data,file);fclose(file);char err[160];assert(fm_load(&g,data,n,err,sizeof err));
 for(unsigned ri=0;ri<4;++ri){float sr=rates[ri];memset(&sa,0,sizeof sa);memset(&sb,0,sizeof sb);assert(fm_start(&a,&g,sr)&&fm_ref_start(&b,&g,sr));
 for(unsigned block=0;block<8192;++block){if(block%7==0){unsigned k=block/7;static const int h[]={1,2,3,7,31,100,4096,16777215};float freq=sr*.5f/h[k%8];if(k%3==1)freq=nextafterf(freq,INFINITY);else if(k%3==2)freq=nextafterf(freq,0);if(freq>sr*.5f)freq=sr*.5f;if(sr*.5f/freq>16777216)freq=nextafterf(freq,INFINITY);
 assert(fm_set(&a,&g,"freq",freq)==fm_ref_set(&b,&g,"freq",freq));static const float widths[]={0,1,.5f,.001f,.999f};assert(fm_set(&a,&g,"width",widths[k%5])==fm_ref_set(&b,&g,"width",widths[k%5]));assert(fm_set(&a,&g,"harmonics",1+k%97)==fm_ref_set(&b,&g,"harmonics",1+k%97));}
 float x[128]={0},y[128]={0};fm_render(&g,&a,&sa,x);fm_ref_render(&g,&b,&sb,y);if(a.fault || b.fault || memcmp(x,y,sizeof x) || memcmp(&a,&b,sizeof a)){fprintf(stderr,"Mismatch %s sr=%g block=%u faults=%d/%d output=%d state=%d\n",argv[f],sr,block,a.fault,b.fault,memcmp(x,y,sizeof x),memcmp(&a,&b,sizeof a));return 1;}samples+=128;
 }}}
 printf("{\"passed\":true,\"samples\":%llu}\n",samples);
}