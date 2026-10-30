/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Real LVGL/widget code with simulated display/touch; no timing/hardware claim. */
#include "touch_ui.h"
#include "touch_display.h"
#include "bsp/esp-bsp.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
static bool down;
static lv_point_t point;
static unsigned starts,releases,panics,changed[4];
static unsigned library_actions,last_slot;static bool last_save;
static bool patch_action(unsigned slot,bool save) {++library_actions;last_slot=slot;last_save=save;return true;}
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
static uint32_t new_note(void) { return ++sequence; }
static void panic(void) { ++panics; }
static bool post(inst_event_type type,uint32_t id,float value)
{
    if (type==INST_NOTE_ON) { ++starts; last_on=id; }
    else if (type==INST_NOTE_OFF) { ++releases; last_off=id; }
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
static void save(const char *path)
{
    size_t bytes; void *pixels=touch_ui_snapshot(&bytes); assert(pixels && bytes==368*448*2);
    FILE *file=fopen(path,"wb"); assert(file);
    assert(fwrite(pixels,1,bytes,file)==bytes); assert(fclose(file)==0); free(pixels);
}
int main(int argc,char **argv)
{
    assert(argc==4);
    touch_ui_actions actions={.post=post,.new_note=new_note,.panic=panic,.patch_action=patch_action};
    assert(touch_ui_start(&actions)==ESP_OK);
    input(0,0,false); save(argv[1]);
    input(170,170,true);
    assert(starts==1 && releases==0 && changed[0] && changed[1]);
    input(300,120,true); save(argv[2]);
    assert(last_value[0]>0.8f && last_value[1]>0.8f);
    /* Drag outside the pad and release: press-lock must preserve the release. */
    input(360,255,true); input(360,255,false);
    assert(releases==1 && last_off==last_on);
    for (unsigned k=0;k<4;++k) {
        unsigned before=changed[k];
        int x=16+(k%2)*172+110, y=260+(k/2)*80+50;
        input(x,y,true); input(x-30,y,true); input(x-30,y,false);
        assert(changed[k]>before);
    }
    input(300,35,true); assert(panics>=1); /* Panic acts on down, before release. */
    input(300,35,false);
    input(150,175,true); unsigned before=releases;
    lv_event_send(lv_scr_act(),LV_EVENT_SCREEN_UNLOAD_START,NULL);
    assert(releases==before+1 && last_off==last_on && panics>=2);
    input(150,175,false);
    const char labels[4][12]={"PITCH","LEVEL","ATTACK","TAIL"};
    const char names[9][32]={"Factory Sine","Saved Sine"};const float knobs[4]={.5f,.5f,.1f,.2f};
    touch_ui_patch("Saved Sine",labels,1,knobs,330,names,1);
    input(175,432,true);input(175,432,false);save(argv[3]);
    input(90,145,true);input(90,145,false);
    assert(library_actions==1 && last_slot==0 && !last_save);
    input(250,215,true);input(250,215,false);
    assert(library_actions==2 && last_slot==1 && last_save);
    touch_ui_busy(true,"SAVING");
    input(250,215,true);input(250,215,false);assert(library_actions==2);
    before=panics;input(300,35,true);input(300,35,false);assert(panics>before);
    touch_ui_busy(false,"READY");input(175,432,true);input(175,432,false);
    input(170,170,true);assert(starts==3);input(170,170,false);
    for(unsigned i=0;i<50;++i) {
        touch_ui_busy(true,"LOADING");touch_ui_patch("Saved Sine",labels,1,knobs,330,names,1);
        touch_ui_busy(false,"READY");input(0,0,false);
    }
    before=starts;touch_ui_exercise(true);
    for(unsigned i=0;i<400;++i)input(0,0,false);
    assert(starts>before+20);
    before=starts;for(unsigned i=0;i<30;++i)input(0,0,false);
    assert(starts==before); /* The exercise stops itself, including note starts. */
    touch_ui_exercise(false);
    lv_mem_monitor_t memory;lv_mem_monitor(&memory);
    assert(memory.free_size>16384 && lv_mem_test()==LV_RES_OK);
    printf("UI fixed heap: %u bytes, currently free %u, largest free block %u\n",(unsigned)memory.total_size,(unsigned)memory.free_size,(unsigned)memory.free_biggest_size);
    puts("PASS: real LVGL press/drag/release, all sliders, panic, page cancellation, metadata, library load/save and busy controls");
}
