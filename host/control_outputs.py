"""Bounded reserved control outputs for physical LED adapters, not audio buses."""
def extend_control_outputs(header, load, render):
    before='#define FM_CONTROL_BUSES 32'
    assert header.count(before)==1
    header=header.replace(before,'#define FM_CONTROL_BUSES 68\n#define FM_CONTROL_OUTPUT_BASE 3\n#define FM_CONTROL_OUTPUTS 39')
    before=' uint32_t control_bus_count;'
    assert header.count(before)==1
    header=header.replace(before,before+'\n float control_outputs[FM_CONTROL_OUTPUTS];\n uint64_t control_output_mask;')
    start=load.index('  } else if(u->type==FM_Out) {')
    end=load.index('  } else {',start)
    audio=load[start:end]
    # Keep the original audio-output validation byte-for-byte in its branch.
    load=load[:start]+'''  } else if(u->type==FM_Out && u->rate==1) {
   if(u->outputs || u->inputs<2 || u->inputs>FM_CONTROL_OUTPUTS+1)BAD("Out.kr requires 1..39 control channels");
   if(literal(g,u,0,&v)){
    if(v<FM_CONTROL_OUTPUT_BASE || v>FM_CONTROL_OUTPUT_BASE+FM_CONTROL_OUTPUTS-(u->inputs-1) || floorf(v)!=v)BAD("Out.kr outside reserved output buses 3..41");
   }else{fm_ref *ref=&g->ref[u->input];if(g->node[ref->node].rate>1)BAD("Out.kr bus index requires initial/control rate");}
   for(j=1;j<u->inputs;j++){fm_ref *ref=&g->ref[u->input+j];if(ref->node>=0 && g->node[ref->node].rate>1)BAD("Out.kr requires initial/control signals");}
'''+audio+load[end:]
    before='  if(n->type==FM_Out) {'
    assert render.count(before)==1
    render=render.replace(before,'''  if(n->type==FM_Out && n->rate==1){
   float address=input(g,b,n,0,0);
   int valid=isfinite(address) && address>=FM_CONTROL_OUTPUT_BASE && address<=FM_CONTROL_OUTPUT_BASE+FM_CONTROL_OUTPUTS-(n->inputs-1) && floorf(address)==address;
   if(!valid){v->fault=1;continue;}
   if(initializing)continue;
   unsigned base=(unsigned)address-FM_CONTROL_OUTPUT_BASE;
   for(k=1;k<n->inputs;k++){
    unsigned at=base+k-1;
    checked_signal(v,&v->control_outputs[at],v->control_outputs[at]+input(g,b,n,k,0));
    v->control_output_mask|=UINT64_C(1)<<at;
   }
   continue;
  }
'''+before)
    before=''' if(!v->active || g->valid!=FM_VALID)return;
 fm_prepare(g,v,b);
 render_graph(g,v,b,stereo,0,input_stereo);'''
    assert render.count(before)==1
    render=render.replace(before,''' memset(v->control_outputs,0,sizeof v->control_outputs);v->control_output_mask=0;
 if(!v->active || g->valid!=FM_VALID)return;
 fm_prepare(g,v,b);
 render_graph(g,v,b,stereo,0,input_stereo);
 if(v->fault){memset(v->control_outputs,0,sizeof v->control_outputs);v->control_output_mask=0;}''')
    return header,load,render
