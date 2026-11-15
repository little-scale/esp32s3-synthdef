"""Opt-in exact Saw and Impulse specialisations; no firmware default changes.

Saw reuses b1/total (unused by the pinned Saw recurrence) for the effective
frequency and its exact integer step. A descending harmonic transition must
cache max(new, old), then invalidate on the following steady-frequency block.
No pointers, additional state, tables or delay memory are allocated.
"""
from dsp_binding import function_span


SAW = r'''
static __attribute__((noinline)) void candidate_saw(const fm_graph *g,fm_voice *v,fm_scratch *b,const fm_node *n,fm_state *s,unsigned count,float sr,int initializing){
 float freq=input(g,b,n,0,0),scale;int next_n;
 float *output=b->signal[n->output];
 if(s->initialized && freq==s->freq){next_n=s->env.remaining;scale=s->a0;}
 else{
  float partials=(sr*0.5f)/freq;
  if(!(freq>0) || !isfinite(partials) || partials<1 || partials>16777216){
   v->fault=1;for(unsigned j=0;j<count;j++)output[j]=0;return;
  }
  next_n=(int)partials+(int)floorf((partials-(int)partials)+quotient_error(sr*0.5f,freq,partials));
  scale=0.5f/next_n;
 }
 if(!s->initialized){s->freq=freq;s->env.remaining=next_n;s->a0=scale;s->y1=-0.46f;}
 int old_n=s->env.remaining,crossfade=next_n!=old_n;float old_scale=s->a0;
 float rate=crossfade?fmaxf(freq,s->freq):freq;
 /* b1/total are otherwise unused by Saw. fm_start resets both. */
 if(rate!=s->b1){
  float factor=268435456.0f/sr,product=factor*rate;
  float residual=product_error(factor,rate,product)+quotient_error(268435456.0f,sr,factor)*rate;
  s->total=(uint32_t)((int32_t)product+(int32_t)floorf((product-(int32_t)product)+residual));
  s->b1=rate;
 }
 uint32_t phase=s->phase_acc,step=s->total;float y1=s->y1;
 #define CANDIDATE_SAW_STORE(BLIP) do{ \
  float out=(BLIP)+0.999f*y1;y1=out;phase+=step; \
  if(!isfinite(out) || fabsf(out)>1e12f){v->fault=1;out=0;}output[j]=out; \
 }while(0)
 if(crossfade)for(unsigned j=0;j<count;j++){
  float next=saw_blip(phase,next_n,scale),old=saw_blip(phase,old_n,old_scale);
  float t=(float)j*(1.0f/FM_BLOCK);CANDIDATE_SAW_STORE(old+t*(next-old));
 }else for(unsigned j=0;j<count;j++){
  float blip=saw_blip(phase,next_n,scale);CANDIDATE_SAW_STORE(blip);
 }
 #undef CANDIDATE_SAW_STORE
 s->phase_acc=phase;s->y1=y1;s->a0=scale;s->env.remaining=next_n;s->freq=freq;s->initialized=1;
 s->phase_offset=0;
 if(initializing){s->phase_acc=0;s->y1=-0.46f;}
}
'''


IMPULSE = r'''
static __attribute__((noinline)) void candidate_impulse(const fm_graph *g,fm_voice *v,fm_scratch *b,const fm_node *n,fm_state *s,unsigned count,float sr,int initializing){
 fm_bound_input frequency=bind_input(g,b,n,0,0);
 /* bind_input may collapse a zero control to scalar. Impulse must still
  * interpolate from its previous increment when that control becomes zero. */
 frequency.rate=input_rate(g,n,0);
 float x=frequency.p[0],param=input(g,b,n,1,0),*output=b->signal[n->output];
 if(!s->initialized){s->phase=param-floorf(param);s->last=0;s->freq=x*(1.0f/sr);if(s->phase==0 && s->freq>=0)s->phase=1;}
 float previous_inc=s->freq;
 #define CANDIDATE_IMPULSE_LOOP(INCREMENT) for(unsigned j=0;j<count;j++){ \
  float z=impulse_wrap(s,previous_inc),inc=(INCREMENT); \
  lf_advance(s,inc);previous_inc=inc;checked_signal(v,output+j,z);s->initialized=1; \
 }
 if(frequency.rate==2){
  CANDIDATE_IMPULSE_LOOP(frequency.p[j]*(1.0f/sr));
 }else if(frequency.rate==1){
  float delta=x*(1.0f/sr)-s->freq,reciprocal=count==1?1.0f:1.0f/FM_BLOCK;
  CANDIDATE_IMPULSE_LOOP(s->freq+delta*((float)(j+1)*reciprocal));
 }else{
  CANDIDATE_IMPULSE_LOOP(s->freq);
 }
 #undef CANDIDATE_IMPULSE_LOOP
 s->freq=frequency.p[frequency.rate==2?count-1:0]*(1.0f/sr);
 if(initializing){s->phase=param-floorf(param);s->last=0;if(s->phase==0 && s->freq>=0)s->phase=1;}
}
'''


def prepare(files, *, saw=False, impulse=False):
    files = dict(files)
    if saw:
        text = files['fm_bandlimited.inc']
        start, _ = function_span(text, 'bandlimited')
        text = text[:start+1]+'\n if(n->type==FM_Saw){candidate_saw(g,v,b,n,s,count,sr,initializing);return;}'+text[start+1:]
        anchor = 'static void bandlimited('
        assert text.count(anchor) == 1
        files['fm_bandlimited.inc'] = text.replace(anchor, SAW+'\n'+anchor)
    if impulse:
        text = files['fm_extensions.inc']
        start, _ = function_span(text, 'extensions')
        text = text[:start+1]+'\n if(n->type==FM_Impulse){candidate_impulse(g,v,b,n,s,count,sr,initializing);return;}'+text[start+1:]
        anchor = 'static __attribute__((noinline)) void extensions('
        assert text.count(anchor) == 1
        files['fm_extensions.inc'] = text.replace(anchor, IMPULSE+'\n'+anchor)
    return files
