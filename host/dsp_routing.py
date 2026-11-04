"""Opt-in dedicated kernels for small converters, delays and selectors."""

TYPES = ('A2K','K2A','DC','Delay1','Delay2','Select','Clip','DegreeToKey','RandSeed')

SOURCE = r'''
static float candidate_degree(const fm_graph *g,fm_voice *v,const fm_node *n,float degree,int32_t octave){
 if(!isfinite(degree)||fabsf(degree)>16777216.0f){v->fault=1;return 0.0f;}
 int32_t index=(int32_t)floorf(degree),size=n->partials,oct=index/size,key=index%size;
 if(key<0){key+=size;oct--;}
 return g->constant[g->ref[n->partial+(unsigned)key].output]+(float)octave*(float)oct;
}
static __attribute__((noinline)) void candidate_routing(const fm_graph *g,fm_voice *v,fm_scratch *b,const fm_node *n,fm_state *s,unsigned count,int initializing){
 fm_bound_input in=bind_input(g,b,n,0,0);float *out=b->signal[n->output];
 switch(n->type){
 case FM_A2K:checked_signal(v,out,in.p[0]);break;
 case FM_DC:{
  float z=s->initialized?s->last:in.p[0];s->last=z;checked_signal(v,&z,z);
  for(unsigned j=0;j<count;j++)out[j]=z;break;
 }
 case FM_RandSeed:{
  uint32_t seed=(uint32_t)(int32_t)input(g,b,n,1,0);
  if(in.rate!=2){float a=in.p[0];if(a>0 && s->last<=0)random_seed(v,seed);s->last=a;for(unsigned j=0;j<count;j++)out[j]=0;}
  else for(unsigned j=0;j<count;j++){float a=in.p[j];if(a>0 && s->last<=0)random_seed(v,seed);s->last=a;out[j]=0;}
  break;
 }
 case FM_K2A:{
  float a=in.p[0];if(!s->initialized)s->last=a;
  float previous=s->last,span=a-previous;
  for(unsigned j=0;j<count;j++)checked_signal(v,out+j,previous+(span*(float)j)*(1.0f/FM_BLOCK));
  if(count==FM_BLOCK)s->last=a;break;
 }
 case FM_Delay1:case FM_Delay2:{
  if(!s->initialized){s->y1=input(g,b,n,1,0);s->y2=n->type==FM_Delay2?input(g,b,n,2,0):0;}
  if(initializing){checked_signal(v,out,n->type==FM_Delay1?s->y1:s->y2);break;}
  if(n->type==FM_Delay1)for(unsigned j=0;j<count;j++){
   float z=s->y1;s->y2=s->y1;s->y1=in.p[in.rate==2?j:0];checked_signal(v,out+j,z);
  }else for(unsigned j=0;j<count;j++){
   float z=s->y2;s->y2=s->y1;s->y1=in.p[in.rate==2?j:0];checked_signal(v,out+j,z);
  }break;
 }
 case FM_Select:{
  if(in.rate!=2){
   float choice=fminf(n->inputs-2,fmaxf(0,in.p[0]));
   fm_bound_input selected=bind_input(g,b,n,1+(int)choice,0);
   for(unsigned j=0;j<count;j++)checked_signal(v,out+j,selected.p[selected.rate==2?j:0]);
  }else for(unsigned j=0;j<count;j++){
   float choice=fminf(n->inputs-2,fmaxf(0,in.p[j]));checked_signal(v,out+j,input(g,b,n,1+(int)choice,j));
  }break;
 }
 case FM_Clip:{
  fm_bound_input lo=bind_input(g,b,n,1,0),hi=bind_input(g,b,n,2,0);
  if(!s->initialized){s->a0=lo.p[0];s->b1=hi.p[0];}
  float oldlo=s->a0,oldhi=s->b1;
  for(unsigned j=0;j<count;j++){
   float lower=lo.p[lo.rate==2?j:0],upper=hi.p[hi.rate==2?j:0],t=(float)j*(1.0f/FM_BLOCK);
   if(count>1){if(lo.rate!=2)lower=oldlo+(lower-oldlo)*t;if(hi.rate!=2)upper=oldhi+(upper-oldhi)*t;}
   checked_signal(v,out+j,fmaxf(lower,fminf(upper,in.p[in.rate==2?j:0])));
  }
  s->a0=lo.p[lo.rate==2?count-1:0];s->b1=hi.p[hi.rate==2?count-1:0];break;
 }
 case FM_DegreeToKey:{
  fm_bound_input degree=bind_input(g,b,n,1,0);int32_t octave=(int32_t)input(g,b,n,2,0);
  if(degree.rate!=2){
   float z=candidate_degree(g,v,n,degree.p[0],octave);checked_signal(v,&z,z);
   for(unsigned j=0;j<count;j++)out[j]=z;
  }else for(unsigned j=0;j<count;j++)checked_signal(v,out+j,candidate_degree(g,v,n,degree.p[j],octave));
  break;
 }
 default:v->fault=1;break;
 }
 s->initialized=1;
 if(!n->rate && n->outputs==1)s->initial_value=out[0];
}
'''


def prepare(render):
    anchor='#include "fm_extensions.inc"'
    assert render.count(anchor)==1
    render=render.replace(anchor,SOURCE+'\n'+anchor)
    anchor='  if(n->type==FM_BinaryOpUGen || n->type==FM_MulAdd || n->type==FM_Sum3 || n->type==FM_Sum4){fast_arithmetic'
    at=render.index(anchor)
    dispatch='  if('+' || '.join('n->type==FM_'+typ for typ in TYPES)+'){candidate_routing(g,v,b,n,s,count,initializing);continue;}\n'
    return render[:at]+dispatch+render[at:]
