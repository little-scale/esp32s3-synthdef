/* SPDX-License-Identifier: GPL-3.0-or-later
 * Bounded stream-machine implementation of SC pattern semantics. No SC code,
 * allocation, device I/O or audio calls are executed by this portable module.
 */
#include "pattern_vm.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
enum {N_NUMBER,N_SYMBOL,N_ARRAY,N_REST,N_SEQ,N_SER,N_RAND,N_XRAND,N_SHUF,N_WRAND,
 N_SERIES,N_GEOM,N_WHITE,N_EXPRAND,N_BROWN,N_GBROWN,N_REPEAT,N_STUTTER,N_DUP,
 N_FIN,N_DROP,N_KEY,N_BIND,N_CHAIN,N_BINDF,N_UNARY,N_BINARY,N_TUPLE,N_SWITCH,
 N_SWITCH1,N_SEED,N_TIME,N_BJORK,N_BJORK2,N_OPS};
static uint16_t u16(const unsigned char *p){return (uint16_t)(p[0]|p[1]<<8);
}
static uint32_t u32(const unsigned char *p){return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;
}
static double f64(const unsigned char *p){uint64_t bits=(uint64_t)u32(p)|((uint64_t)u32(p+4)<<32);
double x;
memcpy(&x,&bits,8);
return x;
}
static int fail(pg_vm *v,const char *message){if(!v->error[0])snprintf(v->error,sizeof v->error,"%s",message);
return -1;
}
static pg_value number(double x){pg_value z={0};
z.number=x;
z.kind=PG_NUMBER;
return z;
}
double pg_number(const pg_value *x){return x->kind==PG_NUMBER || x->kind==PG_REST?x->number:NAN;
}
static uint32_t word(pg_vm *v){uint32_t x=v->random;
x^=x<<13;
x^=x>>17;
x^=x<<5;
v->random=x;
return x;
}
static double random01(pg_vm *v){return (double)word(v)*(1.0/4294967296.0);
}
int pg_find(const pg_vm *v,const char *key){for(unsigned i=0;i<v->symbols;i++)if(!strcmp(v->symbol[i],key))return (int)i;
return -1;
}
const pg_value *pg_get(const pg_vm *v,const pg_event *e,const char *key){int id=pg_find(v,key);
if(id<0)return NULL;
for(unsigned i=0;i<e->count;i++)if(e->field[i].key==id)return &e->field[i].value;
return NULL;
}
static int put(pg_vm *v,unsigned key,pg_value x){
 for(unsigned i=0;i<v->event.count;i++)if(v->event.field[i].key==key){v->event.field[i].value=x;
 return 1;
 }
 if(v->event.count==PG_FIELDS)return fail(v,"Event exceeds 32 fields");
 v->event.field[v->event.count++]=(pg_field){(uint16_t)key,x};
 return 1;
}
static unsigned child(const pg_vm *v,unsigned i,unsigned k){return v->ref[v->node[i].first+k];
}
static void reset_node(pg_vm *v,unsigned i){
if(!v->budget){fail(v,"Pattern reset exhausted work budget");return;}
--v->budget;++v->steps;
pg_state *s=&v->state[i];
uint16_t at=s->array_at,event=s->event_at;
memset(s,0,sizeof *s);
s->array_at=at;
s->event_at=event;
for(unsigned k=0;k<v->node[i].argc;k++)reset_node(v,child(v,i,k));
}
void pg_reset(pg_vm *v,uint32_t seed){memset(v->state,0,sizeof v->state);
for(unsigned i=0;i<PG_NODES;i++)v->state[i].array_at=v->state[i].event_at=UINT16_MAX;
v->event_caches=v->arrays_used=0;
v->random=seed?seed:0x6d2b79f5u;
v->events=v->steps=0;
v->beat=v->start_beat=0;
v->error[0]=0;
}
static int array_space(pg_vm *v,pg_state *s,unsigned count){
 if(s->array_at==UINT16_MAX){if(v->arrays_used+count>PG_ARRAY_VALUES)return fail(v,"Pattern array-state budget exceeded");
 s->array_at=v->arrays_used;
 v->arrays_used+=(uint16_t)count;
 }
 return 1;
}
int pg_load(pg_vm *v,const void *data,size_t bytes){
 const unsigned char *p=data;
 memset(v,0,sizeof *v);
 if(bytes<60 || memcmp(p,"ESPp",4) || u16(p+4)!=1)return fail(v,"Invalid pattern header"),0;
 v->nodes=u16(p+6);
 v->refs=u16(p+8);
 v->symbols=u16(p+10);
 v->root=u16(p+12);
 v->flags=u16(p+14);
 v->tempo=f64(p+16);
 v->random=u32(p+24);
 memcpy(v->graph_hash,p+28,32);
 if(!v->nodes || v->nodes>PG_NODES || v->refs>PG_REFS || v->symbols>PG_SYMBOLS || v->root!=v->nodes-1 || v->flags>1 || !isfinite(v->tempo) || v->tempo<.01 || v->tempo>100)return fail(v,"Pattern header limits"),0;
 size_t at=60;
 if(at+(size_t)v->nodes*16+(size_t)v->refs*2>bytes)return fail(v,"Truncated pattern tables"),0;
 for(unsigned i=0;i<v->nodes;i++,at+=16){pg_node *n=&v->node[i];
 n->op=p[at];
 n->argc=p[at+1];
 n->first=u16(p+at+2);
 n->special=u16(p+at+4);
 n->number=f64(p+at+8);
  if(n->op>=N_OPS || u16(p+at+6) || n->argc>64 || (unsigned)n->first+n->argc>v->refs || isnan(n->number) || n->number==-INFINITY || (n->op!=N_NUMBER && n->number!=0) || (n->op==N_SYMBOL && n->special>=v->symbols) || (n->op==N_NUMBER && n->special>1) || (n->op!=N_NUMBER && n->op!=N_SYMBOL && n->op!=N_UNARY && n->op!=N_BINARY && n->special))return fail(v,"Invalid pattern node"),0;
 }
 for(unsigned i=0;i<v->refs;i++,at+=2)v->ref[i]=u16(p+at);
 unsigned parents[PG_NODES]={0},depth[PG_NODES]={0};
 for(unsigned i=0;i<v->nodes;i++){pg_node *n=&v->node[i];
 depth[i]=1;
  for(unsigned k=0;k<n->argc;k++){unsigned c=child(v,i,k);
  if(c>=i || ++parents[c]!=1)return fail(v,"Pattern must be a forward-free stream tree"),0;
  if(depth[c]+1>depth[i])depth[i]=depth[c]+1;
  }
  if(depth[i]>PG_DEPTH+1)return fail(v,"Pattern nesting limit"),0;
  unsigned argc=n->argc;
  int valid=0;
  switch(n->op){
  case N_NUMBER:case N_SYMBOL:valid=argc==0;
  break;
  case N_ARRAY:valid=argc>=1&&argc<=PG_LIST;
  break;
  case N_REST:valid=argc==1;
  break;
  case N_SEQ:case N_SER:case N_WRAND:case N_SERIES:case N_GEOM:case N_WHITE:case N_EXPRAND:valid=argc==3;
  break;
  case N_BROWN:case N_GBROWN:case N_BJORK:case N_BJORK2:valid=argc==4;
  break;
  case N_RAND:case N_XRAND:case N_SHUF:case N_REPEAT:case N_STUTTER:case N_DUP:case N_FIN:case N_DROP:case N_KEY:case N_BINDF:case N_TUPLE:case N_SWITCH:case N_SWITCH1:case N_SEED:valid=argc==2;
  break;
  case N_BIND:valid=argc>=2&&argc%2==0;
  break;
  case N_CHAIN:valid=argc>=1&&argc<=16;
  break;
  case N_UNARY:valid=argc==1&&n->special<25;
  break;
  case N_BINARY:valid=argc==2&&n->special<16;
  break;
  case N_TIME:valid=argc==1;
  break;
  }
  if(!valid)return fail(v,"Pattern node arity"),0;
  if(n->op==N_SEQ || n->op==N_SER || n->op==N_RAND || n->op==N_XRAND || n->op==N_SHUF || n->op==N_WRAND || n->op==N_TUPLE || n->op==N_SWITCH || n->op==N_SWITCH1){if(v->node[child(v,i,0)].op!=N_ARRAY)return fail(v,"List pattern needs an array"),0;
  }
  if(n->op==N_BIND)for(unsigned k=0;k<argc;k+=2){
   if(v->node[child(v,i,k)].op!=N_SYMBOL)return fail(v,"Pbind key must be a symbol"),0;
   for(unsigned j=0;j<k;j+=2)if(v->node[child(v,i,j)].special==v->node[child(v,i,k)].special)return fail(v,"Duplicate Pbind key"),0;
  }
 }
 for(unsigned i=0;i+1<v->nodes;i++)if(parents[i]!=1)return fail(v,"Orphan pattern node"),0;
 if(v->refs!=v->nodes-1)return fail(v,"Pattern reference ownership mismatch"),0;
 for(unsigned i=0;i<v->symbols;i++){
  if(at>=bytes)return fail(v,"Truncated symbols"),0;
  unsigned len=p[at++];
  if(!len || len>63 || at+len>bytes || memchr(p+at,0,len))return fail(v,"Invalid pattern symbol"),0;
  memcpy(v->symbol[i],p+at,len);
  at+=len;
  for(unsigned j=0;j<i;j++)if(!strcmp(v->symbol[j],v->symbol[i]))return fail(v,"Duplicate pattern symbol"),0;
 }
 if(at!=bytes)return fail(v,"Trailing pattern data"),0;
 for(unsigned i=0;i<v->nodes;i++)if(v->node[i].op==N_BIND)for(unsigned k=0;k<v->node[i].argc;k+=2){
  const char *key=v->symbol[v->node[child(v,i,k)].special];
  if(!strcmp(key,"module") || !strcmp(key,"server") || !strcmp(key,"instrument") || !strcmp(key,"group") || !strcmp(key,"out"))return fail(v,"Standalone events target local Main only"),0;
 }
 uint32_t seed=v->random;
 pg_reset(v,seed);
 return 1;
}
static int next(pg_vm *,unsigned,unsigned,pg_value *);
static int argument(pg_vm *v,unsigned i,unsigned k,unsigned depth,double *x){pg_value z;
int ok=next(v,child(v,i,k),depth+1,&z);
if(ok<=0)return ok;
*x=pg_number(&z);
if(isnan(*x))return fail(v,"Numeric pattern argument required");
return 1;
}
static int literal(const pg_vm *v,unsigned i){return v->node[i].op<=N_REST;
}
static double pattern_unary(unsigned op,double x){
 switch(op){case 0:return -x;
 case 1:return fabs(x);
 case 2:return x*x;
 case 3:return x*x*x;
 case 4:return x<0?-sqrt(-x):sqrt(x);
 case 5:return exp(x);
 case 6:return 1/x;
 case 7:return 440*pow(2,(x-69)/12);
 case 8:return 69+12*log2(x/440);
 case 9:return pow(2,x/12);
 case 10:return 12*log2(x);
 case 11:return pow(10,x/20);
 case 12:return 20*log10(x);
 case 13:return log(x);
 case 14:return log2(x);
 case 15:return log10(x);
 case 16:return sin(x);
 case 17:return cos(x);
 case 18:return tan(x);
 case 19:return floor(x);
 case 20:return ceil(x);
 case 21:return x-floor(x);
 case 22:return (x>0)-(x<0);
 case 23:return x/(1+fabs(x));
 case 24:return fabs(x)<=.5?x:(fabs(x)-.25)/x;
 default:return NAN;
 }
}
static double pattern_binary(unsigned op,double a,double b){
 switch(op){case 0:return a+b;
 case 1:return a-b;
 case 2:return a*b;
 case 3:return a/b;
 case 4:return b==0?0:a-b*floor(a/b);
 case 5:return pow(a,b);
 case 6:return fmin(a,b);
 case 7:return fmax(a,b);
 case 8:return a<b;
 case 9:return a<=b;
 case 10:return a>b;
 case 11:return a>=b;
 case 12:return a==b;
 case 13:return a!=b;
 case 14:return b==0?a:floor(a/b+.5)*b;
 case 15:return fmin(b,fmax(-b,a));
 default:return NAN;
 }
}
/* Bounded grouping algorithm equivalent to the installed Bjorklund quark's
 * split/lace construction. Rows are groups of 0/1 symbols, not sample buffers. */
