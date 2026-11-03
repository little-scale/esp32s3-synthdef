"""Exact block kernels layered over the pinned renderer; never edit upstream."""

FILTER = r'''
/* Preserve SC's three-sample coefficient groups, including sample 63 and the
 * one-sample constructor/control rules. Do not replace division by 21 with a
 * reciprocal: that changes rounding. Input and output never alias. */
static __attribute__((noinline)) void fast_filter(const fm_graph *g,fm_voice *v,fm_scratch *b,const fm_node *n,fm_state *s,unsigned count,float sr,int initializing){
 fm_bound_input in=bind_input(g,b,n,0,0);float *out=b->signal[n->output];
 float freq=input(g,b,n,1,0),param=n->inputs>2?input(g,b,n,2,0):0;
 float target0,target1,target2,old0,old1,old2;
 if(!s->initialized || freq!=s->freq || param!=s->width)filter_coeff(n->type,freq,param,sr,&target0,&target1,&target2);
 else{target0=s->a0;target1=s->b1;target2=s->b2;}
 if(!s->initialized){s->a0=target0;s->b1=target1;s->b2=target2;}
 s->freq=freq;s->width=param;old0=s->a0;old1=s->b1;old2=s->b2;
 #define FILTER_SAMPLES(TYPE) do { \
  for(unsigned start=0;start<count;start+=3){ \
   float t=count==1?((TYPE)==FM_Resonz || (TYPE)==FM_Ringz?0:1):(float)(start/3)/(count/3); \
   float a0=old0+(target0-old0)*t,b1=old1+(target1-old1)*t,b2=old2+(target2-old2)*t; \
   unsigned end=start+3;if(end>count)end=count; \
   for(unsigned j=start;j<end;j++){ \
    float z=filter_tick(TYPE,s,in.p[in.rate==2?j:0],a0,b1,b2); \
    if(initializing && (TYPE)==FM_Resonz)z=0; \
    checked_signal(v,out+j,z); \
   } \
  } \
 }while(0)
 switch(n->type){
 case FM_Resonz:FILTER_SAMPLES(FM_Resonz);break;
 case FM_Ringz:FILTER_SAMPLES(FM_Ringz);break;
 case FM_LPF:FILTER_SAMPLES(FM_LPF);break;
 case FM_HPF:FILTER_SAMPLES(FM_HPF);break;
 case FM_RLPF:FILTER_SAMPLES(FM_RLPF);break;
 case FM_RHPF:FILTER_SAMPLES(FM_RHPF);break;
 case FM_BPF:FILTER_SAMPLES(FM_BPF);break;
 case FM_BRF:FILTER_SAMPLES(FM_BRF);break;
 default:v->fault=1;break;
 }
 #undef FILTER_SAMPLES
 s->a0=target0;s->b1=target1;s->b2=target2;s->initialized=1;
}
'''

SAME = r'''
static int dsp_same_bits(float a,float b){uint32_t x,y;memcpy(&x,&a,4);memcpy(&y,&b,4);return x==y;}
'''

LAG = r'''
/* freq/width are otherwise unused for these node types: cache the exact
 * lag-time bit patterns there. The recursive state and coefficients retain
 * their existing fields and equations. A new voice clears all cache fields. */
static __attribute__((noinline)) void fast_lag(const fm_graph *g,fm_voice *v,fm_scratch *b,const fm_node *n,fm_state *s,unsigned count,float sr){
 fm_bound_input in=bind_input(g,b,n,0,0);float *out=b->signal[n->output];
 float up_time=input(g,b,n,1,0),down_time=n->type==FM_LagUD?input(g,b,n,2,0):up_time;
 float target1,target2,old1=s->b1,old2=s->b2;
 if(n->type==FM_LeakDC)target1=target2=up_time;
 else{
  target1=!s->initialized || !dsp_same_bits(up_time,s->freq)?lag_coeff(up_time,sr):old1;
  target2=n->type==FM_LagUD?(!s->initialized || !dsp_same_bits(down_time,s->width)?lag_coeff(down_time,sr):old2):target1;
  s->freq=up_time;s->width=down_time;
 }
 if(!s->initialized){old1=target1;old2=target2;s->y1=n->type==FM_LeakDC?0:in.p[0];s->last=in.p[0];}
 #define LAG_SAMPLES(A) for(unsigned j=0;j<count;j++){ \
  float a=(A),t=count==1?1:(float)(j+(n->type==FM_LeakDC?0:1))*(1.0f/FM_BLOCK); \
  float up=old1+(target1-old1)*t,down=old2+(target2-old2)*t,z; \
  if(n->type==FM_LeakDC){z=a-s->last+up*s->y1;s->last=a;} \
  else z=a+(a>s->y1?up:down)*(s->y1-a); \
  s->y1=z;checked_signal(v,out+j,z); \
 }
 if(in.rate==2){LAG_SAMPLES(in.p[j]);}else{float scalar=in.p[0];LAG_SAMPLES(scalar);}
 #undef LAG_SAMPLES
 s->b1=target1;s->b2=target2;s->initialized=1;
}
'''

