/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "sc_source.h"
#include <string.h>
static int digit(unsigned c){return c>='0' && c<='9';}
static int hex_digit(unsigned c){return digit(c) || (c>='a' && c<='f') || (c>='A' && c<='F');}
static int radix_fraction(unsigned c){return digit(c) || (c>='A' && c<='Z');}
static int letter(unsigned c){return (c>='a' && c<='z') || (c>='A' && c<='Z') || c=='_';}
static int word(unsigned c){return letter(c) || digit(c) || c>=128;}
static int equal(const char *p,size_t n,const char *word){return strlen(word)==n && !memcmp(p,word,n);}
uint32_t sc_source_color(unsigned style)
{
    static const uint32_t palette[]={0x000000,0x008000,0x0000D2,0xD05F00,0xBF0000,0x800080,0xBF0000};
    return palette[style<sizeof palette/sizeof *palette?style:SC_TEXT];
}
uint32_t sc_source_codepoint(const char *p,size_t n,size_t *offset)
{
    size_t i=*offset;if(i>=n)return 0;
    uint32_t c=(unsigned char)p[i++];unsigned more=0;uint32_t minimum=0;
    if(c>=0xc2 && c<=0xdf){more=1;minimum=128;c&=31;}
    else if(c>=0xe0 && c<=0xef){more=2;minimum=2048;c&=15;}
    else if(c>=0xf0 && c<=0xf4){more=3;minimum=65536;c&=7;}
    else if(c>=128){*offset=i;return 0xfffd;}
    if(n-i<more){*offset=i;return 0xfffd;}
    for(unsigned j=0;j<more;++j){unsigned b=(unsigned char)p[i+j];if((b&0xc0)!=0x80){*offset=i;return 0xfffd;}c=(c<<6)|(b&63);}
    i+=more;*offset=i;
    return c<minimum || c>0x10ffff || (c>=0xd800 && c<=0xdfff)?0xfffd:c;
}
void sc_source_highlight(const char *p,size_t n,uint8_t *styles)
{
    if(!n)return;
    memset(styles,SC_TEXT,n);
    for(size_t i=0;i<n;){
        size_t start=i;unsigned c=(unsigned char)p[i++],kind=SC_TEXT;
        if(c=='/' && i<n && p[i]=='/'){
            ++i;while(i<n && p[i]!='\r' && p[i]!='\n')++i;kind=SC_COMMENT;
        }else if(c=='/' && i<n && p[i]=='*'){
            ++i;unsigned depth=1;
            while(i<n && depth){
                if(i+1<n && p[i]=='/' && p[i+1]=='*'){++depth;i+=2;}
                else if(i+1<n && p[i]=='*' && p[i+1]=='/'){--depth;i+=2;}
                else ++i;
            }kind=SC_COMMENT;
        }else if(c=='"' || c=='\''){
            while(i<n){unsigned b=(unsigned char)p[i++];if(b=='\\' && i<n)++i;else if(b==c)break;}kind=SC_STRING;
        }else if(c=='\\'){
            while(i<n && word((unsigned char)p[i]))++i;
            kind=SC_STRING;
        }else if(c=='$'){
            if(i<n){if(p[i]=='\\' && i+1<n)++i;sc_source_codepoint(p,n,&i);}kind=SC_STRING;
        }else if(c=='~' && i<n && (letter((unsigned char)p[i]) || (unsigned char)p[i]>=128)){
            while(i<n && word((unsigned char)p[i]))++i;
            kind=SC_GLOBAL;
        }else if(digit(c) || (c=='.' && i<n && digit((unsigned char)p[i]) && (!start || p[start-1]!='.'))){
            if(c=='0' && i+1<n && p[i]=='x' && hex_digit((unsigned char)p[i+1])){
                i+=2;while(i<n && hex_digit((unsigned char)p[i]))++i;
                memset(styles+start,SC_NUMBER,i-start);continue;
            }
            while(i<n && digit((unsigned char)p[i]))++i;
            if(i<n && p[i]=='r'){
                ++i;while(i<n && word((unsigned char)p[i]))++i;
                if(i+1<n && p[i]=='.' && radix_fraction((unsigned char)p[i+1])){
                    i+=2;while(i<n && radix_fraction((unsigned char)p[i]))++i;
                }
            }else{
                if(c!='.' && i+1<n && p[i]=='.' && digit((unsigned char)p[i+1])){++i;while(i<n && digit((unsigned char)p[i]))++i;}
                if(i<n && (p[i]=='e' || p[i]=='E')){
                    size_t exponent=i+1;if(exponent<n && (p[exponent]=='+' || p[exponent]=='-'))++exponent;
                    if(exponent<n && digit((unsigned char)p[exponent])){i=exponent+1;while(i<n && digit((unsigned char)p[i]))++i;}
                }
                if(i+1<n && p[i]=='p' && p[i+1]=='i' && (i+2==n || !word((unsigned char)p[i+2])))i+=2;
                if(i<n && (p[i]=='s' || p[i]=='b')){
                    size_t suffix=i;while(suffix<n && suffix-i<4 && p[suffix]==p[i])++suffix;
                    if(suffix==n || !word((unsigned char)p[suffix]))i=suffix;
                }
            }kind=SC_NUMBER;
        }else if(letter(c) || c>=128){
            while(i<n && word((unsigned char)p[i]))++i;
            if(c>='A' && c<='Z')kind=SC_CLASS;
            else if(equal(p+start,i-start,"arg") || equal(p+start,i-start,"var"))kind=SC_KEYWORD;
            else if(equal(p+start,i-start,"inf") || equal(p+start,i-start,"nil") || equal(p+start,i-start,"true") || equal(p+start,i-start,"false") || equal(p+start,i-start,"pi"))kind=SC_NUMBER;
        }
        memset(styles+start,kind,i-start);
    }
}
