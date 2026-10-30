/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "touch_ui.h"
#include "touch_display.h"
#include "bsp/esp-bsp.h"
#include "esp_heap_caps.h"
#include <math.h>
#include <stdio.h>
#include <string.h>

static touch_ui_actions control;
static lv_obj_t *pad, *pad_title, *cursor, *status, *sliders[4], *values[4];
static lv_obj_t *title,*hint,*cards[4],*control_labels[4],*library,*library_labels[9],*library_buttons[17],*page_button,*page_text;
static bool busy,library_open;
static unsigned mapping=1;
static uint32_t notice_until;
static bool slot_available[9]={true};
static float knobs[4] = {0.5f, 0.5f, 0.04040404f, 0.13265306f};
static uint32_t held_note;
static bool held, ready, stress;
static unsigned stress_frame;
static bool exercise;
static unsigned exercise_step;
static uint32_t exercise_started,exercise_note;
static float base_frequency=440.0f;
static const uint32_t BG = 0x0B1018, CARD = 0x162030, INK = 0xF0F4F8;
static const uint32_t MUTED = 0x96A5B8, ACCENT = 0x63DEC7;

static void value_label(unsigned k)
{
    char text[24];
    if(!mapping) {snprintf(text,sizeof text,"%d%%",(int)lroundf(knobs[k]*100));lv_label_set_text(values[k],text);return;}
    switch (k) {
    case 0: snprintf(text,sizeof text,"%d Hz", (int)lroundf(base_frequency*exp2f((knobs[0]-.5f)*2))); break;
    case 1: snprintf(text,sizeof text,"%d%%", (int)lroundf(knobs[1]*100)); break;
    case 2: snprintf(text,sizeof text,"%d ms", (int)lroundf(2+knobs[2]*198)); break;
    default: snprintf(text,sizeof text,"%d ms", (int)lroundf(20+knobs[3]*980)); break;
    }
    lv_label_set_text(values[k], text);
}

static void place_cursor(float x, float y)
{
    lv_obj_set_pos(cursor, (lv_coord_t)(10 + x*306), (lv_coord_t)(10 + (1-y)*116));
}

static void set_knob(unsigned k, float value)
{
    knobs[k] = fminf(1, fmaxf(0, value));
    lv_slider_set_value(sliders[k], (int)lroundf(knobs[k]*1000), LV_ANIM_OFF);
    value_label(k);
    control.post((inst_event_type)(INST_KNOB1+k),0,knobs[k]);
    place_cursor(knobs[0],knobs[1]);
}

static void release_pad(void)
{
    if (held) control.post(INST_NOTE_OFF,held_note,0);
    held = false;
    lv_label_set_text_static(pad_title,"HOLD TO PLAY");
    lv_obj_set_style_border_color(pad,lv_color_hex(0x304558),0);
}

static void pad_event(lv_event_t *event)
{
    if(busy)return;
    lv_event_code_t code = lv_event_get_code(event);
    if (code==LV_EVENT_PRESSED || code==LV_EVENT_PRESSING) {
        lv_indev_t *input = lv_indev_get_act();
        if (!input) return;
        lv_point_t point; lv_area_t area;
        lv_indev_get_point(input,&point); lv_obj_get_coords(pad,&area);
        set_knob(0,(float)(point.x-area.x1)/335.0f);
        set_knob(1,1.0f-(float)(point.y-area.y1)/149.0f);
        if (code==LV_EVENT_PRESSED) {
            held_note=control.new_note();
            held=control.post(INST_NOTE_ON,held_note,0);
            if (held) {
                lv_label_set_text_static(pad_title,"PLAYING");
                lv_obj_set_style_border_color(pad,lv_color_hex(ACCENT),0);
            }
        }
    } else if (code==LV_EVENT_RELEASED || code==LV_EVENT_PRESS_LOST || code==LV_EVENT_DELETE) {
        release_pad();
    }
}

static void slider_event(lv_event_t *event)
{
    if(busy)return;
    unsigned k=(unsigned)(uintptr_t)lv_event_get_user_data(event);
    set_knob(k,(float)lv_slider_get_value(lv_event_get_target(event))/1000.0f);
}

static void panic_event(lv_event_t *event)
{
    (void)event;
    control.panic();
    release_pad();
    lv_label_set_text_static(status,"STOPPED");
}

static void screen_event(lv_event_t *event)
{
    (void)event;
    control.panic(); release_pad();
}

static lv_obj_t *label(lv_obj_t *parent, const char *text, int x, int y, uint32_t color, const lv_font_t *font)
{
    lv_obj_t *obj=lv_label_create(parent);
    lv_label_set_text(obj,text); lv_obj_set_pos(obj,x,y);
    lv_obj_set_style_text_color(obj,lv_color_hex(color),0);
    lv_obj_set_style_text_font(obj,font,0);
    return obj;
}