UNARY = r'''
/* Pure unary scalar inputs need one evaluation per block, not 64. Retain a
 * bitwise input/result cache across blocks in otherwise-unused freq/last.
 * Bitwise comparison distinguishes signed zeros. Audio inputs still evaluate
 * every sample, with dispatch outside the loop and the original equations. */
static __attribute__((noinline)) void fast_unary(const fm_graph *g,fm_voice *v,fm_scratch *b,const fm_node *n,fm_state *s,unsigned count){
 fm_bound_input in=bind_input(g,b,n,0,0);float *out=b->signal[n->output];
 if(in.rate!=2){
  float a=in.p[0],z;
  if(s->initialized && dsp_same_bits(a,s->freq))z=s->last;
  else z=unary(n->special,a);
  s->freq=a;s->last=z;checked_signal(v,&z,z);
  for(unsigned j=0;j<count;j++)out[j]=z;
 }else{
  #define UNARY_SAMPLES(EXPR) for(unsigned j=0;j<count;j++){float a=in.p[j];checked_signal(v,out+j,(EXPR));}
  switch(n->special){
  case 0:UNARY_SAMPLES(-a);break;
  case 5:UNARY_SAMPLES(fabsf(a));break;
  case 8:UNARY_SAMPLES(ceilf(a));break;
  case 9:UNARY_SAMPLES(floorf(a));break;
  case 10:UNARY_SAMPLES(a-floorf(a));break;
  case 11:UNARY_SAMPLES((a>0)-(a<0));break;
  case 12:UNARY_SAMPLES(a*a);break;
  case 13:UNARY_SAMPLES(a*a*a);break;
  case 14:UNARY_SAMPLES(a<0?-sqrtf(-a):sqrtf(a));break;
  case 16:UNARY_SAMPLES(1.0f/a);break;
  case 42:UNARY_SAMPLES(a/(1.0f+fabsf(a)));break;
  case 43:UNARY_SAMPLES(fabsf(a)<=0.5f?a:(fabsf(a)-0.25f)/a);break;
  default:UNARY_SAMPLES(unary(n->special,a));break;
  }
  #undef UNARY_SAMPLES
 }
 s->initialized=1;
 if(!n->rate)s->initial_value=out[0];
}
'''


def prepare(render, filters=True, lag=True, unary=True):
    parts=[]
    if filters: parts.append(FILTER)
    if lag or unary: parts.append(SAME)
    if lag: parts.append(LAG)
    if unary: parts.append(UNARY)
    if not parts:return render,''
    include='#include "fm_fast.inc"'
    assert render.count(include)==1
    render=render.replace(include,include+'\n#include "fm_dsp_kernels.inc"')
    anchor='  if(n->type==FM_BinaryOpUGen || n->type==FM_MulAdd || n->type==FM_Sum3 || n->type==FM_Sum4){fast_arithmetic'
    at=render.index(anchor)
    dispatch=''
    if filters:dispatch+='  if(is_filter(n->type)){fast_filter(g,v,b,n,s,count,sr,initializing);continue;}\n'
    if lag:dispatch+='  if(n->type==FM_Lag || n->type==FM_LagUD || n->type==FM_LeakDC){fast_lag(g,v,b,n,s,count,sr);continue;}\n'
    if unary:dispatch+='  if(n->type==FM_UnaryOpUGen){fast_unary(g,v,b,n,s,count);continue;}\n'
    render=render[:at]+dispatch+render[at:]
    return render,'/* SPDX-License-Identifier: GPL-3.0-or-later\n * Block-specialized forms of the pinned SC-derived float32 equations. */\n'+''.join(parts)


def packed_miverb(source):
    """Word transfers through memcpy preserve aliasing and packed Q1.15 bytes."""
    before=' unsigned bits=c->mem[at]|((unsigned)c->mem[at+1]<<8);'
    assert source.count(before)==1
    source=source.replace(before,''' /* Arena slices are float-aligned and every offset is even. memcpy keeps
  * the float-arena aliasing contract; the target can use one aligned load. */
#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
 uint16_t word;const void *address=__builtin_assume_aligned(c->mem+at,2);
 memcpy(&word,address,sizeof word);unsigned bits=word;
#else
 unsigned bits=c->mem[at]|((unsigned)c->mem[at+1]<<8);
#endif''')
    before=' c->mem[at]=(unsigned char)sample;c->mem[at+1]=(unsigned char)(sample>>8);c->acc*=scale;'
    assert source.count(before)==1
    return source.replace(before,'''#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
 void *address=__builtin_assume_aligned(c->mem+at,2);memcpy(address,&sample,sizeof sample);
#else
 c->mem[at]=(unsigned char)sample;c->mem[at+1]=(unsigned char)(sample>>8);
#endif
 c->acc*=scale;''')
