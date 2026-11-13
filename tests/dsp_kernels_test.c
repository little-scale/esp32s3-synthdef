/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "fm_synth.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern int dsp_ref_start(fm_voice *,const fm_graph *,float);
extern int dsp_ref_seed(fm_voice *,uint32_t);
extern int dsp_ref_set(fm_voice *,const fm_graph *,const char *,float);
extern int dsp_ref_bind_delay(fm_voice *,const fm_graph *,float *,uint32_t);
extern int dsp_ref_bind_control_buses(fm_voice *,const float *,uint32_t);
extern void dsp_ref_prepare(const fm_graph *,fm_voice *,fm_scratch *);
extern void dsp_ref_render_input(const fm_graph *,fm_voice *,fm_scratch *,float *,const float *);
static fm_graph graph;
static fm_voice a,b,va,vb;
static fm_scratch sa,sb;
static unsigned char bytes[FM_FILE_BYTES];
static void set(const char *name,float value){int x=fm_set(&a,&graph,name,value),y=dsp_ref_set(&b,&graph,name,value);assert(x==y);}
static void normalize(fm_voice *v){
 v->delay_memory=NULL;v->control_buses=NULL;
 /* Only new, otherwise-unused coefficient/input cache fields are ignored.
  * All recursive filter/envelope history, RNG, flags and arena stay compared. */
 for(unsigned i=0;i<graph.nodes;i++){
#if defined(DSP_CORE_COMPARISON) || defined(DSP_ALL_CANDIDATES)
  unsigned type=graph.node[i].type;fm_state *s=&v->state[i];
  if(type==FM_Line || type==FM_XLine)s->freq=s->width=0;
  if(type==FM_Amplitude)s->freq=s->width=s->b1=s->b2=0;
  if(type==FM_SinOscFB){s->freq=s->width=s->a0=0;s->total=0;}
  if(type==FM_Blip){s->initial_value=s->a0=0;s->total=s->dice[0]=0;}
  if(type==FM_Formant){for(unsigned k=0;k<3;k++)s->previous[k]=0;for(unsigned k=3;k<8;k++)s->dice[k]=0;}
  if(type==FM_Gendy1 || type==FM_Gendy2 || type==FM_Gendy3){for(unsigned k=1;k<4;k++)s->dice[k]=0;s->env.start=s->env.end=s->env.level=s->env.grow=0;}
#endif
#if defined(DSP_CHAOS_COMPARISON) || defined(DSP_ALL_CANDIDATES)
  {
  unsigned type=graph.node[i].type;
  if((type>=FM_HenonN && type<=FM_LorenzL) || (type>=FM_FBSineN && type<=FM_StandardL))v->state[i].freq=v->state[i].b1=v->state[i].b2=0;
  }
#endif
#if defined(DSP_ALL_CANDIDATES) || defined(DSP_QUALIFIED_COMPARISON)
  if(graph.node[i].type==FM_Lag2 || graph.node[i].type==FM_Lag3)v->state[i].freq=0;
#elif defined(DSP_BINDING_COMPARISON) || defined(DSP_CORE_COMPARISON) || defined(DSP_CHAOS_COMPARISON) || defined(DSP_STRICT_COMPARISON)
  /* Binding changes no state fields; compare every field directly. */
#elif defined(DSP_CANDIDATE_COMPARISON)
  if(graph.node[i].type==FM_Lag2 || graph.node[i].type==FM_Lag3)v->state[i].freq=0;
#else
  if(graph.node[i].type==FM_UnaryOpUGen)v->state[i].freq=v->state[i].last=0;
  if(graph.node[i].type==FM_Lag || graph.node[i].type==FM_LagUD)v->state[i].freq=v->state[i].width=0;
#endif
 }
}
int main(int argc,char **argv){
 assert(argc>1);uint64_t samples=0,blocks=0,faults=0;
 unsigned rates[]={8000,44100,48000,192000};
 unsigned rate_count=4,block_count=512;
 if(getenv("DSP_TEST_BLOCKS")){block_count=(unsigned)atoi(getenv("DSP_TEST_BLOCKS"));assert(block_count>0 && block_count<=8192);}
 if(getenv("DSP_TEST_RATE")){rates[0]=(unsigned)atoi(getenv("DSP_TEST_RATE"));assert(rates[0]>=8000 && rates[0]<=192000);rate_count=1;}
 for(int file=1;file<argc;file++){
  FILE *f=fopen(argv[file],"rb");assert(f);size_t size=fread(bytes,1,sizeof bytes,f);fclose(f);
  char error[256];if(!fm_load(&graph,bytes,size,error,sizeof error)){fprintf(stderr,"Load %s: %s\n",argv[file],error);return 1;}
  for(unsigned rate=0;rate<rate_count;rate++){
   float sr=(float)rates[rate];uint32_t need=fm_delay_required(&graph,sr);assert(need!=UINT32_MAX);
   float *ma=calloc(need?need:1,4),*mb=calloc(need?need:1,4),bank[32]={0};assert(ma&&mb);
   for(unsigned block=0;block<block_count;block++){
    if(block%128==0){
#if defined(DSP_CORE_COMPARISON) || defined(DSP_ALL_CANDIDATES) || defined(DSP_QUALIFIED_COMPARISON)
     if(strstr(argv[file],"core_dynamic_Blip")){bank[0]=sr*.1f;bank[1]=50;}
     if(strstr(argv[file],"core_dynamic_BPeakEQ") || strstr(argv[file],"core_dynamic_BLowShelf") || strstr(argv[file],"core_dynamic_BHiShelf")){bank[0]=sr*.1f;bank[1]=1;bank[2]=0;}
     if(strstr(argv[file],"core_dynamic_Formlet")){bank[0]=sr*.1f;bank[1]=.01f;bank[2]=.2f;}
     if(strstr(argv[file],"core_dynamic_Amplitude")){bank[1]=.01f;bank[2]=.2f;}
#endif
#ifdef DSP_QUALIFIED_COMPARISON
     if(strstr(argv[file],"qualified_smooth_")){bank[0]=.125f;bank[1]=.1f;}
#endif
     assert(fm_start(&a,&graph,sr)&&dsp_ref_start(&b,&graph,sr));
     assert(fm_seed(&a,12345+block)&&dsp_ref_seed(&b,12345+block));
     assert(fm_bind_delay(&a,&graph,ma,need)&&dsp_ref_bind_delay(&b,&graph,mb,need));
     assert(fm_bind_control_buses(&a,bank,32)&&dsp_ref_bind_control_buses(&b,bank,32));
#if defined(DSP_ALL_CANDIDATES) || defined(DSP_QUALIFIED_COMPARISON) || defined(DSP_STRICT_COMPARISON)
     memset(&sa,0xff,sizeof sa);memset(&sb,0xff,sizeof sb);
#endif
     fm_prepare(&graph,&a,&sa);dsp_ref_prepare(&graph,&b,&sb);
     fm_prepare(&graph,&a,&sa);dsp_ref_prepare(&graph,&b,&sb);
#if defined(DSP_ALL_CANDIDATES) || defined(DSP_QUALIFIED_COMPARISON) || defined(DSP_STRICT_COMPARISON)
     va=a;vb=b;normalize(&va);normalize(&vb);
     if(memcmp(&va,&vb,sizeof va)||memcmp(&sa,&sb,sizeof sa)||memcmp(ma,mb,need*4)){
      fprintf(stderr,"Constructor mismatch %s rate=%u\n",argv[file],rates[rate]);return 1;
     }
#endif
    }
    static const float freq[]={0,.01f,24,220,440,1760,2700};
    static const float rq[]={0,.001f,.1f,.5f,1,2};
    static const float times[]={0,.001f,.01f,.2f,1,1000};
    static const float xs[]={0.0f,-0.0f,.1f,-.1f,1,-1,60,-60,1e-20f};
    unsigned k=block/11;
    set("freq",freq[k%7]);set("rq",rq[(block/17)%6]);set("time",times[(block/19)%6]);
    set("lagUp",times[k%6]);set("lagDown",times[(block/17)%6]);
    set("x",xs[(block/7)%9]);set("gate",(float)(block%16<8));
    bank[0]=xs[(block/7)%9];bank[1]=(float)(block%3==0);
#if defined(DSP_CORE_COMPARISON) || defined(DSP_ALL_CANDIDATES) || defined(DSP_QUALIFIED_COMPARISON)
    if(strstr(argv[file],"core_dynamic_SinOscFB")){
     const float f[]={0,.001f,.1f,.25f,.49999997f,.5f};const float fb[]={-8,-1,-0.0f,0,.5f,1,8};
     bank[0]=sr*f[(block/7)%6];bank[1]=fb[(block/11)%7];
    }
    if(strstr(argv[file],"core_dynamic_Blip")){
     const float f[]={.4f,.1f,.1f,.001f,.25f,.49999997f,.5f};const float h[]={50,5,1,0,-1,1000000};
     bank[0]=sr*f[(block/7)%7];bank[1]=h[(block/13)%6];
    }
    if(strstr(argv[file],"core_dynamic_BPeakEQ") || strstr(argv[file],"core_dynamic_BLowShelf") || strstr(argv[file],"core_dynamic_BHiShelf")){
     const float f[]={.001f,.01f,.1f,.25f,.49999997f};const float rq[]={1,1.1f,2,4};const float db[]={-48,-12,0,12,48};
     bank[0]=sr*f[(block/7)%5];bank[1]=rq[(block/11)%4];bank[2]=db[(block/13)%5];
    }
    if(strstr(argv[file],"core_dynamic_Amplitude")){
     const float t[]={0,-0.0f,.000001f,.001f,.1f,1,1000};bank[1]=t[(block/7)%7];bank[2]=t[(block/11+2)%7];
    }
    if(strstr(argv[file],"core_dynamic_Formlet")){
     const float f[]={0,.001f,.1f,.24999997f,.25f,.49999997f,.5f};const float t[]={0,.000001f,.001f,.1f,1,1000};
     bank[0]=sr*f[(block/7)%7];bank[1]=t[(block/11)%6];bank[2]=t[(block/13+2)%6];
    }
    if(strstr(argv[file],"core_dynamic_Formant")){
     const float factors[]={0,.001f,.1f,.25f,.49999997f,.5f};
     bank[0]=sr*factors[(block/7)%6];bank[1]=sr*factors[(block/11+1)%6];bank[2]=sr*factors[(block/13+2)%6];
    }
    if(strstr(argv[file],"core_dynamic_Gendy")){
     const float distributions[]={0,1,2,3,4,5,6,-1,1.8f};const float shape[]={0,-1,.00001f,.1f,.5f,1,100};
     bank[0]=distributions[(block/7)%9];bank[1]=distributions[(block/11+2)%9];bank[2]=shape[(block/5)%7];bank[3]=shape[(block/13+3)%7];
    }
#endif
#ifdef DSP_QUALIFIED_COMPARISON
    if(strstr(argv[file],"qualified_smooth_")){
     const float lag[]={0,-0.0f,.000001f,.01f,.1f,1000};
     const float coef[]={-1,-.5f,-0.0f,0,.5f,1};
     bank[1]=strstr(argv[file],"Lag")?lag[(block/9)%6]:coef[(block/9)%6];
     if(strstr(argv[file],"_fault") && block>=31)bank[1]=strstr(argv[file],"Lag")?-1:1.1f;
    }
    if(strstr(argv[file],"qualified_delay_")){
     const float delay[]={0,-0.0f,.000001f,.013f,.049999f,.05f,.051f,-.1f};
     const float decay[]={-2,-.2f,0,.001f,.2f,2};
     bank[1]=delay[(block/11)%8];bank[2]=decay[(block/13)%6];
    }
#endif
#if defined(DSP_CHAOS_COMPARISON) || defined(DSP_ALL_CANDIDATES)
    if(strstr(argv[file],"chaos_dynamic")){
     const float factors[]={0,.000001f,.001f,.1f,.5f,.99999994f,1,2,4};
     bank[0]=sr*factors[(block/7)%9];
    }
#endif
    float oa[FM_BLOCK*2]={0},ob[FM_BLOCK*2]={0},in[FM_BLOCK*2];
    for(unsigned j=0;j<FM_BLOCK*2;j++)in[j]=(float)((int)((j+block)%31)-15)*.001f;
    memset(&sa,0xff,sizeof sa);memset(&sb,0xff,sizeof sb);
    fm_render_input(&graph,&a,&sa,oa,in);dsp_ref_render_input(&graph,&b,&sb,ob,in);
    va=a;vb=b;normalize(&va);normalize(&vb);
    if(memcmp(oa,ob,sizeof oa)||memcmp(&va,&vb,sizeof va)||memcmp(ma,mb,need*4)
#if defined(DSP_ALL_CANDIDATES) || defined(DSP_QUALIFIED_COMPARISON) || defined(DSP_STRICT_COMPARISON)
       || memcmp(&sa,&sb,sizeof sa)
#endif
       ){
     unsigned differing=0;while(differing<sizeof va && ((unsigned char*)&va)[differing]==((unsigned char*)&vb)[differing])differing++;
     fprintf(stderr,"Mismatch %s rate=%u block=%u audio=%d voice_offset=%u fault=%u/%u\n",argv[file],rates[rate],block,memcmp(oa,ob,sizeof oa),differing,a.fault,b.fault);return 1;
    }
    samples+=FM_BLOCK*2;blocks++;faults+=a.fault!=0;
   }
   free(ma);free(mb);
  }
 }
 printf("{\"passed\":true,\"graphs\":%d,\"blocks\":%llu,\"samples\":%llu,\"matching_fault_blocks\":%llu}\n",argc-1,(unsigned long long)blocks,(unsigned long long)samples,(unsigned long long)faults);
 return 0;
}
