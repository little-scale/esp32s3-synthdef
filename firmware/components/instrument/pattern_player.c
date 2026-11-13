/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "pattern_player.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <float.h>
static int error(pg_player *p,const char *text){p->active=0;
snprintf(p->error,sizeof p->error,"%s",text);
return -1;
}
static int control(const fm_graph *g,const char *name){for(unsigned i=0;i<g->names;i++)if(!strcmp(g->control_name[i].name,name))return g->control_name[i].index;
return -1;
}
static int reserved(const char *key){
 static const char *keys[]={"type","stage","dur","delta","stretch","legato","sustain","degree","note","midinote","octave","root","scale","ctranspose","mtranspose","gtranspose","harmonic","detune","db","isRest","freq","amp","gate"};
 for(unsigned i=0;i<sizeof keys/sizeof *keys;i++)if(!strcmp(key,keys[i]))return 1;
 return 0;
}
int pg_player_start(pg_player *p,pg_vm *v,const fm_graph *g,uint32_t boot,uint32_t revision,uint32_t stream,uint64_t now,uint32_t seed){
 memset(p,0,sizeof *p);
 p->vm=v;
 p->graph=g;
 p->boot=boot;
 p->revision=revision;
 p->stream=stream;
 p->anchor=now+100000;
 p->next_us=p->anchor;
 if(!boot||!revision||!stream)return error(p,"Invalid pattern binding"),0;
 for(unsigned i=0;i<g->nodes;i++){const fm_node *n=&g->node[i];
 if((n->type==FM_Control || n->type==FM_LagControl || n->type==FM_TrigControl) && n->rate==1)for(unsigned j=0;j<n->outputs;j++){unsigned k=(unsigned)n->special+j;
 if(k<g->controls)p->writable[k]=1;
 }}
 for(unsigned i=0;i<g->names;i++)if(!strncmp(g->control_name[i].name,"__esp32_",8))p->writable[g->control_name[i].index]=0;
 p->gate=control(g,"gate");
 p->freq=control(g,"freq");
 p->amp=control(g,"amp");
 for(unsigned i=0;i<v->symbols;i++){
  int index=control(g,v->symbol[i]);
  p->control[i]=(int16_t)index;
  if(index>=0){unsigned width=g->controls-(unsigned)index;
  for(unsigned k=0;k<g->names;k++)if(g->control_name[k].index>index && (unsigned)(g->control_name[k].index-index)<width)width=g->control_name[k].index-index;
  p->width[i]=(uint16_t)width;
  }
 }
 for(unsigned i=0;i<v->nodes;i++)if(v->node[i].op==22){const pg_node *n=&v->node[i];
 for(unsigned k=0;k<n->argc;k+=2){unsigned symbol=v->node[v->ref[n->first+k]].special;
 const char *name=v->symbol[symbol];
 int index=p->control[symbol];
  if(!reserved(name) && (index<0 || !p->writable[index]))return error(p,"Pbind key is not a writable Main control"),0;
 }}
 pg_reset(v,seed);
 p->active=1;
 return 1;
}
static double get(pg_player *p,const pg_event *event,const char *key,double fallback){const pg_value *v=pg_get(p->vm,event,key);
return v?pg_number(v):fallback;
}
static int named(const pg_vm *v,const pg_value *x,const char *name){return x&&x->kind==PG_SYMBOL&&!strcmp(v->symbol[x->at],name);
}
static int append(pg_player *p,rc_event *event,unsigned index,double x){
 if(index>=p->graph->controls || !p->writable[index] || !isfinite(x) || fabs(x)>FLT_MAX || event->count==RC_PAIRS)return error(p,"Invalid pattern control value");
 for(unsigned i=0;i<event->count;i++)if(event->index[i]==index)return error(p,"Overlapping pattern control fields");
 event->index[event->count]=(uint8_t)index;
 event->value[event->count++]=(float)x;
 return 1;
}
static double degree_note(pg_player *p,const pg_event *event,double degree){
 if(!isfinite(degree) || fabs(degree)>1000000)return NAN;
 static const double major[]={0,2,4,5,7,9,11};
 const pg_value *scale=pg_get(p->vm,event,"scale");
 unsigned count=scale?scale->count:7;
 if((scale && scale->kind!=PG_ARRAY) || !count)return NAN;
 double base=floor(degree),frac=degree-base,total[2];
 for(unsigned j=0;j<2;j++){double d=base+j,octave=floor(d/count),key=d-octave*count;
  if(!isfinite(key) || key<0 || key>=count)return NAN;
  unsigned index=(unsigned)key;
  double value=scale?pg_number(&p->vm->arrays[scale->at+index]):major[index];
  total[j]=value+12*octave;
 }
 return total[0]+frac*(total[1]-total[0]);
}
int pg_player_poll(pg_player *p,uint64_t now,rc_event *event){
 if(!p->active)return 0;
 if(p->next_us>now+50000)return 0;
 if(p->next_us+100000<now)return error(p,"Pattern scheduler missed its deadline");
 pg_event generated;
 int ok=pg_next(p->vm,p->beat,&generated);
 if(ok<0)return error(p,p->vm->error);
 if(!ok){p->active=0;
 p->ended=1;
 return 0;
 }
 double dur=get(p,&generated,"dur",1),stretch=get(p,&generated,"stretch",1);
 double delta=get(p,&generated,"delta",dur)*stretch;
 if(!isfinite(dur)||dur<=0||!isfinite(delta)||delta<=0||!isfinite(stretch)||stretch<=0 || delta/p->vm->tempo<.005)return error(p,"Pattern duration must be positive, at most 200 events/second");
 memset(event,0,sizeof *event);
 event->boot=p->boot;
 event->revision=p->revision;
 event->stream=p->stream;
 event->at=p->next_us;
 if(p->sequence==UINT32_MAX)return error(p,"Pattern sequence exhausted; restart it");
 event->sequence=++p->sequence;
 double beat=p->beat+delta,offset=beat*1000000/p->vm->tempo;
 if(!isfinite(offset)||offset<0||offset>9007199254740991.0 || (uint64_t)offset>UINT64_MAX-p->anchor)return error(p,"Pattern time overflow");
 p->beat=beat;
 p->next_us=p->anchor+(uint64_t)(offset+.5);
 const pg_value *type=pg_get(p->vm,&generated,"type"),*stage=pg_get(p->vm,&generated,"stage");
 if(stage && !named(p->vm,stage,"main"))return error(p,"Standalone patterns currently target Main only");
 if(generated.rest || named(p->vm,type,"rest") || get(p,&generated,"isRest",0)!=0){p->rests++;
 return 2;
 }
 int set=named(p->vm,type,"esp32Set") || named(p->vm,type,"set");
 if(type && !set && !named(p->vm,type,"esp32Note") && !named(p->vm,type,"note"))return error(p,"Unsupported standalone event type");
 event->kind=set?0:1;
 if(!set){
  if(p->gate<0 || !p->writable[p->gate])return error(p,"Note pattern requires a writable gate control");
  double sustain=get(p,&generated,"sustain",dur*stretch*get(p,&generated,"legato",.8))/p->vm->tempo;
  if(!isfinite(sustain)||sustain<=0||sustain>60)return error(p,"Pattern sustain must be in 0..60 seconds");
  event->duration=(uint32_t)fmax(1,floor(sustain*1000000+.5));
  if(p->freq>=0){
   double note=get(p,&generated,"note",NAN);
   if(isnan(note))note=degree_note(p,&generated,get(p,&generated,"degree",0)+get(p,&generated,"mtranspose",0))+get(p,&generated,"gtranspose",0);
   double midi=get(p,&generated,"midinote",note+12*get(p,&generated,"octave",5)+get(p,&generated,"root",0)+get(p,&generated,"ctranspose",0));
   double freq=get(p,&generated,"freq",440*pow(2,(midi-69)/12)*get(p,&generated,"harmonic",1)+get(p,&generated,"detune",0));
   if(append(p,event,(unsigned)p->freq,freq)<0)return -1;
  }
  if(p->amp>=0){double amp=get(p,&generated,"amp",.1),db=get(p,&generated,"db",NAN);
  if(!isnan(db))amp=pow(10,db/20);
  if(append(p,event,(unsigned)p->amp,amp)<0)return -1;
  }
 }
 for(unsigned i=0;i<generated.count;i++){
  pg_field *field=&generated.field[i];
  const char *key=p->vm->symbol[field->key];
  if(reserved(key) && (!set || (strcmp(key,"freq")&&strcmp(key,"amp")&&strcmp(key,"gate"))))continue;
  int index=p->control[field->key];
  if(index<0)return error(p,"Unknown pattern control");
  if(field->value.kind==PG_ARRAY){if(field->value.count!=p->width[field->key])return error(p,"Pattern control array width mismatch");
  for(unsigned k=0;k<field->value.count;k++)if(append(p,event,(unsigned)index+k,pg_number(&p->vm->arrays[field->value.at+k]))<0)return -1;
  }
  else {if(p->width[field->key]!=1)return error(p,"Array control requires an array value");
  if(append(p,event,(unsigned)index,pg_number(&field->value))<0)return -1;
  }
 }
 ++p->emitted;
 return 1;
}
void pg_player_cancel(pg_player *p,rc_event *event){memset(event,0,sizeof *event);
event->boot=p->boot;
event->revision=p->revision;
event->stream=p->stream;
event->sequence=p->sequence==UINT32_MAX?p->sequence:++p->sequence;
event->kind=2;
p->active=0;
}
