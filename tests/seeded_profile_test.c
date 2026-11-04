/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Offline execution of the target diagnostic, with fake clocks/allocator only. */
#include "diagnostics.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
static int allocation_fail=-1;
void *test_alloc(size_t n,unsigned flags){(void)flags;if(allocation_fail==0)return NULL;if(allocation_fail>0)--allocation_fail;return malloc(n);}
uint32_t esp_cpu_get_cycle_count(void){static uint32_t cycles;return cycles+=240;}
uint32_t fm_ugen_clock(void){return esp_cpu_get_cycle_count();}
int64_t esp_timer_get_time(void){static int64_t us;return ++us;}
int esp_clk_cpu_freq(void){return 240000000;}
void vTaskDelay(unsigned ticks){(void)ticks;}
int main(int argc,char **argv){
 assert(argc==2);FILE *f=fopen(argv[1],"rb");assert(f);unsigned char bytes[65536];size_t n=fread(bytes,1,sizeof bytes,f);fclose(f);
 fm_graph *g=calloc(1,sizeof *g);fm_voice *v=calloc(1,sizeof *v),*saved=malloc(sizeof *v);
 fm_scratch *b=calloc(1,sizeof *b),*saved_b=malloc(sizeof *b);char error[256];assert(fm_load(g,bytes,n,error,sizeof error));
 unsigned need=fm_delay_required(g,44100);assert(need<=FM_DELAY_LIMIT);
 float *arena=calloc(need+2,sizeof(float)),*saved_a=malloc((need+2)*sizeof(float)),bus[FM_CONTROL_BUSES]={.5f,.25f};
 assert(fm_start(v,g,44100) && fm_seed(v,987654) && fm_bind_delay(v,g,arena,need) && fm_bind_control_buses(v,bus,FM_CONTROL_BUSES));
 float out[FM_BLOCK*2]={0};fm_render(g,v,b,out);arena[need]=1234;arena[need+1]=-4321;
 instrument s={.graph=g,.voice=v,.scratch=b,.arena=arena,.arena_needed=need,.arena_samples=need,.sample_rate=44100};
 memcpy(saved,v,sizeof *v);memcpy(saved_b,b,sizeof *b);memcpy(saved_a,arena,(need+2)*sizeof(float));
 for(int i=-1;i<(need?3:2);++i){
  allocation_fail=i;assert(diagnostic_ugen_profile_seeded(&s));
  assert(!memcmp(saved,v,sizeof *v) && !memcmp(saved_b,b,sizeof *b) && !memcmp(saved_a,arena,(need+2)*sizeof(float)));
  diagnostic_ugen_report();
 }
 allocation_fail=-1;assert(diagnostic_ugen_profile_seeded(&s));diagnostic_ugen_report();
 assert(!memcmp(saved,v,sizeof *v) && !memcmp(saved_b,b,sizeof *b) && !memcmp(saved_a,arena,(need+2)*sizeof(float)));
 free(g);free(v);free(saved);free(b);free(saved_b);free(arena);free(saved_a);
 puts("PROFILE_TEST_END");return 0;
}
