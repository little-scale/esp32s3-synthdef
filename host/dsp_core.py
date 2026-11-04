"""Opt-in exact block kernels and invariant caches for the remaining core UGens."""
TYPES=('LFSaw','LFTri','LFPulse','Klang','Klank','Line','XLine','Formant','Gendy1','Gendy2','Gendy3','SinOscFB','Blip','BPeakEQ','BLowShelf','BHiShelf','Amplitude','Formlet')

SOURCE=r'''
static int candidate_core_same(float a,float b){uint32_t x,y;memcpy(&x,&a,4);memcpy(&y,&b,4);return x==y;}
static __attribute__((noinline)) void candidate_lf(const fm_graph *g,fm_voice *v,fm_scratch *b,const fm_node *n,fm_state *s,unsigned count,float sr,int initializing){
 fm_bound_input freq=bind_input(g,b,n,0,0);float *out=b->signal[n->output];
 if(!s->initialized){s->phase=input(g,b,n,1,0);if(n->type==FM_LFTri)s->phase-=4*floorf(s->phase*.25f);if(n->type==FM_LFPulse)s->width=input(g,b,n,2,0);}
 switch(n->type){
 case FM_LFSaw:for(unsigned j=0;j<count;j++){
  float z=s->phase;lf_advance(s,freq.p[freq.rate==2?j:0]*(2.0f/sr));if(lf_ge(s,1))s->phase-=2;else if(lf_le(s,-1))s->phase+=2;checked_signal(v,out+j,z);
 }break;
 case FM_LFTri:for(unsigned j=0;j<count;j++){
  float z=s->phase>1?2-s->phase:s->phase;lf_advance(s,freq.p[freq.rate==2?j:0]*(4.0f/sr));if(lf_ge(s,3))s->phase-=4;checked_signal(v,out+j,z);
 }break;
 case FM_LFPulse:{float width=input(g,b,n,2,0);for(unsigned j=0;j<count;j++){
  float z;if(lf_ge(s,1)){s->phase-=1;s->width=width;z=s->width<=.5f?1:0;}else z=s->phase<s->width || (s->phase==s->width && s->last<0)?1:0;
  lf_advance(s,freq.p[freq.rate==2?j:0]*(1.0f/sr));checked_signal(v,out+j,z);
 }break;}
 default:v->fault=1;break;
 }
 s->initialized=1;
 if(initializing){s->phase=input(g,b,n,1,0);s->last=0;if(n->type==FM_LFTri)s->phase-=4*floorf(s->phase*.25f);if(n->type==FM_LFPulse)s->width=input(g,b,n,2,0);}
}
static __attribute__((noinline)) void candidate_bank(const fm_graph *g,fm_voice *v,fm_scratch *b,const fm_node *n,fm_state *s,unsigned count,float sr,int initializing){
 float *out=b->signal[n->output];fm_bound_input excitation=bind_input(g,b,n,0,0);
 if(!s->initialized)for(unsigned k=0;k<n->partials;k++){
  fm_partial *p=&v->partial[n->partial+k];int base=(n->type==FM_Klang?2:4)+3*k;
  if(n->type==FM_Klang){
   float w=(input(g,b,n,base,0)*input(g,b,n,0,0)+input(g,b,n,1,0))*TAU/sr,amp=input(g,b,n,base+1,0),phase=input(g,b,n,base+2,0);
   p->y1=amp*sinf(phase-w);p->y2=amp*sinf(phase-2*w);p->b1=2*cosf(w);
  }else{
   resonator(input(g,b,n,base,0)*input(g,b,n,1,0)+input(g,b,n,2,0),input(g,b,n,base+2,0)*input(g,b,n,3,0),sr,1,&p->a0,&p->b1,&p->b2);p->a0=input(g,b,n,base+1,0)*.25f;
  }
 }
 if(n->type==FM_Klang)for(unsigned j=0;j<count;j++){
  float sum=0;for(unsigned k=0;k<n->partials;k++){fm_partial *p=&v->partial[n->partial+k];float y=p->b1*p->y1-p->y2;sum+=y;p->y2=p->y1;p->y1=y;}checked_signal(v,out+j,sum);
 }else for(unsigned j=0;j<count;j++){
  float sum=0,a=excitation.p[excitation.rate==2?j:0];
  for(unsigned k=0;k<n->partials;k++){fm_partial *p=&v->partial[n->partial+k];float y=a+p->b1*p->y1+p->b2*p->y2;sum+=p->a0*y;p->y2=p->y1;p->y1=y;}
  float z=sum-s->y2;s->y2=s->y1;s->y1=sum;checked_signal(v,out+j,z);
 }
 s->initialized=1;
 if(initializing){s->initialized=0;if(n->type==FM_Klank){s->y1=s->y2=0;for(unsigned k=0;k<n->partials;k++)v->partial[n->partial+k].y1=v->partial[n->partial+k].y2=0;}}
}
static float candidate_line_lerp(float a,float span,float spanlow,float numerator,float denominator){
 float q=numerator/denominator,qlow=quotient_error(numerator,denominator,q);
 float product=span*q,low=product_error(span,q,product)+span*qlow+spanlow*q;
 float sum=a+product,back=sum-a;return sum+((a-(sum-back))+(product-back)+low);
}
static __attribute__((noinline)) void candidate_line(const fm_graph *g,fm_voice *v,fm_scratch *b,const fm_node *n,fm_state *s,unsigned count,float sr,int initializing,int *free_voice){
 fm_env *e=&s->env;float *out=b->signal[n->output];int done=input(g,b,n,3,0)==2;
 if(!s->initialized){
  float a=input(g,b,n,0,0);e->level=a;e->start=a;e->end=input(g,b,n,1,0);e->remaining=(int32_t)fminf(1e9f,fmaxf(0,input(g,b,n,2,0)*sr+.5f));
  e->duration=fmaxf(1,(float)e->remaining);
  if(e->remaining>0){
   e->grow=n->type==FM_Line?(e->end-a)/e->remaining:powf(e->end/a,1.0f/e->remaining);
   if(n->type==FM_Line){s->freq=e->end-a;float back=s->freq-e->end;s->width=(e->end-(s->freq-back))+(-a-back);}
   else s->freq=e->end/a;
  }else e->level=e->end;
 }
 if(n->type==FM_Line)for(unsigned j=0;j<count;j++){
  float z=e->level;
  if(!initializing && e->remaining>0){e->elapsed++;e->level=candidate_line_lerp(e->start,s->freq,s->width,(float)e->elapsed,e->duration);e->remaining--;}
  if(!initializing && !e->remaining){e->level=e->end;if(done)*free_voice=1;}
  checked_signal(v,out+j,z);
 }else for(unsigned j=0;j<count;j++){
  float z=e->level;
  if(!initializing && e->remaining>0){e->elapsed++;float t=(float)e->elapsed/e->duration;e->level=e->start*powf(s->freq,t);e->remaining--;}
  if(!initializing && !e->remaining){e->level=e->end;if(done)*free_voice=1;}
  checked_signal(v,out+j,z);
 }
 s->initialized=1;
}
'''


