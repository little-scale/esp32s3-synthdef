"""Computer-verified candidates, opt-in only until ESP32 timing qualification."""

SMOOTH_TYPES = ('Lag2', 'Lag3', 'OnePole', 'OneZero', 'LPZ1', 'HPZ1')
NOISE_TYPES = ('WhiteNoise', 'PinkNoise', 'LFNoise0', 'LFNoise1', 'LFNoise2')
BINARY_SCALAR_SELECTORS = (0,1,2,3,4,5,6,7,8,9,10,11,12,13,17,18,19,20,21,22,23,24,25,
                           30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46)

SMOOTH = r'''
/* Same equations as utilities/extensions. Lag2/3 use their otherwise-unused
 * freq field solely to cache the last lag time; recursive state is unchanged. */
static __attribute__((noinline)) void candidate_smooth(const fm_graph *g,fm_voice *v,fm_scratch *b,const fm_node *n,fm_state *s,unsigned count,float sr,int initializing){
 fm_bound_input in=bind_input(g,b,n,0,0);float *out=b->signal[n->output];
 float x=in.p[0],param=n->inputs>1?input(g,b,n,1,0):0,old=s->b1,target=old;
 if(n->type==FM_Lag2 || n->type==FM_Lag3){
  /* utilities writes these otherwise-unused history fields on construction. */
  if(!s->initialized){s->previous[0]=param;s->previous[1]=0;s->y1=s->y2=s->a0=x;}
  if(param<0){v->fault=1;return;}
  target=!s->initialized || param!=s->freq?lag_coeff(param,sr):s->b1;
  s->freq=param;if(!s->initialized)s->b1=target;
  old=s->b1;
 }else if(n->type==FM_OnePole || n->type==FM_OneZero){
  if(fabsf(param)>1){v->fault=1;return;}
  target=param;if(!s->initialized){old=param;s->y1=n->type==FM_OneZero?x:0;}
 }else if(!s->initialized)s->y1=x;
 /* Retain multiply-then-scale order in Lag2/3; precomputing the coefficient
  * slope changes rounding. The reciprocal is exact for count 64 or 1. */
 float scale=count==1?1.0f:(1.0f/FM_BLOCK);
 #define CANDIDATE_SAMPLES(EXPR) for(unsigned j=0;j<count;j++){ \
  float a=in.p[in.rate==2?j:0],z; \
  EXPR;checked_signal(v,out+j,z);s->initialized=1; \
 }
 switch(n->type){
 case FM_OnePole:
  CANDIDATE_SAMPLES(float coef=old+(target-old)*((float)j*(1.0f/FM_BLOCK)); \
   z=initializing?a+coef*(s->y1-a):(1-fabsf(coef))*a+coef*s->y1;s->y1=z);break;
 case FM_OneZero:
  CANDIDATE_SAMPLES(float coef=old+(target-old)*((float)j*(1.0f/FM_BLOCK)); \
   z=(1-fabsf(coef))*a+coef*s->y1;s->y1=a);break;
 case FM_LPZ1:CANDIDATE_SAMPLES(z=0.5f*(a+s->y1);s->y1=a);break;
 case FM_HPZ1:CANDIDATE_SAMPLES(z=0.5f*(a+-s->y1);s->y1=a);break;
 case FM_Lag2:
  CANDIDATE_SAMPLES(float coef=old+((target-old)*(float)(j+1))*scale; \
   s->y1=a+coef*(s->y1-a);s->y2=s->y1+coef*(s->y2-s->y1);z=s->y2);break;
 case FM_Lag3:
  CANDIDATE_SAMPLES(float coef=old+((target-old)*(float)(j+1))*scale; \
   s->y1=a+coef*(s->y1-a);s->y2=s->y1+coef*(s->y2-s->y1); \
   s->a0=s->y2+coef*(s->a0-s->y2);z=s->a0);break;
 default:v->fault=1;break;
 }
 #undef CANDIDATE_SAMPLES
 s->b1=target;
}
'''

