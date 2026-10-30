/* SPDX-License-Identifier: GPL-3.0-or-later */
#define _POSIX_C_SOURCE 200809L
#include "patch_format.h"
#include <math.h>
#include <string.h>
#include <unistd.h>
#define PATCH_CATALOG_IMPLEMENTATION
#include "catalog_generated.h"
#ifdef ESP_PLATFORM
#include "sdkconfig.h"
#endif
#ifndef PATCH_ALLOW_CANDIDATES
#ifdef CONFIG_SYNTHDEF_DIAGNOSTICS
#define PATCH_ALLOW_CANDIDATES 1
#else
#define PATCH_ALLOW_CANDIDATES 0
#endif
#endif

uint32_t patch_get32(const unsigned char *p) { return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24; }
void patch_put32(unsigned char *p,uint32_t v) { for(unsigned i=0;i<4;++i)p[i]=(unsigned char)(v>>(8*i)); }
static uint32_t crc_update(uint32_t c,const void *data,size_t n)
{
    const unsigned char *p=data;
    while(n--) { c^=*p++; for(unsigned k=0;k<8;++k)c=(c>>1)^(0xedb88320u & (0u-(c&1))); }
    return c;
}
uint32_t patch_crc32(const void *p,size_t n) { return ~crc_update(UINT32_MAX,p,n); }
static int bad(char e[160],const char *message) { snprintf(e,160,"%s",message); return 0; }
static int field(const unsigned char *p,size_t n)
{
    size_t i=0;
    while(i<n && p[i]) { if(p[i]<32 || p[i]>126 || p[i]=='"' || p[i]=='\\')return 0; ++i; }
    if(!i || i==n)return 0;
    for(;i<n;++i)if(p[i])return 0;
    return 1;
}
int patch_meta_decode(const void *data,size_t n,patch_meta *m,char e[160])
{
    const unsigned char *p=data;
    if(n!=PATCH_META_BYTES)return bad(e,"Wrong manifest size");
    if(!field(p+76,32))return bad(e,"Invalid patch name");
    for(unsigned k=0;k<4;++k)if(!field(p+108+12*k,12))return bad(e,"Invalid control label");
    if(p[156]>1 || p[157] || p[158] || p[159])return bad(e,"Unknown UI mapping/schema flags");
    memset(m,0,sizeof *m);
    m->transfer=patch_get32(p); m->graph_bytes=patch_get32(p+4); m->source_bytes=patch_get32(p+8);
    if(!m->graph_bytes || m->graph_bytes>FM_FILE_BYTES || m->source_bytes>PATCH_SOURCE_BYTES)
        return bad(e,"Package length exceeds device limits");
    memcpy(m->graph_hash,p+12,32); memcpy(m->source_hash,p+44,32);
    memcpy(m->name,p+76,32); memcpy(m->label,p+108,48); m->mapping=p[156];
    return 1;
}
void patch_meta_encode(const patch_meta *m,unsigned char p[PATCH_META_BYTES])
{
    memset(p,0,PATCH_META_BYTES);
    patch_put32(p,m->transfer); patch_put32(p+4,m->graph_bytes); patch_put32(p+8,m->source_bytes);
    memcpy(p+12,m->graph_hash,32); memcpy(p+44,m->source_hash,32);
    memcpy(p+76,m->name,32); memcpy(p+108,m->label,48); p[156]=m->mapping;
}
static int utf8(const unsigned char *p,size_t n)
{
    while(n) {
        uint32_t c=*p++; --n; unsigned more; uint32_t minimum;
        if(c<128) { if(!c)return 0; continue; }
        if(c>=0xc2 && c<=0xdf) {more=1;minimum=128;c&=31;}
        else if(c>=0xe0 && c<=0xef) {more=2;minimum=2048;c&=15;}
        else if(c>=0xf0 && c<=0xf4) {more=3;minimum=65536;c&=7;}
        else return 0;
        if(n<more)return 0;
        n-=more;
        while(more--) { unsigned b=*p++; if((b&0xc0)!=0x80)return 0; c=(c<<6)|(b&63); }
        if(c<minimum || c>0x10ffff || (c>=0xd800 && c<=0xdfff))return 0;
    }
    return 1;
}
int patch_verify(const patch_meta *m,const unsigned char *blob,patch_hash_fn hash,char e[160])
{
    unsigned char sum[32];
    if(!hash(blob,m->graph_bytes,sum) || memcmp(sum,m->graph_hash,32))return bad(e,"Graph SHA-256 mismatch");
    if(!hash(blob+m->graph_bytes,m->source_bytes,sum) || memcmp(sum,m->source_hash,32))return bad(e,"Source SHA-256 mismatch");
    if(!utf8(blob+m->graph_bytes,m->source_bytes))return bad(e,"Source is not valid UTF-8 text");
    return 1;
}
int patch_validate(const fm_graph *g,const patch_meta *m,char e[160])
{
    /* Callers must hash-verify the raw bytes and parse them before this check.
     * Catalog matches are exact binaries, not a general UGen-family expansion. */
    const patch_catalog_entry *catalog=NULL;
    for(unsigned i=0;i<sizeof patch_catalog/sizeof patch_catalog[0];++i)
        if(!memcmp(m->graph_hash,patch_catalog[i].hash,32))catalog=&patch_catalog[i];
    if(catalog && (catalog->state==2 || (catalog->state==0 && !PATCH_ALLOW_CANDIDATES)))return bad(e,"Catalog graph is not qualified for this build");
    if(catalog && (g->nodes!=catalog->nodes || g->outputs!=catalog->signals || g->inputs!=catalog->inputs || m->graph_bytes!=catalog->bytes))return bad(e,"Catalog graph structure mismatch");
    if(g->nodes>(catalog?24:20) || g->outputs>32 || g->inputs>256 || fm_delay_required(g,44100)!=0)
        return bad(e,"simple-voice-v1: graph/memory budget exceeded");
    if(!catalog) {
    unsigned audio=0,sines=0,envs=0,powers=0,pans=0,outs=0;
    for(unsigned i=0;i<g->nodes;++i) {
        const fm_node *n=&g->node[i]; audio+=n->rate==2;
        switch(n->type) {
        case FM_Control: case FM_MulAdd: case FM_DC: break;
        case FM_Out: ++outs; break;
        case FM_Pan2: {
            ++pans;const fm_ref *r=&g->ref[n->input+1];
            if(r->node>=0 && g->node[r->node].rate==2)return bad(e,"Audio-rate panning outside upload policy");
            break;
        }
        case FM_SinOsc:
            ++sines;
            for(unsigned k=0;k<2;++k) {const fm_ref *r=&g->ref[n->input+k];
                if(r->node>=0 && g->node[r->node].rate==2)return bad(e,"Audio-rate oscillator modulation outside upload policy");}
            break;
        case FM_EnvGen:
            ++envs;
            if(n->inputs>25)return bad(e,"Envelope exceeds four segments");
            for(unsigned k=11;k<n->inputs;k+=4) {
                const fm_ref *shape=&g->ref[n->input+k],*curve=&g->ref[n->input+k+1];
                if(shape->node>=0 || curve->node>=0)return bad(e,"Envelope curves must be literal");
                float v=g->constant[shape->output],c=g->constant[curve->output];
                if((v!=0 && v!=1 && v!=5 && v!=8 && v!=9) || fabsf(c)>20)return bad(e,"Envelope curve outside upload policy");
            }
            break;
        case FM_BinaryOpUGen:
            if(n->special==25 && n->rate==1) { ++powers; break; }
            if(n->special==0 || n->special==1 || n->special==2 || n->special==4 || n->special==12 || n->special==13)break;
            return bad(e,"simple-voice-v1: unsupported operator/rate");
        default: snprintf(e,160,"simple-voice-v1: unsupported UGen %s",fm_type_name(n->type)); return 0;
        }
    }
    if(audio>8 || sines!=1 || envs!=1 || pans!=1 || outs!=1 || powers>1)return bad(e,"simple-voice-v1: voice complexity exceeded");
    }
    static const char *const required[]={"freq","amp","gate","knob1","knob2","knob3","knob4"};
    for(unsigned k=0;k<7;++k) {
        int found=0;
        for(unsigned i=0;i<g->names;++i)if(!strcmp(g->control_name[i].name,required[k])) {
            unsigned index=g->control_name[i].index; float v=g->defaults[index];
            if(k==0 ? v<20 || v>20000 : v<0 || v>1)return bad(e,"Control default outside supported range");
            for(unsigned j=0;j<g->nodes;++j) {
                const fm_node *n=&g->node[j];
                if(n->type==FM_Control && n->special>=0 && index>=(unsigned)n->special && index<(unsigned)n->special+n->outputs) {
                    if(n->rate==0)return bad(e,"Live control overlaps an initial-rate control");
                    if(n->rate==1)found=1;
                }
            }
        }
        if(!found) {snprintf(e,160,"Missing live control %s",required[k]);return 0;}
    }
    return 1;
}

