/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include "patch_format.h"
#include <stdbool.h>
typedef struct {
    unsigned iram_bytes, dram_bytes;
    unsigned app_bytes, partition_bytes;
} patch_program_usage;

typedef struct {
    int (*pause)(bool);
    int (*activate)(fm_graph *);
    int (*define)(fm_graph *,bool start);
    int (*stop)(void);
    int (*master_activate)(fm_graph *);
    int (*master_define)(fm_graph *,bool start);
    int (*instance)(bool start,const unsigned char *,size_t);
    void (*master_display)(const char *,int);
    void (*display)(const patch_meta *,const fm_graph *,const char names[PATCH_SLOTS+1][32],int slot,const char *source,size_t source_bytes);
    void (*busy)(bool,const char *);
    int (*effect)(const float *,float[3]);
    int (*effect_save)(void);
    int (*volume)(int percent,bool save);
    int (*identify)(void);
    uint32_t (*seed)(void);
    int (*remote)(const char *,const unsigned char *,size_t,char *,size_t);
    bool (*console_write)(const char *,size_t);
    const char *build_id,*engine_commit,*profile_hash;
    patch_program_usage program;
} patch_hooks;
int patches_init(fm_graph *first,fm_graph *spare,const void *factory,size_t bytes,const patch_hooks *hooks);
void patches_restore(bool factory_only);
void patches_line(const char *line);
void patches_exchange(const char *line,char *reply,size_t size);
void patches_tick(void);
bool patches_request(unsigned slot,bool save);
void patches_publish(void);
int patches_master_init(fm_graph *,fm_graph *,const void *,size_t,const char *,size_t);
void patches_master_restore(bool factory_only);
bool patches_master_request(unsigned slot);
