#pragma once
#include <stdlib.h>
#define MALLOC_CAP_SPIRAM 1
#define MALLOC_CAP_8BIT 2
extern unsigned pg_alloc_fail;
static inline void *heap_caps_calloc(size_t n,size_t size,unsigned caps){
 (void)caps;if(pg_alloc_fail){--pg_alloc_fail;return NULL;}return calloc(n,size);
}
