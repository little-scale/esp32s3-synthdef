/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Silent differential runner. Binary stdout includes samples AND voice flags.
 * Poison scratch between voices/blocks: only persistent voice state may survive. */
#include "fm_synth.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static fm_graph g;
static fm_graph other;
static fm_voice voices[2];
static struct { unsigned before[8];fm_scratch value;unsigned after[8]; } storage;
static unsigned char bytes[FM_FILE_BYTES+1];

#ifdef FM_SIGNAL_REUSE
static void check_plan(void) {
 unsigned pending[FM_OUTPUTS]={0};unsigned char live[FM_OUTPUTS]={0};
 for(unsigned i=0;i<g.inputs;i++)if(g.ref[i].node>=0)
  ++pending[g.node[g.ref[i].node].output+g.ref[i].output];
 for(unsigned i=0;i<g.nodes;i++){
  const fm_node *n=&g.node[i];
  /* Outputs must be disjoint from every still-live input and each sibling.
   * This independently simulates reference counts, not planner end indices. */
  for(unsigned k=0;k<n->outputs;k++){
   unsigned o=n->output+k,begin=g.signal_offset[o],len=n->rate==2?FM_BLOCK:1;
   assert(begin+len<=sizeof(storage.value.data)/sizeof(float));
   assert(n->rate==2?begin%FM_BLOCK==0 && begin+len<=FM_AUDIO_BUFFERS*FM_BLOCK:begin>=FM_AUDIO_BUFFERS*FM_BLOCK);
   for(unsigned p=0;p<g.outputs;p++)if(live[p]){
    unsigned other=g.signal_offset[p],count=g.output_rate[p]==2?FM_BLOCK:1;
    assert(begin+len<=other || other+count<=begin);
   }
   live[o]=1;
  }
  for(unsigned k=0;k<n->inputs;k++){
   const fm_ref *r=&g.ref[n->input+k];if(r->node<0)continue;
   unsigned o=g.node[r->node].output+r->output;assert(live[o] && pending[o]);
   if(!--pending[o])live[o]=0;
  }
  for(unsigned k=0;k<n->outputs;k++)if(!pending[n->output+k])live[n->output+k]=0;
 }
}
#endif

static void set_if_present(fm_voice *v,const char *name,float value) {
 for(unsigned i=0;i<g.names;i++)if(!strcmp(g.control_name[i].name,name)){
  assert(fm_set(v,&g,name,value));return;
 }
}

int main(int argc,char **argv) {
 if(argc<2 || argc>3)return 2;
 unsigned blocks=argc==3?(unsigned)atoi(argv[2]):32;
 FILE *f=fopen(argv[1],"rb");if(!f)return 2;
 size_t size=fread(bytes,1,sizeof bytes,f);fclose(f);
 char error[256]={0};int loaded=fm_load(&g,bytes,size,error,sizeof error);
 if(!loaded){fprintf(stderr,"{\"loaded\":false,\"valid\":%u}\n",g.valid);return 0;}
#ifdef FM_SIGNAL_REUSE
 check_plan();
#endif
 other=g;
#ifdef FM_SIGNAL_REUSE
 /* Different, equally valid physical mapping in the other graph. This catches
  * stale pointer tables when independent graphs share one scratch arena. */
 for(unsigned i=0;i<other.outputs;i++){
  unsigned offset=g.signal_offset[i];
  other.signal_offset[i]=g.output_rate[i]==2?(g.audio_buffers-1-offset/FM_BLOCK)*FM_BLOCK:
      FM_AUDIO_BUFFERS*FM_BLOCK+g.scalar_values-1-(offset-FM_AUDIO_BUFFERS*FM_BLOCK);
 }
#endif
 uint32_t need=fm_delay_required(&g,44100);
 if(need==UINT32_MAX){fputs("{\"loaded\":true,\"prepared\":false}\n",stderr);return 0;}
 float *arena[2]={NULL,NULL},bank[32]={0};
 for(unsigned v=0;v<2;v++){
  arena[v]=need?calloc(need,sizeof(float)):NULL;assert(!need || arena[v]);
  assert(fm_start(&voices[v],&g,44100));
  assert(fm_seed(&voices[v],12345+v));
  assert(fm_bind_delay(&voices[v],&g,arena[v],need));
  assert(fm_bind_control_buses(&voices[v],bank,32));
  memset(&storage.value,0xff,sizeof storage.value);
  fm_prepare(v?&other:&g,&voices[v],&storage.value);
  fm_prepare(v?&other:&g,&voices[v],&storage.value);
 }
 for(unsigned i=0;i<8;i++)storage.before[i]=storage.after[i]=0x1234abcdu;
 for(unsigned b=0;b<blocks;b++){
  bank[0]=(float)(b%17)/16;bank[1]=1-bank[0];bank[2]=(float)(b%3==0);
  for(unsigned v=0;v<2;v++){
   fm_voice *voice=&voices[v];
   if(b==16 && v==0){
    assert(fm_start(voice,&g,44100));assert(fm_seed(voice,777));
    assert(fm_bind_delay(voice,&g,arena[v],need));assert(fm_bind_control_buses(voice,bank,32));
   }
   set_if_present(voice,"freq",(float)(220+v*110+b*3));
   set_if_present(voice,"amp",.1f+(float)v*.05f);
   set_if_present(voice,"gate",(float)(b%16<8));
   float out[FM_BLOCK*2]={0},in[FM_BLOCK*2];
   for(unsigned i=0;i<FM_BLOCK*2;i++)in[i]=(float)((int)((i+b)%19)-9)*.01f;
   memset(&storage.value,0xff,sizeof storage.value);
   fm_render_input(v?&other:&g,voice,&storage.value,out,in);
   for(unsigned i=0;i<8;i++)assert(storage.before[i]==0x1234abcdu && storage.after[i]==0x1234abcdu);
   assert(fwrite(out,sizeof out,1,stdout)==1);
   unsigned flags=(unsigned)voice->active|((unsigned)voice->fault<<8)|((unsigned)voice->prepared<<16);
   assert(fwrite(&flags,sizeof flags,1,stdout)==1);
  }
 }
 /* Compare final persistent state and feedback memory too. Process-local
  * addresses are not DSP state and differ between the two executables. */
 for(unsigned v=0;v<2;v++){
  fm_voice snapshot=voices[v];snapshot.delay_memory=NULL;snapshot.control_buses=NULL;
  assert(fwrite(&snapshot,sizeof snapshot,1,stdout)==1);
  if(need)assert(fwrite(arena[v],sizeof(float),need,stdout)==need);
 }
 fprintf(stderr,"{\"loaded\":true,\"prepared\":true,\"nodes\":%u,\"outputs\":%u,\"inputs\":%u,\"scratch_bytes\":%zu",
         g.nodes,g.outputs,g.inputs,sizeof(fm_scratch));
#ifdef FM_SIGNAL_REUSE
 fprintf(stderr,",\"audio_buffers\":%u,\"scalar_values\":%u,\"used_sample_bytes\":%u",g.audio_buffers,g.scalar_values,(g.audio_buffers*FM_BLOCK+g.scalar_values)*4u);
#endif
 fputs("}\n",stderr);for(unsigned v=0;v<2;v++)free(arena[v]);
 return ferror(stdout)?2:0;
}
