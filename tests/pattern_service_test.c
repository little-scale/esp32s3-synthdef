/* Native storage/protocol test: fake time/audio, real files and SHA-256. */
#include "pattern_service.h"
#include "remote_control.h"
#include "mbedtls/sha256.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
static fm_graph graph;
static uint64_t now;
static uint32_t revision=1;
static unsigned events,starts,cancels;
unsigned pg_alloc_fail;
/* ESP-IDF SPIFFS does not implement access(); deletion must use unlink/errno. */
int pg_test_access(const char *path,int mode){(void)path;(void)mode;errno=ENOSYS;return -1;}
int64_t esp_timer_get_time(void){return (int64_t)now;}
uint32_t esp_random(void){static uint32_t n=123;return ++n;}
static int remote(const char *op,const unsigned char *p,size_t n,char *out,size_t size){
 if(!strcmp(op,"RCREOPEN")){assert(n==8 && patch_get32(p+4)==revision);snprintf(out,size,"{}");return 1;}
 if(!strcmp(op,"RCINFO")){snprintf(out,size,"{\"boot\":42,\"revision\":%u,\"now_us\":%llu}",revision,(unsigned long long)now);return 1;}
 assert(!strcmp(op,"RCEVENT") && n>=RC_HEADER);
 assert(patch_get32(p)==42 && patch_get32(p+4)==revision);
 if(p[28]==2)cancels++;else events++;
 snprintf(out,size,"{\"queued\":true}");return 1;
}
static int instance(bool start,const unsigned char *p,size_t n){
 assert(start && n==15 && p[9]==1 && p[10]==2 && patch_get32(p+11)==0);
 assert(patch_get32(p)==42 && patch_get32(p+4)==revision);
 ++revision;++starts;return 1;
}
static char reply[4000];
static int command(const char *op,const void *data,size_t n,unsigned channel){return pattern_service_command(op,data,n,channel,reply,sizeof reply);}
static void begin(const unsigned char *raw,size_t n){
 unsigned char header[40];patch_put32(header,123);patch_put32(header+4,(uint32_t)n);
 assert(!mbedtls_sha256(raw,n,header+8,0));assert(command("PBEGIN",header,40,0));
 for(size_t at=0;at<n;){
  unsigned char chunk[264];size_t count=n-at;if(count>256)count=256;
  patch_put32(chunk,123);patch_put32(chunk+4,(uint32_t)at);memcpy(chunk+8,raw+at,count);
  assert(!command("PDATA",chunk,count+8,1));assert(!command("PABORT",NULL,0,1));
  assert(command("PDATA",chunk,count+8,0));at+=count;
 }
}
static int commit(void){unsigned char id[4];patch_put32(id,123);return command("PCOMMIT",id,4,0);}
int main(int argc,char **argv){
 assert(argc==3);FILE *f=fopen(argv[1],"rb");assert(f);
 unsigned char raw[32768];size_t n=fread(raw,1,sizeof raw,f);fclose(f);assert(n>=60);
 graph.controls=3;graph.names=3;graph.nodes=1;
 graph.node[0].type=FM_Control;graph.node[0].rate=1;graph.node[0].outputs=3;
 for(unsigned i=0;i<3;i++){graph.control_name[i].index=i;strcpy(graph.control_name[i].name,((const char *[]){"freq","amp","gate"})[i]);}
 assert(pattern_service_init(remote,instance));
 unsigned char hash[32];memcpy(hash,raw+28,32);
 if(!strcmp(argv[2],"mismatch"))hash[0]^=1;
 pattern_service_bind(&graph,hash,true);pattern_service_tick(true);
 if(!strcmp(argv[2],"install")){
  begin(raw,n);assert(commit());assert(command("PSAVE",NULL,0,0));assert(command("PSAVE",NULL,0,0));
  assert(command("PPLAY",NULL,0,0));assert(starts==1);
  now=50000;pattern_service_tick(true);assert(events==1);
  ++revision;now=100000;pattern_service_tick(true);
  assert(command("PINFO",NULL,0,0) && strstr(reply,"\"running\":false"));
  assert(command("PPLAY",NULL,0,0));assert(starts==2);
  assert(command("PSTOP",NULL,0,0));assert(cancels>=1);
  raw[28]^=1;begin(raw,n);assert(!commit());assert(command("PABORT",NULL,0,0));raw[28]^=1;
  begin(raw,n);pg_alloc_fail=1;assert(!commit());assert(command("PABORT",NULL,0,0));
  assert(command("PINFO",NULL,0,0) && strstr(reply,"\"loaded\":true"));
 }else if(!strcmp(argv[2],"delete")){
  assert(command("PDELETE",NULL,0,0));
  assert(command("PINFO",NULL,0,0) && strstr(reply,"\"loaded\":false"));
 }else if(!strcmp(argv[2],"boot")){
  assert(starts==1);assert(command("PINFO",NULL,0,0) && strstr(reply,"\"running\":true"));
 }else if(!strcmp(argv[2],"empty") || !strcmp(argv[2],"mismatch")){
  assert(starts==0);assert(command("PINFO",NULL,0,0) && strstr(reply,"\"loaded\":false"));
 }else assert(!"unknown mode");
 puts("PASS");return 0;
}
