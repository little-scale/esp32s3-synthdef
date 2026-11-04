/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "fm_synth.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
extern int candidate_ref_start(fm_voice *,const fm_graph *,float);
extern int candidate_ref_seed(fm_voice *,uint32_t);
extern int candidate_ref_bind_control_buses(fm_voice *,const float *,uint32_t);
extern int candidate_ref_bind_delay(fm_voice *,const fm_graph *,float *,uint32_t);
extern void candidate_ref_prepare(const fm_graph *,fm_voice *,fm_scratch *);
extern void candidate_ref_render_input(const fm_graph *,fm_voice *,fm_scratch *,float *,const float *);
static fm_graph graph;
static fm_voice a,b,va,vb;
static fm_scratch sa,sb;
static unsigned char bytes[FM_FILE_BYTES];
static uint64_t samples,blocks,faults,constructors;
static float *arena_a,*arena_b;static uint32_t arena_capacity;
#ifdef FM_CANDIDATE_NOISE
extern uint32_t fm_candidate_test_pink_index(uint32_t);
static void pink_index_probes(void){
 uint32_t word=0;
 for(unsigned i=0;i<200000;i++){
  if(i<65536)word=i;
  else if(i<65568)word=1u<<(i-65536);
  else word=word*1664525u+1013904223u;
  uint32_t copy=word;unsigned k=0;
  if(!copy)k=32;else while(!(copy&1u)){k++;copy>>=1;}
  assert(fm_candidate_test_pink_index(word)==(k&15));
 }
}
#endif
static void compare(const char *file,unsigned rate,unsigned block,const float *oa,const float *ob){
 va=a;vb=b;va.control_buses=vb.control_buses=NULL;
 va.delay_memory=vb.delay_memory=NULL;
 /* Only the newly used, previously unused Lag2/3 input-time cache is ignored. */
 for(unsigned i=0;i<graph.nodes;i++){
  unsigned type=graph.node[i].type;
  if(type==FM_Lag2 || type==FM_Lag3)va.state[i].freq=vb.state[i].freq=0;
#ifdef DSP_CHAOS_COMPARISON
  if((type>=FM_HenonN && type<=FM_LorenzL) || (type>=FM_FBSineN && type<=FM_StandardL))va.state[i].freq=vb.state[i].freq=va.state[i].b1=vb.state[i].b1=va.state[i].b2=vb.state[i].b2=0;
#endif
#ifdef DSP_CORE_COMPARISON
  if(type==FM_Line || type==FM_XLine)va.state[i].freq=vb.state[i].freq=va.state[i].width=vb.state[i].width=0;
  if(type==FM_Amplitude)va.state[i].freq=vb.state[i].freq=va.state[i].width=vb.state[i].width=va.state[i].b1=vb.state[i].b1=va.state[i].b2=vb.state[i].b2=0;
  if(type==FM_SinOscFB){va.state[i].freq=vb.state[i].freq=va.state[i].width=vb.state[i].width=va.state[i].a0=vb.state[i].a0=0;va.state[i].total=vb.state[i].total=0;}
  if(type==FM_Blip){va.state[i].initial_value=vb.state[i].initial_value=va.state[i].a0=vb.state[i].a0=0;va.state[i].total=vb.state[i].total=va.state[i].dice[0]=vb.state[i].dice[0]=0;}
  if(type==FM_Formant){for(unsigned k=0;k<3;k++)va.state[i].previous[k]=vb.state[i].previous[k]=0;for(unsigned k=3;k<8;k++)va.state[i].dice[k]=vb.state[i].dice[k]=0;}
  if(type==FM_Gendy1 || type==FM_Gendy2 || type==FM_Gendy3){
   for(unsigned k=1;k<4;k++)va.state[i].dice[k]=vb.state[i].dice[k]=0;
   va.state[i].env.start=vb.state[i].env.start=va.state[i].env.end=vb.state[i].env.end=va.state[i].env.level=vb.state[i].env.level=va.state[i].env.grow=vb.state[i].env.grow=0;
  }
#endif
 }
 if((oa && memcmp(oa,ob,FM_BLOCK*2*sizeof(float))) || memcmp(&va,&vb,sizeof va)){
  unsigned diff=0;while(diff<sizeof va && ((unsigned char*)&va)[diff]==((unsigned char*)&vb)[diff])diff++;
  fprintf(stderr,"Mismatch %s rate=%u block=%u audio=%d state_offset=%u fault=%u/%u\n",file,rate,block,oa?memcmp(oa,ob,FM_BLOCK*2*sizeof(float)):0,diff,a.fault,b.fault);exit(1);
 }
}
static void prepare(float sr,float *bank,unsigned seed){
 assert(fm_start(&a,&graph,sr)&&candidate_ref_start(&b,&graph,sr));
 assert(fm_seed(&a,seed)&&candidate_ref_seed(&b,seed));
 uint32_t need=fm_delay_required(&graph,sr);assert(need!=UINT32_MAX);
 if(need){
  if(need>arena_capacity){free(arena_a);free(arena_b);arena_a=malloc(need*sizeof(float));arena_b=malloc(need*sizeof(float));assert(arena_a&&arena_b);arena_capacity=need;}
  assert(fm_bind_delay(&a,&graph,arena_a,need)&&candidate_ref_bind_delay(&b,&graph,arena_b,need));
 }
 assert(fm_bind_control_buses(&a,bank,32)&&candidate_ref_bind_control_buses(&b,bank,32));
 memset(&sa,0xff,sizeof sa);memset(&sb,0xff,sizeof sb);
 fm_prepare(&graph,&a,&sa);candidate_ref_prepare(&graph,&b,&sb);constructors++;
}
static void inputs(float *in,unsigned block){
 static const float values[]={0.0f,-0.0f,.1f,-.1f,1,-1,.5f,-.5f,1e-44f,-1e-44f};
 for(unsigned j=0;j<FM_BLOCK;j++){
  in[j*2]=values[(j+block)%10];in[j*2+1]=values[(j*3+block/3+1)%10];
 }
}
static int benchmark(const char *file){
 FILE *f=fopen(file,"rb");assert(f);size_t size=fread(bytes,1,sizeof bytes,f);fclose(f);
 char error[256];assert(fm_load(&graph,bytes,size,error,sizeof error));
 float bank[32]={.25f,.5f,.1f},in[FM_BLOCK*2],out[FM_BLOCK*2];inputs(in,0);
 for(unsigned k=0;k<graph.nodes;k++)if(graph.node[k].type==FM_BinaryOpUGen && (graph.node[k].special==17 || graph.node[k].special==18)){
  const float integers[]={13,21,34,55,89,144,-13,-55};bank[1]=89;
  for(unsigned j=0;j<FM_BLOCK;j++){in[2*j]=integers[j%8];in[2*j+1]=89;}
 }
 const unsigned warm=1024,iterations=16384;double elapsed[2];volatile float sink=0;
 fm_voice reference_final;float reference_out[FM_BLOCK*2];uint32_t need=fm_delay_required(&graph,44100);
 float *reference_arena=malloc((need?need:1)*sizeof(float));assert(reference_arena);
 for(unsigned version=0;version<2;version++){
  prepare(44100,bank,12345);
  for(unsigned k=0;k<warm;k++){
   memset(out,0,sizeof out);if(version)fm_render_input(&graph,&a,&sa,out,in);else candidate_ref_render_input(&graph,&b,&sb,out,in);
  }
  assert(version?a.active:b.active);
  clock_t begin=clock();
  for(unsigned k=0;k<iterations;k++){
   memset(out,0,sizeof out);if(version)fm_render_input(&graph,&a,&sa,out,in);else candidate_ref_render_input(&graph,&b,&sb,out,in);sink+=out[k%128];
  }
  elapsed[version]=(double)(clock()-begin)/CLOCKS_PER_SEC;
  assert(!(version?a.fault:b.fault));
  if(!version){reference_final=b;memcpy(reference_out,out,sizeof out);if(need)memcpy(reference_arena,arena_b,need*sizeof(float));}
  else{b=reference_final;compare(file,44100,iterations,out,reference_out);if(need)assert(!memcmp(reference_arena,arena_a,need*sizeof(float)));}
 }
 free(reference_arena);
 printf("{\"reference_seconds\":%.9f,\"candidate_seconds\":%.9f,\"iterations\":%u,\"sink\":%.9g}\n",elapsed[0],elapsed[1],iterations,(double)sink);return 0;
}
int main(int argc,char **argv){
#ifdef FM_CANDIDATE_NOISE
 pink_index_probes();
#endif
 assert(argc>1);if(!strcmp(argv[1],"--benchmark")){assert(argc==3);return benchmark(argv[2]);}
 const unsigned rates[]={8000,44100,48000,192000};
 const float coeffs[]={0.0f,-0.0f,.99f,-.99f,1,-1,.01f,-.01f,.5f,-.5f};
 const float times[]={0.0f,-0.0f,.000001f,.001f,.1f,1,1000,1000000};
 const float vals[]={0.0f,-0.0f,.1f,-.1f,1,-1,.5f,-.5f,1e-44f};
 for(int file=1;file<argc;file++){
  FILE *f=fopen(argv[file],"rb");assert(f);size_t size=fread(bytes,1,sizeof bytes,f);fclose(f);
  char error[256];if(!fm_load(&graph,bytes,size,error,sizeof error)){fprintf(stderr,"Load %s: %s\n",argv[file],error);return 1;}
  for(unsigned r=0;r<4;r++){
   float bank[32]={.25f,.5f,.1f};
   for(unsigned block=0;block<512;block++){
    if(block%128==0){
     bank[0]=.25f;bank[1]=.5f;bank[2]=strstr(argv[file],"Noise")?(float)rates[r]/128:.1f;
     prepare((float)rates[r],bank,12345+block);compare(argv[file],rates[r],block,NULL,NULL);
     assert(!memcmp(&sa,&sb,sizeof sa));
     fm_prepare(&graph,&a,&sa);candidate_ref_prepare(&graph,&b,&sb);compare(argv[file],rates[r],block,NULL,NULL);
    }
    unsigned step=block%128;
    /* Sustained values exercise no-ramp paths; changing values exercise exact
     * control interpolation and resume after equality/signed-zero boundaries. */
    bank[0]=vals[(step/5)%9];bank[1]=vals[(step/7+2)%9];
    bank[2]=strstr(argv[file],"Lag")?times[(step/9)%8]:coeffs[(step/9)%10];
    if(strstr(argv[file],"Noise")){
     const float frequencies[]={1e9f,192000,1000,100,1,.1f,.001f,0};bank[2]=frequencies[(step/9)%8];
    }
    if(strstr(argv[file],"fault") && step>=120)bank[2]=-2;
    float in[FM_BLOCK*2],oa[FM_BLOCK*2]={0},ob[FM_BLOCK*2]={0};inputs(in,block);
    memset(&sa,0xff,sizeof sa);memset(&sb,0xff,sizeof sb);
    fm_render_input(&graph,&a,&sa,oa,in);candidate_ref_render_input(&graph,&b,&sb,ob,in);
    compare(argv[file],rates[r],block,oa,ob);
    blocks++;samples+=FM_BLOCK*2;faults+=a.fault!=0;
   }
   /* Fault during construction, then clean reconstruction of the same voice.
    * LPZ1/HPZ1 have no coefficient domain. Other normal fixtures also exercise
    * legal endpoint/zero/subnormal constructor coefficients. */
   if(strstr(argv[file],"fault")){
    bank[2]=-2;prepare((float)rates[r],bank,17);compare(argv[file],rates[r],512,NULL,NULL);
    assert(a.fault && b.fault);assert(!memcmp(&sa,&sb,sizeof sa));
    bank[2]=0;prepare((float)rates[r],bank,18);compare(argv[file],rates[r],513,NULL,NULL);
    assert(!a.fault && !b.fault);
   }
  }
 }
 printf("{\"passed\":true,\"graphs\":%d,\"blocks\":%llu,\"samples\":%llu,\"constructors\":%llu,\"matching_fault_blocks\":%llu}\n",argc-1,(unsigned long long)blocks,(unsigned long long)samples,(unsigned long long)constructors,(unsigned long long)faults);return 0;
}
