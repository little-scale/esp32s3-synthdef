/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "voice_pe_codec_sequence.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    uint8_t reg[2][128], page;
    unsigned calls, fail_at, unmute_writes, delay_ms;
    unsigned no_clock, reset_stuck;
    int corrupt_page, corrupt_reg;
} model;

static void defaults(model *m)
{
    memset(m->reg, 0, sizeof m->reg);
    m->page = 0;
    m->reg[0][64] = 0x0c;
    m->reg[0][11] = m->reg[0][12] = 1;
    for (unsigned i = 16; i <= 19; ++i) m->reg[1][i] = 0x40;
}
static void setup(model *m)
{
    memset(m, 0, sizeof *m);
    m->corrupt_page = m->corrupt_reg = -1;
    defaults(m);
}
static int write_byte(void *ctx, uint8_t r, uint8_t v)
{
    model *m = ctx;
    if (++m->calls == m->fail_at) return 0;
    assert(r < 128);
    if (!r) { assert(v < 2); m->page = v; return 1; }
    if (m->page == 0 && r == 1 && v == 1) {
        defaults(m); m->reg[0][1] = m->reset_stuck ? 1 : 0;
        return 1;
    }
    if ((m->page == 0 && r == 64 && (v & 0x0c) != 0x0c) ||
        (m->page == 1 && r >= 16 && r <= 19 && !(v & 0x40)))
        ++m->unmute_writes;
    m->reg[m->page][r] = v;
    return 1;
}
static int read_byte(void *ctx, uint8_t r, uint8_t *v)
{
    model *m = ctx;
    if (++m->calls == m->fail_at) return 0;
    assert(r < 128);
    *v = m->reg[m->page][r];
    if (!m->page && r == 37) {
        /* Independent status model: DAC enable and analog enables power up
         * only with a clock and after the reference's startup delay. */
        *v = !m->no_clock && m->delay_ms >= 2500 &&
             (m->reg[0][63] & 0xc0) == 0xc0 &&
             (m->reg[1][9] & 0x3c) == 0x3c ? 0xee : 0;
    }
    if (m->page == m->corrupt_page && r == m->corrupt_reg) *v ^= 0xff;
    return 1;
}
static void wait_ms(void *ctx, unsigned ms) { ((model *)ctx)->delay_ms += ms; }
static vpe_codec_io io_for(model *m)
{
    return (vpe_codec_io){m, write_byte, read_byte, wait_ms};
}
static void assert_muted(const model *m)
{
    assert((m->reg[0][64] & 0x0c) == 0x0c);
    for (unsigned i = 16; i <= 19; ++i) assert(m->reg[1][i] & 0x40);
}
static int selected_gain;
static unsigned selected_rate=48000;
static int init(vpe_codec *c,const vpe_codec_io *io)
{return vpe_codec_init_muted_rate(c,io,selected_gain,selected_rate);}
static int unmute(vpe_codec *c)
{return selected_gain==-24?vpe_codec_unmute_test(c):vpe_codec_unmute(c);}
static void test_profile(int gain_db,unsigned rate)
{
    selected_gain=gain_db;selected_rate=rate;
    model m; vpe_codec c; setup(&m); vpe_codec_io io = io_for(&m);
    assert(init(&c, &io));
    assert(c.gain_db==gain_db);
    assert(c.sample_rate==rate && m.reg[0][11]==(rate==16000?0x86:0x82));
    assert(m.reg[0][65]==(gain_db==0?0:0xd0) && m.reg[0][66]==m.reg[0][65]);
    assert(c.ready && c.muted && c.power_flags == 0xee && c.checks >= 20);
    assert(m.delay_ms >= 2500 && !m.unmute_writes); assert_muted(&m);
    unsigned init_calls = m.calls;
    assert(unmute(&c) && c.ready && !c.muted);
    assert(vpe_codec_mute(&c) && c.muted); assert_muted(&m);
    assert(init(&c, &c.io));

    for (unsigned fault = 1; fault <= init_calls; ++fault) {
        setup(&m); m.fail_at = fault; io = io_for(&m);
        assert(!init(&c, &io));
        assert(!c.ready && !m.unmute_writes);
        assert(!unmute(&c)); assert_muted(&m);
    }
    printf("PASS (%u Hz, %d dB): all %u initialization I/O failure positions leave readiness false and never unmute\n", rate,gain_db,init_calls);
    static const int corrupt[][2] = {{0,11},{0,12},{0,14},{0,27},{0,56},
        {0,31},{0,32},{0,60},{0,63},{0,64},{0,65},{0,66},
        {1,12},{1,13},{1,14},{1,15},{1,16},{1,17},{1,18},{1,19},{1,9}};
    for (unsigned i = 0; i < sizeof corrupt/sizeof corrupt[0]; ++i) {
        setup(&m); m.corrupt_page = corrupt[i][0]; m.corrupt_reg = corrupt[i][1]; io = io_for(&m);
        assert(!init(&c, &io) && !c.ready && !m.unmute_writes);
    }
    setup(&m); m.no_clock = 1; io = io_for(&m);
    assert(!init(&c, &io) && !c.ready && m.delay_ms <= 3100);
    setup(&m); m.reset_stuck = 1; io = io_for(&m);
    assert(!init(&c, &io) && !c.ready && m.delay_ms == 2);

    setup(&m); io = io_for(&m); assert(init(&c, &io));
    m.reg[0][11] ^= 4; /* A mismatched native-rate divider must remain muted. */
    assert(!unmute(&c) && !c.ready); assert_muted(&m);
    setup(&m); io = io_for(&m); assert(init(&c, &io));
    unsigned before = m.calls;
    assert(unmute(&c)); unsigned unmute_calls = m.calls-before;
    for (unsigned fault = 1; fault <= unmute_calls; ++fault) {
        setup(&m); io = io_for(&m); assert(init(&c, &io));
        m.fail_at = m.calls+fault;
        assert(!unmute(&c) && !c.ready); assert_muted(&m);
    }
    setup(&m); io = io_for(&m); assert(init(&c, &io));
    m.reg[0][65] ^= 1; /* Unexpected gain cannot open either profile. */
    assert(!unmute(&c) && !c.ready); assert_muted(&m);
    assert(!init(&c, NULL) && !c.ready);
    assert(!init(NULL, &io) && !vpe_codec_mute(NULL));
    printf("PASS: %zu corrupted readbacks, missing clock, stuck reset, %u unmute failures, fixed gain guard and reinitialization\n", sizeof corrupt/sizeof corrupt[0], unmute_calls);
}

