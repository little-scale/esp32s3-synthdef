/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "instrument.h"
#include <math.h>
#include <string.h>
static const char *const knob_names[4] = {"knob1", "knob2", "knob3", "knob4"};

static int live_index(const fm_graph *g, const char *name)
{
    unsigned i, j;
    for (i = 0; i < g->names; ++i) {
        if (strcmp(g->control_name[i].name, name)) continue;
        unsigned index = g->control_name[i].index;
        int found=0;
        for (j = 0; j < g->nodes; ++j) {
            const fm_node *n = &g->node[j];
            if(n->type!=FM_Control || n->special<0 || index<(unsigned)n->special ||
               index>=(unsigned)n->special+n->outputs)continue;
            /* A scalar alias would make fm_set reject updates after prepare.
             * Reject it up front rather than bypassing that engine contract. */
            if(n->rate==0)return -1;
            if(n->rate==1)found=1;
        }
        return found?(int)index:-1;
    }
    return -1;
}

int instrument_init(instrument *s, fm_graph *g, fm_voice *v, fm_scratch *scratch,
                    float *arena, uint32_t samples, uint32_t rate)
{
    if (!s || !g || !v || !scratch || (rate != 44100 && rate != 48000)) return 0;
    int16_t indices[7];
    static const char *const names[]={"freq","amp","gate","knob1","knob2","knob3","knob4"};
    for(unsigned i=0;i<7;++i)indices[i]=(int16_t)live_index(g,names[i]);
    uint32_t need = fm_delay_required(g, (float)rate);
    if (need == UINT32_MAX || need > samples || (need && !arena) ||
        indices[0]<0 || indices[1]<0 || indices[2]<0) return 0;
    memset(s, 0, sizeof *s);
    memset(v, 0, sizeof *v);
    s->graph = g; s->voice = v; s->scratch = scratch;
    s->arena = arena; s->arena_samples = samples; s->sample_rate = rate;
    memcpy(s->control_index,indices,sizeof indices);
    s->frequency = 440.0f; s->amplitude = 0.5f; s->master_gain = 0.8f;
    for(unsigned i=0;i<g->names;++i) {
        if(!strcmp(g->control_name[i].name,"freq"))s->frequency=g->defaults[g->control_name[i].index];
        if(!strcmp(g->control_name[i].name,"amp"))s->amplitude=g->defaults[g->control_name[i].index];
    }
    for (unsigned k = 0; k < 4; ++k) {
        if (indices[3+k]<0) continue;
        s->knob_mask |= 1u << k;
        for (unsigned i = 0; i < g->names; ++i)
            if (!strcmp(g->control_name[i].name, knob_names[k]))
                s->knob[k] = g->defaults[g->control_name[i].index];
    }
    return 1;
}

void instrument_panic(instrument *s)
{
    s->voice->active = 0;
    s->held = 0;
    s->release_frames = 0;
}

int instrument_apply(instrument *s, const inst_event *e)
{
    if (!e) return 0;
    switch (e->type) {
    case INST_NOTE_OFF:
        if (s->held && e->note_id == s->note_id) {
            s->voice->control[s->control_index[2]]=0;
            s->held = 0; s->release_frames = 0;
        }
        return 1;
    case INST_FREQ:
        if (!isfinite(e->value) || e->value < 20.0f || e->value > 20000.0f) break;
        s->frequency = e->value;
        if (s->voice->active) s->voice->control[s->control_index[0]]=e->value;
        return 1;
    case INST_AMP:
        if (!isfinite(e->value) || e->value < 0.0f || e->value > 1.0f) break;
        s->amplitude = e->value;
        if (s->voice->active) s->voice->control[s->control_index[1]]=e->value;
        return 1;
    case INST_KNOB1: case INST_KNOB2: case INST_KNOB3: case INST_KNOB4: {
        unsigned k = (unsigned)e->type - INST_KNOB1;
        if (!(s->knob_mask & (1u << k)) || !isfinite(e->value) || e->value < 0 || e->value > 1) break;
        s->knob[k] = e->value;
        if (s->voice->active) s->voice->control[s->control_index[3+k]]=e->value;
        return 1;
    }
    case INST_NOTE_ON: {
        uint64_t begin = s->clock_us ? s->clock_us() : 0;
        instrument_panic(s);
        if (!fm_start(s->voice, s->graph, (float)s->sample_rate) ||
            !fm_bind_delay(s->voice, s->graph, s->arena, s->arena_samples)) break;
        uint64_t reset_done=s->clock_us?s->clock_us():0;
        fm_seed(s->voice, 0);
        s->voice->control[s->control_index[0]]=s->frequency;
        s->voice->control[s->control_index[1]]=s->amplitude;
        s->voice->control[s->control_index[2]]=1;
        for (unsigned k = 0; k < 4; ++k)
            if (s->knob_mask & (1u << k)) s->voice->control[s->control_index[3+k]]=s->knob[k];
        uint64_t controls_done=s->clock_us?s->clock_us():0;
        fm_prepare(s->graph, s->voice, s->scratch);
        if (s->clock_us) {
            uint64_t end=s->clock_us();
            s->reset_us=(uint32_t)(reset_done-begin);
            s->controls_us=(uint32_t)(controls_done-reset_done);
            s->prepare_us=(uint32_t)(end-controls_done);
            uint64_t elapsed = end - begin;
            if (elapsed > s->preparation_max_us)
                s->preparation_max_us = elapsed > UINT32_MAX ? UINT32_MAX : (uint32_t)elapsed;
        }
        if (s->voice->fault) { ++s->faults; instrument_panic(s); break; }
        s->note_id = e->note_id; s->held = 1; s->fade_frame = 0;
        return 1;
    }
    default: break;
    }
    ++s->rejected;
    return 0;
}

