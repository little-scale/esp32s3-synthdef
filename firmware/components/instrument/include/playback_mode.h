/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include "fm_synth.h"
#include <string.h>
/* A scalar compile-time marker, not a control bus or a playing gate.
 * Return -1 for a malformed reserved marker, 0 for normal patches, 1 for autoplay. */
static inline int graph_continuous_mode(const fm_graph *g)
{
    if(!g || !g->valid)return 0;
    int found=0;
    for(unsigned i=0;i<g->names;++i)if(!strcmp(g->control_name[i].name,"__esp32_autoplay")) {
        unsigned index=g->control_name[i].index;int scalar=0;
        if(found || index>=g->controls || g->defaults[index]!=1)return -1;
        for(unsigned j=0;j<g->nodes;++j){
            const fm_node *n=&g->node[j];
            if(n->type==FM_Control && n->special>=0 && index>=(unsigned)n->special && index<(unsigned)n->special+n->outputs){
                if(n->rate!=0)return -1;
                scalar=1;
            }
        }
        if(!scalar)return -1;
        found=1;
    }
    return found;
}
