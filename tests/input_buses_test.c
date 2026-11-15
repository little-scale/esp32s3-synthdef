/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "input_buses.h"
#include "fm_synth.h"
#include <assert.h>
#include <float.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static fm_graph graph;
static fm_voice main_voice, fx_voice;
static fm_scratch scratch;
static ib_bank bank;
static ib_config config[IB_SLOTS];
static const float expected[IB_SLOTS] = {0, .25f, .5f, .25f, 1, 1, 0, .5f};

static void setup(void)
{
    ib_init(&bank);
    memset(config, 0, sizeof config);
    for (unsigned i = 0; i < IB_SLOTS; ++i)
        config[i] = (ib_config){i+1, 0, 100, .2f, 1000, IB_CONTINUOUS, 0};
    config[2].minimum = -50; config[2].maximum = 50;
    config[3].invert = 1;
    config[4] = (ib_config){5, 0, 1, 0, 1000, IB_BINARY, 0};
    assert(ib_configure(&bank, config, 0));
}

static void populate(void)
{
    const float raw[IB_SLOTS] = {0, 25, 0, 75, 1, 150, -100, 50};
    ib_sample samples[IB_SLOTS];
    for (unsigned i = 0; i < IB_SLOTS; ++i)
        samples[i] = (ib_sample){i+1, raw[i], 100, 1};
    assert(ib_ingest(&bank, bank.generation, samples, IB_SLOTS, 100));
}

static void check_snapshot(void)
{
    ib_snapshot s;
    assert(ib_snapshot_at(&bank, 100, &s));
    for (unsigned i = 0; i < IB_SLOTS; ++i) {
        assert(s.value[i] == expected[i] && s.valid[i] == 1);
        assert(s.clipped[i] == (unsigned)(i == 5 || i == 6));
    }
}

static void invalid_batches(void)
{
    ib_bank before = bank;
    ib_sample samples[2] = {{1, 100, 101, 1}, {999, 0, 101, 1}};
    assert(!ib_ingest(&bank, bank.generation, samples, 2, 101));
    assert(!memcmp(&before, &bank, sizeof bank)); /* First sample not applied. */
    samples[1].source_id = 1;
    assert(!ib_ingest(&bank, bank.generation, samples, 2, 101));
    samples[1].source_id = 2; samples[1].sampled_at_us = 102;
    assert(!ib_ingest(&bank, bank.generation, samples, 2, 101));
    samples[1].sampled_at_us = 99;
    assert(!ib_ingest(&bank, bank.generation, samples, 2, 101));
    samples[1].sampled_at_us = 101; samples[1].valid = 2;
    assert(!ib_ingest(&bank, bank.generation, samples, 2, 101));
    assert(!ib_ingest(&bank, 0, samples, 1, 101));
    assert(!ib_ingest(&bank, bank.generation+1, samples, 1, 101));
    assert(!ib_ingest(&bank, bank.generation, samples, 1, 99));
    assert(!ib_ingest(&bank, bank.generation, NULL, 1, 101));
    assert(!ib_ingest(&bank, bank.generation, samples, IB_SLOTS+1, 101));
    assert(!memcmp(&before, &bank, sizeof bank));
}

