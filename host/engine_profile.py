#!/usr/bin/env python3
"""Generate an audited target copy; keep the vendored engine byte-for-byte intact."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from signal_buffers import prepare as prepare_signals
from dsp_kernels import prepare as prepare_dsp,packed_miverb
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'upstream/fm1-synthdef/synthdef-engine/src'
LIMITS={'FM_NODES':(160,24),'FM_OUTPUTS':(192,32),'FM_INPUTS':(1024,256),'FM_DELAY_LIMIT':('65536u','262144u')}
PROFILES={'compact':LIMITS,'fm1':{**LIMITS,'FM_NODES':(160,256),'FM_OUTPUTS':(192,512),'FM_INPUTS':(1024,2048)}}

def profile_renderer(render, delay):
    """Separate diagnostic translation unit: zero timing overhead in normal DSP."""
    names=sorted(set(re.findall(r"^(?:int|void|uint32_t) (fm_\w+)\(",render+'\n'+delay,re.M)))
    # Keep diagnostic locals distinct in the linker map and size/IRAM audit.
    local_text=render+'\n'+''.join(p.read_text() for p in SOURCE.glob('*.inc'))
    locals=set(re.findall(r"\b((?:rg_|rings_|fast_)\w+)\s*\(",local_text))
    locals.update(('rg_init_precleared','render_graph','binary','unary','envelope',
                   'envelope_init','segment','sine_control_step','delay_render','fm_sine'))
    prefix=''.join(f'#define {name} fm_ugen_{name[3:]}\n' for name in names)
    prefix+=''.join(f'#define {name} ugen_local_{name}\n' for name in sorted(locals))
    prefix+='''#include "fm_synth.h"
#ifdef ESP_PLATFORM
static inline uint32_t ugen_clock_cycles(void){uint32_t value;__asm__ __volatile__("rsr.ccount %0" : "=a"(value) :: "memory");return value;}
#define UGEN_CLOCK() ugen_clock_cycles()
#else
extern uint32_t fm_ugen_clock(void);
#define UGEN_CLOCK() fm_ugen_clock()
#endif
uint64_t fm_ugen_cycles[FM_NODES];
uint32_t fm_ugen_calls[FM_NODES];
static uint32_t ugen_started;
static __attribute__((noinline)) void ugen_begin(void){ugen_started=UGEN_CLOCK();}
static __attribute__((noinline)) void ugen_end(unsigned i){
 uint32_t elapsed=UGEN_CLOCK()-ugen_started;fm_ugen_cycles[i]+=elapsed;++fm_ugen_calls[i];
}
'''
    loop='for(ni=0;ni<g->nodes && !v->fault;ni++) {'
    assert render.count(loop)==1
    return prefix+render.replace(loop,'for(ni=0;ni<g->nodes && !v->fault;ugen_end(ni),ni++) {\n  ugen_begin();')

def generate(output, profile='compact', optimize_kernels=True, optimize_miverb=True, optimize_saw=True, reuse_buffers=True, optimize_filters=True, optimize_lag=True, optimize_unary=True, optimize_miverb_packed=False):
    output.mkdir(parents=True,exist_ok=True)
    source=(SOURCE/'fm_synth.h').read_text();header=source
    limits=PROFILES[profile]
    for name,(old,new) in limits.items():
        before=f'#define {name} {old}';after=f'#define {name} {new}'
        if header.count(before)!=1:raise RuntimeError('Pinned header does not match '+name)
        header=header.replace(before,after)
    declaration='int fm_bind_delay(fm_voice *, const fm_graph *, float *memory, uint32_t samples);'
    assert header.count(declaration)==1
    header=header.replace(declaration,declaration+'\n/* Caller must zero the complete required arena before binding. Same validation\n * and layout as fm_bind_delay; permits bounded clearing between audio blocks. */\nint fm_bind_delay_precleared(fm_voice *, const fm_graph *, float *memory, uint32_t samples);')
    header=header.replace('#define FM_CONTROLS 64','#define FM_CONTROLS 64\n#define FM_CONTROL_BUSES 32')
    header=header.replace('float control[FM_CONTROLS], sample_rate;',
                          'float control[FM_CONTROLS], sample_rate;\n const float *control_buses;\n uint32_t control_bus_count;')
    header=header.replace('\n#endif','\n/* Caller-owned snapshot, stable throughout prepare/render. Bind after fm_start. */\nint fm_bind_control_buses(fm_voice *,const float *,uint32_t);\n#endif')
    load=(SOURCE/'fm_load.c').read_text()
    in_start=load.index('  } else if(u->type==FM_In) {');in_end=load.index('  } else if(u->type==FM_Out)',in_start)
    load=load[:in_start]+'''  } else if(u->type==FM_In) {
   if(u->inputs!=1 || u->outputs<1 || (u->rate!=1 && u->rate!=2))BAD("In requires audio/control rate and one bus input");
   if(u->rate==1){
    if(u->outputs>FM_CONTROL_BUSES)BAD("In.kr channel count exceeds control bus bank");
    if(literal(g,u,0,&v)){if(v<0 || v>FM_CONTROL_BUSES-u->outputs || floorf(v)!=v)BAD("Control bus range outside bank");}
    else {fm_ref *ref=&g->ref[u->input];if(g->node[ref->node].rate>1)BAD("Control bus index requires initial/control rate");}
   }else{
    if(u->outputs>2)BAD("In.ar requires one or two audio channels");
    if(literal(g,u,0,&v)){if(v!=0)BAD("Only audio input bus 0 is supported");}
    else {fm_ref *ref=&g->ref[u->input];if(g->node[ref->node].rate>1)BAD("In bus requires initial/control rate");}
   }
''' +load[in_end:]
    # DynKlank/DynKlang are SC-language composites of Ringz/SinOsc. SC's
    # Ringz samples coefficient inputs at offset zero even if fed audio-rate
    # buffers; SinOsc selects its input-rate calculation independently of its
    # own output rate. Retain the rate check on Ringz excitation itself.
    before=' || u->type==FM_Resonz || u->type==FM_Ringz || u->type==FM_LFPulse) {'
    assert load.count(before)==1
    load=load.replace(before,' || u->type==FM_Resonz || u->type==FM_LFPulse) {')
    before='else if(u->type!=FM_A2K && !(u->type==FM_Amplitude && j==0) && rate>u->rate)'
    assert load.count(before)==1
    load=load.replace(before,'else if(u->type!=FM_A2K && u->type!=FM_SinOsc && !(u->type==FM_Ringz && j>0) && !(u->type==FM_Amplitude && j==0) && rate>u->rate)')
    render=(SOURCE/'fm_render.c').read_text()
    anchor='/* Error term of a float product, without requiring double or hardware FMA. */'
    assert render.count(anchor)==1
    render=render.replace(anchor,'''int fm_bind_control_buses(fm_voice *v,const float *values,uint32_t count) {
 if(!v || count>FM_CONTROL_BUSES || (!values && count))return 0;
 v->control_buses=values;v->control_bus_count=count;return 1;
}
'''+anchor)
    anchor='  if(n->type==FM_In){'
    assert render.count(anchor)==1
    render=render.replace(anchor,'''  if(n->type==FM_In && n->rate==1){
   float address=input(g,b,n,0,0);
   int valid=isfinite(address) && address>=0 && address<=FM_CONTROL_BUSES-n->outputs && floorf(address)==address;
   if(!valid)v->fault=1;
   unsigned base=valid?(unsigned)address:0;
   for(k=0;k<n->outputs;k++){
    float value=valid && v->control_buses && base+k<v->control_bus_count?v->control_buses[base+k]:0;
    checked_signal(v,&b->signal[n->output+k][0],value);
   }
   s->initialized=1;continue;
  }
'''+anchor)
    delay=(SOURCE/'fm_delay.inc').read_text()
    start=delay.index('int fm_bind_delay(');end=delay.index('static float delay_feedback',start)
    original=delay[start:end]
    signature='int fm_bind_delay(fm_voice *v,const fm_graph *g,float *memory,uint32_t capacity)'
    clear='if(need)memset(memory,0,need*sizeof(float));'
    assert original.count(signature)==1 and original.count(clear)==1
    binding=original.replace(signature,'static int fm_bind_delay_mode(fm_voice *v,const fm_graph *g,float *memory,uint32_t capacity,int clear)')
    binding=binding.replace(clear,'if(need && clear)memset(memory,0,need*sizeof(float));')
    binding+='int fm_bind_delay(fm_voice *v,const fm_graph *g,float *m,uint32_t n){return fm_bind_delay_mode(v,g,m,n,1);}\n'
    binding+='int fm_bind_delay_precleared(fm_voice *v,const fm_graph *g,float *m,uint32_t n){return fm_bind_delay_mode(v,g,m,n,0);}\n'
    delay=delay[:start]+binding+delay[end:]
    gendy=(SOURCE/'fm_gendy.inc').read_text()
    old_guard='index++;if(index<0 || index>=(int)s->dice[0]){v->fault=1;return;}'
    old_next='next=extra[index+1];'
    assert gendy.count(old_guard)==1 and gendy.count(old_next)==1
    gendy=gendy.replace(old_guard,'/* The normalized retained durations can sum to less than one when\n     * sub-sample breakpoints are discarded. The allocated closing segment\n     * at active is valid and holds zero until the next period. */\n    index++;if(index<0 || index>(int)s->dice[0]){v->fault=1;return;}')
    gendy=gendy.replace(old_next,'next=index==(int)s->dice[0]?0:extra[index+1];')
    rings=(SOURCE/'fm_rings.inc').read_text()
    rings_clear='memset(mem,0,rings_words(model,compact)*4u);rg_common c;'
    assert rings.count(rings_clear)==1
    initializer='static void rg_init(float *mem,unsigned model,float sr,uint32_t seed,unsigned compact)'
    assert rings.count(initializer)==1 and rings.count('if(initializing){rg_init(')==1
    rings=rings.replace(initializer,initializer.replace('rg_init(','rg_init_precleared('))
    rings=rings.replace(rings_clear,'/* Both binding APIs require a fully cleared, non-overlapping slice.\n  * Re-clearing it here duplicates work and breaks the bounded note startup. */\n rg_common c;')
    # Keep the standalone initializer's contract for the independent oracle.
    anchor='static float rg_note('
    assert rings.count(anchor)==1
    rings=rings.replace(anchor,'static __attribute__((unused)) void rg_init(float *mem,unsigned model,float sr,uint32_t seed,unsigned compact){\n memset(mem,0,rings_words(model,compact)*4u);rg_init_precleared(mem,model,sr,seed,compact);\n}\n'+anchor)
    rings=rings.replace('if(initializing){rg_init(','if(initializing){rg_init_precleared(')
    fast=(SOURCE/'fm_fast.inc').read_text()
    before='if(f.rate!=2)step=sine_control_step(f.p[0],sr);'
    assert fast.count(before)==1
    fast=fast.replace(before,'''/* Frequency and sample rate are unchanged between most blocks. Keep the
    * exact integer phase increment; fm_start clears this per-node cache. */
 if(f.rate!=2){
  if(!s->initialized || f.p[0]!=s->freq){s->total=sine_control_step(f.p[0],sr);s->freq=f.p[0];}
  step=s->total;
 }''')
    extensions=(SOURCE/'fm_extensions.inc').read_text()
    before='float a=in.p[in.rate==2?j:0],t=(float)j/count;'
    assert extensions.count(before)==1
    extensions=extensions.replace(before,'''/* count is 64, or a constructor/control pass where j is zero.
     * Division by 64 is exactly multiplication by its binary reciprocal. */
  float a=in.p[in.rate==2?j:0],t=(float)j*(1.0f/FM_BLOCK);''')
    before='''if(!s->initialized || attack!=s->a0 || decay!=s->freq){
  target=decay_grow(decay,sr);target2=two?decay_grow(attack,sr):-1;
 }else{target=old;target2=old2;}'''
    assert extensions.count(before)==1
    extensions=extensions.replace(before,'''/* A changing decay does not invalidate the independent attack coefficient. */
 target=!s->initialized || decay!=s->freq?decay_grow(decay,sr):old;
 target2=two?(!s->initialized || attack!=s->a0?decay_grow(attack,sr):old2):-1;''')
    before=''' for(j=0;j<count;j++){
  float r=random_uniform(v),z=r<threshold?r*scale-offset:0;
  checked_signal(v,out+j,z);
 }
 s->initialized=1;'''
    assert extensions.count(before)==1
    extensions=extensions.replace(before,''' /* The same taus88 words, in the same order. Keep the three words in
    registers for this block; no other UGen runs inside the sample loop. */
 uint32_t r0=v->random[0],r1=v->random[1],r2=v->random[2];
 for(j=0;j<count;j++){
  r0=((r0&~1u)<<12)^(((r0<<13)^r0)>>19);
  r1=((r1&~7u)<<4)^(((r1<<2)^r1)>>25);
  r2=((r2&~15u)<<17)^(((r2<<3)^r2)>>11);
  uint32_t bits=0x3f800000u|((r0^r1^r2)>>9);float r;memcpy(&r,&bits,4);r-=1.0f;
  float z=r<threshold?r*scale-offset:0;checked_signal(v,out+j,z);
 }
 v->random[0]=r0;v->random[1]=r1;v->random[2]=r2;
 s->initialized=1;''')
    if not optimize_kernels:  # Reproducible pre-optimization oracle, tests only.
        fast=(SOURCE/'fm_fast.inc').read_text();extensions=(SOURCE/'fm_extensions.inc').read_text()
    miverb=(SOURCE/'fm_miverb.inc').read_text()
    if optimize_miverb:
        before='x=fminf(32767.0f/32768.0f,fmaxf(-1.0f,x));'
        assert miverb.count(before)==1
        # The preceding isfinite guard has already mapped invalid x to zero.
        # Nonzero bounds preserve signed zero; retain the original accumulator
        # scaling and exact float-to-int quantisation, including saturation.
        miverb=miverb.replace(before,'''/* Ordered comparisons avoid two library calls per delay write.
  * x is finite here; keep the same inclusive Q1.15 saturation bounds. */
 if(x < -1.0f)x=-1.0f;
 else if(x > 32767.0f/32768.0f)x=32767.0f/32768.0f;''')
    bandlimited=(SOURCE/'fm_bandlimited.inc').read_text()
    if optimize_miverb and optimize_miverb_packed:miverb=packed_miverb(miverb)
    if optimize_saw:
        before='float out,blip,t=(float)j/count;'
        assert bandlimited.count(before)==1
        # render_graph uses FM_BLOCK frames or a one-sample pass (j == 0).
        # FM_BLOCK is 64: the reciprocal is exact and preserves the crossfade.
        bandlimited=bandlimited.replace(before,'''/* Avoid software division in the sample loop. A one-sample pass
   * has j == 0, so it also produces the original zero fraction. */
  float out,blip,t=(float)j*(1.0f/FM_BLOCK);''')
    render,dsp=prepare_dsp(render,optimize_filters,optimize_lag,optimize_unary)
    files={path.name:path.read_text() for path in SOURCE.iterdir() if path.suffix in ('.c','.h','.inc')}
    files['fm_dsp_kernels.inc']=dsp
    files.update({'fm_render.c':render,'fm_delay.inc':delay,'fm_gendy.inc':gendy,'fm_rings.inc':rings,
                  'fm_fast.inc':fast,'fm_extensions.inc':extensions,'fm_miverb.inc':miverb,'fm_bandlimited.inc':bandlimited})
    if reuse_buffers:
        header,load,files=prepare_signals(header,load,files,min(int(limits['FM_OUTPUTS'][1]),192))
    render=files['fm_render.c'];delay=files['fm_delay.inc']
    gendy=files['fm_gendy.inc'];rings=files['fm_rings.inc'];fast=files['fm_fast.inc']
    extensions=files['fm_extensions.inc'];miverb=files['fm_miverb.inc'];bandlimited=files['fm_bandlimited.inc']
    for path in SOURCE.iterdir():
        if path.suffix not in ('.c','.h','.inc'):continue
        data=header.encode() if path.name=='fm_synth.h' else load.encode() if path.name=='fm_load.c' else files[path.name].encode()
        destination=output/path.name
        if not destination.exists() or destination.read_bytes()!=data:destination.write_bytes(data)
    (output/'fm_dsp_kernels.inc').write_text(files['fm_dsp_kernels.inc'])
    (output/'fm_profile_render.inc').write_text(profile_renderer(render,delay))
    manifest={'profile':profile,'changes':{name:{'upstream':old,'target':new} for name,(old,new) in limits.items()},
              'block_kernels':{'filters':optimize_filters,'lag':optimize_lag,'unary':optimize_unary},
              'miverb_packed_words':optimize_miverb and optimize_miverb_packed,
              'dsp_kernels_sha256':hashlib.sha256((ROOT/'host/dsp_kernels.py').read_bytes()).hexdigest(),
              'signal_reuse':reuse_buffers,
              'signal_planner_sha256':hashlib.sha256((ROOT/'host/signal_buffers.py').read_bytes()).hexdigest(),
              'audio_buffers_max':min(int(limits['FM_OUTPUTS'][1]),192) if reuse_buffers else int(limits['FM_OUTPUTS'][1]),
              'signal_storage':'Loader-planned conservative audio lifetimes, independent scalar values; persistent logical IDs unchanged.' if reuse_buffers else 'Dedicated full vector for every logical output; comparison oracle.',
              'upstream_header_sha256':hashlib.sha256(source.encode()).hexdigest(),
              'target_header_sha256':hashlib.sha256(header.encode()).hexdigest(),
              'control_bus_extension':'32 caller-owned snapshot channels via In.kr; existing In.ar unchanged; missing channels read zero, invalid ranges fault/reject.',
              'target_load_sha256':hashlib.sha256(load.encode()).hexdigest(),
              'dynamic_banks':'DynKlank/DynKlang expand to Ringz/SinOsc; mixed-rate parameter inputs accepted with the existing SC sampling semantics; Ringz excitation rate remains checked.',
              'target_render_sha256':hashlib.sha256(render.encode()).hexdigest(),
              'binding_extension':'fm_bind_delay_precleared: same checked layout; caller clears arena incrementally',
              'target_delay_sha256':hashlib.sha256(delay.encode()).hexdigest(),
              'target_gendy_sha256':hashlib.sha256(gendy.encode()).hexdigest(),
              'target_rings_sha256':hashlib.sha256(rings.encode()).hexdigest(),
              'target_fast_sha256':hashlib.sha256(fast.encode()).hexdigest(),
              'target_extensions_sha256':hashlib.sha256(extensions.encode()).hexdigest(),
              'target_miverb_sha256':hashlib.sha256(miverb.encode()).hexdigest(),
              'miverb_optimized':optimize_miverb,
              'target_bandlimited_sha256':hashlib.sha256(bandlimited.encode()).hexdigest(),
              'saw_crossfade_optimized':optimize_saw,
              'saw_crossfade_optimization':'Exact j/64 reciprocal multiplication; constructor/control one-sample fraction remains zero.' if optimize_saw else 'Pinned Saw/Pulse crossfade division oracle for comparison.',
              'miverb_optimization':'Finite ordered Q1.15 write clamp; identical quantisation, fault handling and accumulator scaling.' if optimize_miverb else 'Pinned MiVerb clamp oracle for comparison.',
              'kernel_optimized':optimize_kernels,
              'kernel_optimization':'Exact cached sine increments; power-of-two Decay2 ramp division; independent coefficient caches; identical block-local Dust/Dust2 RNG.' if optimize_kernels else 'Pre-optimization oracle for native comparison.',
              'rings_startup':'Bound voices use rg_init_precleared after zeroed binding; standalone rg_init retains its original clear for independent oracle callers.',
              'gendy_fix':'Allow the allocated zero-valued Gendy3 closing segment after discarded sub-sample breakpoints; keep bounds checks beyond it.',
              'scope':'Checked capacities, control bus input, precleared binding, Gendy3 closing-segment fix and duplicate Rings clear removal and bit-preserving hot-kernel optimizations; no precision reduction or changes to existing DSP equations.'}
    (output.parent/'profile.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return output

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--profile',choices=PROFILES,default='compact')
    args=parser.parse_args();generate(args.output,args.profile)
