"""Audited transformation of the pinned renderer to planned signal storage.

Logical output IDs remain unchanged: persistent state and rate metadata must
never be indexed by a recycled physical slot. Only temporary sample addresses
are mapped. The loader computes the complete plan outside the audio thread.
"""

PLANNER = r'''
/* Conservative whole-UGen lifetimes: never alias an input with this UGen's
 * output, even when it is the input's final consumer. Multi-output kernels
 * also receive distinct slots. Preserve graph execution and RNG order. */
static int plan_signals(fm_graph *g,char *error,size_t cap) {
 uint16_t ends[FM_AUDIO_BUFFERS];
 unsigned ni,k,peak=0,scalars=0;
 /* This map temporarily stores last consumers, avoiding a second large
  * loader-stack array. All last consumers are known before mapping begins. */
 for(ni=0;ni<g->nodes;ni++){
  const fm_node *n=&g->node[ni];
  for(k=0;k<n->outputs;k++)g->signal_offset[n->output+k]=ni;
 }
 for(ni=0;ni<g->nodes;ni++){
  const fm_node *n=&g->node[ni];
  for(k=0;k<n->inputs;k++){
   const fm_ref *r=&g->ref[n->input+k];
   if(r->node>=0)g->signal_offset[g->node[r->node].output+r->output]=ni;
  }
 }
 for(ni=0;ni<g->nodes;ni++){
  const fm_node *n=&g->node[ni];
  for(k=0;k<n->outputs;k++){
   unsigned o=n->output+k,last=g->signal_offset[o];
   if(n->rate==2){
    unsigned slot=0;
    while(slot<peak && ends[slot]>=ni)++slot;
    if(slot==peak){
     if(peak==FM_AUDIO_BUFFERS){
      if(cap)snprintf(error,cap,"Graph exceeds %u simultaneously live audio buffers",(unsigned)FM_AUDIO_BUFFERS);
      return 0;
     }
     ++peak;
    }
    ends[slot]=(uint16_t)last;g->signal_offset[o]=slot*FM_BLOCK;
   }else{
    /* Scalar outputs retain independent slots. They cost one float, not a
     * whole vector, and remain separate from every audio vector. */
    g->signal_offset[o]=FM_AUDIO_BUFFERS*FM_BLOCK+scalars++;
   }
  }
 }
 g->audio_buffers=(uint16_t)peak;g->scalar_values=(uint16_t)scalars;
 return 1;
}
'''


def addresses(source):
    """Replace only complete b->signal[index] accesses, including nested []."""
    marker = 'b->signal['
    result = []
    at = 0
    while True:
        start = source.find(marker, at)
        if start < 0:
            result.append(source[at:]); break
        begin = start + len(marker)
        end, depth = begin, 1
        while depth:
            if end >= len(source): raise ValueError('Unclosed pinned signal access')
            if source[end] == '[': depth += 1
            elif source[end] == ']': depth -= 1
            end += 1
        result.extend((source[at:start], 'fm_signal(g,b,' + source[begin:end-1] + ')'))
        at = end
    return ''.join(result)


def prepare(header, load, files, audio_buffers):
    before = ' uint8_t output_rate[FM_OUTPUTS],used[FM_NODES];'
    assert header.count(before) == 1
    header = header.replace(before, before + '\n uint32_t signal_offset[FM_OUTPUTS];\n uint16_t audio_buffers,scalar_values;')
    before = 'typedef struct { float signal[FM_OUTPUTS][FM_BLOCK]; } fm_scratch;'
    assert header.count(before) == 1
    header = header.replace(before, f'''#define FM_SIGNAL_REUSE 1
#define FM_AUDIO_BUFFERS {audio_buffers}
typedef struct {{ float data[FM_AUDIO_BUFFERS*FM_BLOCK+FM_OUTPUTS]; }} fm_scratch;
/* Preserve the const qualification of the caller's scratch pointer. Each
 * argument is evaluated exactly once. */
#define fm_signal(g,b,output) ((b)->data+(g)->signal_offset[(output)])''')
    before = 'int fm_load('
    at = load.index(before)
    load = load[:at] + PLANNER + load[at:]
    before = ' g->valid=FM_VALID; return 1;'
    assert load.count(before) == 1
    load = load.replace(before, ' if(!plan_signals(g,error,cap))return 0;\n' + before)
    return header, load, {name: addresses(data) for name,data in files.items()}
