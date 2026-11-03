/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "audio_transition.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
static void fill(float *x){for(unsigned i=0;i<FM_BLOCK;i++){x[2*i]=1;x[2*i+1]=-0.5f;}}
int main(void){
 unsigned rates[]={8000,44100,48000,192000};
 for(unsigned r=0;r<4;r++){
  audio_transition t;float x[FM_BLOCK*2];audio_transition_init(&t,rates[r]);
  fill(x);float original[FM_BLOCK*2];memcpy(original,x,sizeof x);audio_transition_apply(&t,x);assert(!memcmp(x,original,sizeof x));
  audio_transition_to(&t,0);unsigned blocks=(t.frames+FM_BLOCK-1)/FM_BLOCK;float previous=1;
  for(unsigned b=0;b<blocks;b++){
   fill(x);audio_transition_apply(&t,x);
   for(unsigned j=0;j<FM_BLOCK;j++){assert(x[2*j]<=previous && x[2*j]>=0);assert(x[2*j+1]==-0.5f*x[2*j]);previous=x[2*j];}
  }
  assert(t.current==0 && t.position==t.frames);
  /* Preserved FX cannot jump back to full gain after fade-out, or while the
   * control task loads a definition and DMA drains. */
  for(unsigned b=0;b<24;b++){fill(x);audio_transition_apply(&t,x);for(unsigned j=0;j<FM_BLOCK*2;j++)assert(x[j]==0);}
  /* Delayed construction/inactive definitions stay at zero until resume. */
  audio_transition_to(&t,1);previous=0;
  for(unsigned b=0;b<blocks;b++){fill(x);audio_transition_apply(&t,x);for(unsigned j=0;j<FM_BLOCK;j++){assert(x[2*j]>=previous && x[2*j]<=1);previous=x[2*j];}}
  assert(t.current==1);fill(x);audio_transition_apply(&t,x);assert(!memcmp(x,original,sizeof x));
  /* An interrupted fade starts from its last gain, not an endpoint. */
  audio_transition_to(&t,0);fill(x);audio_transition_apply(&t,x);float last=t.current;
  audio_transition_to(&t,1);fill(x);audio_transition_apply(&t,x);assert(x[0]==last);
 }
 puts("PASS: 5 ms stereo ramps, exact endpoints, silence through DMA drain, delayed resume, interruption and bit-exact steady unity at four rates.");
}
