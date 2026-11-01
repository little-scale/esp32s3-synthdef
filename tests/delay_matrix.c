/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "master_delay.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static fm_graph graph;static fm_voice voice;static fm_scratch scratch;static master_delay bus;
int main(int argc,char **argv) {
 assert(argc==3);unsigned char bytes[FM_FILE_BYTES];char error[160];FILE *f=fopen(argv[1],"rb");assert(f);size_t size=fread(bytes,1,sizeof bytes,f);fclose(f);assert(fm_load(&graph,bytes,size,error,sizeof error));
 float *arena=malloc(MASTER_DELAY_SAMPLES*sizeof(float));assert(arena);assert(master_delay_init(&bus,&graph,&voice,arena,MASTER_DELAY_SAMPLES,44100,&scratch));
 float result[4][4][FM_BLOCK]={0};const float times[]={.02f,.35f,1,5};
 for(unsigned c=0;c<4;++c) {
  master_delay_set(&bus,0,times[c]);master_delay_set(&bus,1,.35f);master_delay_set(&bus,2,1);assert(master_delay_reset(&bus,&scratch));
  unsigned distance=(unsigned)lroundf(times[c]*44100),start[]={0,distance-16,2*distance-16};
  for(unsigned base=0;base<2*distance+FM_BLOCK;base+=FM_BLOCK) {
   float input[FM_BLOCK*2]={0},output[FM_BLOCK*2];if(!base)input[0]=input[1]=.25f;master_delay_render(&bus,&scratch,input,output);
   for(unsigned j=0;j<FM_BLOCK;++j)for(unsigned w=0;w<3;++w)if(base+j>=start[w] && base+j<start[w]+FM_BLOCK)result[c][w][base+j-start[w]]=.5f*(output[2*j]+output[2*j+1]);
  }
  master_delay_panic(&bus);float input[FM_BLOCK*2]={0},output[FM_BLOCK*2];master_delay_render(&bus,&scratch,input,output);for(unsigned j=0;j<FM_BLOCK;++j)result[c][3][j]=output[2*j];
  assert(!bus.faults);
 }
 f=fopen(argv[2],"wb");assert(f);assert(fwrite(result,1,sizeof result,f)==sizeof result);assert(!fclose(f));free(arena);
}
