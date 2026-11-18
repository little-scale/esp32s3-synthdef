/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "voice_pe_dlight.h"
#include <assert.h>
#include <math.h>
#include <limits.h>
#include <stdio.h>
typedef struct {unsigned commands,reads;uint8_t bytes[32];uint16_t raw;bool fail_write,fail_read;} fixture;
static bool command(void *p,uint8_t byte)
{fixture *f=p;assert(f->commands<sizeof f->bytes);f->bytes[f->commands++]=byte;return !f->fail_write;}
static bool receive(void *p,uint8_t bytes[2])
{fixture *f=p;++f->reads;bytes[0]=(uint8_t)(f->raw>>8);bytes[1]=(uint8_t)f->raw;return !f->fail_read;}
static int64_t configure(vpe_dlight *s,vpe_dlight_io *io,int64_t at)
{for(unsigned i=0;i<4;++i){assert(!vpe_dlight_poll(s,io,at));at=s->due_us;}return at;}
int main(void)
{
    fixture f={.raw=600};vpe_dlight_io io={&f,command,receive};vpe_dlight sensor;
    vpe_dlight_mailbox box;vpe_dlight_mailbox_init(&box);
    uint32_t sequence=0;float buses[2]={.25f,250};
    vpe_dlight_init(&sensor,1000);
    assert(!vpe_dlight_consume(&box,&sequence,buses));
    assert(buses[0]==.25f && buses[1]==250 && sequence==0);
    assert(!vpe_dlight_poll(&sensor,&io,5999) && f.commands==0);
    int64_t first=configure(&sensor,&io,6000);
    assert(f.commands==4 && f.bytes[0]==0x01 && f.bytes[1]==0x42 && f.bytes[2]==0x65 && f.bytes[3]==0x10);
    assert(first==216000 && f.reads==0);
    assert(!vpe_dlight_poll(&sensor,&io,first-1) && !f.reads);
    assert(vpe_dlight_poll(&sensor,&io,first));
    assert(sensor.available && sensor.raw==600 && sensor.samples==1 && !sensor.errors);
    vpe_dlight_publish(&box,sensor.raw);
    assert(vpe_dlight_consume(&box,&sequence,buses) && sequence==2);
    assert(fabsf(buses[0]-.5f)<.00001f && fabsf(buses[1]-500)<.001f);
    /* Four hundred audio blocks without new sensor bytes do not write buses. */
    for(unsigned i=0;i<400;++i){
        float previous[2]={buses[0],buses[1]};
        assert(!vpe_dlight_consume(&box,&sequence,buses));
        assert(buses[0]==previous[0] && buses[1]==previous[1]);
    }
    assert(!vpe_dlight_poll(&sensor,&io,first+199999) && f.reads==1);
    f.fail_read=true;
    assert(!vpe_dlight_poll(&sensor,&io,first+200000));
    assert(!sensor.available && sensor.errors==1 && sensor.samples==1 && sensor.raw==600);
    assert(!vpe_dlight_consume(&box,&sequence,buses) && fabsf(buses[0]-.5f)<.00001f);
    f.fail_read=false;
    assert(!vpe_dlight_poll(&sensor,&io,sensor.due_us-1));
    int64_t again=configure(&sensor,&io,sensor.due_us);
    assert(vpe_dlight_poll(&sensor,&io,again));
    vpe_dlight_publish(&box,sensor.raw);
    assert(vpe_dlight_consume(&box,&sequence,buses) && sequence==4); /* same value, new conversion */
    f.raw=0;
    assert(vpe_dlight_poll(&sensor,&io,sensor.due_us));vpe_dlight_publish(&box,sensor.raw);
    assert(vpe_dlight_consume(&box,&sequence,buses) && buses[0]==0 && buses[1]==0);
    f.raw=65535;
    assert(vpe_dlight_poll(&sensor,&io,sensor.due_us));vpe_dlight_publish(&box,sensor.raw);
    assert(vpe_dlight_consume(&box,&sequence,buses) && buses[0]==1 && fabsf(buses[1]-54612.5f)<.01f);
    /* An in-progress publication is skipped without a loop or partial pair. */
    float saved=buses[1];atomic_store(&box.sequence,9);
    assert(!vpe_dlight_consume(&box,&sequence,buses) && buses[1]==saved);
    atomic_store(&box.sequence,UINT_MAX-1);vpe_dlight_publish(&box,1200);
    assert(vpe_dlight_consume(&box,&sequence,buses) && sequence==2 && fabsf(buses[1]-1000)<.001f);
    vpe_dlight_init(&sensor,0);f.fail_write=true;f.commands=0;
    assert(!vpe_dlight_poll(&sensor,&io,5000));
    assert(sensor.errors==1 && !sensor.available && sensor.samples==0 && sensor.due_us==1005000);
    assert(!vpe_dlight_poll(&sensor,&io,1004999) && f.commands==1);
    sensor.errors=UINT32_MAX;assert(!vpe_dlight_poll(&sensor,&io,1005000));assert(sensor.errors==UINT32_MAX);
    puts("PASS: BH1750 protocol/conversion deadlines, fresh-only publication, hold-last on failure, recovery, dark/full-scale and mailbox rollover");
}
