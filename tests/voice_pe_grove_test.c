/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "../firmware/components/headless_io/voice_pe_grove.c"
#include <math.h>
#include <stdlib.h>
#include <string.h>
int main(int argc,char **argv)
{
    assert(argc==2);fail_at=atoi(argv[1]);
    voice_pe_grove_init();
    uint32_t sequence=0;float buses[2]={.7f,700};char info[1024];
    assert(voice_pe_grove_info(info,sizeof info)>0);
    assert(strstr(info,"\"age_ms\":-1") && strstr(info,"\"has_sample\":false"));
    assert(!headless_io_grove_sample(&sequence,buses) && buses[1]==700);
#ifndef CONFIG_SYNTHDEF_VOICE_PE_DLIGHT
    assert(!ready && !init_step && !power_level);return 0;
#else
    if(fail_at){
        assert(!ready && !power_level && !write_count && !read_count);
        assert(deleted==(fail_at==3));return 0;
    }
    assert(ready && power_level==1);
    for(unsigned i=0;i<4;++i){fake_now=5000+10000*i;voice_pe_grove_poll();assert(!headless_io_grove_sample(&sequence,buses));}
    fake_now=214999;voice_pe_grove_poll();assert(!read_count);
    fake_now=215000;voice_pe_grove_poll();assert(read_count==1);
    assert(headless_io_grove_sample(&sequence,buses));
    assert(fabsf(buses[0]-.2f)<.00001f && fabsf(buses[1]-200)<.001f && sequence==2);
    for(unsigned i=0;i<100;++i){++fake_now;voice_pe_grove_poll();assert(!headless_io_grove_sample(&sequence,buses));}
    assert(read_count==1);
    read_fail=true;fake_now=415000;voice_pe_grove_poll();
    assert(!headless_io_grove_sample(&sequence,buses) && fabsf(buses[1]-200)<.001f);
    voice_pe_grove_info(info,sizeof info);
    assert(strstr(info,"\"available\":false") && strstr(info,"\"has_sample\":true") && strstr(info,"\"sequence\":2"));
    read_fail=false;fake_raw=1200;
    for(unsigned i=0;i<4;++i){fake_now=1415000+10000*i;voice_pe_grove_poll();}
    fake_now=1625000;voice_pe_grove_poll();assert(headless_io_grove_sample(&sequence,buses) && sequence==4);
    assert(fabsf(buses[1]-1000)<.001f);
    voice_pe_grove_info(info,sizeof info);assert(strstr(info,"\"available\":true") && strstr(info,"\"age_ms\":0"));
    puts(info);return 0;
#endif
}
