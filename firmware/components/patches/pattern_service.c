/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "pattern_service.h"
#include "pattern_player.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "esp_random.h"
#include "mbedtls/sha256.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#define PROGRAM_MAX 32768u
typedef struct {
 pg_vm *vm;
 pg_player player;
 const fm_graph *graph;
 unsigned char graph_hash[32],hash[32],expected[32],*blob,*stage;
 unsigned bytes,stage_bytes,received,channel;
 uint32_t transfer,generation[2],program_stream;
 int (*remote)(const char *,const unsigned char *,size_t,char *,size_t);
 int (*instance)(bool,const unsigned char *,size_t);
 bool mounted,restored;
 uint64_t last_rx,next_check,eval_us,eval_calls;
 unsigned max_us;
 char reply[4000],error[160];
} program_service;
static program_service *ps;
const char *pattern_service_error(void){return ps && ps->error[0]?ps->error:"Invalid program request, binding or transfer state";
}
static void *memory(size_t size){return heap_caps_calloc(1,size,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
}
static void hex(const unsigned char hash[32],char out[65]){for(unsigned i=0;i<32;i++)snprintf(out+2*i,3,"%02x",hash[i]);
}
static uint64_t field(const char *json,const char *key){const char *p=strstr(json,key);
return p?strtoull(p+strlen(key),NULL,10):UINT64_MAX;
}
static int context(uint32_t *boot,uint32_t *revision,uint64_t *now){
 const unsigned char query[2]={0,0};
 if(!ps->remote || ps->remote("RCINFO",query,2,ps->reply,sizeof ps->reply)<=0)return 0;
 uint64_t b=field(ps->reply,"\"boot\":"),r=field(ps->reply,"\"revision\":"),t=field(ps->reply,"\"now_us\":");
 if(!b||b>UINT32_MAX||!r||r>UINT32_MAX||t==UINT64_MAX)return 0;
 *boot=(uint32_t)b;
 *revision=(uint32_t)r;
 *now=t;
 return 1;
}
static int send_event(const rc_event *e){
 unsigned char wire[RC_HEADER+5*RC_PAIRS]={0};
 patch_put32(wire,e->boot);
 patch_put32(wire+4,e->revision);
 patch_put32(wire+8,e->stream);
 patch_put32(wire+12,e->sequence);
 patch_put32(wire+16,(uint32_t)e->at);
 patch_put32(wire+20,(uint32_t)(e->at>>32));
 patch_put32(wire+24,e->duration);
 wire[28]=e->kind;
 wire[29]=e->stage;
 wire[30]=e->count;
 for(unsigned i=0;i<e->count;i++){wire[32+5*i]=e->index[i];
 uint32_t bits;
 memcpy(&bits,&e->value[i],4);
 patch_put32(wire+33+5*i,bits);
 }
 return ps->remote && ps->remote("RCEVENT",wire,RC_HEADER+5*e->count,ps->reply,sizeof ps->reply)>0;
}
void pattern_service_stop(void){
 if(!ps || !ps->player.stream)return;
 rc_event event;
 pg_player_cancel(&ps->player,&event);
 send_event(&event);
 ps->player.stream=0;
}
static int bound(void){return ps->vm && ps->graph && !memcmp(ps->vm->graph_hash,ps->graph_hash,32);
}
static int start(void){
 if(!bound()){snprintf(ps->error,sizeof ps->error,"Pattern belongs to a different Main definition");
 return 0;
 }
 uint32_t boot,revision;
 uint64_t now;
 if(!context(&boot,&revision,&now)){snprintf(ps->error,sizeof ps->error,"Pattern owner unavailable");
 return 0;
 }
 pattern_service_stop();
 if(!ps->program_stream)ps->program_stream=esp_random()|0x80000000u;
 uint32_t stream=ps->program_stream;
 uint32_t seed=patch_get32(ps->blob+24);
 if(!seed)seed=esp_random();
 if(!pg_player_start(&ps->player,ps->vm,ps->graph,boot,revision,stream,now,seed)){
  snprintf(ps->error,sizeof ps->error,"%s",ps->player.error);
  return 0;
  }
 /* Explicitly create the saved Main. A zero gate avoids an unsolicited first
  * note; set-only programs can also start a continuous gate-free Function.
  * The existing instance hook parks/ramp-resumes audio and rebinds ownership. */
 unsigned char initial[15]={0};patch_put32(initial,boot);patch_put32(initial+4,revision);
 size_t initial_bytes=10;
 if(ps->player.gate>=0 && ps->player.writable[ps->player.gate]){
  initial[9]=1;initial[10]=(unsigned char)ps->player.gate;initial_bytes=15;
 }
 if(!ps->instance || ps->instance(true,initial,initial_bytes)<=0 ||
    !context(&boot,&revision,&now)){
  ps->player.active=0;ps->player.stream=0;
  snprintf(ps->error,sizeof ps->error,"Could not create Main for the standalone program");return 0;
 }
 unsigned char reopen[8];patch_put32(reopen,stream);patch_put32(reopen+4,revision);
 if(ps->remote("RCREOPEN",reopen,8,ps->reply,sizeof ps->reply)<=0 ||
    !pg_player_start(&ps->player,ps->vm,ps->graph,boot,revision,stream,now,seed)){
  ps->player.active=0;ps->player.stream=0;
  snprintf(ps->error,sizeof ps->error,"Could not reopen the local program stream");return 0;
 }
 ps->next_check=0;
 ps->eval_us=ps->eval_calls=ps->max_us=0;
 return 1;
}
#ifndef PG_STORAGE_DIRECTORY
#define PG_STORAGE_DIRECTORY "/patches"
#endif
static void path(unsigned bank,char out[48]){snprintf(out,48,PG_STORAGE_DIRECTORY "/program_%c.bin",bank?'b':'a');
}
static unsigned char *read_record(unsigned bank,unsigned *size,uint32_t *generation){
 char filename[48];
 path(bank,filename);
 FILE *f=fopen(filename,"rb");
 if(!f)return NULL;
 unsigned char header[12];
 if(fread(header,1,12,f)!=12 || memcmp(header,"PGs1",4)){fclose(f);
 return NULL;
 }
 unsigned n=patch_get32(header+8);
 uint32_t gen=patch_get32(header+4);
 if(!gen || !n || n>PROGRAM_MAX){fclose(f);
 return NULL;
 }
 unsigned char *data=memory(n+16);
 if(!data){fclose(f);
 return NULL;
 }
 memcpy(data,header,12);
 int good=fread(data+12,1,n+4,f)==n+4 && fgetc(f)==EOF && patch_crc32(data,n+12)==patch_get32(data+n+12);
 fclose(f);
 if(!good){free(data);
 return NULL;
 }
 memmove(data,data+12,n);
 *size=n;
 *generation=gen;
 return data;
}
static int activate(unsigned char *data,unsigned bytes,bool owned){
 pg_vm *vm=memory(sizeof *vm);
 if(!vm){snprintf(ps->error,sizeof ps->error,"Pattern VM allocation failed");
 return 0;
 }
 if(!pg_load(vm,data,bytes)){snprintf(ps->error,sizeof ps->error,"%s",vm->error);
 free(vm);
 return 0;
 }
 if(memcmp(vm->graph_hash,ps->graph_hash,32)){snprintf(ps->error,sizeof ps->error,"Main changed during program upload");
 free(vm);
 return 0;
 }
 /* Check control binding without starting audio or admitting an event. */
 pg_player check;
 if(!pg_player_start(&check,vm,ps->graph,1,1,1,0,1)){snprintf(ps->error,sizeof ps->error,"%s",check.error);
 free(vm);
 return 0;
 }
 pg_reset(vm,patch_get32(data+24));
 unsigned char digest[32];
 if(mbedtls_sha256(data,bytes,digest,0)){free(vm);
 return 0;
 }
 unsigned char *copy=owned?data:memory(bytes);
 if(!copy){free(vm);
 return 0;
 }
 if(!owned)memcpy(copy,data,bytes);
 pattern_service_stop();
 free(ps->vm);
 free(ps->blob);
 ps->vm=vm;
 ps->blob=copy;
 ps->bytes=bytes;
 memcpy(ps->hash,digest,32);
 memset(&ps->player,0,sizeof ps->player);
 return 1;
}
static int save(void){
 if(!ps->mounted || !bound() || !ps->blob){snprintf(ps->error,sizeof ps->error,"No bound program or storage unavailable");
 return 0;
 }
 uint32_t best=ps->generation[0]>ps->generation[1]?ps->generation[0]:ps->generation[1];
 if(best==UINT32_MAX)return 0;
 unsigned bank=ps->generation[0]<=ps->generation[1]?0:1;
 unsigned n=ps->bytes;
 unsigned char *record=memory(n+16);
 if(!record)return 0;
 memcpy(record,"PGs1",4);
 patch_put32(record+4,best+1);
 patch_put32(record+8,n);
 memcpy(record+12,ps->blob,n);
 patch_put32(record+n+12,patch_crc32(record,n+12));
 char filename[48];
 path(bank,filename);
 FILE *f=fopen(filename,"wb");
 int ok=0;
 if(f){ok=fwrite(record,1,n+16,f)==n+16 && fflush(f)==0;
 if(ok)ok=fsync(fileno(f))==0;
 if(fclose(f))ok=0;
 }
 free(record);
 if(ok){unsigned bytes=0;
 uint32_t gen=0;
 unsigned char *read=read_record(bank,&bytes,&gen);
 ok=read && bytes==n && gen==best+1 && !memcmp(read,ps->blob,n);
 free(read);
 }
 if(ok)ps->generation[bank]=best+1;
 else snprintf(ps->error,sizeof ps->error,"Program storage verification failed");
 return ok;
}
int pattern_service_init(int (*remote)(const char *,const unsigned char *,size_t,char *,size_t),
                         int (*instance)(bool,const unsigned char *,size_t)){
 ps=memory(sizeof *ps);
 if(!ps)return 0;
 ps->remote=remote;
 ps->instance=instance;
 return 1;
}
void pattern_service_bind(const fm_graph *graph,const unsigned char hash[32],bool mounted){
 if(!ps)return;
 ps->player.active=0;
 ps->player.stream=0;
 ps->graph=graph;
 ps->mounted=mounted;
 memcpy(ps->graph_hash,hash,32);
}
static void restore(void){
 ps->restored=true;
 if(!ps->mounted || !ps->graph)return;
 unsigned sizes[2]={0};
 uint32_t gen[2]={0};
 unsigned char *data[2];
 for(unsigned k=0;k<2;k++){data[k]=read_record(k,&sizes[k],&gen[k]);
 ps->generation[k]=gen[k];
 }
 int bank=gen[1]>gen[0]?1:gen[0]?0:-1;
 if(bank>=0 && sizes[bank]>=60 && !memcmp(data[bank]+28,ps->graph_hash,32)){
  if(activate(data[bank],sizes[bank],true)){data[bank]=NULL;
  if(ps->vm->flags&1)start();
  }
 }
 for(unsigned k=0;k<2;k++)free(data[k]);
}
void pattern_service_tick(bool available){
 if(!ps || !available)return;
 if(!ps->restored)restore();
 uint64_t now=(uint64_t)esp_timer_get_time();
 if(ps->stage && now-ps->last_rx>30000000){free(ps->stage);
 ps->stage=NULL;
 ps->received=0;
 }
 if(!ps->player.active)return;
 if(!bound()){pattern_service_stop();
 return;
 }
 if(!ps->next_check || now>=ps->next_check){
  uint32_t boot,revision;
  uint64_t clock;
  if(!context(&boot,&revision,&clock) || boot!=ps->player.boot || revision!=ps->player.revision){ps->player.active=0;
  ps->player.stream=0;
  snprintf(ps->error,sizeof ps->error,"Main/Panic changed pattern ownership; restart required");
  return;
  }
  now=clock;
  ps->next_check=now+50000;
 }
 /* Limit each control-loop turn. No catch-up loop can monopolize this task. */
 for(unsigned k=0;k<4 && ps->player.active;k++){
  rc_event event;
  uint64_t begin=(uint64_t)esp_timer_get_time();
  int result=pg_player_poll(&ps->player,now,&event);
  unsigned elapsed=(unsigned)((uint64_t)esp_timer_get_time()-begin);
  ps->eval_us+=elapsed;
  ps->eval_calls++;
  if(elapsed>ps->max_us)ps->max_us=elapsed;
  if(result<0){snprintf(ps->error,sizeof ps->error,"%s",ps->player.error);
  pattern_service_stop();
  break;
  }
  if(!result)break;
  if(result==1 && !send_event(&event)){snprintf(ps->error,sizeof ps->error,"Pattern event rejected by audio owner");
  pattern_service_stop();
  break;
  }
 }
}
int pattern_service_command(const char *op,const unsigned char *data,size_t bytes,unsigned channel,char *out,size_t size){
 if(!ps)return 0;
 if(!strcmp(op,"PINFO") && !bytes){
  char hash[65]={0};
  if(ps->blob)hex(ps->hash,hash);
  snprintf(out,size,"{\"loaded\":%s,\"running\":%s,\"ended\":%s,\"bound\":%s,\"autostart\":%s,\"bytes\":%u,\"vm_bytes\":%u,\"service_bytes\":%u,\"events\":%llu,\"rests\":%llu,\"steps\":%llu,\"eval_calls\":%llu,\"eval_us\":%llu,\"max_eval_us\":%u,\"sha256\":\"%s\",\"faulted\":%s}",ps->vm?"true":"false",ps->player.active?"true":"false",ps->player.ended?"true":"false",bound()?"true":"false",ps->vm && (ps->vm->flags&1)?"true":"false",ps->bytes,ps->vm?(unsigned)sizeof(pg_vm):0,(unsigned)sizeof *ps,(unsigned long long)ps->player.emitted,(unsigned long long)ps->player.rests,(unsigned long long)(ps->vm?ps->vm->steps:0),(unsigned long long)ps->eval_calls,(unsigned long long)ps->eval_us,ps->max_us,hash,(ps->player.error[0] || ps->error[0])?"true":"false");
  const char *why=ps->player.error[0]?ps->player.error:ps->error;
  char error_hex[321]={0};
  for(unsigned i=0;why[i] && i<160;i++)snprintf(error_hex+2*i,3,"%02x",(unsigned char)why[i]);
  size_t end=strlen(out);
  if(end && out[end-1]=='}' && end<size)snprintf(out+end-1,size-end+1,",\"error_hex\":\"%s\"}",error_hex);
  return 1;
 }
 ps->error[0]=0;
 if(!strcmp(op,"PBEGIN") && bytes==40){
  unsigned total=patch_get32(data+4);
  if(ps->stage || total<60 || total>PROGRAM_MAX || !patch_get32(data))return 0;
  ps->stage=memory(total);
  if(!ps->stage)return 0;
  ps->stage_bytes=total;
  ps->received=0;
  ps->transfer=patch_get32(data);
  ps->channel=channel;
  memcpy(ps->expected,data+8,32);
  ps->last_rx=esp_timer_get_time();
  snprintf(out,size,"{\"received\":0}");
  return 1;
 }
 if(!strcmp(op,"PDATA") && bytes>=9 && ps->stage && channel==ps->channel && patch_get32(data)==ps->transfer){
  unsigned at=patch_get32(data+4),n=(unsigned)bytes-8;
  if(at!=ps->received || at>ps->stage_bytes || n>ps->stage_bytes-at)return 0;
  memcpy(ps->stage+at,data+8,n);
  ps->received+=n;
  ps->last_rx=esp_timer_get_time();
  snprintf(out,size,"{\"received\":%u}",ps->received);
  return 1;
 }
 if(!strcmp(op,"PCOMMIT") && bytes==4 && ps->stage && channel==ps->channel && patch_get32(data)==ps->transfer && ps->received==ps->stage_bytes){
  unsigned char hash[32];
  if(mbedtls_sha256(ps->stage,ps->stage_bytes,hash,0) || memcmp(hash,ps->expected,32))return 0;
  if(!activate(ps->stage,ps->stage_bytes,true))return 0;
  ps->stage=NULL;
  ps->received=0;
  char text[65];
  hex(ps->hash,text);
  snprintf(out,size,"{\"loaded\":true,\"sha256\":\"%s\"}",text);
  return 1;
 }
 if(!strcmp(op,"PABORT") && !bytes){if(ps->stage && channel!=ps->channel)return 0;
 free(ps->stage);
 ps->stage=NULL;
 ps->received=0;
 snprintf(out,size,"{\"aborted\":true}");
 return 1;
 }
 if(!strcmp(op,"PSAVE") && !bytes){if(!save())return 0;
 snprintf(out,size,"{\"saved\":true}");
 return 1;
 }
 if(!strcmp(op,"PPLAY") && !bytes){if(!start())return 0;
 snprintf(out,size,"{\"running\":true}");
 return 1;
 }
 if(!strcmp(op,"PSTOP") && !bytes){pattern_service_stop();
 snprintf(out,size,"{\"running\":false}");
 return 1;
 }
 if(!strcmp(op,"PDELETE") && !bytes){pattern_service_stop();
 if(ps->mounted){char filename[48];
 for(unsigned k=0;k<2;k++){path(k,filename);
  if(unlink(filename)!=0 && errno!=ENOENT){
   snprintf(ps->error,sizeof ps->error,"Could not delete saved program record");return 0;
  }
 }}
 free(ps->vm);
 free(ps->blob);
 ps->vm=NULL;
 ps->blob=NULL;
 ps->bytes=0;
 memset(ps->generation,0,sizeof ps->generation);
 snprintf(out,size,"{\"deleted\":true}");
 return 1;
 }
 return 0;
}