BINARY_EXPRESSIONS = {
    3: 'floorf(av/bv)', 5: 'bv==0?0:av-bv*floorf(av/bv)',
    6: 'av==bv', 7: 'av!=bv', 8: 'av<bv', 9: 'av>bv',
    10: 'av<=bv', 11: 'av>=bv', 12: 'fminf(av,bv)', 13: 'fmaxf(av,bv)',
    17: 'integer_gcd(av,bv,1)', 18: 'integer_gcd(av,bv,0)',
    19: 'bv==0?av:floorf(av/bv+.5f)*bv',
    20: 'bv==0?av:ceilf(av/bv)*bv', 21: 'bv==0?av:floorf(av/bv)*bv',
    22: 'atan2f(av,bv)', 23: 'hypotf(av,bv)',
    24: 'fabsf(av)+fabsf(bv)-(1.4142135623730951f-1.0f)*fminf(fabsf(av),fabsf(bv))',
    25: 'av>=0?powf(av,bv):-powf(-av,bv)',
    30: 'av*bv+av', 31: 'av*bv+av+bv', 32: 'av*av*bv',
    33: 'av*av*bv-av*bv*bv', 34: 'av*av-bv*bv', 35: 'av*av+bv*bv',
    36: '(av+bv)*(av+bv)', 37: '(av-bv)*(av-bv)', 38: 'fabsf(av-bv)',
    40: 'av*0.5f*(bv+fabsf(bv))', 41: 'av>=0?av:av*bv', 46: 'av',
    39: 'av<bv?0:av', 42: 'fminf(bv,fmaxf(-bv,av))',
    43: 'av-fminf(bv,fmaxf(-bv,av))',
    44: 'bounded_fold(av,-bv,bv)', 45: 'bounded_wrap(av,-bv,bv)',
}

NOISE = r'''
/* Local Taus88 words are committed before the next node executes. This keeps
 * the original shared sequence, including PinkNoise construction and resets. */
static inline __attribute__((always_inline)) uint32_t candidate_word(uint32_t *r0,uint32_t *r1,uint32_t *r2){
 *r0=((*r0&~1u)<<12)^(((*r0<<13)^*r0)>>19);
 *r1=((*r1&~7u)<<4)^(((*r1<<2)^*r1)>>25);
 *r2=((*r2&~15u)<<17)^(((*r2<<3)^*r2)>>11);
 return *r0^*r1^*r2;
}
static inline __attribute__((always_inline)) float candidate_bipolar(uint32_t *r0,uint32_t *r1,uint32_t *r2){
 uint32_t bits=0x40000000u|(candidate_word(r0,r1,r2)>>9);float z;memcpy(&z,&bits,4);return z-3.0f;
}
static unsigned candidate_pink_index(uint32_t word){
 /* ctz(0) is undefined. The pinned loop maps zero to 32 & 15 == 0. */
 return word?((unsigned)__builtin_ctz(word)&15u):0;
}
#ifdef FM_CANDIDATE_TEST
uint32_t fm_candidate_test_pink_index(uint32_t word){return candidate_pink_index(word);}
#endif
static __attribute__((noinline)) void candidate_noise(const fm_graph *g,fm_voice *v,fm_scratch *b,const fm_node *n,fm_state *s,unsigned count,float sr){
 uint32_t r0=v->random[0],r1=v->random[1],r2=v->random[2];float *out=b->signal[n->output];
 fm_env *e=&s->env;float frequency=n->inputs?input(g,b,n,0,0):0;
 #define NEXT_WORD() candidate_word(&r0,&r1,&r2)
 #define NEXT_BIPOLAR() candidate_bipolar(&r0,&r1,&r2)
 if(!s->initialized){
  if(n->type==FM_PinkNoise){s->total=0;for(unsigned k=0;k<16;k++){s->dice[k]=NEXT_WORD()>>13;s->total+=s->dice[k];}}
  if(n->type==FM_LFNoise1)e->level=NEXT_BIPOLAR();
  if(n->type==FM_LFNoise2){e->end=NEXT_BIPOLAR();e->start=e->end*0.5f;}
 }
 /* All three LFNoise frequencies are sampled at block offset zero. Reuse the
  * exact segment length only within this block; frequency may change between
  * blocks while an existing segment continues. Preserve decrement order. */
 int32_t length=0;
 #define LF_SAMPLES(MODE) for(unsigned j=0;j<count;j++){ \
  if(e->remaining<=0){ \
   if(!length){length=(int32_t)fminf(1e9f,sr/fmaxf(0.001f,frequency));if(length<((MODE)==2?2:1))length=(MODE)==2?2:1;} \
   e->remaining=length; \
   if((MODE)==0)e->level=NEXT_BIPOLAR(); \
   else if((MODE)==1)e->grow=(NEXT_BIPOLAR()-e->level)/e->remaining; \
   else {float previous=e->end,len=(float)e->remaining;e->end=NEXT_BIPOLAR();e->level=e->start;e->start=(e->end+previous)*0.5f;e->curve=2*(e->start-e->level-len*e->grow)/(len*len+len);} \
  } \
  float z=e->level;if((MODE)==2)e->grow+=e->curve;if((MODE)!=0)e->level+=e->grow;e->remaining--;checked_signal(v,out+j,z); \
 }
 switch(n->type){
 case FM_WhiteNoise:
  for(unsigned j=0;j<count;j++)checked_signal(v,out+j,NEXT_BIPOLAR());break;
 case FM_PinkNoise:
  for(unsigned j=0;j<count;j++){
   uint32_t word=NEXT_WORD(),bits;unsigned k=candidate_pink_index(word);float z;
   s->total+=(word>>13)-s->dice[k];s->dice[k]=word>>13;
   bits=(s->total+(NEXT_WORD()>>13))|0x40000000u;memcpy(&z,&bits,4);checked_signal(v,out+j,z-3.0f);
  }break;
 case FM_LFNoise0:LF_SAMPLES(0);break;
 case FM_LFNoise1:LF_SAMPLES(1);break;
 case FM_LFNoise2:LF_SAMPLES(2);break;
 default:v->fault=1;break;
 }
 v->random[0]=r0;v->random[1]=r1;v->random[2]=r2;s->initialized=1;
 #undef LF_SAMPLES
 #undef NEXT_WORD
 #undef NEXT_BIPOLAR
}
'''