def prepare(files):
    files=dict(files);render=files['fm_render.c'];anchor='#include "fm_extensions.inc"'
    assert render.count(anchor)==1;render=render.replace(anchor,SOURCE+'\n'+anchor)
    anchor='  if(n->type==FM_BinaryOpUGen || n->type==FM_MulAdd || n->type==FM_Sum3 || n->type==FM_Sum4){fast_arithmetic'
    at=render.index(anchor)
    dispatch='''  if(n->type==FM_LFSaw || n->type==FM_LFTri || n->type==FM_LFPulse){candidate_lf(g,v,b,n,s,count,sr,initializing);continue;}
  if(n->type==FM_Klang || n->type==FM_Klank){candidate_bank(g,v,b,n,s,count,sr,initializing);continue;}
  if(n->type==FM_Line || n->type==FM_XLine){candidate_line(g,v,b,n,s,count,sr,initializing,&free_voice);continue;}
'''
    files['fm_render.c']=render[:at]+dispatch+render[at:]
    text=files['fm_formants.inc']
    start=text.index(' uint32_t inc[3],phase[3],width;float scale=')
    end=text.index(' for(j=0;j<count;j++){',start)
    text=text[:start]+''' uint32_t inc[3],phase[3],width;float args[3];unsigned j,k;
 for(k=0;k<3;k++){args[k]=input(g,b,n,k,0);if(!isfinite(args[k]) || args[k]<0 || args[k]>sr*.5f){v->fault=1;return;}phase[k]=s->dice[k];}
 if(!s->dice[7] || args[0]!=s->previous[0] || args[1]!=s->previous[1] || args[2]!=s->previous[2]){
  float scale=536870912.0f/sr;for(k=0;k<3;k++){s->dice[3+k]=(uint32_t)(scale*args[k]);s->previous[k]=args[k];}
  s->dice[6]=s->dice[3]>s->dice[5]?s->dice[3]:s->dice[5];s->dice[7]=1;
 }
 for(k=0;k<3;k++)inc[k]=s->dice[3+k];width=s->dice[6];
'''+text[end:]
    files['fm_formants.inc']=text
    text=files['fm_gendy.inc'];old=' ca=gendy_constant(wa,p[2]);cd=gendy_constant(wd,p[3]);'
    assert text.count(old)==1
    text=text.replace(old,''' /* Independent distribution caches use fields absent from the recurrence. */
 if(!s->dice[3] || s->dice[1]!=(uint32_t)wa || s->env.start!=p[2]){s->env.level=gendy_constant(wa,p[2]);s->dice[1]=(uint32_t)wa;s->env.start=p[2];}
 if(!s->dice[3] || s->dice[2]!=(uint32_t)wd || s->env.end!=p[3]){s->env.grow=gendy_constant(wd,p[3]);s->dice[2]=(uint32_t)wd;s->env.end=p[3];}
 s->dice[3]=1;ca=s->env.level;cd=s->env.grow;''')
    files['fm_gendy.inc']=text
    text=files['fm_expansion.inc']
    old='float target=expansion_radians(p[1]);if(!s->initialized)s->last=target;'
    new='''float target;
  if(!s->initialized || !candidate_core_same(p[1],s->width)){s->a0=expansion_radians(p[1]);s->width=p[1];}target=s->a0;
  if(!s->initialized)s->last=target;'''
    assert text.count(old)==1;text=text.replace(old,new)
    old='float fb=s->last,delta=(target-fb)/(n->rate==2?FM_BLOCK:1);uint32_t step=sine_control_step(p[0],sr);'
    new='''float fb=s->last,delta=(target-fb)/(n->rate==2?FM_BLOCK:1);
  if(!s->initialized || !candidate_core_same(p[0],s->freq)){s->total=sine_control_step(p[0],sr);s->freq=p[0];}uint32_t step=s->total;'''
    assert text.count(old)==1;text=text.replace(old,new)
    old='int old=s->env.remaining;float f=(old!=nh&&requested>maximum)?fmaxf(s->freq,p[0]):p[0];uint32_t step=sine_control_step(f,sr)/2;'
    new='''int old=s->env.remaining;float f=(old!=nh&&requested>maximum)?fmaxf(s->freq,p[0]):p[0];
  /* Cache the effective crossfade frequency, not merely the requested pitch. */
  if(!s->dice[0] || !candidate_core_same(f,s->initial_value)){s->total=sine_control_step(f,sr)/2;s->initial_value=f;s->dice[0]=1;}uint32_t step=s->total;
  float oldscale=s->a0,scale=!s->initialized || old!=nh?.5f/nh:s->a0;s->a0=scale;'''
    assert text.count(old)==1;text=text.replace(old,new)
    old='saw_blip(s->phase_acc,nh,.5f/nh)';assert text.count(old)==1;text=text.replace(old,'saw_blip(s->phase_acc,nh,scale)')
    old='saw_blip(s->phase_acc,old,.5f/old)';assert text.count(old)==1;text=text.replace(old,'saw_blip(s->phase_acc,old,oldscale)')
    files['fm_expansion.inc']=text
    # Retain each exact three-sample coefficient group, calculating it once
    # instead of repeating the same five/four coefficient expressions per frame.
    text=files['fm_modulation.inc']
    anchor=' unsigned j,k,steps=count;float p[4]={0},old[5]={0},target[5]={0};'
    assert text.count(anchor)==1
    text=text.replace(anchor,anchor+'\n float candidate_eq[5];unsigned candidate_eq_group=UINT32_MAX;')
    old='''   float c[5],t=count==1?1:(float)(j/3)/(count/3),y;
   for(k=0;k<5;k++)c[k]=old[k]+(target[k]-old[k])*t;
   y=a-c[3]*s->phase+c[4]*s->y2;z=c[0]*y-c[2]*s->y2+c[1]*s->phase;lf_advance(s,y);s->y2=y;break;'''
    new='''   float y;
   if(candidate_eq_group!=j/3){float t=count==1?1:(float)(j/3)/(count/3);for(k=0;k<5;k++)candidate_eq[k]=old[k]+(target[k]-old[k])*t;candidate_eq_group=j/3;}
   y=a-candidate_eq[3]*s->phase+candidate_eq[4]*s->y2;z=candidate_eq[0]*y-candidate_eq[2]*s->y2+candidate_eq[1]*s->phase;lf_advance(s,y);s->y2=y;break;'''
    assert text.count(old)==1;text=text.replace(old,new)
    old='  target[0]=p[1]==0?0:expf(-2.302585092994046f/(p[1]*sr));target[1]=p[2]==0?0:expf(-2.302585092994046f/(p[2]*sr));'
    new='''  if(!s->initialized || !candidate_core_same(s->freq,p[1])){s->b1=p[1]==0?0:expf(-2.302585092994046f/(p[1]*sr));s->freq=p[1];}
  if(!s->initialized || !candidate_core_same(s->width,p[2])){s->b2=p[2]==0?0:expf(-2.302585092994046f/(p[2]*sr));s->width=p[2];}target[0]=s->b1;target[1]=s->b2;'''
    assert text.count(old)==1;text=text.replace(old,new);files['fm_modulation.inc']=text
    text=files['fm_formants.inc']
    anchor='static void formlet_render('
    opening=text.index('{',text.index(anchor))
    text=text[:opening+1]+'\n float c[4];unsigned candidate_formlet_group=UINT32_MAX;'+text[opening+1:]
    old='float c[4],t=count==1?1:(float)(j/3)/(count/3),x='
    assert text.count(old)==1;text=text.replace(old,'float x=')
    old='  for(k=0;k<4;k++)c[k]=s->previous[k]+(target[k]-s->previous[k])*t;'
    new='  if(candidate_formlet_group!=j/3){float t=count==1?1:(float)(j/3)/(count/3);for(k=0;k<4;k++)c[k]=s->previous[k]+(target[k]-s->previous[k])*t;candidate_formlet_group=j/3;}'
    assert text.count(old)==1;text=text.replace(old,new);files['fm_formants.inc']=text
    return files
