/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stddef.h>
#include <stdint.h>
#define PG_NODES 256
#define PG_REFS 2048
#define PG_SYMBOLS 64
#define PG_LIST 32
#define PG_DEPTH 24
#define PG_ARRAY_VALUES 256
#define PG_FIELDS 32
#define PG_BUDGET 4096
enum {PG_NUMBER,PG_SYMBOL,PG_ARRAY,PG_REST,PG_EVENT};
/* Arrays reference a bounded VM-owned pool; never allocate on next(). */
typedef struct {double number;uint16_t at;uint8_t kind,count;} pg_value;
typedef struct {uint16_t key;pg_value value;} pg_field;
typedef struct {pg_field field[PG_FIELDS];unsigned count,rest;} pg_event;
typedef struct {uint8_t op,argc;uint16_t first,special;double number;} pg_node;
typedef struct {
    uint64_t emitted,cycles;double current,limit;
    pg_value cached;
    uint32_t rng;uint16_t index,last,remaining,array_at,event_at;
    uint8_t initialized,active,ended,integer,order[PG_LIST];
} pg_state;
typedef struct {
    pg_node node[PG_NODES];pg_state state[PG_NODES];uint16_t ref[PG_REFS];
    char symbol[PG_SYMBOLS][64];pg_value arrays[PG_ARRAY_VALUES];
    pg_value scratch[PG_DEPTH+2];pg_event event;
    pg_event event_cache[8];unsigned event_caches;
    uint16_t nodes,refs,symbols,root,flags,arrays_used;
    uint32_t random,budget;double tempo,beat,start_beat;
    unsigned char graph_hash[32];char error[128];uint64_t events,steps;
} pg_vm;
/* Decode into an inactive caller-owned VM. Returns 0 with a fixed error string. */
int pg_load(pg_vm *,const void *,size_t);
void pg_reset(pg_vm *,uint32_t seed);
/* Returns 1 event, 0 natural end, -1 fault. Input beat is absolute program beats. */
int pg_next(pg_vm *,double beat,pg_event *);
int pg_next_value(pg_vm *,double beat,pg_value *);
int pg_find(const pg_vm *,const char *);
const pg_value *pg_get(const pg_vm *,const pg_event *,const char *);
/* Shared numerical evaluator used by the host reference harness too. */
double pg_number(const pg_value *);
