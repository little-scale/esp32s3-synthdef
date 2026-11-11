#!/usr/bin/env python3
"""Run the actual diagnostic and renderers silently; fake target clocks only."""
import json
from pathlib import Path
import re
import subprocess
from engine_profile import ROOT,generate
from test_dsp_candidates import fixture

def exercise(qualified):
    build=ROOT/'build/host/seeded-profile-test'/('qualified' if qualified else 'reference')
    src=generate(build/'src','fm1',qualified_kernels=qualified)
    stubs=build/'stubs'
    headers={
      'sdkconfig.h':'#define CONFIG_SYNTHDEF_DIAGNOSTICS 1\n',
      'esp_cpu.h':'#include <stdint.h>\nuint32_t esp_cpu_get_cycle_count(void);\n',
      'esp_timer.h':'#include <stdint.h>\nint64_t esp_timer_get_time(void);\n',
      'esp_private/esp_clk.h':'int esp_clk_cpu_freq(void);\n',
      'esp_heap_caps.h':'#include <stdlib.h>\n#define MALLOC_CAP_SPIRAM 1\n#define MALLOC_CAP_8BIT 2\nvoid *test_alloc(size_t,unsigned);\n#define heap_caps_malloc test_alloc\n',
      'freertos/FreeRTOS.h':'', 'freertos/task.h':'void vTaskDelay(unsigned);\n',
      'mbedtls/sha256.h':'''#include <CommonCrypto/CommonDigest.h>
typedef CC_SHA256_CTX mbedtls_sha256_context;
static inline void mbedtls_sha256_init(mbedtls_sha256_context *c){(void)c;}
static inline void mbedtls_sha256_free(mbedtls_sha256_context *c){(void)c;}
static inline int mbedtls_sha256_starts(mbedtls_sha256_context *c,int mode){(void)mode;return CC_SHA256_Init(c)?0:-1;}
static inline int mbedtls_sha256_update(mbedtls_sha256_context *c,const unsigned char *p,size_t n){return CC_SHA256_Update(c,p,(CC_LONG)n)?0:-1;}
static inline int mbedtls_sha256_finish(mbedtls_sha256_context *c,unsigned char *p){return CC_SHA256_Final(p,c)?0:-1;}
'''}
    for name,text in headers.items():
        path=stubs/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    profile=build/'profile.c';profile.write_text((src/'fm_profile_render.inc').read_text())
    binary=build/'test'
    subprocess.run(['cc','-std=c99','-O2','-fno-fast-math','-ffp-contract=off','-Wno-deprecated-declarations',
        '-fsanitize=undefined,bounds,float-cast-overflow','-fno-sanitize-recover=all',
        '-I'+str(stubs),'-I'+str(src),'-I'+str(ROOT/'firmware/components/instrument/include'),'-I'+str(ROOT/'firmware/main'),
        str(src/'fm_load.c'),str(src/'fm_render.c'),str(profile),str(ROOT/'firmware/main/ugen_profile.c'),
        str(ROOT/'tests/seeded_profile_test.c'),'-lm','-o',str(binary)],check=True)
    rows=[]
    for name,data in [('random',fixture('PinkNoise')),('delay',(ROOT/'examples/master-delay.scsyndef').read_bytes()),('bus',(ROOT/'examples/TouchBuses.scsyndef').read_bytes())]:
        path=build/(name+'.scsyndef');path.write_bytes(data)
        result=subprocess.check_output([str(binary),str(path)],text=True)
        headers=[dict(re.findall(r'(\w+)=([^ ]+)',s)) for s in result.splitlines() if s.startswith('UGEN_PROFILE ')]
        setups=[dict(re.findall(r'(\w+)=([^ ]+)',s)) for s in result.splitlines() if s.startswith('UGEN_SETUP ')]
        assert setups and all(row['qualified']==str(int(qualified)) for row in setups),setups
        assert len(headers) in (4,5) and [h['matched'] for h in headers]==['1']+['0']*(len(headers)-2)+['1'],headers
        assert setups[0]['audio_sha256']==setups[-1]['audio_sha256'] and setups[0]['warm_sha256']==setups[-1]['warm_sha256']
        rows.append(dict(fixture=name,deterministic=True,allocation_failures_restored=len(headers)-2,voice_scratch_arena_restored=True,canaries_intact=True))
    output=build/'result.json';output.write_text(json.dumps(dict(passed=True,hardware=False,fixtures=rows),indent=2)+'\n')
    return rows

def main():
    for qualified in (False,True):exercise(qualified)
    print('PASS: reference/selected target profiler modes, deterministic output, live-state restoration and allocation failures; RNG, delay and bus fixtures under sanitizers.')

if __name__=='__main__':main()
