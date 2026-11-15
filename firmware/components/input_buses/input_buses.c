/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "input_buses.h"
#include <math.h>
#include <string.h>

void ib_init(ib_bank *bank)
{
    if (bank) memset(bank, 0, sizeof *bank);
}

static int unit_value(float value)
{
    return isfinite(value) && value >= 0 && value <= 1;
}

int ib_configure(ib_bank *bank, const ib_config config[IB_SLOTS], uint64_t now_us)
{
    if (!bank || !config || now_us < bank->clock_us || bank->generation == UINT32_MAX)
        return 0;
    for (unsigned i = 0; i < IB_SLOTS; ++i) {
        const ib_config *c = &config[i];
        if (!c->source_id) continue;
        if (!isfinite(c->minimum) || !isfinite(c->maximum) ||
            c->minimum >= c->maximum || !unit_value(c->fallback) ||
            !c->stale_after_us || c->invert > 1 ||
            (c->kind != IB_CONTINUOUS && c->kind != IB_BINARY)) return 0;
        if (c->kind == IB_BINARY && (c->minimum != 0 || c->maximum != 1 ||
                                     c->fallback != 0 || c->invert)) return 0;
        for (unsigned j = 0; j < i; ++j)
            if (config[j].source_id == c->source_id) return 0;
    }
    /* memmove permits using the bank's current table to explicitly reset it. */
    memmove(bank->config, config, sizeof bank->config);
    memset(bank->channel, 0, sizeof bank->channel);
    bank->clock_us = now_us;
    bank->configured_at_us = now_us;
    ++bank->generation;
    return 1;
}

static int find_slot(const ib_bank *bank, uint32_t source_id)
{
    if (!source_id) return -1;
    for (unsigned i = 0; i < IB_SLOTS; ++i)
        if (bank->config[i].source_id == source_id) return (int)i;
    return -1;
}

int ib_ingest(ib_bank *bank, uint32_t generation, const ib_sample *samples,
              size_t count, uint64_t now_us)
{
    if (!bank || !generation || generation != bank->generation ||
        now_us < bank->clock_us || count > IB_SLOTS || (!samples && count)) return 0;
    unsigned slots[IB_SLOTS];
    for (size_t i = 0; i < count; ++i) {
        int slot = find_slot(bank, samples[i].source_id);
        if (slot < 0 || samples[i].valid > 1 || samples[i].sampled_at_us > now_us ||
            samples[i].sampled_at_us < bank->configured_at_us)
            return 0;
        slots[i] = (unsigned)slot;
        const ib_channel_state *state = &bank->channel[slot];
        if (state->has_seen && samples[i].sampled_at_us < state->last_seen_us) return 0;
        for (size_t j = 0; j < i; ++j) if (slots[j] == slots[i]) return 0;
    }
    for (size_t i = 0; i < count; ++i) {
        const ib_sample *s = &samples[i];
        const ib_config *c = &bank->config[slots[i]];
        ib_channel_state *state = &bank->channel[slots[i]];
        state->has_seen = 1;
        state->last_seen_us = s->sampled_at_us;
        if (!s->valid || !isfinite(s->raw) ||
            (c->kind == IB_BINARY && s->raw != 0 && s->raw != 1)) continue;
        /* Double intermediates keep every finite float32 endpoint/raw value safe,
         * even when the float32 difference itself would overflow. */
        double u = ((double)s->raw - c->minimum) / ((double)c->maximum - c->minimum);
        state->clipped = u < 0 || u > 1;
        if (u < 0) u = 0;
        if (u > 1) u = 1;
        state->normalized = (float)(c->invert ? 1 - u : u);
        state->last_good_us = s->sampled_at_us;
        state->has_good = 1;
    }
    bank->clock_us = now_us;
    return 1;
}

int ib_snapshot_at(ib_bank *bank, uint64_t now_us, ib_snapshot *out)
{
    if (!bank || !out || now_us < bank->clock_us) return 0;
    ib_snapshot result = {0};
    result.generation = bank->generation;
    result.at_us = now_us;
    for (unsigned i = 0; i < IB_SLOTS; ++i) {
        const ib_config *c = &bank->config[i];
        const ib_channel_state *state = &bank->channel[i];
        if (!c->source_id) continue;
        int fresh = state->has_good && now_us - state->last_good_us < c->stale_after_us;
        result.value[i] = fresh ? state->normalized : c->fallback;
        result.valid[i] = fresh ? 1 : 0;
        result.clipped[i] = fresh ? state->clipped : 0;
    }
    *out = result;
    bank->clock_us = now_us;
    return 1;
}

int ib_write_buses(const ib_snapshot *snapshot, float *buses, size_t count)
{
    if (!snapshot || !buses || count < IB_BUS_COUNT) return 0;
    for (unsigned i = 0; i < IB_SLOTS; ++i)
        if (!unit_value(snapshot->value[i]) ||
            (snapshot->valid[i] != 0 && snapshot->valid[i] != 1)) return 0;
    for (unsigned i = 0; i < IB_SLOTS; ++i) {
        buses[IB_VALUE_BASE+i] = snapshot->value[i];
        buses[IB_VALID_BASE+i] = snapshot->valid[i];
    }
    return 1;
}
