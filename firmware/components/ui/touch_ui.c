/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "touch_ui.h"
#include "output_volume.h"
#include "touch_display.h"
#include "sc_code_view.h"
#include "bsp/esp-bsp.h"
#include "esp_heap_caps.h"
#include <math.h>
#include <stdio.h>
#include <string.h>

static touch_ui_actions control;
static lv_obj_t *title,*subtitle,*status,*cpu,*battery,*slots_background,*source,*library,*rows[2],*names_label[2],*details[2],*slots_button,*slots_text,*cursor;
static char active_name[32]="SYNTHDEF";
static bool ready,busy,slots_open,held,pending,stress,exercise,available[2]={false};
static uint32_t held_note,notice_until,exercise_started,exercise_note;
static unsigned stress_frame,exercise_step;
static int selected_slot=0;
static float x_value=.5f,y_value=.5f;
static bool battery_low;
static bool automatic;
static lv_obj_t *wifi,*receive_dot;
static char module_name[32]="Instrument",module_id[24]="MAIN + FX";
static bool wifi_online,receive_active;
static lv_obj_t *master_rows[2],*master_names[2],*master_details[2];
static bool master_available;
static lv_obj_t *volume_panel,*volume_slider,*volume_label;
static const uint32_t INK=0x111111,MUTED=0x666666;

