/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "sc_source.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
static void token(const char *text,unsigned color)
{
    size_t n=strlen(text);uint8_t style[256];assert(n<sizeof style);sc_source_highlight(text,n,style);
    for(size_t i=0;i<n;++i)assert(style[i]==color);
}
int main(void)
{
    token("SinOsc",SC_CLASS);token("Pbind",SC_CLASS);token("Pseq",SC_CLASS);token("Out",SC_CLASS);
    token("var",SC_KEYWORD);token("arg",SC_KEYWORD);token("variable",SC_TEXT);token("argument",SC_TEXT);
    token("~global_1",SC_GLOBAL);token("~caf\xc3\xa9",SC_GLOBAL);
    token("\\symbol_123",SC_STRING);token("'var SinOsc ~global 123'",SC_STRING);
    token("\"escaped \\\" quote #0000ff text#\"",SC_STRING);token("$a",SC_STRING);token("$\\n",SC_STRING);
    token("123",SC_NUMBER);token("12.5",SC_NUMBER);token(".125",SC_NUMBER);token("1.2e-3",SC_NUMBER);
    token("16rFF",SC_NUMBER);token("2pi",SC_NUMBER);token("inf",SC_NUMBER);token("nil",SC_NUMBER);
    token("0x29A",SC_NUMBER);token("12r4A.ABC",SC_NUMBER);token("2ssss",SC_NUMBER);
    {uint8_t range[5];sc_source_highlight("1..10",5,range);assert(range[0]==SC_NUMBER && range[1]==SC_TEXT && range[2]==SC_TEXT && range[3]==SC_NUMBER);}
    token("// var SinOsc 123",SC_COMMENT);token("/* nested /* SinOsc */ end */",SC_COMMENT);
    token("/* unfinished",SC_COMMENT);token("\"unfinished",SC_STRING);
    const char *mixed="var x=SinOsc.ar(440); // \\a\r\n~x='symbol';";
    uint8_t style[128];sc_source_highlight(mixed,strlen(mixed),style);
    assert(style[0]==SC_KEYWORD && style[6]==SC_CLASS && style[13]==SC_TEXT);
    const char *number=strstr(mixed,"440");assert(style[number-mixed]==SC_NUMBER);
    const char *global=strstr(mixed,"~x");assert(style[global-mixed]==SC_GLOBAL);
    size_t offset=0;assert(sc_source_codepoint("\xcf\x80",2,&offset)==0x3c0 && offset==2);
    offset=0;assert(sc_source_codepoint("\xf0",1,&offset)==0xfffd && offset==1);
    unsigned state=12345;
    size_t page=(size_t)sysconf(_SC_PAGESIZE),capacity=(SC_SOURCE_MAX+page-1)/page*page;
    unsigned char *input=mmap(NULL,capacity+2*page,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0);
    unsigned char *output=mmap(NULL,capacity+2*page,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0);
    assert(input!=MAP_FAILED && output!=MAP_FAILED);
    assert(!mprotect(input,page,PROT_NONE) && !mprotect(input+page+capacity,page,PROT_NONE));
    assert(!mprotect(output,page,PROT_NONE) && !mprotect(output+page+capacity,page,PROT_NONE));
    for(unsigned trial=0;trial<1000;++trial){
        size_t n=trial==999?SC_SOURCE_MAX:(state%SC_SOURCE_MAX);
        unsigned char *bytes=input+page+capacity-n,*colors=output+page+capacity-n;
        for(size_t i=0;i<n;++i){state=1664525u*state+1013904223u;bytes[i]=(unsigned char)(state>>24);}
        sc_source_highlight((const char *)bytes,n,colors);
        offset=0;while(offset<n){size_t previous=offset;sc_source_codepoint((const char *)bytes,n,&offset);assert(offset>previous && offset<=n);}
    }munmap(input,capacity+2*page);munmap(output,capacity+2*page);
    puts("Source lexer: token boundaries, escapes, nested comments, UTF-8, markup literals and 1000 guarded fuzz cases passed");
}
