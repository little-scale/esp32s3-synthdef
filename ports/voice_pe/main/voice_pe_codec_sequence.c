/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "voice_pe_codec_sequence.h"
#include <string.h>

/* Board routing follows the pinned ESPHome AIC3204 driver. Register fields:
 * TI SLAA557 pp. 96, 104, 110-111, 126-127. Keep digital AND analog mute.
 * There is no assumed chip-ID register; address ACK isn't unique identity. */
static int page(vpe_codec *c, uint8_t p) { return c->io.write(c->io.context, 0, p); }
static int write_reg(vpe_codec *c, uint8_t p, uint8_t r, uint8_t v)
{
    return page(c, p) && c->io.write(c->io.context, r, v);
}
static int read_reg(vpe_codec *c, uint8_t p, uint8_t r, uint8_t *v)
{
    return page(c, p) && c->io.read(c->io.context, r, v);
}
static int check(vpe_codec *c, uint8_t p, uint8_t r, uint8_t value, uint8_t mask)
{
    uint8_t got;
    if (!read_reg(c, p, r, &got) || (got & mask) != (value & mask)) return 0;
    ++c->checks;
    return 1;
}
static int mute_writes(vpe_codec *c)
{
    /* Attempt every independent mute even if a previous transaction fails. */
    int ok = write_reg(c, 0, 64, 0x0c);
    ok = write_reg(c, 1, 16, 0x7e) && ok;
    ok = write_reg(c, 1, 17, 0x7e) && ok;
    ok = write_reg(c, 1, 18, 0x40) && ok;
    ok = write_reg(c, 1, 19, 0x40) && ok;
    return ok;
}
static int fail(vpe_codec *c)
{
    c->ready = 0;
    c->muted = 0; /* Unknown until all mute readbacks pass. */
    (void)mute_writes(c);
    return 0;
}
int vpe_codec_check_muted(vpe_codec *c)
{
    if (!c || !c->io.read || !c->io.write) return 0;
    if (!check(c, 0, 64, 0x0c, 0x0c) ||
        !check(c, 1, 16, 0x7e, 0x7f) || !check(c, 1, 17, 0x7e, 0x7f) ||
        !check(c, 1, 18, 0x40, 0x7f) || !check(c, 1, 19, 0x40, 0x7f))
        return fail(c);
    c->muted = 1;
    return 1;
}
int vpe_codec_mute(vpe_codec *c)
{
    if (!c || !c->io.read || !c->io.write) return 0;
    c->muted = 0;
    if (!mute_writes(c)) return fail(c);
    return vpe_codec_check_muted(c);
}
int vpe_codec_init_muted_rate(vpe_codec *c,const vpe_codec_io *io,int gain_db,unsigned rate)
{
    if (!c) return 0;
    if (!io || !io->read || !io->write || !io->delay_ms) {
        memset(c, 0, sizeof *c);
        return 0;
    }
    vpe_codec_io selected = *io; /* Also permits reinit with &c->io. */
    memset(c, 0, sizeof *c);
    c->io = selected;
    if((gain_db!=-24 && gain_db!=0) || (rate!=16000 && rate!=48000))return fail(c);
    c->gain_db=gain_db;c->sample_rate=rate;
    uint8_t ndac=rate==16000?0x86:0x82;
    uint8_t gain=gain_db==0?0:0xd0;
    if (!vpe_codec_mute(c) || !write_reg(c, 0, 1, 1)) return fail(c);
    c->io.delay_ms(c->io.context, 2);
    if (!check(c, 0, 1, 0, 1)) return fail(c);
    static const uint8_t setup[][3] = {
        {0,64,0x0c}, {0,11,0x82}, {0,12,0x82}, {0,13,0}, {0,14,0x80},
        {0,27,0x30}, {0,56,2}, {0,31,1}, {0,32,1}, {0,60,1},
        {1,2,9}, {1,1,8}, {1,2,1}, {1,10,0x40}, {1,3,0}, {1,4,0},
        {1,123,1}, {1,20,0x25}, {1,12,8}, {1,13,8}, {1,14,8}, {1,15,8},
        {1,16,0x7e}, {1,17,0x7e}, {1,18,0x40}, {1,19,0x40}, {1,9,0x3c}
    };
    for (unsigned i = 0; i < sizeof setup/sizeof setup[0]; ++i){
        uint8_t value=setup[i][0]==0 && setup[i][1]==11?ndac:setup[i][2];
        if (!write_reg(c, setup[i][0], setup[i][1], value)) return fail(c);
    }
    /* Match the board driver's analog soft-start interval before DAC power. */
    c->io.delay_ms(c->io.context, 2500);
    if (!write_reg(c, 0, 63, 0xd4) || !write_reg(c, 0, 65, gain) ||
        !write_reg(c, 0, 66, gain) || !vpe_codec_mute(c)) return fail(c);
    static const uint8_t expected[][3] = {
        {0,11,0x82}, {0,12,0x82}, {0,13,0}, {0,14,0x80},
        {0,27,0x30}, {0,56,2}, {0,31,1}, {0,32,1}, {0,60,1},
        {0,63,0xd4},
        {1,12,8}, {1,13,8}, {1,14,8}, {1,15,8}, {1,9,0x3c}
    };
    for (unsigned i = 0; i < sizeof expected/sizeof expected[0]; ++i){
        uint8_t value=expected[i][0]==0 && expected[i][1]==11?ndac:expected[i][2];
        if (!check(c, expected[i][0], expected[i][1], value, 0xff)) return fail(c);
    }
    if(!check(c,0,65,gain,0xff) || !check(c,0,66,gain,0xff))return fail(c);
    for (unsigned i = 0; i < 50; ++i) {
        if (!read_reg(c, 0, 37, &c->power_flags)) return fail(c);
        if ((c->power_flags & 0xee) == 0xee) {
            c->ready = 1;
            return 1;
        }
        c->io.delay_ms(c->io.context, 10);
    }
    return fail(c);
}
int vpe_codec_unmute(vpe_codec *c)
{
    if (!c || !c->ready || !c->muted) return 0;
    if((c->gain_db!=-24 && c->gain_db!=0) || (c->sample_rate!=16000 && c->sample_rate!=48000))return fail(c);
    uint8_t gain=c->gain_db==0?0:0xd0;
    if (!vpe_codec_check_muted(c) || !check(c, 0, 65, gain, 0xff) ||
        !check(c, 0, 66, gain, 0xff) || !check(c,0,11,c->sample_rate==16000?0x86:0x82,0xff)) return fail(c);
    if (!write_reg(c, 1, 16, 0x3e) || !write_reg(c, 1, 17, 0x3e) ||
        !write_reg(c, 1, 18, 0) || !write_reg(c, 1, 19, 0) ||
        !write_reg(c, 0, 64, 0)) return fail(c);
    if (!check(c, 0, 64, 0, 0x0c) || !check(c, 1, 16, 0x3e, 0x7f) ||
        !check(c, 1, 17, 0x3e, 0x7f) || !check(c, 1, 18, 0, 0x7f) ||
        !check(c, 1, 19, 0, 0x7f)) return fail(c);
    c->muted = 0;
    return 1;
}

int vpe_codec_init_muted(vpe_codec *c,const vpe_codec_io *io)
{return vpe_codec_init_muted_gain(c,io,-24);}
int vpe_codec_init_muted_gain(vpe_codec *c,const vpe_codec_io *io,int gain_db)
{return vpe_codec_init_muted_rate(c,io,gain_db,48000);}
int vpe_codec_unmute_test(vpe_codec *c)
{
    if(!c || !c->ready || !c->muted)return 0;
    if(c->gain_db!=-24)return fail(c);
    return vpe_codec_unmute(c);
}
