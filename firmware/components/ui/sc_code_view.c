/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "sc_code_view.h"
#include "sc_source.h"
#include "esp_heap_caps.h"
#include <stdio.h>
#include <string.h>
extern const lv_font_t sc_code_font;
enum { CELL=8,ROW=18 };
typedef struct {char *text;uint8_t *style;uint32_t *line;size_t bytes;uint32_t lines,columns;} document;
static document doc;
static lv_obj_t *area,*strips[2];
static int32_t scroll_x,scroll_y;
static bool strip_drag[2],failed;
static void dispose(document *d){heap_caps_free(d->text);heap_caps_free(d->style);heap_caps_free(d->line);memset(d,0,sizeof *d);}
static unsigned gutter(void){unsigned digits=1;for(uint32_t n=doc.lines;n>=10;n/=10)++digits;return digits*CELL+12;}
static void location(void)
{
    for(unsigned k=0;k<2;++k)if(strips[k])lv_obj_invalidate(strips[k]);
}
static void clamp_scroll(void)
{
    int32_t y=(int32_t)(doc.lines*ROW)-lv_obj_get_height(area);
    int32_t x=(int32_t)(doc.columns*CELL)-lv_obj_get_width(area)+(int32_t)gutter()+4;
    if(y<0)y=0;
    if(x<0)x=0;
    if(scroll_y<0)scroll_y=0;
    if(scroll_y>y)scroll_y=y;
    if(scroll_x<0)scroll_x=0;
    if(scroll_x>x)scroll_x=x;
}
static void draw(lv_event_t *event)
{
    lv_draw_ctx_t *ctx=lv_event_get_draw_ctx(event);lv_area_t bounds;
    lv_obj_get_coords(area,&bounds);
    if(!doc.bytes){
        lv_draw_label_dsc_t d;lv_draw_label_dsc_init(&d);d.font=&sc_code_font;d.color=lv_color_hex(0x555555);
        lv_area_t message={bounds.x1+16,bounds.y1+20,bounds.x2-12,bounds.y2};
        lv_draw_label(ctx,&d,&message,failed?"Source could not be loaded.":"This patch has no source text.",NULL);return;
    }
    unsigned margin=gutter();lv_draw_rect_dsc_t background;lv_draw_rect_dsc_init(&background);
    background.bg_color=lv_color_hex(0xF4F4F4);background.bg_opa=LV_OPA_COVER;background.radius=0;background.border_width=0;
    lv_area_t strip={bounds.x1,bounds.y1,bounds.x1+(lv_coord_t)margin-1,bounds.y2};lv_draw_rect(ctx,&background,&strip);
    lv_area_t visible;if(!_lv_area_intersect(&visible,&bounds,ctx->clip_area))return;
    uint32_t first=(uint32_t)(scroll_y+visible.y1-bounds.y1)/ROW;
    uint32_t last=(uint32_t)(scroll_y+visible.y2-bounds.y1)/ROW+1;if(last>doc.lines)last=doc.lines;
    const lv_area_t *original=ctx->clip_area;
    lv_area_t text_clip=visible;text_clip.x1=LV_MAX(text_clip.x1,bounds.x1+(lv_coord_t)margin);
    lv_draw_label_dsc_t glyph;lv_draw_label_dsc_init(&glyph);glyph.font=&sc_code_font;
    for(uint32_t line=first;line<last;++line){
        lv_coord_t y=(lv_coord_t)(bounds.y1+(int32_t)(line*ROW)-scroll_y);
        char number[12];snprintf(number,sizeof number,"%lu",(unsigned long)line+1);
        glyph.color=lv_color_hex(0x777777);glyph.align=LV_TEXT_ALIGN_RIGHT;
        lv_area_t counter={bounds.x1+2,y,bounds.x1+(lv_coord_t)margin-6,y+ROW-1};
        ctx->clip_area=original;lv_draw_label(ctx,&glyph,&counter,number,NULL);glyph.align=LV_TEXT_ALIGN_LEFT;
        if(text_clip.x1>text_clip.x2)continue;
        ctx->clip_area=&text_clip;
        size_t offset=doc.line[line],end=line+1<doc.lines?doc.line[line+1]:doc.bytes;
        while(end>offset && (doc.text[end-1]=='\n' || doc.text[end-1]=='\r'))--end;
        uint32_t column=0;
        while(offset<end){
            size_t start=offset;uint32_t code=sc_source_codepoint(doc.text,end,&offset);
            if(code=='\t'){column=(column+4)&~3u;continue;}
            int32_t x=bounds.x1+(int32_t)margin+(int32_t)(column*CELL)-scroll_x;
            if(x>text_clip.x2)break;
            if(x+CELL>=text_clip.x1){
                lv_point_t point={(lv_coord_t)x,y};glyph.color=lv_color_hex(sc_source_color(doc.style[start]));
                lv_draw_letter(ctx,&glyph,&point,code<32?0xfffd:code);
            }++column;
        }
    }ctx->clip_area=original;
}
static int32_t maximum(unsigned axis)
{
    int32_t value=axis?(int32_t)(doc.lines*ROW)-lv_obj_get_height(area):
        (int32_t)(doc.columns*CELL)-lv_obj_get_width(area)+(int32_t)gutter()+4;
    return value>0?value:0;
}
static void strip_event(lv_event_t *event)
{
    unsigned axis=(unsigned)(uintptr_t)lv_event_get_user_data(event);
    lv_event_code_t code=lv_event_get_code(event);lv_area_t bounds;lv_obj_get_coords(lv_event_get_target(event),&bounds);
    int start=axis?bounds.y1+18:bounds.x1+18;
    int length=(axis?lv_area_get_height(&bounds):lv_area_get_width(&bounds))-36;
    if(code==LV_EVENT_DRAW_MAIN){
        lv_draw_ctx_t *ctx=lv_event_get_draw_ctx(event);lv_draw_rect_dsc_t d;lv_draw_rect_dsc_init(&d);
        d.bg_color=lv_color_hex(0xD2D6DA);d.bg_opa=LV_OPA_COVER;d.radius=2;
        lv_area_t track=axis?(lv_area_t){bounds.x1+22,start,bounds.x1+25,start+length-1}:
            (lv_area_t){start,bounds.y1+18,start+length-1,bounds.y1+21};
        lv_draw_rect(ctx,&d,&track);int32_t max=maximum(axis),value=axis?scroll_y:scroll_x;
        int offset=max?(int)((int64_t)value*(length-24)/max):0;
        d.bg_color=lv_color_hex(max?0x5E6F7E:0xBBC2C8);d.radius=4;
        lv_area_t thumb=axis?(lv_area_t){bounds.x1+18,start+offset,bounds.x1+29,start+offset+23}:
            (lv_area_t){start+offset,bounds.y1+14,start+offset+23,bounds.y1+25};
        lv_draw_rect(ctx,&d,&thumb);return;
    }
    if(code==LV_EVENT_PRESSED)strip_drag[axis]=true;
    else if(code==LV_EVENT_RELEASED || code==LV_EVENT_PRESS_LOST || code==LV_EVENT_DELETE){strip_drag[axis]=false;return;}
    if((code!=LV_EVENT_PRESSED && code!=LV_EVENT_PRESSING) || !strip_drag[axis])return;
    lv_indev_t *input=lv_indev_get_act();if(!input)return;lv_point_t p;lv_indev_get_point(input,&p);
    int point=axis?p.y:p.x;point-=start+12;if(point<0)point=0;if(point>length-24)point=length-24;
    int32_t value=(int32_t)((int64_t)point*maximum(axis)/(length-24));
    if(axis)scroll_y=value;else scroll_x=value;clamp_scroll();location();lv_obj_invalidate(area);
}
lv_obj_t *sc_code_view_create(lv_obj_t *parent,lv_event_cb_t play)
{
    area=lv_obj_create(parent);lv_obj_set_pos(area,0,0);lv_obj_set_size(area,320,320);
    lv_obj_set_style_bg_color(area,lv_color_hex(0xFFFFFF),0);lv_obj_set_style_bg_opa(area,LV_OPA_COVER,0);
    lv_obj_set_style_border_width(area,0,0);lv_obj_set_style_radius(area,0,0);lv_obj_set_style_pad_all(area,0,0);
    lv_obj_clear_flag(area,LV_OBJ_FLAG_SCROLLABLE);lv_obj_add_flag(area,LV_OBJ_FLAG_PRESS_LOCK);
    lv_obj_add_event_cb(area,draw,LV_EVENT_DRAW_MAIN,NULL);lv_obj_add_event_cb(area,play,LV_EVENT_ALL,NULL);
    for(unsigned axis=0;axis<2;++axis){
        lv_obj_t *s=lv_obj_create(parent);strips[axis]=s;
        lv_obj_set_pos(s,axis?320:0,axis?0:320);lv_obj_set_size(s,axis?48:320,axis?320:40);
        lv_obj_set_style_bg_color(s,lv_color_hex(0xF0F2F4),0);lv_obj_set_style_bg_opa(s,LV_OPA_COVER,0);
        lv_obj_set_style_radius(s,0,0);lv_obj_set_style_border_width(s,0,0);lv_obj_set_style_pad_all(s,0,0);
        lv_obj_clear_flag(s,LV_OBJ_FLAG_SCROLLABLE);lv_obj_add_flag(s,LV_OBJ_FLAG_PRESS_LOCK);
        lv_obj_add_event_cb(s,strip_event,LV_EVENT_ALL,(void *)(uintptr_t)axis);
    }
    return area;
}
bool sc_code_view_source(const char *text,size_t bytes)
{
    strip_drag[0]=strip_drag[1]=false;
    if(bytes==doc.bytes && ((!bytes && !failed) || (text && doc.text && !memcmp(text,doc.text,bytes))))return true;
    document next={0};bool ok=bytes<=SC_SOURCE_MAX && (text || !bytes);
    if(bytes && ok){
        next.text=heap_caps_malloc(bytes+1,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
        next.style=heap_caps_malloc(bytes,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
        uint32_t lines=1;
        for(size_t i=0;i<bytes;++i){if(text[i]=='\r'){++lines;if(i+1<bytes && text[i+1]=='\n')++i;}else if(text[i]=='\n')++lines;}
        next.line=heap_caps_malloc(lines*sizeof *next.line,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
        ok=next.text && next.style && next.line;
        if(ok){
            memcpy(next.text,text,bytes);next.text[bytes]=0;next.bytes=bytes;next.lines=1;next.line[0]=0;
            sc_source_highlight(next.text,bytes,next.style);
            size_t i=0;uint32_t column=0;
            while(i<bytes){
                uint32_t code=sc_source_codepoint(next.text,bytes,&i);
                if(code=='\r' || code=='\n'){
                    if(code=='\r' && i<bytes && next.text[i]=='\n')++i;
                    if(column>next.columns)next.columns=column;
                    column=0;next.line[next.lines++]=(uint32_t)i;
                }else column=code=='\t'?(column+4)&~3u:column+1;
            }if(column>next.columns)next.columns=column;
        }
    }
    if(!ok)dispose(&next);
    dispose(&doc);doc=next;failed=!ok;scroll_x=scroll_y=0;
    if(area){clamp_scroll();location();lv_obj_invalidate(area);}return ok;
}
void sc_code_view_position(uint32_t *line,uint32_t *column){*line=(uint32_t)(scroll_y/ROW);*column=(uint32_t)(scroll_x/CELL);}
void sc_code_view_scroll_to(uint32_t line,uint32_t column)
{
    if(!area)return;
    if(line>=doc.lines)line=doc.lines?doc.lines-1:0;
    if(column>doc.columns)column=doc.columns;
    scroll_y=(int32_t)(line*ROW);scroll_x=(int32_t)(column*CELL);
    clamp_scroll();location();lv_obj_invalidate(area);
}
