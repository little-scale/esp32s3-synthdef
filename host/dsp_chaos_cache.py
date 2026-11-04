"""Opt-in exact per-voice cycle-period cache for all fourteen chaos UGens."""
import re

TYPES=('HenonN','HenonL','HenonC','CuspN','CuspL','LatoocarfianN','LatoocarfianL','LatoocarfianC','LorenzL','FBSineN','FBSineL','FBSineC','StandardN','StandardL')


def prepare(files):
    files=dict(files);text=files['fm_chaos.inc']
    old='typedef struct {chaos_state *s;const float *args;float *out;float sr;} chaos_unit;'
    new='''/* Cache fields must be outside the complete overlaid chaotic state. */
typedef char chaos_cache_fits[(offsetof(fm_state,b1)>=sizeof(chaos_state) && offsetof(fm_state,b2)>=sizeof(chaos_state) && offsetof(fm_state,freq)>=sizeof(chaos_state))?1:-1];
typedef struct {chaos_state *s;const float *args;float *out;float sr,period,slope;} chaos_unit;'''
    assert text.count(old)==1;text=text.replace(old,new)
    for name in TYPES:
        start=text.index('static void chaos_'+name+'_next(')
        end=text.find('\nstatic void ',start+1)
        if end<0:end=len(text)
        body=text[start:end]
        assert body.count('    float freq = unit->args[0];')==1
        body=body.replace('    float freq = unit->args[0];\n','')
        opening=body.index('    float samplesPerCycle;')
        closing=body.index('\n\n',opening)
        original=body[opening:closing]
        replacement='    float samplesPerCycle=unit->period;'
        if 'float slope;' in original:replacement+='\n    float slope=unit->slope;'
        body=body[:opening]+replacement+body[closing:]
        text=text[:start]+body+text[end:]
    files['fm_chaos.inc']=text
    text=files['fm_stochastic.inc']
    old='chaos_state state;memcpy(&state,s,sizeof state);chaos_unit unit={&state,args,b->signal[n->output],sr};'
    new='''/* Same divisions and clamp, only when the held frequency changes.
  * The sample rate is immutable until fm_start clears this voice. N variants
  * do not need an interpolation slope; keep their original division count. */
 if(!s->initialized || s->freq!=args[0]){
  s->b1=args[0]<sr?sr/fmaxf(args[0],0.001f):1.f;
  int interpolated=!(n->type==FM_HenonN || n->type==FM_CuspN || n->type==FM_LatoocarfianN || n->type==FM_FBSineN || n->type==FM_StandardN);
  s->b2=interpolated && args[0]<sr?1.f/s->b1:1.f;s->freq=args[0];
 }
 chaos_state state;memcpy(&state,s,sizeof state);chaos_unit unit={&state,args,b->signal[n->output],sr,s->b1,s->b2};'''
    assert text.count(old)==1;text=text.replace(old,new)
    files['fm_stochastic.inc']=text
    return files
