/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "patch_format.h"
#include <assert.h>
#include <stdlib.h>
static fm_graph graph;
static unsigned char bytes[FM_FILE_BYTES+1];
int main(int argc,char **argv)
{
    assert(argc==4);char error[160];FILE *file=fopen(argv[1],"rb");assert(file);
    size_t size=fread(bytes,1,sizeof bytes,file);fclose(file);
    int loaded=fm_load(&graph,bytes,size,error,sizeof error),admitted=0;
    patch_meta meta={0};meta.graph_bytes=(uint32_t)size;
    if(loaded)admitted=patch_validate(&graph,&meta,error);
    if(!!loaded!=atoi(argv[2]) || !!admitted!=atoi(argv[3])) {
        fprintf(stderr,"load=%d admission=%d: %s\n",loaded,admitted,error);return 1;
    }
    return 0;
}