int main(void)
{
    test_profile(-24,48000);test_profile(0,48000);
    test_profile(-24,16000);test_profile(0,16000);
    model m;vpe_codec c;setup(&m);vpe_codec_io io=io_for(&m);
    assert(vpe_codec_init_muted(&c,&io) && c.gain_db==-24);
    assert(vpe_codec_unmute_test(&c));
    assert(vpe_codec_init_muted_gain(&c,&io,0));
    assert(!vpe_codec_unmute_test(&c) && !c.ready);assert_muted(&m);
    const int invalid[]={-25,-1,1,6};
    for(unsigned i=0;i<sizeof invalid/sizeof invalid[0];++i){
        setup(&m);io=io_for(&m);
        assert(!vpe_codec_init_muted_gain(&c,&io,invalid[i]) && !c.ready && !m.unmute_writes);assert_muted(&m);
    }
    assert(vpe_codec_init_muted_gain(&c,&io,0));c.gain_db=6;
    assert(!vpe_codec_unmute(&c) && !c.ready);assert_muted(&m);
    setup(&m);io=io_for(&m);
    assert(!vpe_codec_init_muted_rate(&c,&io,0,44100) && !c.ready);assert_muted(&m);
    puts("PASS: commissioning wrapper remains -24 dB; bench unmute rejects unity; unsupported profiles fail muted");
}
