"""Select the measured smoothing/bank/delay winners without broad core caches.

The arithmetic bodies are reused verbatim from the qualified candidate revision.
Only function names and dispatch placement differ; combined-image target timing
must therefore be checked separately from the individual candidate measurements.
"""
from dsp_candidates import SMOOTH
from dsp_core import SOURCE
from dsp_binding import function_span,prepare as bind_inputs

BINDINGS=('delay_render','render_miverb')
SMOOTH_TYPES=('Lag2','Lag3','OnePole','OneZero','LPZ1','HPZ1')
BANK_TYPES=('Klang','Klank')


def prepare(files,*,smooth=True,banks=True,binding_families=BINDINGS):
    files=dict(files);render=files['fm_render.c'];definitions=[]
    if smooth:
        definitions.append(SMOOTH.replace('candidate_smooth','qualified_smooth'))
        # Keep the existing filter/arithmetic/envelope/oscillator fast exits first.
        anchor='  if(n->type>=FM_OnePole && n->type<=FM_Decay2){extensions'
        assert render.count(anchor)==1
        guard='  if((n->type>=FM_OnePole && n->type<=FM_HPZ1) || n->type==FM_Lag2 || n->type==FM_Lag3){qualified_smooth(g,v,b,n,s,count,sr,initializing);continue;}\n'
        render=render.replace(anchor,guard+anchor)
    if banks:
        start=SOURCE.index('static __attribute__((noinline)) void candidate_bank(')
        _,end=function_span(SOURCE,'candidate_bank')
        definitions.append(SOURCE[start:end].replace('candidate_bank','qualified_bank'))
        # This fallback is reached after existing fast paths, effects and delays.
        anchor='  if(!s->initialized && (n->type==FM_Klang || n->type==FM_Klank)) {'
        assert render.count(anchor)==1
        guard='  if(n->type==FM_Klang || n->type==FM_Klank){qualified_bank(g,v,b,n,s,count,sr,initializing);continue;}\n'
        render=render.replace(anchor,guard+anchor)
    if definitions:
        anchor='#include "fm_extensions.inc"';assert render.count(anchor)==1
        render=render.replace(anchor,'\n'.join(definitions)+'\n'+anchor)
    files['fm_render.c']=render
    counts={}
    if binding_families:files,counts=bind_inputs(files,binding_families)
    return files,dict(smoothing=smooth,partial_banks=banks,input_binding=counts)