/* Keep the grouping workspace out of every recursive next() stack frame. */
static __attribute__((noinline)) unsigned euclid(unsigned pulses,unsigned steps,uint8_t out[PG_LIST]){
 uint8_t a[PG_LIST][PG_LIST]={{0}},b[PG_LIST][PG_LIST]={{0}};
 unsigned lengths[PG_LIST],next_lengths[PG_LIST];
 for(unsigned i=0;i<steps;i++){a[i][0]=i<pulses;
 lengths[i]=1;
 }
 unsigned groups=steps;
 for(unsigned pass=0;pass<PG_LIST;pass++){
  unsigned split=0;
  while(split+1<groups && (lengths[split]!=lengths[groups-1] || memcmp(a[split],a[groups-1],lengths[split])))split++;
  unsigned trailing=groups-split;
  if(trailing<=1 || !split)break;
  unsigned count=0;
  for(unsigned i=0;i<split;i++){
   memcpy(b[count],a[i],lengths[i]);
   unsigned len=lengths[i];
   if(i<trailing){memcpy(b[count]+len,a[split+i],lengths[split+i]);
   len+=lengths[split+i];
   }
   next_lengths[count++]=len;
  }
  for(unsigned i=split;i<trailing;i++){memcpy(b[count],a[split+i],lengths[split+i]);
  next_lengths[count++]=lengths[split+i];
  }
  memcpy(a,b,sizeof a);
  memcpy(lengths,next_lengths,count*sizeof *lengths);
  groups=count;
 }
 unsigned at=0;
 for(unsigned i=0;i<groups;i++){memcpy(out+at,a[i],lengths[i]);
 at+=lengths[i];
 }
 return at;
}
static __attribute__((noinline)) int euclid_next(pg_vm *v,unsigned i,unsigned depth,pg_value *out){
 pg_node *n=&v->node[i];pg_state *s=&v->state[i];double x,y,z;

  if(!s->initialized){if(argument(v,i,2,depth,&s->limit)<=0)return 0;
  s->initialized=1;
  }
  if(!s->remaining){
   if((double)s->cycles>=s->limit)return 0;
   if(argument(v,i,0,depth,&x)<=0 || argument(v,i,1,depth,&y)<=0 || argument(v,i,3,depth,&z)<=0)return 0;
   if(!isfinite(x)||!isfinite(y)||!isfinite(z)||x<0||y<1||y>PG_LIST||x>y||floor(x)!=x||floor(y)!=y||floor(z)!=z || (n->op==N_BJORK2 && x==0))return fail(v,"Euclidean rhythm needs 0<=pulses<=steps<=32 (duration form needs pulses>0)");
   uint8_t bits[PG_LIST];
   unsigned size=euclid((unsigned)x,(unsigned)y,bits);
   if(n->op==N_BJORK)memcpy(s->order,bits,size);
   else{unsigned positions[PG_LIST],hits=0;
   for(unsigned k=0;k<size;k++)if(bits[k])positions[hits++]=k;
    for(unsigned k=0;k<hits;k++)s->order[k]=(uint8_t)((positions[(k+1)%hits]+(k+1==hits?size:0))-positions[k]);
    size=hits;
    }
   s->last=(uint16_t)size;
   s->index=(uint16_t)((int64_t)fmod(z,size)+(int64_t)size)%size;
   s->remaining=(uint16_t)size;
   s->cycles++;
  }
  *out=number(s->order[s->index]);
  s->index=(uint16_t)((s->index+1)%s->last);
  s->remaining--;
  return 1;

}
static int next(pg_vm *v,unsigned i,unsigned depth,pg_value *out){
 if(v->error[0])return -1;
 if(depth>PG_DEPTH || !v->budget--)return fail(v,"Pattern work/nesting budget exceeded");
 ++v->steps;
 pg_node *n=&v->node[i];
 pg_state *s=&v->state[i];
 if(s->ended)return 0;
 pg_value *a=&v->scratch[depth],b;
 double x,y,z,length;
 unsigned c;
 switch(n->op){
 case N_NUMBER:*out=number(n->number);
 out->count=n->special;
 return 1;
 case N_SYMBOL:*out=number(0);
 out->kind=PG_SYMBOL;
 out->at=n->special;
 return 1;
 case N_REST:{int ok=next(v,child(v,i,0),depth+1,out);
 if(ok>0){if(out->kind!=PG_NUMBER)return fail(v,"Rest requires a number");
 out->kind=PG_REST;
 }
 return ok;
 }
 case N_ARRAY:case N_TUPLE:{
  unsigned list=n->op==N_ARRAY?i:child(v,i,0),count=v->node[list].argc;
  if(n->op==N_TUPLE && !s->initialized){if(argument(v,i,1,depth,&s->limit)<=0)return 0;
  s->initialized=1;
  }
  if(array_space(v,s,count)<0)return -1;
  for(;;){if(n->op==N_TUPLE && (double)s->cycles>=s->limit)return 0;
  unsigned k;
   for(k=0;k<count;k++){int ok=next(v,child(v,list,k),depth+1,&v->arrays[s->array_at+k]);
   if(ok<0)return ok;
   if(!ok)break;
   }
   if(k==count)break;
   if(n->op!=N_TUPLE)return 0;
   s->cycles++;
   for(k=0;k<count;k++)reset_node(v,child(v,list,k));
   if(!v->budget--)return fail(v,"Empty tuple exhausted work budget");
   }
  *out=number(0);
  out->kind=PG_ARRAY;
  out->at=s->array_at;
  out->count=(uint8_t)count;
  s->emitted++;
  return 1;
 }
 case N_SEQ:case N_SER:case N_RAND:case N_XRAND:case N_SHUF:case N_WRAND:{
  unsigned list=child(v,i,0),count=v->node[list].argc;
  unsigned length_arg=n->op==N_WRAND?2:1;
  if(!s->initialized){
   if(argument(v,i,length_arg,depth,&s->limit)<=0)return 0;
   if(s->limit<0 || (!isinf(s->limit)&&floor(s->limit)!=s->limit))return fail(v,"List repeat/count must be a nonnegative integer");
   s->index=0;
   s->last=UINT16_MAX;
   if(n->op==N_SEQ || n->op==N_SER){if(argument(v,i,2,depth,&x)<=0)return 0;
   if(!isfinite(x))return fail(v,"Invalid list offset");
   s->index=(uint16_t)((int64_t)fmod(x,(double)count)+(int64_t)count)%count;
   }
   for(unsigned k=0;k<count;k++)s->order[k]=(uint8_t)k;
   if(n->op==N_SHUF)for(unsigned k=count;k>1;k--){unsigned at=(unsigned)(random01(v)*k);
   uint8_t t=s->order[k-1];
   s->order[k-1]=s->order[at];
   s->order[at]=t;
   }
   s->initialized=1;
  }
  for(;;){
   if(!v->budget--)return fail(v,"Empty/infinite list exhausted work budget");
   if((double)(n->op==N_SEQ || n->op==N_SHUF?s->cycles:s->emitted)>=s->limit)return 0;
   if(!s->active){
    unsigned at=s->index;
    if(n->op==N_RAND || n->op==N_XRAND){at=(unsigned)(random01(v)*count);
    if(n->op==N_XRAND && count>1 && at==s->last)at=(at+1+(unsigned)(random01(v)*(count-1)))%count;
    }
    if(n->op==N_WRAND){
     int ok=next(v,child(v,i,1),depth+1,a);
     if(ok<=0)return ok;
     if(a->kind!=PG_ARRAY || a->count!=count)return fail(v,"Pwrand weight count mismatch");
     double sum=0;
     for(unsigned k=0;k<count;k++){x=pg_number(&v->arrays[a->at+k]);
     if(!isfinite(x)||x<0)return fail(v,"Invalid Pwrand weight");
     sum+=x;
     }
     if(!(sum>0))return fail(v,"Pwrand needs a positive weight sum");
     x=random01(v)*sum;
     at=count-1;
     for(unsigned k=0;k<count;k++){x-=pg_number(&v->arrays[a->at+k]);
     if(x<0){at=k;
     break;
     }}
    }
    if(n->op==N_SHUF)at=s->order[s->index];
    s->last=(uint16_t)at;
    reset_node(v,child(v,list,at));
    s->active=1;
   }
   c=child(v,list,s->last);
   int ok=next(v,c,depth+1,out);
   if(ok<0)return ok;
   if(ok>0 && !literal(v,c))return 1;
   s->active=0;
   s->emitted++;
   s->index=(uint16_t)((s->index+1)%count);
   if(++s->remaining==count){s->cycles++;
   s->remaining=0;
   }
   if(ok>0)return 1;
  }
 }
 case N_SERIES:case N_GEOM:{
  if(argument(v,i,2,depth,&length)<=0)return 0;
  if((double)s->emitted>=length)return 0;
  if(!s->initialized){if(argument(v,i,0,depth,&s->current)<=0)return 0;
  s->initialized=1;
  }
  if(argument(v,i,1,depth,&x)<=0)return 0;
  *out=number(s->current);
  s->current=n->op==N_SERIES?s->current+x:s->current*x;
  s->emitted++;
  return 1;
 }
 case N_WHITE:case N_EXPRAND:case N_BROWN:case N_GBROWN:{
  unsigned arg=n->op==N_WHITE || n->op==N_EXPRAND?2:3;
  if(argument(v,i,arg,depth,&length)<=0)return 0;
  if((double)s->emitted>=length)return 0;
  if((n->op==N_BROWN || n->op==N_GBROWN) && !s->initialized){
   if(argument(v,i,0,depth,&x)<=0 || argument(v,i,1,depth,&y)<=0 ||
      argument(v,i,2,depth,&z)<=0)return 0;
   if(!isfinite(x)||!isfinite(y)||x>y||!isfinite(z)||z<0)return fail(v,"Invalid Brownian initial interval");
   int integer=v->node[child(v,i,0)].op==N_NUMBER&&v->node[child(v,i,0)].special &&
               v->node[child(v,i,1)].op==N_NUMBER&&v->node[child(v,i,1)].special;
   s->current=integer?x+floor(random01(v)*(y-x+1)):x+(y-x)*random01(v);
   s->initialized=1;
  }
  if(argument(v,i,0,depth,&x)<=0 || argument(v,i,1,depth,&y)<=0)return 0;
  if(!isfinite(x)||!isfinite(y)||x>y)return fail(v,"Invalid random interval");
  if(n->op==N_EXPRAND){if(x<=0)return fail(v,"Pexprand requires positive bounds");
  z=x*pow(y/x,random01(v));
  }
  else if(n->op==N_WHITE){int integer=v->node[child(v,i,0)].op==N_NUMBER&&v->node[child(v,i,0)].special && v->node[child(v,i,1)].op==N_NUMBER&&v->node[child(v,i,1)].special;
  z=integer?x+floor(random01(v)*(y-x+1)):x+(y-x)*random01(v);
  }
  else{
   if(argument(v,i,2,depth,&z)<=0)return 0;
   if(!isfinite(z)||z<0)return fail(v,"Invalid Brownian step");
   double increment;
   if(v->node[child(v,i,2)].op==N_NUMBER && v->node[child(v,i,2)].special){
    increment=z==0?0:floor(random01(v)*(2*z))-z;
    if(z>0 && increment>=0)increment++;
   }else increment=(2*random01(v)-1)*z;
   double result=s->current,next_value=n->op==N_BROWN?result+increment:result*(1+increment);
   double span=y-x;
   if(span==0)next_value=x;
   else{double t=fmod(next_value-x,2*span);
   if(t<0)t+=2*span;
   next_value=x+(t>span?2*span-t:t);
   }
   s->current=next_value;
   z=next_value;
   s->initialized=1;
  }
  *out=number(z);
  s->emitted++;
  return 1;
 }
 case N_REPEAT:{
  if(!s->initialized){if(argument(v,i,1,depth,&s->limit)<=0)return 0;
  s->initialized=1;
  }
  while((double)s->cycles<s->limit){unsigned item=child(v,i,0);
  int ok=next(v,item,depth+1,out);
  if(ok && (ok<0 || !literal(v,item)))return ok;
  s->cycles++;
  reset_node(v,item);
  if(ok>0)return 1;
  if(!v->budget--)return fail(v,"Empty repetition exhausted work budget");
  }
  return 0;
 }
 case N_STUTTER:case N_DUP:{
  while(!s->remaining){int ok=next(v,child(v,i,1),depth+1,&s->cached);
  if(ok<=0)return ok;
  if(argument(v,i,0,depth,&x)<=0)return 0;
  x=fabs(x);
  if(!isfinite(x)||x>65535||floor(x)!=x)return fail(v,"Invalid repeat count");
  s->remaining=(uint16_t)x;
   if(s->cached.kind==PG_EVENT){if(s->event_at==UINT16_MAX){if(v->event_caches==8)return fail(v,"Pattern event-cache budget exceeded");
   s->event_at=(uint16_t)v->event_caches++;
   }
   v->event_cache[s->event_at]=v->event;
   }
   if(!v->budget--)return fail(v,"Zero stutters exhausted work budget");
   }
  if(s->cached.kind==PG_EVENT)v->event=v->event_cache[s->event_at];
  *out=s->cached;
  s->remaining--;
  return 1;
 }
 case N_FIN:case N_DROP:{
  if(!s->initialized){if(argument(v,i,0,depth,&s->limit)<=0)return 0;
  if(!isfinite(s->limit)||s->limit<0||floor(s->limit)!=s->limit)return fail(v,"Invalid count limit");
  s->initialized=1;
  }
  if(n->op==N_FIN && (double)s->emitted>=s->limit)return 0;
 if(n->op==N_DROP)while((double)s->emitted<s->limit){
  if(s->event_at==UINT16_MAX){if(v->event_caches==8)return fail(v,"Pattern event-cache budget exceeded");
  s->event_at=(uint16_t)v->event_caches++;
  }
  v->event_cache[s->event_at]=v->event;
  int ok=next(v,child(v,i,1),depth+1,out);
  v->event=v->event_cache[s->event_at];
  if(ok<=0)return ok;
  s->emitted++;
  if(!v->budget--)return fail(v,"Pdrop exhausted work budget");
 }
  int ok=next(v,child(v,i,1),depth+1,out);
  if(ok>0)s->emitted++;
  return ok;
 }
 case N_KEY:{
  int ok=next(v,child(v,i,0),depth+1,a);
  if(ok<=0)return ok;
  if(a->kind!=PG_SYMBOL)return fail(v,"Pkey requires a symbol");
  if(argument(v,i,1,depth,&x)<=0)return 0;
  if((double)s->emitted>=x)return 0;
  for(unsigned k=0;k<v->event.count;k++)if(v->event.field[k].key==a->at){*out=v->event.field[k].value;
  s->emitted++;
  return 1;
  }
  return 0;
 }
 case N_BIND:{
  for(unsigned k=0;k<n->argc;k+=2){unsigned key=v->node[child(v,i,k)].special;
  int ok=next(v,child(v,i,k+1),depth+1,a);
  if(ok<=0)return ok;
  if(a->kind==PG_EVENT)return fail(v,"Pbind values must be value streams");
  if(a->kind==PG_REST)v->event.rest=1;
  if(put(v,key,*a)<0)return -1;
  }
  *out=number(0);
  out->kind=PG_EVENT;
  return 1;
 }
 case N_CHAIN:case N_BINDF:{
  if(n->op==N_CHAIN){for(unsigned k=n->argc;k>0;k--){int ok=next(v,child(v,i,k-1),depth+1,a);
  if(ok<=0)return ok;
  if(a->kind!=PG_EVENT)return fail(v,"Pchain requires event patterns");
  }}
  else{for(unsigned k=0;k<2;k++){int ok=next(v,child(v,i,k),depth+1,a);
  if(ok<=0)return ok;
  if(a->kind!=PG_EVENT)return fail(v,"Pbindf requires event patterns");
  }}
  *out=number(0);
  out->kind=PG_EVENT;
  return 1;
 }
 case N_UNARY:case N_BINARY:{
  int ok=next(v,child(v,i,0),depth+1,a);
  if(ok<=0)return ok;
  if(n->op==N_BINARY){ok=next(v,child(v,i,1),depth+1,&b);
  if(ok<=0)return ok;
  }
  if(a->kind==PG_ARRAY || (n->op==N_BINARY && b.kind==PG_ARRAY)){
   if(array_space(v,s,PG_LIST)<0)return -1;
   unsigned left=a->kind==PG_ARRAY?a->count:1,right=n->op==N_BINARY && b.kind==PG_ARRAY?b.count:1;
   unsigned count=left>right?left:right;
   for(unsigned k=0;k<count;k++){
    x=pg_number(a->kind==PG_ARRAY?&v->arrays[a->at+k%left]:a);
    y=n->op==N_BINARY?pg_number(b.kind==PG_ARRAY?&v->arrays[b.at+k%right]:&b):0;
    z=n->op==N_UNARY?pattern_unary(n->special,x):pattern_binary(n->special,x,y);
    if(!isfinite(z))return fail(v,"Nonfinite array pattern arithmetic");
    v->arrays[s->array_at+k]=number(z);
   }
   *out=number(0);out->kind=PG_ARRAY;out->at=s->array_at;out->count=(uint8_t)count;return 1;
  }
  x=pg_number(a);
  y=n->op==N_BINARY?pg_number(&b):0;
  z=n->op==N_UNARY?pattern_unary(n->special,x):pattern_binary(n->special,x,y);
  if(!isfinite(z))return fail(v,"Nonfinite pattern arithmetic");
  *out=number(z);
  if(a->kind==PG_REST || (n->op==N_BINARY && b.kind==PG_REST))out->kind=PG_REST;
  return 1;
 }
 case N_SWITCH:case N_SWITCH1:{
  unsigned list=child(v,i,0),count=v->node[list].argc;
  for(;;){if(!s->active || n->op==N_SWITCH1){if(argument(v,i,1,depth,&x)<=0)return 0;
  if(!isfinite(x))return fail(v,"Invalid pattern selector");
  s->index=(uint16_t)((int64_t)fmod(x,count)+(int64_t)count)%count;
  s->active=1;
  }
   unsigned item=child(v,list,s->index);
   int ok=next(v,item,depth+1,out);
   if(ok || n->op==N_SWITCH1){if(ok>0 && n->op==N_SWITCH && literal(v,item))s->active=0;
   return ok;
   }
   reset_node(v,item);
   s->active=0;
   if(!v->budget--)return fail(v,"Empty switch exhausted work budget");
   }
 }
 case N_SEED:{
  for(;;){if(!s->initialized){if(argument(v,i,0,depth,&x)<=0)return 0;
  if(!isfinite(x)||x<0||x>4294967295.0)return fail(v,"Invalid seed");
  s->rng=(uint32_t)x;
  if(!s->rng)s->rng=0x6d2b79f5u;
  s->initialized=1;
  }
   uint32_t outside=v->random;
   v->random=s->rng;
   int ok=next(v,child(v,i,1),depth+1,out);
   s->rng=v->random;
   v->random=outside;
   if(ok)return ok;
   reset_node(v,child(v,i,1));
   s->initialized=0;
   if(!v->budget--)return fail(v,"Empty seeded pattern exhausted work budget");
   }
 }
 case N_TIME:if(argument(v,i,0,depth,&length)<=0)return 0;
 if((double)s->emitted>=length)return 0;
 if(!s->initialized){s->current=v->beat;
 s->initialized=1;
 }
 *out=number(v->beat-s->current);
 s->emitted++;
 return 1;
 case N_BJORK:case N_BJORK2:return euclid_next(v,i,depth,out);
 default:return fail(v,"Unknown pattern opcode");
 }
}
int pg_next_value(pg_vm *v,double beat,pg_value *out){if(!isfinite(beat)||beat<0)return fail(v,"Invalid pattern beat");
v->budget=PG_BUDGET;
v->beat=beat;
memset(&v->event,0,sizeof v->event);
int ok=next(v,v->root,0,out);
return v->error[0]?-1:ok;
}
int pg_next(pg_vm *v,double beat,pg_event *event){pg_value out;
int ok=pg_next_value(v,beat,&out);
if(ok>0){if(out.kind!=PG_EVENT)return fail(v,"Program root did not produce an event");
*event=v->event;
v->events++;
}
return ok;
}
