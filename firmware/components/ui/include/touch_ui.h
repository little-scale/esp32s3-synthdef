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
} touch_ui_actions;
esp_err_t touch_ui_start(const touch_ui_actions *actions);
void touch_ui_status(bool active, bool fault, float base_frequency);
void touch_ui_stress(bool enabled);
/* Explicit bounded diagnostic; uses the normal controls/queues for 30 seconds. */
void touch_ui_exercise(bool enabled);
void touch_ui_busy(bool busy,const char *text);
void touch_ui_patch(const char *name,const char labels[4][12],unsigned mapping,const float knobs[4],float base_frequency,const char names[9][32],int slot);
/* Snapshot caller frees the PSRAM pixels; call off the audio task. */
void *touch_ui_snapshot(size_t *bytes);
