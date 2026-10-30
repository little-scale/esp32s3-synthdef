/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include "patch_format.h"
#include <stdbool.h>
typedef struct {
    int (*pause)(bool);
    int (*activate)(fm_graph *);
    void (*display)(const patch_meta *,const fm_graph *,const char names[PATCH_SLOTS+1][32],int slot);
    void (*busy)(bool,const char *);
    const char *build_id,*engine_commit,*profile_hash;
} patch_hooks;
int patches_init(fm_graph *first,fm_graph *spare,const void *factory,size_t bytes,const patch_hooks *hooks);
void patches_restore(bool factory_only);
void patches_line(const char *line);
void patches_tick(void);
bool patches_request(unsigned slot,bool save);
void patches_publish(void);
