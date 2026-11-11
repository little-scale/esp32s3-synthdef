"""Opt-in input-reference binding; preserves sample indexing and DSP equations."""
import re

# Only renderers with actual sample-loop input decoding are touched. Parameters
# already sampled once per block stay on the existing path.
FUNCTIONS = {
    'fm_delay.inc': {'delay_render': 3},
    'fm_extensions.inc': {'extensions': 3},
    'fm_utilities.inc': {'utilities': 6},
    'fm_modulation.inc': {'modulation': 2},
    'fm_formants.inc': {'formlet_render': 1},
    'fm_miverb.inc': {'render_miverb': 8},
    'fm_rings.inc': {'rings_render': 1},
    'fm_stochastic.inc': {'stochastic_render': 3},
    'fm_expansion.inc': {'expansion_shift': 3, 'expansion_render': 6},
}

TYPE_FAMILIES = {
    'delay_render': ('DelayN','DelayL','DelayC','CombN','CombL','CombC','AllpassN','AllpassL','AllpassC'),
    'extensions': ('OnePole','OneZero','LPZ1','HPZ1','Latch','Gate','TRand','TExpRand','Impulse'),
    'utilities': ('Fold','Wrap','BrownNoise','ClipNoise','Trig','Trig1','PulseDivider','PulseCount','ToggleFF','SetResetFF','Stepper','XFade2','LinXFade2','Balance2','LinExp','Slew','Lag2','Lag3','MiMu'),
    'modulation': ('VarSaw','SyncSaw','LFCub','LFPar','LFDNoise0','LFDNoise1','LFDNoise3','Amplitude','BPeakEQ','BLowShelf','BHiShelf'),
    'formlet_render': ('Formlet',),
    'render_miverb': ('MiVerb',),
    'rings_render': tuple('MiRings'+str(i) for i in range(1,7)),
    'stochastic_render': ('Crackle','LFClipNoise','LFDClipNoise','GrayNoise','Hasher','CoinGate','TIRand','TWindex','Logistic'),
    'expansion_shift': ('FreqShift',),
    'expansion_render': ('SinOscFB','Blip','Phasor','Pluck','MoogFF','Limiter'),
}

HELPERS = r'''
/* The loader requires each output rate to match its node rate. These immutable
 * pointers are local to one renderer invocation; no global cache or allocation.
 * Absent optional inputs remain unbound and are never read by legal branches. */
typedef struct {const float *p;unsigned rate;} candidate_input_ref;
static inline __attribute__((always_inline)) candidate_input_ref candidate_bind_ref(const fm_graph *g,const fm_scratch *b,const fm_node *n,unsigned k){
 candidate_input_ref x={NULL,0};if(k>=n->inputs)return x;
 const fm_ref *r=&g->ref[n->input+k];
 if(r->node<0)x.p=&g->constant[r->output];
 else{unsigned o=g->node[r->node].output+r->output;x.p=b->signal[o];x.rate=g->output_rate[o];}
 return x;
}
static inline __attribute__((always_inline)) float candidate_read_ref(const candidate_input_ref *x,unsigned k,unsigned j){
 return x[k].p[x[k].rate==2?j:0];
}
'''


def function_span(text, name):
    start = re.search(r'^static [^\n]*\b'+name+r'\(', text, re.M)
    assert start, name
    opening = text.index('{', start.start())
    # Tokenise comments/strings so their braces cannot truncate a function.
    tokens = re.finditer(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\{|\}', text[opening:], re.S)
    depth = 0
    for token in tokens:
        if token[0] == '{': depth += 1
        elif token[0] == '}':
            depth -= 1
            if depth == 0:
                return opening, opening+token.end()
    raise AssertionError('Unclosed function '+name)


def prepare(files, families=None):
    selected=set(TYPE_FAMILIES if families is None else families)
    if not selected or selected-set(TYPE_FAMILIES):
        raise ValueError('Choose known binding entry points: '+','.join(TYPE_FAMILIES))
    files = dict(files)
    render = files['fm_render.c']
    anchor = 'static uint32_t phase_word('
    assert render.count(anchor) == 1
    if HELPERS not in render:
        files['fm_render.c'] = render.replace(anchor, HELPERS+'\n'+anchor)
    counts = {}
    for filename, functions in FUNCTIONS.items():
        text = files[filename]
        for name, capacity in functions.items():
            if name not in selected:continue
            opening, end = function_span(text, name)
            body = text[opening+1:end-1]
            sample_calls = 0

            def replace(match):
                nonlocal sample_calls
                index, sample = match.groups()
                if sample.strip() == '0': return match[0]
                if index.isdigit(): assert int(index) < capacity, (name, index)
                sample_calls += 1
                return f'candidate_read_ref(candidate_refs,{index},{sample})'

            body = re.sub(r'input\(g,b,n,([^,()]+),([^()]+?)\)', replace, body)
            assert sample_calls, name
            rates = 0

            def replace_rate(match):
                nonlocal rates
                index = int(match[1])
                if index >= capacity: return match[0]
                rates += 1
                return f'candidate_refs[{index}].rate'

            body = re.sub(r'input_rate\(g,n,(\d+)\)', replace_rate, body)
            bind = f'\n candidate_input_ref candidate_refs[{capacity}];for(unsigned ci=0;ci<{capacity};ci++)candidate_refs[ci]=candidate_bind_ref(g,b,n,ci);\n'
            # Avoid binding twice in delegated frequency-shift/chaos paths.
            early = {
                'expansion_render': ' if(n->type==FM_FreqShift){expansion_shift(g,v,b,n,s,count,sr,init);return;}',
                'stochastic_render': ' if(n->type>=FM_HenonN){chaos_render(g,v,b,n,s,count,sr,init);return;}',
            }.get(name)
            if early:
                assert body.count(early) == 1
                body = body.replace(early, early+bind)
            else:
                body = bind+body
            text = text[:opening+1]+body+text[end-1:]
            counts[name] = {'bound_slots': capacity, 'sample_call_sites': sample_calls, 'rate_call_sites': rates}
        files[filename] = text
    return files, counts
