/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "patch_format.h"
#include "instrument.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
static fm_graph graph;
static fm_voice voice;
static fm_scratch scratch;
static instrument synth;
static void load(const char *path)
{
    unsigned char bytes[FM_FILE_BYTES];char error[160];
    FILE *f=fopen(path,"rb");assert(f);
    size_t n=fread(bytes,1,sizeof bytes,f);assert(!ferror(f));fclose(f);
    assert(fm_load(&graph,bytes,n,error,sizeof error));
}
int main(int argc,char **argv)
{
    assert(argc==7);const unsigned rates[]={16000,44100,48000};
    patch_meta meta={.flags=PATCH_DEFINITION};char error[160];unsigned cases=0;
    for(int p=1;p<argc;++p) {
        load(argv[p]);fm_node *osc=&graph.node[0];
        assert(osc->type==FM_LFPar || osc->type==FM_LFCub || osc->type==FM_VarSaw);
        unsigned frequency=graph.ref[osc->input].output;
        for(unsigned r=0;r<3;++r) {
            float maximum=(float)rates[r]/(osc->rate==2?2.0f:2.0f*FM_BLOCK);
            float values[]={-.005f,-0.0f,0,.1f,maximum,nextafterf(maximum,INFINITY)};
            for(unsigned v=0;v<sizeof values/sizeof *values;++v) {
                graph.constant[frequency]=values[v];int valid=v>0 && v<5;
                assert(patch_validate_at_rate(&graph,&meta,rates[r],error)==valid);
                if(!valid)assert(strstr(error,fm_type_name(osc->type)) && strstr(error,"node 0"));
                assert(patch_validate_master_at_rate(&graph,&meta,rates[r],error)==valid);
                assert(fm_start(&voice,&graph,rates[r]));assert(fm_bind_delay(&voice,&graph,NULL,0));
                fm_prepare(&graph,&voice,&scratch);
                assert((!voice.fault)==valid);++cases;
            }
            /* Legal signed initial phases are not mistaken for frequencies. */
            graph.constant[frequency]=.1f;
            graph.constant[graph.ref[osc->input+1].output]=-.02f;
            assert(patch_validate_at_rate(&graph,&meta,rates[r],error));
            assert(fm_start(&voice,&graph,rates[r]));assert(fm_bind_delay(&voice,&graph,NULL,0));
            fm_prepare(&graph,&voice,&scratch);assert(!voice.fault);
        }
    }
    /* Reproduce the actual initializer path: a negative LFPar literal makes
     * instrument_arm_bus fail synchronously, without any task timeout. */
    load(argv[1]);graph.constant[graph.ref[graph.node[0].input].output]=-.0025f;
    assert(instrument_init_definition(&synth,&graph,&voice,&scratch,NULL,0,16000,1));
    synth.defer_note_render=1;
    assert(!instrument_arm_bus(&synth) && voice.fault);
    assert(!patch_validate_at_rate(&graph,&meta,16000,error));
    puts(error);
    printf("PASS: %u audio/control-rate domain cases; Main/FX guards match prepare at 16/44.1/48k; signed phase retained; startup failure reproduced\n",cases);
}
