/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "pattern_player.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static pg_vm vm;
static fm_graph graph;
static pg_player player;
int main(int argc,char **argv){
 assert(argc==3);FILE *f=fopen(argv[1],"rb");assert(f);unsigned char raw[32768];
 size_t n=fread(raw,1,sizeof raw,f);fclose(f);assert(pg_load(&vm,raw,n));
 graph.controls=3;graph.names=3;graph.nodes=1;
 graph.node[0].type=FM_Control;graph.node[0].rate=1;graph.node[0].outputs=3;
 for(unsigned i=0;i<3;i++){graph.control_name[i].index=i;strcpy(graph.control_name[i].name,((const char *[]){"freq","amp","gate"})[i]);}
 int started=pg_player_start(&player,&vm,&graph,10,20,30,0,123);
 if(!strcmp(argv[2],"unknown")){assert(!started);assert(strstr(player.error,"writable"));return 0;}
 assert(started);rc_event event;
 assert(pg_player_poll(&player,49999,&event)==0);
 if(!strcmp(argv[2],"notes")){
  assert(pg_player_poll(&player,50000,&event)==1);
  assert(event.at==100000 && event.duration==100000 && event.count==2);
  assert(event.kind==1 && event.stream==30 && event.boot==10 && event.revision==20);
  assert(event.index[0]==0 && event.value[0]>261.62f && event.value[0]<261.64f);
  assert(pg_player_poll(&player,174999,&event)==0);
  assert(pg_player_poll(&player,175000,&event)==1 && event.at==225000);
  assert(pg_player_poll(&player,300000,&event)==1 && event.at==350000);
  assert(pg_player_poll(&player,425000,&event)==0 && player.ended);
 }else if(!strcmp(argv[2],"rest")){
  assert(pg_player_poll(&player,50000,&event)==2 && player.rests==1);
  assert(pg_player_poll(&player,175000,&event)==1 && event.at==225000);
 }else if(!strcmp(argv[2],"set")){
  assert(pg_player_poll(&player,50000,&event)==1 && event.kind==0 && event.duration==0);
  assert(event.count==1 && event.index[0]==0 && event.value[0]==550);
 }else if(!strcmp(argv[2],"late")){
  assert(pg_player_poll(&player,200001,&event)==-1 && !player.active);
 }else if(!strcmp(argv[2],"fault")){
  assert(pg_player_poll(&player,50000,&event)==-1 && !player.active);
 }else assert(!"unknown test");
 pg_player_cancel(&player,&event);assert(event.kind==2 && !player.active && event.stream==30);
 puts("PASS");return 0;
}