static void freshness_and_config(void)
{
    ib_snapshot s;
    ib_sample failed[] = {{1, NAN, 600, 1}, {2, INFINITY, 600, 1},
                          {3, 1, 600, 0}, {5, .5f, 600, 1}};
    assert(ib_ingest(&bank, bank.generation, failed, 4, 600));
    assert(ib_snapshot_at(&bank, 1099, &s));
    assert(s.valid[0] == 1 && s.value[0] == 0 && s.valid[4] == 1);
    assert(ib_snapshot_at(&bank, 1100, &s));
    for (unsigned i = 0; i < IB_SLOTS; ++i) {
        assert(s.value[i] == config[i].fallback && s.valid[i] == 0 && !s.clipped[i]);
    }
    ib_sample recovered = {2, 25, 1100, 1};
    assert(ib_ingest(&bank, bank.generation, &recovered, 1, 1100));
    assert(ib_snapshot_at(&bank, 1100, &s));
    assert(s.value[1] == .25f && s.valid[1] == 1 && s.valid[0] == 0);
    recovered.sampled_at_us = 2000; /* unchanged value still refreshes freshness */
    assert(ib_ingest(&bank, bank.generation, &recovered, 1, 2000));
    assert(ib_snapshot_at(&bank, 2999, &s) && s.valid[1] == 1);
    assert(ib_snapshot_at(&bank, 3000, &s) && s.valid[1] == 0);
    ib_bank before = bank;
    ib_snapshot saved = s;
    assert(!ib_snapshot_at(&bank, 2999, &s));
    assert(!memcmp(&s, &saved, sizeof s) && !memcmp(&bank, &before, sizeof bank));
    config[7].source_id = 2; /* Duplicate config rejected atomically. */
    assert(!ib_configure(&bank, config, 3000));
    assert(!memcmp(&bank, &before, sizeof bank));
    config[7].source_id = 8;
    uint32_t old_generation = bank.generation;
    config[1].source_id = 0; /* Hole does not renumber any later slot. */
    assert(ib_configure(&bank, config, 3000));
    assert(bank.config[2].source_id == 3 && bank.config[7].source_id == 8);
    assert(ib_snapshot_at(&bank, 3000, &s) && s.value[1] == 0 && s.valid[1] == 0);
    recovered = (ib_sample){3, 50, 3000, 1};
    assert(!ib_ingest(&bank, old_generation, &recovered, 1, 3000));
    recovered.sampled_at_us = 2999;
    assert(!ib_ingest(&bank, bank.generation, &recovered, 1, 3000));
    recovered.sampled_at_us = 3000;
    assert(ib_ingest(&bank, bank.generation, &recovered, 1, 3000));
    assert(ib_snapshot_at(&bank, 3000, &s) && s.value[2] == 1 && s.valid[2] == 1);
    for (unsigned i = 0; i < IB_SLOTS; ++i) if (i != 2) assert(s.valid[i] == 0);
    /* Full disable clears output, even though prior cached readings existed. */
    memset(config, 0, sizeof config);
    assert(ib_configure(&bank, config, 3000) && ib_snapshot_at(&bank, 3000, &s));
    for (unsigned i = 0; i < IB_SLOTS; ++i) assert(s.value[i] == 0 && s.valid[i] == 0);
}

static void limits(void)
{
    setup();
    ib_config good = config[0];
    const float invalid[] = {NAN, INFINITY, -INFINITY};
    for (unsigned i = 0; i < 3; ++i) {
        config[0].minimum = invalid[i]; assert(!ib_configure(&bank, config, 0)); config[0] = good;
        config[0].maximum = invalid[i]; assert(!ib_configure(&bank, config, 0)); config[0] = good;
        config[0].fallback = invalid[i]; assert(!ib_configure(&bank, config, 0)); config[0] = good;
    }
    config[0].maximum = 0; assert(!ib_configure(&bank, config, 0)); config[0] = good;
    config[0].maximum = -1; assert(!ib_configure(&bank, config, 0)); config[0] = good;
    config[0].fallback = 2; assert(!ib_configure(&bank, config, 0)); config[0] = good;
    config[0].stale_after_us = 0; assert(!ib_configure(&bank, config, 0)); config[0] = good;
    config[0].kind = (ib_kind)9; assert(!ib_configure(&bank, config, 0)); config[0] = good;
    config[0].invert = 2; assert(!ib_configure(&bank, config, 0)); config[0] = good;
    config[4].fallback = .5f; assert(!ib_configure(&bank, config, 0)); config[4].fallback = 0;
    config[4].invert = 1; assert(!ib_configure(&bank, config, 0)); config[4].invert = 0;
    config[0].minimum = -FLT_MAX; config[0].maximum = FLT_MAX;
    config[1].maximum = nextafterf(0, 1);
    assert(ib_configure(&bank, config, 0));
    ib_sample samples[] = {{1, 0, 0, 1}, {2, FLT_MAX, 0, 1}};
    ib_snapshot s;
    assert(ib_ingest(&bank, bank.generation, samples, 2, 0));
    assert(ib_snapshot_at(&bank, 0, &s));
    assert(s.value[0] == .5f && s.value[1] == 1 && s.valid[0] == 1 && s.clipped[1]);
    /* No timestamp-add overflow at the end of a 64-bit clock. */
    samples[0].sampled_at_us = UINT64_MAX-10;
    assert(ib_ingest(&bank, bank.generation, samples, 1, UINT64_MAX-10));
    assert(ib_snapshot_at(&bank, UINT64_MAX, &s) && s.valid[0] == 1);
    assert(!ib_snapshot_at(&bank, 0, &s));
    bank.generation = UINT32_MAX;
    assert(!ib_configure(&bank, config, UINT64_MAX));
}