int patch_record_write(const char *path,const patch_meta *m,uint32_t generation,const unsigned char *blob,char e[160])
{
    unsigned char header[16+PATCH_META_BYTES],tail[8];
    memcpy(header,"WSP1",4);patch_put32(header+4,1);patch_put32(header+8,generation);
    uint32_t total=m->graph_bytes+m->source_bytes;patch_put32(header+12,total);
    patch_meta_encode(m,header+16);
    memcpy(tail,"DONE",4);
    uint32_t crc=crc_update(UINT32_MAX,header,sizeof header);
    patch_put32(tail+4,~crc_update(crc,blob,total));
    FILE *f=fopen(path,"wb"); if(!f)return bad(e,"Cannot open patch generation");
    int ok=fwrite(header,1,sizeof header,f)==sizeof header && fwrite(blob,1,total,f)==total && fwrite(tail,1,sizeof tail,f)==sizeof tail;
    if(ok)ok=fflush(f)==0 && fsync(fileno(f))==0;
    if(fclose(f))ok=0;
    return ok?1:bad(e,"Patch save incomplete; previous generation retained");
}
int patch_record_read(const char *path,patch_meta *m,uint32_t *generation,unsigned char *blob,size_t cap,patch_hash_fn hash,char e[160])
{
    unsigned char h[16+PATCH_META_BYTES],tail[8]; FILE *f=fopen(path,"rb");
    if(!f)return bad(e,"Patch generation absent");
    int ok=fread(h,1,sizeof h,f)==sizeof h;
    if(ok)ok=!memcmp(h,"WSP1",4) && patch_get32(h+4)==1 && patch_meta_decode(h+16,PATCH_META_BYTES,m,e);
    size_t total=ok?(size_t)m->graph_bytes+m->source_bytes:0;
    if(ok)ok=total<=cap && total==patch_get32(h+12) && patch_get32(h+8)>0;
    if(ok)ok=fread(blob,1,total,f)==total && fread(tail,1,sizeof tail,f)==sizeof tail && fgetc(f)==EOF && !ferror(f);
    fclose(f);
    if(!ok)return bad(e,"Incomplete or invalid patch generation");
    uint32_t crc=crc_update(UINT32_MAX,h,sizeof h);
    if(memcmp(tail,"DONE",4) || patch_get32(tail+4)!=~crc_update(crc,blob,total))return bad(e,"Patch generation CRC mismatch");
    if(!patch_verify(m,blob,hash,e))return 0;
    *generation=patch_get32(h+8); return 1;
}
static int unhex(char c) {return c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:-1;}
int patch_frame_decode(const char *line,uint32_t *id,char op[16],unsigned char *payload,size_t *size,char e[160])
{
    size_t len=strlen(line); while(len && (line[len-1]=='\r'||line[len-1]=='\n'))--len;
    if(len<26 || len>=PATCH_FRAME_BYTES || memcmp(line,"@SD1 ",5))return bad(e,"Invalid frame header/length");
    uint32_t request=0,expected=0;
    for(unsigned i=0;i<8;++i) {int n=unhex(line[5+i]);if(n<0)return bad(e,"Invalid request ID");request=(request<<4)|(unsigned)n;}
    if(line[13]!=' ')return bad(e,"Invalid frame separator");
    size_t pos=14,k=0;
    while(pos<len && line[pos]!=' ') {if(k==15 || line[pos]<'A'||line[pos]>'Z')return bad(e,"Invalid operation");op[k++]=line[pos++];}
    op[k]=0; if(!k || pos>=len)return bad(e,"Missing operation/payload");
    size_t start=++pos; while(pos<len && line[pos]!=' ')++pos;
    size_t hexlen=pos-start;
    if(pos+9!=len)return bad(e,"Invalid frame checksum field");
    for(unsigned i=0;i<8;++i) {int n=unhex(line[pos+1+i]);if(n<0)return bad(e,"Invalid frame checksum");expected=(expected<<4)|(unsigned)n;}
    if(patch_crc32(line+5,pos-5)!=expected)return bad(e,"Frame CRC mismatch");
    size_t bytes=hexlen==1 && line[start]=='-'?0:hexlen/2;
    if(bytes>*size || (bytes && (hexlen%2)) || (!bytes && !(hexlen==1 && line[start]=='-')))return bad(e,"Invalid payload size");
    for(size_t i=0;i<bytes;++i) {int a=unhex(line[start+2*i]),b=unhex(line[start+2*i+1]);if(a<0||b<0)return bad(e,"Invalid payload hex");payload[i]=(unsigned char)((a<<4)|b);}
    *size=bytes;*id=request;return 1;
}
size_t patch_frame_encode(uint32_t id,const char *op,const void *data,size_t n,char *out,size_t cap)
{
    static const char hex[]="0123456789abcdef";const unsigned char *p=data;
    size_t need=5+8+1+strlen(op)+1+(n?2*n:1)+1+8+1+1;
    if(need>cap)return 0;
    int prefix=snprintf(out,cap,"@SD1 %08lx %s ",(unsigned long)id,op); if(prefix<0)return 0;
    size_t used=(size_t)prefix;
    if(n)for(size_t i=0;i<n;++i) {out[used++]=hex[p[i]>>4];out[used++]=hex[p[i]&15];}
    else out[used++]='-';
    uint32_t crc=patch_crc32(out+5,used-5);
    snprintf(out+used,cap-used," %08lx\n",(unsigned long)crc);
    return used+10;
}
