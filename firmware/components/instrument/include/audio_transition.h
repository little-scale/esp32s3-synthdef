/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <string.h>
#include "fm_synth.h"
#define AUDIO_TRANSITION_MS 5u
typedef struct {float current,start,target,step;unsigned position,frames;} audio_transition;
static inline void audio_transition_init(audio_transition *t,unsigned rate){
 unsigned frames=(rate*AUDIO_TRANSITION_MS+999u)/1000u;if(frames<2)frames=2;
 *t=(audio_transition){.current=1,.start=1,.target=1,.position=frames,.frames=frames};
}
static inline void audio_transition_to(audio_transition *t,float target){
 if(target==t->target)return;
 t->start=t->current;t->target=target;t->position=0;
 t->step=(target-t->start)/(float)(t->frames-1);
}
/* Apply after master FX, before volume/PCM. Zero stays zero during DMA drain,
 * including preserved FX tails; steady unity does not touch sample bits. */
static inline void audio_transition_apply(audio_transition *t,float stereo[FM_BLOCK*2]){
 if(t->position==t->frames){if(t->current==0)memset(stereo,0,FM_BLOCK*2*sizeof(float));return;}
 for(unsigned j=0;j<FM_BLOCK;j++){
  if(t->position<t->frames){
   t->current=t->start+t->step*(float)t->position;
   if(++t->position==t->frames)t->current=t->target;
  }
  if(t->current==0)stereo[2*j]=stereo[2*j+1]=0;
  else{stereo[2*j]*=t->current;stereo[2*j+1]*=t->current;}
 }
}
