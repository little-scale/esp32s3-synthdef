"""Compile actual console transport against driver stubs, without hardware."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class ConsoleTests(unittest.TestCase):
    def test_init_and_bounded_batched_frames(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder);(path/'driver').mkdir();(path/'freertos').mkdir()
            (path/'esp_err.h').write_text('#pragma once\ntypedef int esp_err_t;\n#define ESP_OK 0\n#define ESP_FAIL -1\n')
            (path/'esp_timer.h').write_text('#include <stdint.h>\nint64_t esp_timer_get_time(void);\n')
            (path/'freertos/FreeRTOS.h').write_text('typedef unsigned TickType_t;\n')
            (path/'freertos/task.h').write_text('void vTaskDelay(unsigned);\n')
            (path/'driver/usb_serial_jtag.h').write_text('#pragma once\n#include "esp_err.h"\n#include <stddef.h>\ntypedef struct {unsigned tx_buffer_size,rx_buffer_size;} usb_serial_jtag_driver_config_t;\nesp_err_t usb_serial_jtag_driver_install(usb_serial_jtag_driver_config_t *);\nint usb_serial_jtag_write_bytes(const void *,size_t,unsigned);\n')
            (path/'driver/usb_serial_jtag_vfs.h').write_text('void usb_serial_jtag_vfs_use_driver(void);\n')
            (path/'check.c').write_text(r'''
#include <assert.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "usb_console.h"
#include "driver/usb_serial_jtag.h"
static int installed, selected, fail, behavior, calls, delays;
static int64_t clock_us;
static char received[20000];
static size_t used;
int64_t esp_timer_get_time(void) { return clock_us; }
void vTaskDelay(unsigned ticks) { assert(ticks==1);delays++;clock_us+=10000; }
int usb_serial_jtag_driver_install(usb_serial_jtag_driver_config_t *config) {
    assert(config->rx_buffer_size==2048 && config->tx_buffer_size==4096);
    installed++;return fail?-7:0;
}
void usb_serial_jtag_vfs_use_driver(void) { assert(installed==1);selected++; }
int usb_serial_jtag_write_bytes(const void *data,size_t bytes,unsigned wait) {
    assert(data && bytes>0 && bytes<=256 && wait==0);calls++;assert(calls<10000);
    if(behavior==1 || (behavior==2 && calls>2) || (behavior==6 && calls<=3))return 0;
    if(behavior==4)return (int)bytes+1;
    if(behavior==5)return -1;
    size_t sent=behavior==3 && bytes>3 ? 3 : bytes;
    assert(used+sent<=sizeof received);memcpy(received+used,data,sent);used+=sent;
    return (int)sent;
}
static void reset(int mode) {behavior=mode;calls=delays=0;clock_us=0;used=0;}
int main(int argc,char **argv) {
    assert(argc==2);int mode=atoi(argv[1]);fail=mode==1;
    if(mode<3) {
        int before=fcntl(0,F_GETFL);assert(before>=0);
        if(mode==2)close(0);
        int result=usb_console_init();
#if CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG_ENABLED
        if(mode==0) {assert(result==0 && installed==1 && selected==1);assert(fcntl(0,F_GETFL)&O_NONBLOCK);}
        if(mode==1) {assert(result==-7 && installed==1 && selected==0);assert(fcntl(0,F_GETFL)==before);}
        if(mode==2) {assert(result==-1 && installed==1 && selected==1);}
#else
        assert(result==0 && !installed && !selected);
        if(mode!=2)assert(fcntl(0,F_GETFL)==before);
#endif
        return 0;
    }
    char wire[9000];for(unsigned i=0;i<sizeof wire;++i)wire[i]=(char)('a'+i%26);
    reset(0);
    assert(usb_console_write_frame(NULL,0));assert(!usb_console_write_frame(NULL,1));assert(!calls);
#if CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG_ENABLED
    if(mode==3) {
        const size_t lengths[]={1,63,64,65,255,256,257,4096,4222,8999};
        for(unsigned i=0;i<sizeof lengths/sizeof *lengths;++i) {
            reset(0);size_t n=lengths[i];assert(usb_console_write_frame(wire,n));
            assert(used==n+1 && received[0]=='\n' && !memcmp(received+1,wire,n));
            assert(calls==1+(int)((n+255)/256) && !delays);
        }
    } else if(mode==4 || mode==5) {
        reset(mode==4?1:2);assert(!usb_console_write_frame(wire,sizeof wire));
        assert(delays==5 && clock_us==50000);
        size_t partial=used;behavior=0;
        assert(usb_console_write_frame(wire,4222));
        assert(received[partial]=='\n' && used==partial+4223);
        assert(!memcmp(received+partial+1,wire,4222)); /* fresh frame after truncation */
    } else if(mode==6) {
        reset(3);assert(usb_console_write_frame(wire,4222));
        assert(used==4223 && received[0]=='\n' && !memcmp(received+1,wire,4222));
    } else if(mode==7 || mode==8) {
        reset(mode==7?4:5);assert(!usb_console_write_frame(wire,4222));assert(calls==1);
    } else if(mode==9) {
        reset(6);assert(usb_console_write_frame(wire,4222));assert(delays==3);
        assert(used==4223 && received[0]=='\n' && !memcmp(received+1,wire,4222));
    }
#else
    assert(usb_console_write_frame("legacy\n",7));assert(!calls && !delays);
#endif
}
''')
            for enabled in (0,1):
                (path/'sdkconfig.h').write_text(f'#define CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG_ENABLED {enabled}\n')
                exe=path/f'check-{enabled}'
                subprocess.run(['cc','-std=c99','-D_POSIX_C_SOURCE=200809L','-Wall','-Wextra','-Werror',
                    '-fsanitize=undefined,bounds','-fno-sanitize-recover=all',
                    '-I'+str(path),'-I'+str(ROOT/'firmware/main'),'-include',str(path/'sdkconfig.h'),
                    str(ROOT/'firmware/main/usb_console.c'),str(path/'check.c'),'-o',str(exe)],check=True)
                for mode in range(10):
                    result=subprocess.run([str(exe),str(mode)],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,check=True)
                    self.assertEqual(result.stdout,b'legacy\n' if not enabled and mode>=3 else b'')


if __name__=='__main__':unittest.main()
