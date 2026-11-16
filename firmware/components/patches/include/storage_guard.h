/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stddef.h>
#include <stdbool.h>
#include <stdint.h>

/* A failed filesystem mount is not permission to erase another app's data. */
typedef bool (*patch_storage_read)(void *, size_t, void *, size_t);
static inline bool patch_storage_erased(patch_storage_read read, void *context,
                                        size_t bytes, unsigned char *scratch, size_t capacity)
{
    if(!read || !bytes || !scratch || !capacity)return false;
    size_t offset=0;
    while(offset<bytes){
        size_t count=bytes-offset;if(count>capacity)count=capacity;
        if(!read(context,offset,scratch,count))return false;
        for(size_t i=0;i<count;++i)if(scratch[i]!=UINT8_MAX)return false;
        offset+=count;
    }
    return true;
}