def prepare(render, fast, smooth=True, binary=True, noise=False):
    include='#include "fm_fast.inc"'
    if smooth or noise:
        assert render.count(include)==1
        render=render.replace(include,include+'\n#include "fm_dsp_candidates.inc"')
    if smooth:
        anchor='  if(n->type>=FM_OnePole && n->type<=FM_Decay2){extensions'
        assert render.count(anchor)==1
        at=render.index(anchor)
        dispatch='  if(n->type==FM_OnePole || n->type==FM_OneZero || n->type==FM_LPZ1 || n->type==FM_HPZ1 || n->type==FM_Lag2 || n->type==FM_Lag3){candidate_smooth(g,v,b,n,s,count,sr,initializing);continue;}\n'
        render=render[:at]+dispatch+render[at:]
    if noise:
        anchor='  if(n->type==FM_BinaryOpUGen || n->type==FM_MulAdd || n->type==FM_Sum3 || n->type==FM_Sum4){fast_arithmetic'
        at=render.index(anchor)
        dispatch='  if('+ ' || '.join(f'n->type==FM_{typ}' for typ in NOISE_TYPES)+'){candidate_noise(g,v,b,n,s,count,sr);continue;}\n'
        render=render[:at]+dispatch+render[at:]
    if binary:
        # The original path remains authoritative whenever either input ramps.
        # Avoid changes to accumulated ramps of discontinuous operators.
        anchor='  switch(op){\n  case 0:BINARY_CASE(+);break;'
        assert fast.count(anchor)==1
        macro=r'''  /* The pinned discontinuous path adds +0 to held inputs after sample
   * zero. A held -0 can therefore become +0; downstream atan2 observes it.
   * Retain that exact transient rather than filling a block with -0. */
  if((op==3 || op==5 || (op>=17 && op<=21) || op==39 || (op>=42 && op<=45)) &&
     ((x[0].rate!=2 && a[0]==0 && signbit(a[0])) || (x[1].rate!=2 && bval[0]==0 && signbit(bval[0]))))goto general_arithmetic;
  /* Pure scalar expressions need one evaluation per block, regardless of
   * selector. Keep the original evaluator and all changing-control paths. */
  if(x[0].rate!=2 && x[1].rate!=2){
   float z=binary(op,a[0],bval[0]);checked_signal(v,&z,z);
   for(j=0;j<count;j++)out[j]=z;goto arithmetic_done;
  }
  #define BINARY_EXPR(EXPR) \
   for(j=0;j<count;j++){float av=a[x[0].rate==2?j:0],bv=bval[x[1].rate==2?j:0];(void)bv;checked_signal(v,out+j,(EXPR));}
'''
        cases=''.join(f'  case {op}:BINARY_EXPR({expr});break;\n' for op,expr in BINARY_EXPRESSIONS.items())
        fast=fast.replace(anchor,macro+anchor.replace('  case 0:',cases+'  case 0:'))
        fast=fast.replace('  #undef BINARY_CASE','  #undef BINARY_EXPR\n  #undef BINARY_CASE')
    return render,fast,(SMOOTH if smooth else '')+(NOISE if noise else '')
