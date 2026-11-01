/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Real LVGL/widget code with simulated display/touch; no timing/hardware claim. */
#include "touch_ui.h"
#include "touch_display.h"
#include "sc_code_view.h"
#include "sc_source.h"
#include "bsp/esp-bsp.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static bool down;
static lv_point_t point;
static unsigned starts,releases,panics,changed[4];
static unsigned library_actions,last_slot;static bool last_save;
static bool reject_patch;
static unsigned effect_changes[3],effect_saves;
static bool effect_post(unsigned k,float value) {assert(k<3);assert(value>=0 && value<=(k==0?5:k==1?.8f:1));++effect_changes[k];return true;}
static bool effect_save(void) {++effect_saves;return true;}
static bool patch_action(unsigned slot,bool save) {++library_actions;last_slot=slot;last_save=save;return !reject_patch;}
static unsigned master_actions,last_master;
static unsigned volume_updates,volume_commits,volume_value=100;
static bool volume_post(unsigned percent,bool save){assert(percent<=100);volume_value=percent;if(save)++volume_commits;else ++volume_updates;return true;}
static bool master_action(unsigned slot) {++master_actions;last_master=slot;return true;}
static lv_obj_t *find_label(lv_obj_t *parent,const char *text)
{
    if(lv_obj_check_type(parent,&lv_label_class) && !strcmp(lv_label_get_text(parent),text))return parent;
    for(unsigned i=0;i<lv_obj_get_child_cnt(parent);++i){lv_obj_t *found=find_label(lv_obj_get_child(parent,i),text);if(found)return found;}
    return NULL;
}
static uint32_t sequence,last_on,last_off;
static float last_value[4];

static void flush(lv_disp_drv_t *driver,const lv_area_t *area,lv_color_t *pixels)
{ (void)area; (void)pixels; lv_disp_flush_ready(driver); }
static void read_pointer(lv_indev_drv_t *driver,lv_indev_data_t *data)
{ (void)driver; data->point=point; data->state=down?LV_INDEV_STATE_PRESSED:LV_INDEV_STATE_RELEASED; }
lv_disp_t *bsp_display_start_with_config(const bsp_display_cfg_t *cfg)
{
    (void)cfg;
    lv_init();
    static lv_color_t pixels[368*20];
    static lv_disp_draw_buf_t buffer;
    static lv_disp_drv_t display;
    lv_disp_draw_buf_init(&buffer,pixels,NULL,368*20);
    lv_disp_drv_init(&display); display.hor_res=368; display.ver_res=448;
    display.draw_buf=&buffer; display.flush_cb=flush;
    lv_disp_t *result=lv_disp_drv_register(&display);
    static lv_indev_drv_t input;
    lv_indev_drv_init(&input); input.type=LV_INDEV_TYPE_POINTER; input.read_cb=read_pointer;
    assert(lv_indev_drv_register(&input));
    return result;
}
bool bsp_display_lock(uint32_t ms) { (void)ms; return true; }
void bsp_display_unlock(void) {}
esp_err_t bsp_display_brightness_set(int percent) { (void)percent; return ESP_OK; }
esp_err_t touch_display_start(void)
{
    bsp_display_cfg_t cfg={0};
    return bsp_display_start_with_config(&cfg)?ESP_OK:ESP_FAIL;
}
esp_err_t touch_display_battery(touch_battery *sample) { *sample=(touch_battery){.present=true,.charging=true,.usb=true,.percent=78};return ESP_OK; }
static uint32_t new_note(void) { return ++sequence; }
static void panic(void) { ++panics; }
static bool post(inst_event_type type,uint32_t id,float value)
{
    if (type==INST_NOTE_ON) { ++starts; last_on=id; }
    else if (type==INST_NOTE_OFF) { ++releases; last_off=id; }
    else if (type==INST_TOUCH_X || type==INST_TOUCH_Y) {
        unsigned k=type==INST_TOUCH_X?0:1;++changed[k];last_value[k]=value;assert(value>=0 && value<=1);
    }
    else if (type>=INST_KNOB1 && type<=INST_KNOB4) {
        unsigned k=type-INST_KNOB1; ++changed[k]; last_value[k]=value;
        assert(value>=0 && value<=1);
    }
    return true;
}
static void input(int x,int y,bool pressed)
{
    point=(lv_point_t){x,y}; down=pressed;
    for (unsigned i=0;i<4;++i) { lv_tick_inc(20); lv_timer_handler(); }
}
static void swipe(int x0,int y0,int x1,int y1)
{
    input(x0,y0,true);input((x0+x1)/2,(y0+y1)/2,true);
    input(x1,y1,true);input(x1,y1,false);
}

