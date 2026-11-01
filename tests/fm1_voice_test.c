/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "instrument.h"
#include "patch_format.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static fm_graph graph;
static fm_voice direct_voice,pending_voice;
static fm_scratch scratch;
static unsigned char bytes[FM_FILE_BYTES+1];
int main(void)
{
    char path[4096],error[160];unsigned graphs=0,memory_graphs=0;
    while(fgets(path,sizeof path,stdin)) {
        path[strcspn(path,"\r\n")]=0;
        FILE *file=fopen(path,"rb");assert(file);
        size_t size=fread(bytes,1,sizeof bytes,file);fclose(file);
        if(!fm_load(&graph,bytes,size,error,sizeof error)) {fprintf(stderr,"%s: %s\n",path,error);return 1;}
        patch_meta meta={0};meta.graph_bytes=(uint32_t)size;
        if(!patch_validate(&graph,&meta,error)) {fprintf(stderr,"%s: %s\n",path,error);return 1;}
        uint32_t need=fm_delay_required(&graph,44100);assert(need!=UINT32_MAX);
        float *a=malloc(((size_t)need+2)*sizeof(float)),*b=malloc(((size_t)need+2)*sizeof(float));assert(a && b);
        for(uint32_t i=0;i<need+2;++i)a[i]=b[i]=77.5f;
        instrument direct,pending;
        assert(instrument_init(&direct,&graph,&direct_voice,&scratch,a+1,need,44100));
        assert(instrument_init(&pending,&graph,&pending_voice,&scratch,b+1,need,44100));
        pending.defer_note_render=1;
        inst_event on={INST_NOTE_ON,17,0},off={INST_NOTE_OFF,17,0};
        assert(instrument_apply(&direct,&on));assert(instrument_apply(&pending,&on));
        unsigned blocks=0;
        while(pending.preparing_memory || pending.deferred_blocks) {
            uint32_t previous=pending.arena_cleared;float out[FM_BLOCK*2];
            instrument_render_stereo(&pending,out);
            for(unsigned j=0;j<FM_BLOCK*2;++j)assert(out[j]==0);
            assert(pending.arena_cleared-previous<=1024);
            assert(++blocks<=FM_DELAY_LIMIT/1024+2);
            assert(pending.voice->blocks==0);
        }
        assert(!memcmp(a,b,((size_t)need+2)*sizeof(float)));
        unsigned render_blocks=need==FM_DELAY_LIMIT?(6*44100+FM_BLOCK-1)/FM_BLOCK:16;
        for(unsigned block=0;block<render_blocks;++block) {
            float x[FM_BLOCK*2],y[FM_BLOCK*2];
            instrument_render_stereo(&direct,x);instrument_render_stereo(&pending,y);
            for(unsigned j=0;j<FM_BLOCK*2;++j)assert(isfinite(x[j]) && x[j]==y[j]);
        }
        assert(!direct.voice->fault && !pending.voice->fault);
        assert(!memcmp(a,b,((size_t)need+2)*sizeof(float)));
        assert(!memcmp(direct_voice.state,pending_voice.state,sizeof direct_voice.state));
        assert(a[0]==77.5f && a[need+1]==77.5f && b[0]==77.5f && b[need+1]==77.5f);
        if(need) {
            ++memory_graphs;
            /* A release or Panic during clearing cancels construction. A new
             * note restarts clearing and cannot inherit a previous tail. */
            assert(instrument_apply(&pending,&on));assert(pending.preparing_memory);
            assert(instrument_apply(&pending,&off));assert(!pending.held && !pending.preparing_memory && !pending.voice->active);
            assert(instrument_apply(&pending,&on));instrument_panic(&pending);
            assert(!pending.preparing_memory && !pending.voice->active);
            assert(fm_start(&pending_voice,&graph,44100));
            assert(!fm_bind_delay_precleared(&pending_voice,&graph,b+1,need-1));
            assert(!fm_bind_delay_precleared(&pending_voice,&graph,NULL,need));
        }
        instrument_panic(&direct);instrument_panic(&pending);
        free(a);free(b);++graphs;
    }
    printf("{\"passed\":true,\"graphs\":%u,\"memory_graphs\":%u,\"minimum_compared_frames_per_graph\":1024,\"full_arena_seconds\":6}\n",graphs,memory_graphs);
    return 0;
}
