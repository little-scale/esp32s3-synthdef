/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "patch_format.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>
/* A deterministic injected digest tests record plumbing; the target exercises
 * the actual mbedTLS SHA-256 implementation with host-generated manifests. */
static int digest(const void *p,size_t n,unsigned char out[32])
{ uint32_t crc=patch_crc32(p,n);for(unsigned i=0;i<32;++i)out[i]=(unsigned char)(crc>>(8*(i%4)));return 1; }
static fm_graph graph;
static unsigned char blob[PATCH_BLOB_BYTES],readback[PATCH_BLOB_BYTES],record[PATCH_BLOB_BYTES+184];
static char error[160];
static void write_bytes(const char *path,const void *p,size_t n)
{ FILE *f=fopen(path,"wb");assert(f);assert(fwrite(p,1,n,f)==n);assert(!fclose(f)); }
int main(int argc,char **argv)
{
    assert(argc==3);
    FILE *f=fopen(argv[1],"rb");assert(f);size_t bytes=fread(blob,1,FM_FILE_BYTES,f);fclose(f);
    assert(fm_load(&graph,blob,bytes,error,sizeof error));
    patch_meta m={.transfer=123,.graph_bytes=(uint32_t)bytes,.source_bytes=6,.mapping=1};
    strcpy(m.name,"Test Sine");for(unsigned k=0;k<4;++k)strcpy(m.label[k],"PARAM");
    memcpy(blob+bytes,"// hi\n",6);digest(blob,bytes,m.graph_hash);digest(blob+bytes,6,m.source_hash);
    assert(patch_validate(&graph,&m,error));assert(patch_verify(&m,blob,digest,error));
    graph.node[graph.nodes]=graph.node[0];graph.node[graph.nodes].rate=0;++graph.nodes;
    assert(!patch_validate(&graph,&m,error));--graph.nodes;
    unsigned char meta[160];patch_meta decoded;patch_meta_encode(&m,meta);
    assert(patch_meta_decode(meta,sizeof meta,&decoded,error));assert(!memcmp(&m,&decoded,sizeof m));
    for(unsigned i=0;i<160;++i)assert(!patch_meta_decode(meta,i,&decoded,error));
    meta[156]=2;assert(!patch_meta_decode(meta,sizeof meta,&decoded,error));meta[156]=1;
    meta[76]='"';assert(!patch_meta_decode(meta,sizeof meta,&decoded,error));meta[76]='T';
    patch_put32(meta+4,65537);assert(!patch_meta_decode(meta,sizeof meta,&decoded,error));
    blob[bytes]=0xff;digest(blob+bytes,6,m.source_hash);assert(!patch_verify(&m,blob,digest,error));
    blob[bytes]='/';digest(blob+bytes,6,m.source_hash);
    blob[0]^=1;assert(!patch_verify(&m,blob,digest,error));blob[0]^=1;
    uint8_t type=graph.node[1].type;graph.node[1].type=FM_WhiteNoise;
    assert(!patch_validate(&graph,&m,error));graph.node[1].type=type;
    float default_value=graph.defaults[0];graph.defaults[0]=0;
    assert(!patch_validate(&graph,&m,error));graph.defaults[0]=default_value;
    for(size_t n=0;n<=PATCH_FRAME_PAYLOAD;++n) {
        char line[PATCH_FRAME_BYTES],op[16];unsigned char payload[PATCH_FRAME_PAYLOAD];size_t count=sizeof payload;
        uint32_t id=0;size_t len=patch_frame_encode(0x1234abcd,"DATA",blob,n,line,sizeof line);assert(len>0);
        assert(patch_frame_decode(line,&id,op,payload,&count,error));
        assert(id==0x1234abcd && !strcmp(op,"DATA") && count==n && !memcmp(payload,blob,n));
        line[len-2]=line[len-2]=='0'?'1':'0';count=sizeof payload;
        assert(!patch_frame_decode(line,&id,op,payload,&count,error));
    }
    assert(patch_record_write(argv[2],&m,2,blob,error));
    f=fopen(argv[2],"rb");assert(f);size_t record_bytes=fread(record,1,sizeof record,f);fclose(f);
    uint32_t generation=0;
    assert(patch_record_read(argv[2],&decoded,&generation,readback,sizeof readback,digest,error));assert(generation==2);
    /* Every byte boundary of an interrupted generation must be rejected. A
     * caller can then retain the other independently validated generation. */
    for(size_t cut=0;cut<record_bytes;++cut) {
        write_bytes(argv[2],record,cut);
        assert(!patch_record_read(argv[2],&decoded,&generation,readback,sizeof readback,digest,error));
    }
    for(size_t at=0;at<record_bytes;++at) {
        record[at]^=1;write_bytes(argv[2],record,record_bytes);
        assert(!patch_record_read(argv[2],&decoded,&generation,readback,sizeof readback,digest,error));record[at]^=1;
    }
    write_bytes(argv[2],record,record_bytes);
    assert(patch_record_read(argv[2],&decoded,&generation,readback,sizeof readback,digest,error));
    assert(generation==2 && !memcmp(readback,blob,bytes+6));remove(argv[2]);
    printf("PASS: 513 frame sizes/CRC rejection, manifest bounds, admission, digest/UTF-8, %zu truncated and %zu corrupt generations rejected\n",record_bytes,record_bytes);
}