static void save(const char *path)
{
    size_t bytes;void *pixels=touch_ui_snapshot(&bytes);assert(pixels && bytes==368*448*2);
    FILE *f=fopen(path,"wb");assert(f);assert(fwrite(pixels,1,bytes,f)==bytes);assert(!fclose(f));free(pixels);
}
static unsigned received_pixels(void)
{
    size_t bytes;lv_color_t *pixels=touch_ui_snapshot(&bytes);assert(pixels && bytes==368*448*2);
    unsigned green=0;lv_color_t expected=lv_color_hex(0x18B65A);
    for(unsigned y=8;y<26;++y)for(unsigned x=240;x<258;++x)green+=pixels[y*368+x].full==expected.full;
    free(pixels);return green;
}
int main(int argc,char **argv)
{
    assert(argc==7 || argc==8);
    touch_ui_actions actions={.post=post,.new_note=new_note,.panic=panic,.patch_action=patch_action,.master_action=master_action,.volume=volume_post,.effect=effect_post,.effect_save=effect_save};
    assert(touch_ui_start(&actions)==ESP_OK);lv_obj_update_layout(lv_scr_act());touch_ui_battery();touch_ui_cpu(123,240);
    touch_ui_connectivity("AMOLED-3ad390","esp32-2884853ad390",true,-63,false);
    assert(find_label(lv_scr_act(),LV_SYMBOL_WIFI " -63 dBm"));assert(!received_pixels());
    touch_ui_connectivity("AMOLED-3ad390","esp32-2884853ad390",true,-63,true);assert(received_pixels()>8);
    touch_ui_connectivity("AMOLED-3ad390","esp32-2884853ad390",false,-127,false);assert(!received_pixels());assert(find_label(lv_scr_act(),"Wi-Fi off"));
    touch_ui_connectivity("AMOLED-3ad390","esp32-2884853ad390",true,-63,false);
    const char labels[4][12]={"PITCH","LEVEL","ATTACK","TAIL"};
    const char names[2][32]={"Factory","Saved Sine"};
    const float knobs[4]={.5f,.5f,.1f,.2f};
    if(argc==8){
        const char showcase[]="SynthDef(\\touchSine, {\n    arg root = 110;\n    var xy = In.kr(0, 3);\n    var hz = xy[0].linexp(\n        0, 1, root, root * 8\n    );\n    var amp = Lag.kr(\n        xy[1] * xy[2], 0.02\n    );\n\n    Out.ar(0,\n        SinOsc.ar(hz) * amp * 0.2\n    );\n});\n";
        touch_ui_patch("Touch sine",labels,1,knobs,330,names,1,showcase,strlen(showcase));
        input(0,0,false);save(argv[7]);
    }
    char source[4096]="// Touch bus SynthDef\nSynthDef(\\touch, {\n    var xy = In.kr(0, 3);\n    var frequency = xy[0].linexp(0, 1, 55, 1760);\n    Out.ar(0, SinOsc.ar(frequency) * xy[1] * xy[2] * 0.2);\n});\n";
    for(unsigned k=0;k<40;++k)strcat(source,"// More original source text to test scrolling in both directions without triggering a note.\n");
    touch_ui_patch("Touch buses",labels,1,knobs,330,names,1,source,strlen(source));
    input(0,0,false);save(argv[1]);save(argv[5]);
    uint32_t line,column;sc_code_view_position(&line,&column);assert(!line && !column);
    /* The default code body plays; even a fast horizontal drag never selects. */
    input(80,180,true);assert(starts==1);input(300,90,true);
    assert(last_value[0]>.9f && last_value[1]>.8f);
    touch_ui_connectivity("AMOLED-3ad390","esp32-2884853ad390",true,-63,true);save(argv[2]);
    touch_ui_connectivity("AMOLED-3ad390","esp32-2884853ad390",true,-63,false);
    input(350,220,true);assert(last_value[0]==1);sc_code_view_position(&line,&column);assert(!line && !column);
    input(350,220,false);assert(releases==1 && last_off==last_on && !library_actions);
    unsigned begun=starts,ended=releases,cx=changed[0],cy=changed[1];
    /* Right strip owns the drag when it crosses into the playing area. */
    input(348,100,true);input(160,330,true);input(160,330,false);
    sc_code_view_position(&line,&column);assert(line>0 && !column && starts==begun && releases==ended && cx==changed[0] && cy==changed[1]);
    input(70,389,true);input(280,200,true);input(280,200,false);
    sc_code_view_position(&line,&column);assert(column>0 && starts==begun && !library_actions);save(argv[6]);
    /* Coordinate values do not change with the scroll position. */
    input(160,208,true);assert(fabsf(last_value[0]-.5015674f)<.001f && fabsf(last_value[1]-.4984326f)<.001f);
    input(160,208,false);assert(last_off==last_on);
    unsigned before=panics;input(310,430,true);assert(panics==before+1);input(310,430,false);
    /* Slot list scrolls, without turning the scroll into a load. */
    input(55,430,true);input(55,430,false);save(argv[3]);begun=starts;
    assert(find_label(lv_scr_act(),"AMOLED-3ad390") && find_label(lv_scr_act(),"esp32-2884853ad390"));
    assert(find_label(lv_scr_act(),"100%"));
    swipe(335,88,184,88);assert(volume_updates && volume_commits==1 && volume_value>=49 && volume_value<=51);
    assert(!library_actions && starts==begun);unsigned updates=volume_updates;
    touch_ui_busy(true,"SAVING VOLUME");swipe(184,88,28,88);assert(volume_updates==updates);
    touch_ui_busy(false,"READY");touch_ui_volume(100);assert(find_label(lv_scr_act(),"100%"));
    swipe(180,300,180,132);assert(!library_actions && starts==begun);save(argv[4]);
    touch_ui_code(true);input(55,430,true);input(55,430,false);
    swipe(180,132,180,360);for(unsigned i=0;i<12;++i)input(0,0,false);
    input(120,151,true);input(120,151,false);assert(library_actions==1 && last_slot==1 && !last_save);
    input(120,150,true);input(120,150,false);assert(library_actions==1); /* Only one queued request. */
    touch_ui_busy(true,"LOADING");touch_ui_patch("Factory",labels,1,knobs,440,names,0,source,strlen(source));touch_ui_busy(false,"READY");
    input(160,208,true);assert(starts==begun+1);input(160,208,false); /* A load returns to CODE. */
    begun=starts;touch_ui_busy(true,"SAVING");
    input(160,208,true);input(160,208,false);assert(starts==begun);
    before=panics;input(310,430,true);assert(panics>before);input(310,430,false);touch_ui_busy(false,"READY");
    /* Busy or page changes release the exact held note. */
    input(100,180,true);uint32_t note=last_on;ended=releases;touch_ui_code(false);assert(releases==ended+1 && last_off==note);input(100,180,false);
    /* A rejected slot action can be retried; empty slots cannot load. */
    reject_patch=true;input(120,151,true);input(120,151,false);assert(library_actions==2);
    reject_patch=false;input(120,151,true);input(120,151,false);assert(library_actions==3);
    touch_ui_patch("Saved Sine",labels,1,knobs,330,names,1,source,strlen(source));
    /* Master choices are separate from sound slots and return to the code. */
    touch_ui_master("Fixture FX",0);touch_ui_code(false);
    lv_obj_t *master=lv_obj_get_parent(find_label(lv_scr_act(),"Bypass"));assert(master);
    lv_obj_scroll_to_view(master,LV_ANIM_OFF);lv_obj_update_layout(lv_scr_act());
    lv_area_t bounds;lv_obj_get_coords(master,&bounds);input(150,(bounds.y1+bounds.y2)/2,true);input(150,(bounds.y1+bounds.y2)/2,false);
    assert(master_actions==1 && last_master==0);touch_ui_master("Fixture FX",0);touch_ui_code(false);
    master=lv_obj_get_parent(find_label(lv_scr_act(),"FX   Fixture FX"));assert(master);
    lv_obj_scroll_to_view(master,LV_ANIM_OFF);lv_obj_update_layout(lv_scr_act());lv_obj_get_coords(master,&bounds);
    input(150,(bounds.y1+bounds.y2)/2,true);input(150,(bounds.y1+bounds.y2)/2,false);
    assert(master_actions==2 && last_master==1);touch_ui_master("Fixture FX",1);
    /* Owned source text and bounded 64 KiB edge cases remain valid. */
    size_t bytes;void *original=touch_ui_snapshot(&bytes);assert(original);source[0]='X';void *copy=touch_ui_snapshot(&bytes);assert(copy && !memcmp(original,copy,bytes));free(original);free(copy);
    char *large=malloc(SC_SOURCE_MAX);assert(large);memset(large,'\n',SC_SOURCE_MAX);
    touch_ui_patch("65537 lines",labels,1,knobs,330,names,1,large,SC_SOURCE_MAX);sc_code_view_scroll_to(UINT32_MAX,UINT32_MAX);
    copy=touch_ui_snapshot(&bytes);assert(copy);free(copy);memset(large,'x',SC_SOURCE_MAX);
    touch_ui_patch("Long line",labels,1,knobs,330,names,1,large,SC_SOURCE_MAX);sc_code_view_scroll_to(UINT32_MAX,UINT32_MAX);
    copy=touch_ui_snapshot(&bytes);assert(copy);free(copy);free(large);
    touch_ui_patch("No source",labels,1,knobs,330,names,1,NULL,0);copy=touch_ui_snapshot(&bytes);assert(copy);free(copy);
    lv_mem_monitor_t memory;lv_mem_monitor(&memory);assert(memory.free_size>12288);
    printf("UI fixed heap: 65536 bytes, currently free %u, largest free block %u\n",(unsigned)memory.free_size,(unsigned)memory.free_biggest_size);
    puts("PASS: code-first play/controls screens, X/Y, release ownership, independent vertical/horizontal scroll strips, Main restart and FX bypass, busy/Panic, source ownership and 64 KiB limits");
    return 0;
}
