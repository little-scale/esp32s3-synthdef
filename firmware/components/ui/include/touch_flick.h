/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stdbool.h>
#include <stdint.h>

/* Body drags retain their existing meaning unless released as a short,
 * predominantly horizontal flick. Use only coordinates sampled while down:
 * touch controllers need not provide a valid position on finger-up. */
typedef struct {
    int start_x,end_x,min_y,max_y;
    uint32_t started;
    bool active;
} touch_flick;
static inline void touch_flick_begin(touch_flick *f,int x,int y,uint32_t now)
{
    *f=(touch_flick){.start_x=x,.end_x=x,.min_y=y,.max_y=y,.started=now,.active=true};
}
static inline void touch_flick_move(touch_flick *f,int x,int y)
{
    if(!f->active)return;
    f->end_x=x;if(y<f->min_y)f->min_y=y;if(y>f->max_y)f->max_y=y;
}
static inline bool touch_flick_end(touch_flick *f,uint32_t now,bool *next)
{
    bool active=f->active;f->active=false;
    int dx=f->end_x-f->start_x,ax=dx<0?-dx:dx;
    if(!active || now-f->started>500 || ax<88 || ax<2*(f->max_y-f->min_y))return false;
    *next=dx<0;return true;
}