static void publish_bounds(void)
{
    setup(); populate();
    ib_snapshot s;
    assert(ib_snapshot_at(&bank, 100, &s));
    float buses[IB_BUS_COUNT+1], before[IB_BUS_COUNT+1];
    for (unsigned i = 0; i <= IB_BUS_COUNT; ++i) buses[i] = -.125f;
    memcpy(before, buses, sizeof buses);
    assert(!ib_write_buses(&s, buses, IB_BUS_COUNT-1));
    assert(!memcmp(before, buses, sizeof buses));
    ib_snapshot bad = s; bad.value[7] = NAN;
    assert(!ib_write_buses(&bad, buses, IB_BUS_COUNT));
    bad = s; bad.valid[7] = .5f;
    assert(!ib_write_buses(&bad, buses, IB_BUS_COUNT));
    assert(!memcmp(before, buses, sizeof buses));
    assert(ib_write_buses(&s, buses, IB_BUS_COUNT));
    for (unsigned i = 0; i < IB_VALUE_BASE; ++i) assert(buses[i] == before[i]);
    assert(buses[IB_BUS_COUNT] == before[IB_BUS_COUNT]);
    for (unsigned i = 0; i < IB_SLOTS; ++i)
        assert(buses[IB_VALUE_BASE+i] == expected[i] && buses[IB_VALID_BASE+i] == 1);
}

static void render_check(fm_voice *voice, float left, float right)
{
    float output[FM_BLOCK*2];
    for (unsigned b = 0; b < 2; ++b) {
        memset(output, 0, sizeof output);
        fm_render(&graph, voice, &scratch, output);
        assert(!voice->fault);
    }
    /* K2A has settled after two blocks; all frames must match, not just first. */
    for (unsigned f = 0; f < FM_BLOCK; ++f)
        assert(fabsf(output[f*2]-left) < 1e-6f && fabsf(output[f*2+1]-right) < 1e-6f);
}

static void engine_check(const char *path, unsigned rate)
{
    unsigned char bytes[FM_FILE_BYTES]; char error[192];
    FILE *f = fopen(path, "rb"); assert(f);
    size_t n = fread(bytes, 1, sizeof bytes, f); assert(!fclose(f));
    assert(fm_load(&graph, bytes, n, error, sizeof error));
    setup(); populate();
    ib_snapshot s; float buses[IB_BUS_COUNT] = {0};
    assert(ib_snapshot_at(&bank, 100, &s) && ib_write_buses(&s, buses, IB_BUS_COUNT));
    for (unsigned slot = 0; slot < IB_SLOTS; ++slot) {
        assert(fm_start(&main_voice, &graph, (float)rate));
        assert(fm_start(&fx_voice, &graph, (float)rate));
        assert(fm_set(&main_voice, &graph, "slot", (float)slot));
        assert(fm_set(&fx_voice, &graph, "slot", (float)slot));
        assert(fm_bind_control_buses(&main_voice, buses, IB_BUS_COUNT));
        assert(fm_bind_control_buses(&fx_voice, buses, IB_BUS_COUNT));
        render_check(&main_voice, expected[slot], 1);
        render_check(&fx_voice, expected[slot], 1);
    }
    assert(ib_snapshot_at(&bank, 1100, &s) && ib_write_buses(&s, buses, IB_BUS_COUNT));
    render_check(&main_voice, .2f, 0); render_check(&fx_voice, .2f, 0);
    /* fm_start clears binding: required rebind is exercised, not assumed. */
    assert(fm_start(&main_voice, &graph, (float)rate)); render_check(&main_voice, 0, 0);
    assert(fm_bind_control_buses(&main_voice, buses, IB_BUS_COUNT)); render_check(&main_voice, .2f, 0);
    main_voice.active = 0;
    ib_sample recovered = {1, 50, 1200, 1};
    assert(ib_ingest(&bank, bank.generation, &recovered, 1, 1200));
    assert(ib_snapshot_at(&bank, 1200, &s) && ib_write_buses(&s, buses, IB_BUS_COUNT));
    assert(!main_voice.active); /* Publication never owns the voice lifecycle. */
    printf("PASS: normalized In.kr, all 8 slots, two engine voices, stale validity and rebind at %u Hz\n", rate);
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    assert(!ib_configure(NULL, config, 0) && !ib_ingest(NULL, 1, NULL, 0, 0));
    assert(!ib_snapshot_at(NULL, 0, NULL) && !ib_write_buses(NULL, NULL, 0));
    setup();
    ib_snapshot initial; assert(ib_snapshot_at(&bank, 0, &initial));
    for (unsigned i = 0; i < IB_SLOTS; ++i)
        assert(initial.value[i] == config[i].fallback && initial.valid[i] == 0);
    populate(); check_snapshot(); invalid_batches(); freshness_and_config(); limits(); publish_bounds();
    puts("PASS: normalization, clipping, inversion, binary levels, invalid data/config, timestamps, expiry/recovery, stable slots, generations and bounded publication");
    engine_check(argv[1], 16000); engine_check(argv[1], 44100); engine_check(argv[1], 48000);
    return 0;
}