static lv_obj_t *label(lv_obj_t *parent,const char *text,int x,int y,int width,uint32_t color)
{
    lv_obj_t *o=lv_label_create(parent);lv_label_set_text(o,text);lv_obj_set_pos(o,x,y);
    lv_obj_set_width(o,width);lv_label_set_long_mode(o,LV_LABEL_LONG_DOT);
    lv_obj_set_style_text_font(o,&lv_font_montserrat_14,0);lv_obj_set_style_text_color(o,lv_color_hex(color),0);
    lv_obj_clear_flag(o,LV_OBJ_FLAG_CLICKABLE);return o;
}
static void release_touch(void)
{
    if(held)control.post(INST_NOTE_OFF,held_note,0);
    held=false;if(cursor)lv_obj_add_flag(cursor,LV_OBJ_FLAG_HIDDEN);
}
static void set_slots(bool visible)
{
    release_touch();if(exercise_note){control.post(INST_NOTE_OFF,exercise_note,0);exercise_note=0;}
    slots_open=visible;
    lv_label_set_text(title,visible?module_name:active_name);
    lv_label_set_text(subtitle,visible?module_id:automatic?"PLAYS AUTOMATICALLY":"TOUCH CODE TO PLAY");
    lv_obj_set_style_text_color(title,lv_color_hex(visible?0xFFFFFF:INK),0);
    lv_obj_set_style_text_color(subtitle,lv_color_hex(visible?0xFFFFFF:MUTED),0);
    lv_obj_set_style_text_color(battery,lv_color_hex(battery_low?0xBF0000:visible?0xFFFFFF:INK),0);
    lv_obj_set_style_text_color(wifi,lv_color_hex(visible?(wifi_online?0xFFFFFF:0x888888):MUTED),0);
    if(visible){lv_obj_add_flag(source,LV_OBJ_FLAG_HIDDEN);lv_obj_clear_flag(library,LV_OBJ_FLAG_HIDDEN);lv_obj_clear_flag(slots_background,LV_OBJ_FLAG_HIDDEN);}
    else {lv_obj_clear_flag(source,LV_OBJ_FLAG_HIDDEN);lv_obj_add_flag(library,LV_OBJ_FLAG_HIDDEN);lv_obj_add_flag(slots_background,LV_OBJ_FLAG_HIDDEN);}
    lv_label_set_text(slots_text,visible?"CODE":"CONTROLS");
    if(volume_panel){if(visible)lv_obj_clear_flag(volume_panel,LV_OBJ_FLAG_HIDDEN);else lv_obj_add_flag(volume_panel,LV_OBJ_FLAG_HIDDEN);}
}
static void panic_event(lv_event_t *e)
{
    (void)e;release_touch();exercise_note=0;control.panic();
    lv_label_set_text(status,"STOPPED");notice_until=lv_tick_get()+1500;
}
static void page_event(lv_event_t *e){(void)e;if(!busy && !pending)set_slots(!slots_open);}
static void select_slot(unsigned slot)
{
    if(busy || pending || !available[slot] || !control.patch_action)return;
    release_touch();pending=true;
    if(!control.patch_action(slot,false)){
        pending=false;lv_label_set_text(status,"PLEASE RETRY");notice_until=lv_tick_get()+2000;
    }
}
static void slot_event(lv_event_t *e){select_slot((unsigned)(uintptr_t)lv_event_get_user_data(e));}
static void master_event(lv_event_t *e)
{
    unsigned slot=(unsigned)(uintptr_t)lv_event_get_user_data(e);
    if(busy || pending || !control.master_action || (slot && !master_available))return;
    release_touch();pending=true;
    if(!control.master_action(slot)){pending=false;lv_label_set_text(status,"PLEASE RETRY");notice_until=lv_tick_get()+2000;}
}
static void volume_event(lv_event_t *e)
{
    lv_event_code_t code=lv_event_get_code(e);
    if(!control.volume || busy || pending || (code!=LV_EVENT_VALUE_CHANGED && code!=LV_EVENT_RELEASED))return;
    unsigned value=(unsigned)lv_slider_get_value(volume_slider);char text[16];
    snprintf(text,sizeof text,"%u%%",value);lv_label_set_text(volume_label,text);
    if(!control.volume(value,code==LV_EVENT_RELEASED)){
        lv_label_set_text(status,"PLEASE RETRY");notice_until=lv_tick_get()+2000;
    }
}
static lv_obj_t *button(lv_obj_t *parent,const char *text,int x,int y,int width,lv_event_cb_t callback,void *data)
{
    lv_obj_t *o=lv_btn_create(parent);lv_obj_set_pos(o,x,y);lv_obj_set_size(o,width,34);
    lv_obj_set_style_bg_color(o,lv_color_hex(0xEEEEEE),0);lv_obj_set_style_shadow_width(o,0,0);
    lv_obj_t *t=label(o,text,0,0,width-8,INK);lv_obj_set_style_text_align(t,LV_TEXT_ALIGN_CENTER,0);lv_obj_center(t);
    lv_obj_add_event_cb(o,callback,LV_EVENT_CLICKED,data);return o;
}
static void play_event(lv_event_t *e)
{
    lv_event_code_t code=lv_event_get_code(e);
    if(code==LV_EVENT_RELEASED || code==LV_EVENT_PRESS_LOST || code==LV_EVENT_DELETE){release_touch();return;}
    if(busy || pending || slots_open || (code!=LV_EVENT_PRESSED && code!=LV_EVENT_PRESSING))return;
    if(code==LV_EVENT_PRESSING && !held)return;
    lv_indev_t *input=lv_indev_get_act();if(!input)return;
    lv_point_t p;lv_area_t a;lv_indev_get_point(input,&p);lv_obj_get_coords(lv_event_get_target(e),&a);
    x_value=fminf(1,fmaxf(0,(float)(p.x-a.x1)/(a.x2-a.x1)));
    y_value=fminf(1,fmaxf(0,1-(float)(p.y-a.y1)/(a.y2-a.y1)));
    control.post(INST_TOUCH_X,0,x_value);control.post(INST_TOUCH_Y,0,y_value);
    if(code==LV_EVENT_PRESSED){held_note=control.new_note();held=control.post(INST_NOTE_ON,held_note,0);}
    if(held){
        lv_obj_set_pos(cursor,(lv_coord_t)(x_value*(a.x2-a.x1-8)),(lv_coord_t)((1-y_value)*(a.y2-a.y1-8)));
        lv_obj_clear_flag(cursor,LV_OBJ_FLAG_HIDDEN);
    }
}
static void screen_event(lv_event_t *e){(void)e;release_touch();control.panic();}
static void redraw(lv_timer_t *timer)
{
    (void)timer;
    if(exercise && lv_tick_elaps(exercise_started)>=30000){exercise=false;exercise_note=0;control.panic();}
    if(busy || pending || slots_open || held)return;
    if(exercise){
        static const float pitch[]={0,.13f,.37f,.5f,.63f,.87f,1};
        control.post(INST_TOUCH_X,0,pitch[exercise_step%7]);control.post(INST_TOUCH_Y,0,.25f+.4f*(exercise_step%11)/10);
        control.post(INST_KNOB3,0,(float)((exercise_step/7)%2));control.post(INST_KNOB4,0,(float)((exercise_step/14)%2));
        if(control.effect){
            static const float times[]={.02f,.125f,.35f,1,5},feedback[]={0,.35f,.8f},wet[]={0,.25f,1};
            control.effect(0,times[(exercise_step/7)%5]);control.effect(1,feedback[(exercise_step/11)%3]);control.effect(2,wet[(exercise_step/13)%3]);
        }
        if(exercise_step%5==0){exercise_note=control.new_note();control.post(INST_NOTE_ON,exercise_note,0);}
        if(exercise_step%5==3 && exercise_note){control.post(INST_NOTE_OFF,exercise_note,0);exercise_note=0;}
        ++exercise_step;
    }
    if(stress || exercise){sc_code_view_scroll_to((stress_frame/3)%64,(stress_frame/5)%64);++stress_frame;}
}
esp_err_t touch_ui_start(const touch_ui_actions *actions)
{
    if(!actions || !actions->post || !actions->new_note || !actions->panic)return ESP_ERR_INVALID_ARG;
    control=*actions;esp_err_t err=touch_display_start();if(err!=ESP_OK)return err;
    if(!bsp_display_lock(2000))return ESP_ERR_TIMEOUT;
    lv_obj_t *screen=lv_scr_act();lv_obj_set_style_bg_color(screen,lv_color_hex(0xFFFFFF),0);
    lv_obj_clear_flag(screen,LV_OBJ_FLAG_SCROLLABLE);lv_obj_add_event_cb(screen,screen_event,LV_EVENT_SCREEN_UNLOAD_START,NULL);
    slots_background=lv_obj_create(screen);lv_obj_set_pos(slots_background,0,0);lv_obj_set_size(slots_background,368,408);
    lv_obj_set_style_bg_color(slots_background,lv_color_hex(0x000000),0);
    lv_obj_set_style_border_width(slots_background,0,0);lv_obj_set_style_radius(slots_background,0,0);
    lv_obj_clear_flag(slots_background,LV_OBJ_FLAG_CLICKABLE|LV_OBJ_FLAG_SCROLLABLE);
    title=label(screen,"SYNTHDEF",28,7,208,INK);
    subtitle=label(screen,"TOUCH CODE TO PLAY",12,28,220,MUTED);
    battery=label(screen,"? " LV_SYMBOL_BATTERY_EMPTY,262,12,86,INK);lv_obj_set_style_text_align(battery,LV_TEXT_ALIGN_RIGHT,0);
    wifi=label(screen,"Wi-Fi off",240,28,108,MUTED);lv_obj_set_style_text_align(wifi,LV_TEXT_ALIGN_RIGHT,0);
    receive_dot=lv_obj_create(screen);lv_obj_set_pos(receive_dot,268,14);lv_obj_set_size(receive_dot,8,8);
    lv_obj_set_style_pad_all(receive_dot,0,0);lv_obj_set_style_radius(receive_dot,LV_RADIUS_CIRCLE,0);
    lv_obj_set_style_bg_opa(receive_dot,LV_OPA_TRANSP,0);lv_obj_set_style_border_width(receive_dot,1,0);
    lv_obj_set_style_border_color(receive_dot,lv_color_hex(0x888888),0);
    lv_obj_clear_flag(receive_dot,LV_OBJ_FLAG_CLICKABLE|LV_OBJ_FLAG_SCROLLABLE);
    source=lv_obj_create(screen);lv_obj_set_pos(source,0,48);lv_obj_set_size(source,368,360);
    lv_obj_set_style_border_width(source,0,0);lv_obj_set_style_pad_all(source,0,0);lv_obj_set_style_radius(source,0,0);
    lv_obj_clear_flag(source,LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_t *body=sc_code_view_create(source,play_event);
    cursor=lv_obj_create(body);lv_obj_set_size(cursor,9,9);lv_obj_set_style_radius(cursor,5,0);
    lv_obj_set_style_bg_opa(cursor,LV_OPA_TRANSP,0);lv_obj_set_style_border_width(cursor,2,0);
    lv_obj_set_style_border_color(cursor,lv_color_hex(0x167CBA),0);lv_obj_clear_flag(cursor,LV_OBJ_FLAG_CLICKABLE|LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(cursor,LV_OBJ_FLAG_HIDDEN);
    library=lv_obj_create(screen);lv_obj_set_pos(library,0,48);lv_obj_set_size(library,368,360);
    if(control.volume){
        volume_panel=lv_obj_create(screen);lv_obj_set_pos(volume_panel,0,48);lv_obj_set_size(volume_panel,368,66);
        lv_obj_set_style_bg_color(volume_panel,lv_color_hex(0),0);lv_obj_set_style_border_width(volume_panel,0,0);
        lv_obj_set_style_radius(volume_panel,0,0);lv_obj_set_style_pad_all(volume_panel,0,0);
        lv_obj_clear_flag(volume_panel,LV_OBJ_FLAG_SCROLLABLE|LV_OBJ_FLAG_CLICKABLE);
        label(volume_panel,"VOLUME",20,2,150,0xFFFFFF);
        char default_level[16];snprintf(default_level,sizeof default_level,"%u%%",OUTPUT_VOLUME_DEFAULT_PERCENT);
        volume_label=label(volume_panel,default_level,274,2,70,0xFFFFFF);lv_obj_set_style_text_align(volume_label,LV_TEXT_ALIGN_RIGHT,0);
        volume_slider=lv_slider_create(volume_panel);lv_obj_set_pos(volume_slider,28,36);lv_obj_set_size(volume_slider,312,8);
        lv_slider_set_range(volume_slider,0,100);lv_slider_set_value(volume_slider,OUTPUT_VOLUME_DEFAULT_PERCENT,LV_ANIM_OFF);
        lv_obj_set_ext_click_area(volume_slider,14);
        lv_obj_set_style_bg_color(volume_slider,lv_color_hex(0x444444),LV_PART_MAIN);
        lv_obj_set_style_bg_color(volume_slider,lv_color_hex(0xFFFFFF),LV_PART_INDICATOR);
        lv_obj_set_style_bg_color(volume_slider,lv_color_hex(0xFFFFFF),LV_PART_KNOB);
        lv_obj_set_style_pad_all(volume_slider,7,LV_PART_KNOB);
        lv_obj_add_event_cb(volume_slider,volume_event,LV_EVENT_ALL,NULL);
        lv_obj_set_pos(library,0,114);lv_obj_set_height(library,294);
    }
    lv_obj_set_style_bg_color(library,lv_color_hex(0x000000),0);lv_obj_set_style_border_width(library,0,0);
    lv_obj_set_style_bg_color(library,lv_color_hex(0xFFFFFF),LV_PART_SCROLLBAR);
    lv_obj_set_style_pad_all(library,8,0);lv_obj_set_style_radius(library,0,0);lv_obj_set_scroll_dir(library,LV_DIR_VER);
    for(unsigned k=1;k<2;++k){
        lv_obj_t *row=lv_btn_create(library);rows[k]=row;lv_obj_set_pos(row,0,0);lv_obj_set_size(row,342,60);
        lv_obj_set_style_bg_color(row,lv_color_hex(0x000000),0);lv_obj_set_style_shadow_width(row,0,0);
        lv_obj_set_style_bg_color(row,lv_color_hex(0x242424),LV_STATE_PRESSED);
        lv_obj_set_style_border_width(row,1,0);lv_obj_set_style_border_color(row,lv_color_hex(0xFFFFFF),0);
        lv_obj_set_style_border_color(row,lv_color_hex(0x666666),LV_STATE_DISABLED);
        lv_obj_set_style_color_filter_opa(row,LV_OPA_TRANSP,LV_STATE_DISABLED);
        lv_obj_set_style_pad_all(row,8,0);lv_obj_clear_flag(row,LV_OBJ_FLAG_SCROLLABLE);
        names_label[k]=label(row,k?"EMPTY":"0   Factory",0,0,318,0xFFFFFF);
        details[k]=label(row,k?"EMPTY SLOT":"FACTORY",0,23,318,0xFFFFFF);
        lv_obj_add_event_cb(row,slot_event,LV_EVENT_CLICKED,(void *)(uintptr_t)k);
        if(k)lv_obj_add_state(row,LV_STATE_DISABLED);
    }
    if(control.master_action){
        label(library,"OUTPUT",0,78,318,0xFFFFFF);
        for(unsigned k=0;k<2;++k){
            lv_obj_t *row=lv_btn_create(library);master_rows[k]=row;lv_obj_set_pos(row,0,104+k*66);lv_obj_set_size(row,342,60);
            lv_obj_set_style_bg_color(row,lv_color_hex(0),0);lv_obj_set_style_border_width(row,1,0);
            lv_obj_set_style_border_color(row,lv_color_hex(0xFFFFFF),0);lv_obj_set_style_shadow_width(row,0,0);
            lv_obj_set_style_bg_color(row,lv_color_hex(0x242424),LV_STATE_PRESSED);
            lv_obj_set_style_border_color(row,lv_color_hex(0x666666),LV_STATE_DISABLED);
            lv_obj_set_style_color_filter_opa(row,LV_OPA_TRANSP,LV_STATE_DISABLED);
            lv_obj_set_style_pad_all(row,8,0);lv_obj_clear_flag(row,LV_OBJ_FLAG_SCROLLABLE);
            master_names[k]=label(row,k?"FX":"Bypass",0,0,318,0xFFFFFF);
            master_details[k]=label(row,k?"UPLOAD FX FROM YOUR COMPUTER":"SELECTED",0,23,318,0xFFFFFF);
            lv_obj_add_event_cb(row,master_event,LV_EVENT_CLICKED,(void *)(uintptr_t)k);
            if(k)lv_obj_add_state(row,LV_STATE_DISABLED);
        }
    }
    slots_button=button(screen,"CONTROLS",8,414,100,page_event,NULL);slots_text=lv_obj_get_child(slots_button,0);
    cpu=label(screen,"CPU --",116,414,134,MUTED);lv_obj_set_style_text_align(cpu,LV_TEXT_ALIGN_CENTER,0);
    status=label(screen,"READY",116,431,134,MUTED);lv_obj_set_style_text_align(status,LV_TEXT_ALIGN_CENTER,0);
    lv_obj_t *panic=button(screen,"PANIC",258,414,102,panic_event,NULL);
    lv_obj_set_style_bg_color(panic,lv_color_hex(0x562F37),0);lv_obj_set_style_text_color(lv_obj_get_child(panic,0),lv_color_hex(0xFFFFFF),0);
    lv_obj_remove_event_cb(panic,panic_event);lv_obj_add_event_cb(panic,panic_event,LV_EVENT_PRESSED,NULL);
    set_slots(false);lv_timer_create(redraw,40,NULL);ready=true;bsp_display_unlock();return bsp_display_brightness_set(55);
}
void touch_ui_status(bool active,bool fault,float frequency)
{
    (void)frequency;if(!ready || !bsp_display_lock(10))return;
    if(!busy && !pending && (int32_t)(notice_until-lv_tick_get())<=0){
        const char *text=fault?"AUDIO STOPPED":active?"PLAYING":"READY";
        if(strcmp(lv_label_get_text(status),text))lv_label_set_text(status,text);
    }bsp_display_unlock();
}
void touch_ui_battery(void)
{
    if(!ready)return;
    touch_battery b;bool valid=touch_display_battery(&b)==ESP_OK;char text[40];const char *icon=LV_SYMBOL_BATTERY_EMPTY;
    if(valid && b.present && b.percent>=0){
        int p=b.percent;icon=p>=90?LV_SYMBOL_BATTERY_FULL:p>=60?LV_SYMBOL_BATTERY_3:p>=35?LV_SYMBOL_BATTERY_2:p>=10?LV_SYMBOL_BATTERY_1:LV_SYMBOL_BATTERY_EMPTY;
        snprintf(text,sizeof text,"%d%% %s%s",p,b.charging?LV_SYMBOL_CHARGE " ":"",icon);
    }else snprintf(text,sizeof text,"%s %s",valid && !b.present?(b.usb?LV_SYMBOL_USB:"-"):"?",icon);
    if(!bsp_display_lock(100))return;
    if(strcmp(lv_label_get_text(battery),text))lv_label_set_text(battery,text);
    battery_low=valid && b.present && b.percent>=0 && b.percent<10;
    lv_obj_set_style_text_color(battery,lv_color_hex(battery_low?0xBF0000:slots_open?0xFFFFFF:INK),0);bsp_display_unlock();
}
void touch_ui_connectivity(const char *name,const char *id,bool online,int rssi,bool receiving)
{
    /* The BSP interprets zero as an infinite wait. Retry next tick if busy. */
    if(!ready || !bsp_display_lock(1))return;
    char text[40];
    if(online && rssi>-127 && rssi<=0)snprintf(text,sizeof text,LV_SYMBOL_WIFI " %d dBm",rssi);
    else snprintf(text,sizeof text,online?LV_SYMBOL_WIFI " --":"Wi-Fi off");
    if(strcmp(lv_label_get_text(wifi),text)){
        lv_label_set_text(wifi,text);
        if(online){
            /* Right-aligned RSSI text can move the symbol as its width changes. */
            lv_point_t symbol,next;lv_obj_update_layout(wifi);
            lv_label_get_letter_pos(wifi,0,&symbol);lv_label_get_letter_pos(wifi,1,&next);
            lv_obj_set_x(receive_dot,lv_obj_get_x(wifi)+(symbol.x+next.x-lv_obj_get_width(receive_dot))/2);
        }
    }
    if(wifi_online!=online)lv_obj_set_style_text_color(wifi,lv_color_hex(slots_open?(online?0xFFFFFF:0x888888):MUTED),0);
    wifi_online=online;
    if(name && name[0])snprintf(module_name,sizeof module_name,"%s",name);
    if(id && id[0])snprintf(module_id,sizeof module_id,"%s",id);
    if(slots_open){
        if(strcmp(lv_label_get_text(title),module_name))lv_label_set_text(title,module_name);
        if(strcmp(lv_label_get_text(subtitle),module_id))lv_label_set_text(subtitle,module_id);
    }
    if(receiving!=receive_active){
        receive_active=receiving;
        lv_obj_set_style_bg_color(receive_dot,lv_color_hex(0x18B65A),0);
        lv_obj_set_style_bg_opa(receive_dot,receiving?LV_OPA_COVER:LV_OPA_TRANSP,0);
        lv_obj_set_style_border_color(receive_dot,lv_color_hex(receiving?0x18B65A:0x888888),0);
    }
    bsp_display_unlock();
}
void touch_ui_cpu(uint32_t average,uint32_t peak)
{
    if(!ready || !bsp_display_lock(100))return;
    char text[32];
    if(average==UINT32_MAX)snprintf(text,sizeof text,"CPU --");
    else snprintf(text,sizeof text,"CPU %lu.%lu%%",(unsigned long)(average/10),(unsigned long)(average%10));
    if(strcmp(lv_label_get_text(cpu),text))lv_label_set_text(cpu,text);
    uint32_t color=average==UINT32_MAX?MUTED:peak>=1000?0xBF0000:peak>=700?0x996000:MUTED;
    lv_obj_set_style_text_color(cpu,lv_color_hex(color),0);bsp_display_unlock();
}
void touch_ui_busy(bool yes,const char *text)
{
    if(!ready || !bsp_display_lock(1000))return;
    busy=yes;if(yes)release_touch();else pending=false;
    notice_until=!yes && strcmp(text,"READY")?lv_tick_get()+3000:0;lv_label_set_text(status,text);
    if(yes)lv_obj_add_state(slots_button,LV_STATE_DISABLED);else lv_obj_clear_state(slots_button,LV_STATE_DISABLED);
    for(unsigned k=1;k<2;++k){if(yes || !available[k])lv_obj_add_state(rows[k],LV_STATE_DISABLED);else lv_obj_clear_state(rows[k],LV_STATE_DISABLED);}
    for(unsigned k=0;k<2;++k)if(master_rows[k]){if(yes || (k && !master_available))lv_obj_add_state(master_rows[k],LV_STATE_DISABLED);else lv_obj_clear_state(master_rows[k],LV_STATE_DISABLED);}
    if(volume_slider){if(yes)lv_obj_add_state(volume_slider,LV_STATE_DISABLED);else lv_obj_clear_state(volume_slider,LV_STATE_DISABLED);}
    bsp_display_unlock();
}
void touch_ui_volume(unsigned percent)
{
    if(!ready || !volume_slider || !bsp_display_lock(100))return;
    if(percent>100)percent=100;
    char text[16];snprintf(text,sizeof text,"%u%%",percent);lv_label_set_text(volume_label,text);
    lv_slider_set_value(volume_slider,(int)percent,LV_ANIM_OFF);bsp_display_unlock();
}
void touch_ui_patch(const char *name,const char labels[4][12],unsigned mapping,const float knobs[4],float frequency,const char names[2][32],int slot,const char *text,size_t bytes)
{
    (void)labels;(void)mapping;(void)frequency;
    if(!ready || !bsp_display_lock(1000))return;
    release_touch();pending=false;selected_slot=slot;snprintf(active_name,sizeof active_name,"%s",name);sc_code_view_source(text,bytes);
    x_value=knobs[0];y_value=knobs[1];char row[64];
    for(unsigned k=1;k<2;++k){
        available[k]=names[k][0]!=0;snprintf(row,sizeof row,"MAIN   %s",available[k]?names[k]:"EMPTY");lv_label_set_text(names_label[k],row);
        lv_obj_set_style_text_color(names_label[k],lv_color_hex(available[k]?0xFFFFFF:0x888888),0);
        lv_obj_set_style_text_color(details[k],lv_color_hex(available[k]?0xFFFFFF:0x888888),0);
        lv_label_set_text(details[k],!available[k]?"UPLOAD MAIN FROM YOUR COMPUTER":"TAP TO RESTART MAIN");
        if(!available[k] || busy)lv_obj_add_state(rows[k],LV_STATE_DISABLED);else lv_obj_clear_state(rows[k],LV_STATE_DISABLED);
    }set_slots(false);bsp_display_unlock();
}
void touch_ui_code(bool visible){if(ready && bsp_display_lock(1000)){if(!busy)set_slots(!visible);bsp_display_unlock();}}
void touch_ui_playback(bool continuous)
{
    if(!ready || !bsp_display_lock(100))return;
    automatic=continuous;if(!slots_open)lv_label_set_text(subtitle,automatic?"PLAYS AUTOMATICALLY":"TOUCH CODE TO PLAY");
    bsp_display_unlock();
}
void touch_ui_master(const char *name,int selected)
{
    if(!ready || !master_rows[0] || !bsp_display_lock(100))return;
    master_available=name[0]!=0;char text[64];snprintf(text,sizeof text,"FX   %s",master_available?name:"EMPTY");
    lv_label_set_text(master_names[1],text);
    for(unsigned k=0;k<2;++k){
        lv_label_set_text(master_details[k],(int)k==selected?"SELECTED":k && !master_available?"UPLOAD FX FROM YOUR COMPUTER":"TAP TO ACTIVATE");
        if(busy || (k && !master_available))lv_obj_add_state(master_rows[k],LV_STATE_DISABLED);else lv_obj_clear_state(master_rows[k],LV_STATE_DISABLED);
    }
    pending=false;set_slots(false);bsp_display_unlock();
}
void touch_ui_step_patch(bool next)
{
    if(!ready || !bsp_display_lock(1000))return;
    (void)next;
    if(available[1])select_slot(1);
    bsp_display_unlock();
}
void touch_ui_stress(bool enabled){if(ready && bsp_display_lock(100)){stress=enabled;bsp_display_unlock();}}
void touch_ui_effect(const float value[3]){(void)value;}
void touch_ui_exercise(bool enabled)
{
    if(!ready || !bsp_display_lock(1000))return;
    if(exercise_note)control.post(INST_NOTE_OFF,exercise_note,0);
    exercise_note=0;exercise=enabled;exercise_started=lv_tick_get();exercise_step=0;
    if(enabled)set_slots(false);else control.panic();bsp_display_unlock();
}
void *touch_ui_snapshot(size_t *bytes)
{
    *bytes=0;if(!ready || !bsp_display_lock(200))return NULL;
    lv_obj_t *screen=lv_scr_act();lv_obj_update_layout(screen);size_t size=lv_snapshot_buf_size_needed(screen,LV_IMG_CF_TRUE_COLOR);
    void *pixels=heap_caps_malloc(size,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);lv_img_dsc_t image={0};
    if(pixels && lv_snapshot_take_to_buf(screen,LV_IMG_CF_TRUE_COLOR,&image,pixels,size)!=LV_RES_OK){heap_caps_free(pixels);pixels=NULL;}
    if(pixels)*bytes=image.data_size;
    bsp_display_unlock();return pixels;
}
