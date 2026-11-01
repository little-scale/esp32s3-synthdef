/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"
#include "instrument.h"
typedef struct {
    bool (*post)(inst_event_type type, uint32_t note, float value);
    uint32_t (*new_note)(void);
    void (*panic)(void);
    bool (*patch_action)(unsigned slot,bool save);
    bool (*master_action)(unsigned slot);
    bool (*volume)(unsigned percent,bool save);
    bool (*effect)(unsigned parameter,float value);
    bool (*effect_save)(void);
} touch_ui_actions;
esp_err_t touch_ui_start(const touch_ui_actions *actions);
void touch_ui_status(bool active, bool fault, float base_frequency);
/* Recent audio block budget usage, in tenths of a percent; UINT32_MAX = unavailable. */
void touch_ui_cpu(uint32_t average,uint32_t peak);
/* UI-only snapshot; no Wi-Fi calls or audio work inside this function. */
void touch_ui_connectivity(const char *name,const char *id,bool online,int rssi,bool receiving);
void touch_ui_playback(bool continuous);
void touch_ui_master(const char *fx_name,int selected);
void touch_ui_volume(unsigned percent);
void touch_ui_battery(void);
void touch_ui_stress(bool enabled);
void touch_ui_effect(const float value[3]);
/* Explicit bounded diagnostic; uses the normal controls/queues for 30 seconds. */
void touch_ui_exercise(bool enabled);
void touch_ui_busy(bool busy,const char *text);
void touch_ui_patch(const char *name,const char labels[4][12],unsigned mapping,const float knobs[4],float base_frequency,const char names[2][32],int slot,const char *source,size_t source_bytes);
/* true: code/play screen; false: controls. Also used by USB diagnostics. */
void touch_ui_code(bool visible);
/* Diagnostic next/previous; touch navigation is exclusively through CONTROLS. */
void touch_ui_step_patch(bool next);
/* Snapshot caller frees the PSRAM pixels; call off the audio task. */
void *touch_ui_snapshot(size_t *bytes);
