/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "trace_probe.h"
#include <assert.h>
#include <stdio.h>
static fm_graph graph;
static fm_voice voice;
static fm_scratch scratch;
static float arena[FM_DELAY_LIMIT+2],capture[TRACE_FLOATS];
int main(int argc,char **argv)
{
    assert(argc==3);unsigned char bytes[FM_FILE_BYTES+1];char error[256];
    FILE *f=fopen(argv[1],"rb");assert(f);size_t n=fread(bytes,1,sizeof bytes,f);fclose(f);
    if(!fm_load(&graph,bytes,n,error,sizeof error)){fprintf(stderr,"%s\n",error);return 1;}
    trace_summary s;int passed=trace_probe(&graph,&voice,&scratch,arena,FM_DELAY_LIMIT+2,capture,&s,NULL,NULL);
    f=fopen(argv[2],"wb");assert(f);assert(fwrite(capture,sizeof(float),TRACE_FLOATS,f)==TRACE_FLOATS);assert(!fclose(f));
    printf("{\"passed\":%s,\"blocks\":%u,\"faults\":%u,\"nonfinite\":%u,\"guards\":%u,\"updates\":%u,\"rejected\":%u,\"initial_rejections\":%u,\"initial_accepts\":%u,\"restarts\":%u,\"peak\":%.9g,\"rms\":%.9g}\n",passed?"true":"false",s.blocks,s.faults,s.nonfinite,s.guard_failures,s.event_updates,s.event_rejections,s.initial_rejections,s.unexpected_initial_accepts,s.restarts,s.peak,s.rms);
    return passed?0:1;
}