static void set_page(bool patches)
{
    release_pad();control.panic();library_open=patches;
    if(patches) {
        lv_obj_add_flag(pad,LV_OBJ_FLAG_HIDDEN);
        for(unsigned k=0;k<4;++k)lv_obj_add_flag(cards[k],LV_OBJ_FLAG_HIDDEN);
        lv_obj_clear_flag(library,LV_OBJ_FLAG_HIDDEN);
    } else {
        lv_obj_clear_flag(pad,LV_OBJ_FLAG_HIDDEN);
        for(unsigned k=0;k<4;++k)lv_obj_clear_flag(cards[k],LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(library,LV_OBJ_FLAG_HIDDEN);
    }
    lv_label_set_text_static(page_text,patches?"BACK TO PLAY":"PATCHES");
}
static void page_event(lv_event_t *event) { (void)event;if(!busy)set_page(!library_open); }
static void library_event(lv_event_t *event)
{
    if(busy || !control.patch_action)return;
    unsigned encoded=(unsigned)(uintptr_t)lv_event_get_user_data(event);
    if(!control.patch_action(encoded&255u,(encoded&256u)!=0))lv_label_set_text_static(status,"PLEASE RETRY");
}
static lv_obj_t *button(lv_obj_t *parent,const char *text,int x,int y,int w,lv_event_cb_t callback,void *data)
{
    lv_obj_t *b=lv_btn_create(parent);lv_obj_set_pos(b,x,y);lv_obj_set_size(b,w,34);
    lv_obj_set_style_bg_color(b,lv_color_hex(CARD),0);lv_obj_set_style_shadow_width(b,0,0);
    lv_obj_t *t=label(b,text,0,0,INK,&lv_font_montserrat_14);lv_obj_center(t);
    lv_obj_add_event_cb(b,callback,LV_EVENT_CLICKED,data);return b;
}

static void redraw_stress(lv_timer_t *timer)
{
    (void)timer;
    if(exercise && lv_tick_elaps(exercise_started)>=30000) {
        exercise=false;exercise_note=0;control.panic();
    }
    if(held && exercise_note) {control.post(INST_NOTE_OFF,exercise_note,0);exercise_note=0;}
    if ((!stress && !exercise) || held || library_open || busy) return;
    if(exercise) {
        static const float pitch[]={0,.13f,.37f,.5f,.63f,.87f,1};
        set_knob(0,pitch[exercise_step%7]);
        set_knob(1,.25f+.4f*(float)(exercise_step%11)/10);
        set_knob(2,(float)((exercise_step/7)%2));set_knob(3,(float)((exercise_step/14)%2));
        if(exercise_step%5==0) {exercise_note=control.new_note();control.post(INST_NOTE_ON,exercise_note,0);}
        if(exercise_step%5==3 && exercise_note) {control.post(INST_NOTE_OFF,exercise_note,0);exercise_note=0;}
        ++exercise_step;lv_obj_invalidate(pad);return;
    }
    float phase=(float)(stress_frame++ % 100)/100.0f;
    place_cursor(phase,0.5f+0.4f*sinf(phase*6.2831853f));
    lv_obj_invalidate(pad);
}

esp_err_t touch_ui_start(const touch_ui_actions *actions)
{
    if (!actions || !actions->post || !actions->new_note || !actions->panic) return ESP_ERR_INVALID_ARG;
    control=*actions;
    esp_err_t display_error=touch_display_start();
    if (display_error!=ESP_OK) return display_error;
    if (!bsp_display_lock(2000)) return ESP_ERR_TIMEOUT;
    lv_obj_t *screen=lv_scr_act();
    lv_obj_set_style_bg_color(screen,lv_color_hex(BG),0);
    lv_obj_clear_flag(screen,LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_event_cb(screen,screen_event,LV_EVENT_SCREEN_UNLOAD_START,NULL);
    title=label(screen,"SINE",18,14,INK,&lv_font_montserrat_22);
    lv_obj_set_width(title,220);lv_label_set_long_mode(title,LV_LABEL_LONG_DOT);
    label(screen,"TOUCH SYNTH",18,44,MUTED,&lv_font_montserrat_14);
    lv_obj_t *panic=lv_btn_create(screen);
    lv_obj_set_pos(panic,254,14); lv_obj_set_size(panic,96,44);
    lv_obj_set_style_bg_color(panic,lv_color_hex(0x562F37),0);
    lv_obj_set_style_shadow_width(panic,0,0);
    lv_obj_t *ptext=label(panic,"PANIC",0,0,INK,&lv_font_montserrat_14);
    lv_obj_center(ptext);
    lv_obj_add_event_cb(panic,panic_event,LV_EVENT_PRESSED,NULL);
    status=label(screen,"READY",18,70,ACCENT,&lv_font_montserrat_14);
    pad=lv_obj_create(screen);
    lv_obj_set_pos(pad,16,98); lv_obj_set_size(pad,336,150);
    lv_obj_set_style_bg_color(pad,lv_color_hex(0x11262B),0);
    lv_obj_set_style_border_color(pad,lv_color_hex(0x304558),0);
    lv_obj_set_style_border_width(pad,2,0);
    lv_obj_set_style_pad_all(pad,0,0);
    lv_obj_clear_flag(pad,LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(pad,LV_OBJ_FLAG_PRESS_LOCK);
    pad_title=label(pad,"HOLD TO PLAY",0,0,INK,&lv_font_montserrat_22);
    lv_obj_align(pad_title,LV_ALIGN_TOP_MID,0,20);
    lv_obj_clear_flag(pad_title,LV_OBJ_FLAG_CLICKABLE);
    hint=label(pad,"X: PITCH   Y: LEVEL",0,0,MUTED,&lv_font_montserrat_14);
    lv_obj_align(hint,LV_ALIGN_BOTTOM_MID,0,-14);
    cursor=lv_obj_create(pad);
    lv_obj_set_size(cursor,12,12); lv_obj_set_style_radius(cursor,6,0);
    lv_obj_set_style_bg_opa(cursor,LV_OPA_TRANSP,0);
    lv_obj_set_style_border_color(cursor,lv_color_hex(ACCENT),0);
    lv_obj_set_style_border_width(cursor,2,0); lv_obj_clear_flag(cursor,LV_OBJ_FLAG_CLICKABLE);
    lv_obj_clear_flag(cursor,LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_event_cb(pad,pad_event,LV_EVENT_ALL,NULL);
    static const char *names[]={"PITCH","LEVEL","ATTACK","RELEASE"};
    for (unsigned k=0;k<4;++k) {
        lv_obj_t *card=lv_obj_create(screen);
        cards[k]=card;
        lv_obj_set_pos(card,16+(k%2)*172,260+(k/2)*80); lv_obj_set_size(card,164,72);
        lv_obj_set_style_pad_all(card,10,0); lv_obj_set_style_border_width(card,0,0);
        lv_obj_set_style_bg_color(card,lv_color_hex(CARD),0); lv_obj_clear_flag(card,LV_OBJ_FLAG_SCROLLABLE);
        control_labels[k]=label(card,names[k],0,0,MUTED,&lv_font_montserrat_14);
        lv_obj_set_width(control_labels[k],78);lv_label_set_long_mode(control_labels[k],LV_LABEL_LONG_DOT);
        values[k]=label(card,"",0,0,INK,&lv_font_montserrat_14);
        value_label(k); lv_obj_align(values[k],LV_ALIGN_TOP_RIGHT,0,0);
        sliders[k]=lv_slider_create(card);
        lv_obj_set_pos(sliders[k],5,35); lv_obj_set_size(sliders[k],134,10);
        lv_obj_set_ext_click_area(sliders[k],12);
        lv_slider_set_range(sliders[k],0,1000);
        lv_slider_set_value(sliders[k],(int)lroundf(knobs[k]*1000),LV_ANIM_OFF);
        lv_obj_set_style_bg_color(sliders[k],lv_color_hex(ACCENT),LV_PART_INDICATOR);
        lv_obj_set_style_bg_color(sliders[k],lv_color_hex(INK),LV_PART_KNOB);
        lv_obj_add_event_cb(sliders[k],slider_event,LV_EVENT_VALUE_CHANGED,(void *)(uintptr_t)k);
    }
    library=lv_obj_create(screen);lv_obj_set_pos(library,16,98);lv_obj_set_size(library,336,310);
    lv_obj_set_style_bg_color(library,lv_color_hex(BG),0);lv_obj_set_style_border_width(library,0,0);
    lv_obj_set_style_pad_all(library,0,0);
    for(unsigned slot=0;slot<9;++slot) {
        lv_obj_t *row=lv_obj_create(library);lv_obj_set_pos(row,0,(int)slot*70);lv_obj_set_size(row,328,64);
        lv_obj_set_style_bg_color(row,lv_color_hex(CARD),0);lv_obj_set_style_border_width(row,0,0);
        lv_obj_set_style_pad_all(row,8,0);lv_obj_clear_flag(row,LV_OBJ_FLAG_SCROLLABLE);
        library_labels[slot]=label(row,slot?"EMPTY":"Factory Sine",0,0,INK,&lv_font_montserrat_14);
        lv_obj_set_width(library_labels[slot],300);lv_label_set_long_mode(library_labels[slot],LV_LABEL_LONG_DOT);
        library_buttons[slot]=button(row,"LOAD",0,22,138,library_event,(void *)(uintptr_t)slot);
        if(slot)library_buttons[8+slot]=button(row,"SAVE HERE",150,22,150,library_event,(void *)(uintptr_t)(slot|256u));
    }
    lv_obj_add_flag(library,LV_OBJ_FLAG_HIDDEN);
    page_button=button(screen,"PATCHES",16,414,336,page_event,NULL);
    page_text=lv_obj_get_child(page_button,0);
    place_cursor(knobs[0],knobs[1]);
    lv_timer_create(redraw_stress,40,NULL);
    ready=true;
    bsp_display_unlock();
    return bsp_display_brightness_set(55);
}

void touch_ui_status(bool active, bool fault, float frequency)
{
    if (!ready || !bsp_display_lock(10)) return;
    if(busy || (int32_t)(notice_until-lv_tick_get())>0) {bsp_display_unlock();return;}
    const char *text=fault ? "AUDIO STOPPED" : active ? "PLAYING" : "READY";
    if (strcmp(lv_label_get_text(status),text)) lv_label_set_text(status,text);
    if (frequency>0 && frequency!=base_frequency) { base_frequency=frequency; value_label(0); }
    bsp_display_unlock();
}

void touch_ui_busy(bool yes,const char *text)
{
    if(!ready || !bsp_display_lock(1000))return;
    busy=yes;if(yes)release_pad();
    notice_until=!yes && strcmp(text,"READY")?lv_tick_get()+3000:0;
    lv_label_set_text(status,text);
    lv_obj_t *targets[22]={pad,sliders[0],sliders[1],sliders[2],sliders[3],page_button};
    for(unsigned k=0;k<6;++k) {if(yes)lv_obj_add_state(targets[k],LV_STATE_DISABLED);else lv_obj_clear_state(targets[k],LV_STATE_DISABLED);}
    for(unsigned k=0;k<17;++k)if(library_buttons[k]) {
        if(yes || (k<9 && !slot_available[k]))lv_obj_add_state(library_buttons[k],LV_STATE_DISABLED);
        else lv_obj_clear_state(library_buttons[k],LV_STATE_DISABLED);
    }
    bsp_display_unlock();
}
void touch_ui_patch(const char *name,const char labels[4][12],unsigned kind,const float defaults[4],float frequency,const char names[9][32],int slot)
{
    if(!ready || !bsp_display_lock(1000))return;
    release_pad();mapping=kind;base_frequency=frequency;
    lv_label_set_text(title,name);
    for(unsigned k=0;k<4;++k) {
        knobs[k]=defaults[k];lv_label_set_text(control_labels[k],labels[k]);
        lv_slider_set_value(sliders[k],(int)lroundf(knobs[k]*1000),LV_ANIM_OFF);value_label(k);
    }
    char text[64];snprintf(text,sizeof text,"X: %s   Y: %s",labels[0],labels[1]);lv_label_set_text(hint,text);
    for(unsigned k=0;k<9;++k) {
        slot_available[k]=names[k][0]!=0;
        snprintf(text,sizeof text,"%s%u   %s",(int)k==slot?"> ":"",k,names[k][0]?names[k]:"EMPTY");
        lv_label_set_text(library_labels[k],text);
        if(!slot_available[k])lv_obj_add_state(library_buttons[k],LV_STATE_DISABLED);
        else if(!busy)lv_obj_clear_state(library_buttons[k],LV_STATE_DISABLED);
    }
    place_cursor(knobs[0],knobs[1]);
    if(library_open)set_page(false);
    bsp_display_unlock();
}

void touch_ui_stress(bool enabled)
{
    if (!ready || !bsp_display_lock(10)) return;
    stress=enabled;
    if (!stress) place_cursor(knobs[0],knobs[1]);
    bsp_display_unlock();
}

void touch_ui_exercise(bool enabled)
{
    if(!ready || !bsp_display_lock(1000))return;
    if(exercise_note)control.post(INST_NOTE_OFF,exercise_note,0);
    exercise_note=0;exercise=enabled;exercise_step=0;exercise_started=lv_tick_get();
    if(enabled && library_open)set_page(false);
    if(!enabled)control.panic();
    bsp_display_unlock();
}

void *touch_ui_snapshot(size_t *bytes)
{
    *bytes=0;
    if (!ready || !bsp_display_lock(200)) return NULL;
    lv_obj_t *screen=lv_scr_act(); lv_obj_update_layout(screen);
    size_t size=lv_snapshot_buf_size_needed(screen,LV_IMG_CF_TRUE_COLOR);
    void *pixels=heap_caps_malloc(size,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    lv_img_dsc_t image={0};
    if (pixels && lv_snapshot_take_to_buf(screen,LV_IMG_CF_TRUE_COLOR,&image,pixels,size)!=LV_RES_OK) {
        heap_caps_free(pixels); pixels=NULL;
    }
    if (pixels) *bytes=image.data_size;
    bsp_display_unlock();
    return pixels;
}