void instrument_pcm(const float stereo[FM_BLOCK * 2], int16_t mono[FM_BLOCK],
                    float gain, uint64_t *nonfinite, uint64_t *clipped)
{
    for (unsigned i = 0; i < FM_BLOCK; ++i) {
        float l = stereo[2*i], r = stereo[2*i+1];
        float x = (0.5f*l + 0.5f*r) * gain;
        if (!isfinite(l) || !isfinite(r) || !isfinite(x)) { x = 0; ++*nonfinite; }
        if (x > 1.0f) { x = 1.0f; ++*clipped; }
        if (x < -1.0f) { x = -1.0f; ++*clipped; }
        /* Explicit nearest/even rounding after finite checks and saturation.
         * Xtensa has fast bounded float/int conversions; lrintf takes a library
         * call for every sample. Keep the established quantization rule. */
        float scaled = x * 32767.0f;
        int32_t quantized = (int32_t)scaled;
        float fraction = scaled - (float)quantized;
        if (fraction > 0.5f || (fraction == 0.5f && (quantized & 1))) ++quantized;
        else if (fraction < -0.5f || (fraction == -0.5f && (quantized & 1))) --quantized;
        mono[i] = (int16_t)quantized;
    }
}

void instrument_apply_batch(instrument *s, const inst_event *events, unsigned count)
{
    s->reset_us=s->controls_us=s->prepare_us=0;
    /* One voice admits only the newest start at a boundary. A later release
     * cancels that start and its implied steal, rather than resurrecting an
     * older pending/held note that the producer already replaced. */
    unsigned newest = count;
    for (unsigned i = 0; i < count; ++i)
        if (events[i].type == INST_NOTE_ON) newest = i;
    for (int kind = INST_NOTE_OFF; kind <= INST_NOTE_ON; ++kind) {
        for (unsigned i = 0; i < count; ++i) {
            if ((int)events[i].type != kind) continue;
            int cancelled = 0;
            if (kind == INST_NOTE_ON) {
                if (i != newest) continue;
                for (unsigned j = i + 1; j < count; ++j)
                    if (events[j].type == INST_NOTE_OFF && events[j].note_id == events[i].note_id)
                        cancelled = 1;
            }
            if (cancelled) instrument_panic(s);
            else instrument_apply(s, &events[i]);
        }
    }
}

void instrument_render(instrument *s, int16_t mono[FM_BLOCK])
{
    uint64_t begin=s->clock_us?s->clock_us():0;
    float stereo[FM_BLOCK * 2] = {0};
    if (s->voice->active) {
        fm_render(s->graph, s->voice, s->scratch, stereo);
        if (s->voice->fault) {
            ++s->faults; instrument_panic(s); memset(stereo, 0, sizeof stereo);
        } else {
            for (unsigned i = 0; i < FM_BLOCK && s->fade_frame < 128; ++i, ++s->fade_frame) {
                float fade = (float)s->fade_frame / 128.0f;
                stereo[2*i] *= fade; stereo[2*i+1] *= fade;
            }
        }
        if (!s->held) {
            s->release_frames += FM_BLOCK;
            if (s->release_frames >= (uint64_t)s->sample_rate * 10) instrument_panic(s);
        }
    }
    uint64_t dsp_done=s->clock_us?s->clock_us():0;
    instrument_pcm(stereo, mono, s->master_gain, &s->nonfinite, &s->clipped);
    if(s->clock_us) {s->dsp_us=(uint32_t)(dsp_done-begin);s->pcm_us=(uint32_t)(s->clock_us()-dsp_done);}
    s->frame += FM_BLOCK;
}
