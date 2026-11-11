/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "sdkconfig.h"
#ifdef SYNTHDEF_DSP_QA
#include "diagnostics.h"
#include "fm_build_profile.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mbedtls/sha256.h"
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
typedef struct {const char *name;const unsigned char *data;size_t bytes;unsigned blocks;} qa_fixture;
#include "qa_pack_generated.h"
#include "qa_schedule_generated.h"
typedef struct {unsigned complete,need,fault_blocks,constructors;uint64_t cycles_us;unsigned char sum[4][32];} qa_result;
static qa_result *qa_results;
static unsigned qa_ready;

static void qa_normalize(fm_voice *v,const fm_graph *g)
{
 v->delay_memory=NULL;v->control_buses=NULL;
 for(unsigned i=0;i<g->nodes;++i){
  unsigned type=g->node[i].type;fm_state *s=&v->state[i];
  if(type==FM_Line || type==FM_XLine)s->freq=s->width=0;
  if(type==FM_Amplitude)s->freq=s->width=s->b1=s->b2=0;
  if(type==FM_SinOscFB){s->freq=s->width=s->a0=0;s->total=0;}
  if(type==FM_Blip){s->initial_value=s->a0=0;s->total=s->dice[0]=0;}
  if(type==FM_Formant){for(unsigned k=0;k<3;k++)s->previous[k]=0;for(unsigned k=3;k<8;k++)s->dice[k]=0;}
  if(type==FM_Gendy1 || type==FM_Gendy2 || type==FM_Gendy3){for(unsigned k=1;k<4;k++)s->dice[k]=0;s->env.start=s->env.end=s->env.level=s->env.grow=0;}
  if((type>=FM_HenonN && type<=FM_LorenzL) || (type>=FM_FBSineN && type<=FM_StandardL))s->freq=s->b1=s->b2=0;
  if(type==FM_Lag2 || type==FM_Lag3)s->freq=0;
 }
}
static void qa_hash(mbedtls_sha256_context hash[4],const fm_graph *g,const fm_voice *v,
                    fm_voice *copy,const fm_scratch *scratch,const float *arena,unsigned need,const float *out)
{
 if(out)mbedtls_sha256_update(&hash[0],(const unsigned char *)out,FM_BLOCK*2*sizeof(float));
 memcpy(copy,v,sizeof *copy);qa_normalize(copy,g);
 mbedtls_sha256_update(&hash[1],(const unsigned char *)copy,sizeof *copy);
 mbedtls_sha256_update(&hash[2],(const unsigned char *)scratch,sizeof *scratch);
 if(need)mbedtls_sha256_update(&hash[3],(const unsigned char *)arena,need*sizeof(float));
}
int diagnostic_dsp_qa(instrument *s)
{
 qa_ready=0;free(qa_results);
 qa_results=heap_caps_calloc(sizeof qa_fixtures/sizeof *qa_fixtures,sizeof *qa_results,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
 fm_graph *g=heap_caps_malloc(sizeof *g,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
 fm_voice *copy=heap_caps_malloc(sizeof *copy,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
 float *arena=heap_caps_calloc(FM_DELAY_LIMIT+2,sizeof(float),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
 if(!qa_results || !g || !copy || !arena){free(g);free(copy);free(arena);return 1;}
 for(unsigned f=0;f<sizeof qa_fixtures/sizeof *qa_fixtures;++f){
  const qa_fixture *test=&qa_fixtures[f];qa_result *r=&qa_results[f];char error[256];
  if(!fm_load(g,test->data,test->bytes,error,sizeof error))break;
  unsigned need=fm_delay_required(g,44100);r->need=need;if(need>FM_DELAY_LIMIT)break;
  memset(arena,0,(need+2)*sizeof(float));arena[need]=1234;arena[need+1]=-4321;
  mbedtls_sha256_context hash[4];for(unsigned k=0;k<4;++k){mbedtls_sha256_init(&hash[k]);mbedtls_sha256_starts(&hash[k],0);}
  float bank[32]={0};unsigned ok=1;
  for(unsigned block=0;block<test->blocks && ok;++block){
   if(block%128==0){
    qa_initial(test->name,44100,bank);
    ok=fm_start(s->voice,g,44100) && fm_seed(s->voice,12345+block) &&
       fm_bind_delay(s->voice,g,arena,need) && fm_bind_control_buses(s->voice,bank,32);
    if(!ok)break;
    memset(s->scratch,0xff,sizeof *s->scratch);fm_prepare(g,s->voice,s->scratch);fm_prepare(g,s->voice,s->scratch);
    qa_hash(hash,g,s->voice,copy,s->scratch,arena,need,NULL);++r->constructors;
   }
   qa_controls(test->name,block,44100,bank,s->voice,g);
   float out[FM_BLOCK*2]={0},in[FM_BLOCK*2];
   for(unsigned j=0;j<FM_BLOCK*2;++j)in[j]=(float)((int)((j+block)%31)-15)*.001f;
   memset(s->scratch,0xff,sizeof *s->scratch);
   uint64_t begin=esp_timer_get_time();fm_render_input(g,s->voice,s->scratch,out,in);
   r->cycles_us+=esp_timer_get_time()-begin;
   qa_hash(hash,g,s->voice,copy,s->scratch,arena,need,out);r->fault_blocks+=s->voice->fault!=0;
   if(arena[need]!=1234 || arena[need+1]!=-4321)ok=0;
   if((block&15)==15)vTaskDelay(1);
  }
  for(unsigned k=0;k<4;++k){mbedtls_sha256_finish(&hash[k],r->sum[k]);mbedtls_sha256_free(&hash[k]);}
  r->complete=ok;if(!ok)break;++qa_ready;
 }
 /* The diagnostic borrows the parked voice/scratch, as the existing long trace
  * does. Reinitialize against its real graph so no temporary pointers escape. */
 instrument_init_definition(s,s->graph,s->voice,s->scratch,s->arena,s->arena_samples,s->sample_rate,s->managed_definition);
 instrument_panic(s);free(g);free(copy);free(arena);return 1;
}
void diagnostic_dsp_qa_report(void)
{
 printf("DSPQA_BEGIN cases=%u complete=%u pack=%s candidates=%s qualified=%u rate=44100 block=64\n",(unsigned)(sizeof qa_fixtures/sizeof *qa_fixtures),qa_ready,QA_PACK_SHA256,SYNTHDEF_DSP_CANDIDATE_LABEL,FM_QUALIFIED_KERNELS_ENABLED);
 for(unsigned f=0;f<qa_ready;++f){qa_result *r=&qa_results[f];
  printf("DSPQA_CASE index=%u blocks=%u arena_samples=%u fault_blocks=%u constructors=%u render_us=%" PRIu64,f,qa_fixtures[f].blocks,r->need,r->fault_blocks,r->constructors,r->cycles_us);
  for(unsigned k=0;k<4;++k){printf(" h%u=",k);for(unsigned j=0;j<32;++j)printf("%02x",r->sum[k][j]);}putchar('\n');
 }puts("DSPQA_END");
}
#endif
