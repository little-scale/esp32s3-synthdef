/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "fm_synth.h"
#include <stdio.h>
int main(void)
{
    printf("{\"graph_bytes\":%zu,\"voice_bytes\":%zu,\"scratch_bytes\":%zu,\"block_frames\":%d,\"types\":[",
           sizeof(fm_graph), sizeof(fm_voice), sizeof(fm_scratch), FM_BLOCK);
    for (unsigned i = 0; i < FM_TYPES; ++i) printf("%s\"%s\"", i ? "," : "", fm_type_name(i));
    puts("]}");
    return 0;
}
