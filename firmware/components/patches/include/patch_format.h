/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include "fm_synth.h"
#include <stdio.h>
#define PATCH_META_BYTES 160u
#define PATCH_SOURCE_BYTES 65536u
#define PATCH_BLOB_BYTES (FM_FILE_BYTES + PATCH_SOURCE_BYTES)
#define PATCH_SLOTS 1
#define PATCH_FRAME_PAYLOAD 512u
#define PATCH_FRAME_BYTES 1100u
#define PATCH_DEFINITION 1u
typedef int (*patch_hash_fn)(const void *, size_t, unsigned char[32]);
typedef struct {
    uint32_t transfer, graph_bytes, source_bytes;
    unsigned char graph_hash[32], source_hash[32];
    char name[32], label[4][12];
    unsigned char mapping,flags;
} patch_meta;
uint32_t patch_get32(const unsigned char *p);
void patch_put32(unsigned char *p,uint32_t value);
uint32_t patch_crc32(const void *p,size_t size);
int patch_meta_decode(const void *,size_t,patch_meta *,char error[160]);
void patch_meta_encode(const patch_meta *,unsigned char out[PATCH_META_BYTES]);
int patch_validate(const fm_graph *,const patch_meta *,char error[160]);
int patch_validate_master(const fm_graph *,const patch_meta *,char error[160]);
int patch_verify(const patch_meta *,const unsigned char *,patch_hash_fn,char error[160]);
int patch_record_read(const char *,patch_meta *,uint32_t *,unsigned char *,size_t,patch_hash_fn,char error[160]);
int patch_record_write(const char *,const patch_meta *,uint32_t,const unsigned char *,char error[160]);
int patch_frame_decode(const char *,uint32_t *,char op[16],unsigned char *,size_t *,char error[160]);
size_t patch_frame_encode(uint32_t,const char *,const void *,size_t,char *,size_t);
