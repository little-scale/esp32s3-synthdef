/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "fm_synth.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
extern int osc_ref_start(fm_voice*,const fm_graph*,float);
extern int osc_ref_seed(fm_voice*,uint32_t);
extern int osc_ref_bind_control_buses(fm_voice*,const float*,uint32_t);
extern void osc_ref_prepare(const fm_graph*,fm_voice*,fm_scratch*);
extern void osc_ref_render_input(const fm_graph*,fm_voice*,fm_scratch*,float*,const float*);
static fm_graph graph;
static fm_voice a,b,copy_a,copy_b;
static fm_scratch sa,sb;
static uint64_t blocks,constructors,faults;
static void compare(const char *path,unsigned rate,unsigned block,const float *x,const float *y){
 copy_a=a;copy_b=b;copy_a.control_buses=copy_b.control_buses=NULL;
 for(unsigned k=0;k<graph.nodes;k++)if(graph.node[k].type==FM_Saw){
  /* Only these previously unused Saw cache words differ. The complete phase,
   * integrator, harmonics, old scale, scratch, RNG and flags remain checked. */
  copy_a.state[k].b1=copy_b.state[k].b1=0;
  copy_a.state[k].total=copy_b.state[k].total=0;
 }
 if((x && memcmp(x,y,FM_BLOCK*2*sizeof(float))) || memcmp(&copy_a,&copy_b,sizeof copy_a) || memcmp(&sa,&sb,sizeof sa)){
  unsigned offset=0;while(offset<sizeof copy_a && ((unsigned char*)&copy_a)[offset]==((unsigned char*)&copy_b)[offset])offset++;
  fprintf(stderr,"Mismatch %s rate=%u block=%u audio=%d state_offset=%u scratch=%d faults=%u/%u\n",path,rate,block,x?memcmp(x,y,FM_BLOCK*2*sizeof(float)):0,offset,memcmp(&sa,&sb,sizeof sa),a.fault,b.fault);
  for(unsigned k=0;k<graph.nodes;k++)if(memcmp(&copy_a.state[k],&copy_b.state[k],sizeof(fm_state))){
   unsigned char *pa=(unsigned char*)&copy_a.state[k],*pb=(unsigned char*)&copy_b.state[k];
   for(unsigned z=0;z<sizeof(fm_state);z++)if(pa[z]!=pb[z])fprintf(stderr,"node=%u type=%u byte=%u actual=%02x oracle=%02x\n",k,graph.node[k].type,z,pa[z],pb[z]);
  }exit(1);
 }
}
static void start(float sr,float *bank,unsigned seed){
 memset(&sa,0xff,sizeof sa);memset(&sb,0xff,sizeof sb);
 assert(fm_start(&a,&graph,sr)&&osc_ref_start(&b,&graph,sr));
 assert(fm_seed(&a,seed)&&osc_ref_seed(&b,seed));
 assert(fm_bind_control_buses(&a,bank,32)&&osc_ref_bind_control_buses(&b,bank,32));
}
static void load(const char *path){
 unsigned char data[FM_FILE_BYTES];FILE *f=fopen(path,"rb");assert(f);
 size_t bytes=fread(data,1,sizeof data,f);fclose(f);char error[256];
 if(!fm_load(&graph,data,bytes,error,sizeof error)){fprintf(stderr,"%s: %s\n",path,error);exit(1);}
 assert(fm_delay_required(&graph,48000)==0);
}
static void check(const char *path){
#ifdef OSC_TEST_NATIVE16
 const unsigned rates[]={16000};
#else
 const unsigned rates[]={8000,44100,48000,192000};
#endif
 int saw=strstr(path,"Saw")!=NULL,kr=strstr(path,"_kr")!=NULL;
 for(unsigned r=0;r<sizeof rates/sizeof *rates;r++)for(unsigned pass=0;pass<3;pass++){
  float sr=rates[r],effective=kr?sr/FM_BLOCK:sr,bank[32]={effective/17,0};
  start(sr,bank,12345+pass);
  if(pass!=1){fm_prepare(&graph,&a,&sa);osc_ref_prepare(&graph,&b,&sb);constructors++;compare(path,rates[r],0,NULL,NULL);
   fm_prepare(&graph,&a,&sa);osc_ref_prepare(&graph,&b,&sb);compare(path,rates[r],0,NULL,NULL);}
  for(unsigned block=0;block<2048;block++){
   unsigned change=block/7;
   if(saw){
    const unsigned harmonics[]={1,2,3,7,31,100,4096,16777215,97,2,1,200};
    bank[0]=effective*.5f/harmonics[change%12];
    if(change%3==1)bank[0]=nextafterf(bank[0],INFINITY);
    if(change%3==2)bank[0]=nextafterf(bank[0],0);
    if(bank[0]>effective*.5f)bank[0]=effective*.5f;
    if(effective*.5f/bank[0]>16777216)bank[0]=nextafterf(bank[0],INFINITY);
   }else{
    const float freq[]={0,-0.,1,-1,.001f,-.001f,13,-13,.5f,-.5f,1.5f,-1.5f,100,-100};
    bank[0]=freq[change%14];if(change%5==0)bank[0]*=effective;
   }
   float input[FM_BLOCK*2],x[FM_BLOCK*2]={0},y[FM_BLOCK*2]={0};
   for(unsigned j=0;j<FM_BLOCK;j++){
    input[2*j]=bank[0]+((int)(j%7)-3)*effective/100;
    input[2*j+1]=-input[2*j];
   }
   memset(&sa,0xff,sizeof sa);memset(&sb,0xff,sizeof sb);
   fm_render_input(&graph,&a,&sa,x,input);osc_ref_render_input(&graph,&b,&sb,y,input);
   compare(path,rates[r],block,x,y);assert(!a.fault);blocks++;
  }
  if(saw){
   const float invalid[]={0,-0.,-1,INFINITY,NAN,effective,effective*1e-10f};
   for(unsigned k=0;k<sizeof invalid/sizeof *invalid;k++){
    bank[0]=invalid[k];start(sr,bank,17);
    float x[FM_BLOCK*2]={0},y[FM_BLOCK*2]={0};
    fm_render_input(&graph,&a,&sa,x,NULL);osc_ref_render_input(&graph,&b,&sb,y,NULL);
    compare(path,rates[r],k,x,y);
    /* Literal/Rand frequency fixtures ignore the bank, so only dynamic cases fault. */
    if(strstr(path,"dynamic")){assert(a.fault);faults++;}
   }
  }
 }
}
static void benchmark(const char *path){
 load(path);float bank[32]={220,0},input[128]={0},out[128]={0};double seconds[2];volatile float sink=0;
 static fm_voice saved;static fm_scratch saved_scratch;float saved_output[128];
 const unsigned iterations=131072;
 for(unsigned variant=0;variant<2;variant++){
  start(48000,bank,12345);
  for(unsigned k=0;k<512;k++){memset(out,0,sizeof out);if(variant)fm_render_input(&graph,&a,&sa,out,input);else osc_ref_render_input(&graph,&b,&sb,out,input);}
  clock_t begin=clock();
  for(unsigned k=0;k<iterations;k++){memset(out,0,sizeof out);if(variant)fm_render_input(&graph,&a,&sa,out,input);else osc_ref_render_input(&graph,&b,&sb,out,input);sink+=out[k%128];}
  seconds[variant]=(double)(clock()-begin)/CLOCKS_PER_SEC;assert(!(variant?a.fault:b.fault));
  if(!variant){saved=b;saved_scratch=sb;memcpy(saved_output,out,sizeof out);}
  else{b=saved;sb=saved_scratch;compare(path,48000,iterations,out,saved_output);}
 }
 printf("{\"reference_seconds\":%.9f,\"candidate_seconds\":%.9f,\"blocks\":%u,\"sink\":%.9g}\n",seconds[0],seconds[1],iterations,(double)sink);
}
int main(int argc,char **argv){
 assert(argc>1);if(!strcmp(argv[1],"--benchmark")){assert(argc==3);benchmark(argv[2]);return 0;}
 for(int k=1;k<argc;k++){load(argv[k]);check(argv[k]);}
 printf("{\"passed\":true,\"graphs\":%d,\"blocks\":%llu,\"stereo_samples\":%llu,\"explicit_constructors\":%llu,\"matching_faults\":%llu}\n",argc-1,(unsigned long long)blocks,(unsigned long long)(blocks*128),(unsigned long long)constructors,(unsigned long long)faults);
}
