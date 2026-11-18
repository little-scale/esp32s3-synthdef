/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "voice_pe_dlight.h"
#include <string.h>
#include <limits.h>
/* IDF's -mdisable-hardware-atomics reports only sometimes-lock-free for the
 * entire atomic type (including CAS). We use aligned 32-bit loads/stores only;
 * the target object audit checks that these emit no atomic runtime helpers. */
_Static_assert(sizeof(unsigned)==4,"Mailbox needs 32-bit words");
enum { POWER_ON,MT_HIGH,MT_LOW,MEASURE,READ_SAMPLE };
void vpe_dlight_init(vpe_dlight *s,int64_t now)
{memset(s,0,sizeof *s);s->due_us=now+5000;}
float vpe_dlight_lux(uint16_t raw){return (float)raw/1.2f;}
float vpe_dlight_normalised(uint16_t raw)
{float v=vpe_dlight_lux(raw)/(float)VPE_DLIGHT_NORMALISE_LUX;return v>1?1:v;}
bool vpe_dlight_poll(vpe_dlight *s,const vpe_dlight_io *io,int64_t now)
{
    if(now<s->due_us)return false;
    if(s->phase==READ_SAMPLE){
        uint8_t bytes[2];
        if(io->receive(io->context,bytes)){
            s->raw=(uint16_t)(((unsigned)bytes[0]<<8)|bytes[1]);
            s->available=true;s->last_sample_us=now;
            if(s->samples<UINT32_MAX)++s->samples;
            s->due_us=now+200000;return true;
        }
    } else {
        /* Explicit MTreg=69 restores default sensitivity after reconnect.
         * BH1750 H-resolution: 180 ms worst-case conversion, raw / 1.2 lux. */
        static const uint8_t commands[]={0x01,0x42,0x65,0x10};
        if(s->phase<READ_SAMPLE && io->command(io->context,commands[s->phase])){
            ++s->phase;s->due_us=now+(s->phase==READ_SAMPLE?180000:10000);
            return false;
        }
    }
    s->available=false;if(s->errors<UINT32_MAX)++s->errors;
    s->phase=POWER_ON;s->due_us=now+1000000;
    return false;
}
void vpe_dlight_mailbox_init(vpe_dlight_mailbox *m)
{atomic_init(&m->sequence,0);atomic_init(&m->raw,0);}
void vpe_dlight_publish(vpe_dlight_mailbox *m,uint16_t raw)
{
    unsigned next=atomic_load_explicit(&m->sequence,memory_order_seq_cst)+2u;
    if(!next)next=2;
    atomic_store_explicit(&m->sequence,next-1,memory_order_seq_cst);
    atomic_store_explicit(&m->raw,raw,memory_order_seq_cst);
    atomic_store_explicit(&m->sequence,next,memory_order_seq_cst);
}
bool vpe_dlight_consume(const vpe_dlight_mailbox *m,uint32_t *last,float values[2])
{
    unsigned sequence=atomic_load_explicit(&m->sequence,memory_order_seq_cst);
    if(!sequence || (sequence&1) || sequence==*last)return false;
    uint16_t raw=(uint16_t)atomic_load_explicit(&m->raw,memory_order_seq_cst);
    if(sequence!=atomic_load_explicit(&m->sequence,memory_order_seq_cst))return false;
    values[0]=vpe_dlight_normalised(raw);values[1]=vpe_dlight_lux(raw);
    *last=sequence;return true;
}
