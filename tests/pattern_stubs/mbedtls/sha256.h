#pragma once
#include <CommonCrypto/CommonDigest.h>
static inline int mbedtls_sha256(const unsigned char *p,size_t size,unsigned char out[32],int variant){
 (void)variant;return CC_SHA256(p,(CC_LONG)size,out)?0:-1;
}
