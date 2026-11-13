"""Narrow exact mixer candidates; not enabled in firmware defaults.

All-audio Sum3/Sum4 bypass repeated rate tests. Pan2 binds its two output
pointers once per block. Arithmetic order, faults, control ramps and state stay
identical. This module is deliberately separate from the qualified build.
"""
from dsp_binding import function_span


def prepare(files):
    files = dict(files)
    text = files['fm_fast.inc']
    anchor = ' /* Resolve scalar/audio combinations outside the inner loop.'
    assert text.count(anchor) == 1
    body = r'''
 /* The loader's signal-lifetime mapping keeps all inputs live until this
  * node completes. Bind only within this invocation; never cache pointers in
  * the voice. Keep the original left-associative float32 addition order. */
 if((op==-2 || op==-3) && x[0].rate==2 && x[1].rate==2 && x[2].rate==2 && (op==-2 || x[3].rate==2)){
  const float *a=x[0].p,*c=x[1].p,*d=x[2].p;
  if(op==-2){for(j=0;j<count;j++)checked_signal(v,out+j,a[j]+c[j]+d[j]);}
  else {const float *e=x[3].p;for(j=0;j<count;j++)checked_signal(v,out+j,a[j]+c[j]+d[j]+e[j]);}
  goto arithmetic_done;
 }
'''
    text = text.replace(anchor, body+anchor)
    start, end = function_span(text, 'fast_pan')
    pan = text[start+1:end-1]
    left = 'fm_signal(g,b,n->output)' if 'fm_signal(g,b,n->output)' in pan else 'b->signal[n->output]'
    right = 'fm_signal(g,b,n->output+1)' if 'fm_signal(g,b,n->output+1)' in pan else 'b->signal[n->output+1]'
    assert pan.count(left) == pan.count(right) == 2
    pan = pan.replace(right, 'out_right').replace(left, 'out_left')
    pan = f'\n float *out_left={left},*out_right={right};\n'+pan
    files['fm_fast.inc'] = text[:start+1]+pan+text[end-1:]
    return files
