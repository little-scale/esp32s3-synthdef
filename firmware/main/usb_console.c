/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "usb_console.h"
#include "sdkconfig.h"
#include <stdio.h>
#if CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG_ENABLED
#include <fcntl.h>
#include <unistd.h>
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/usb_serial_jtag.h"
#include "driver/usb_serial_jtag_vfs.h"
#endif

esp_err_t usb_console_init(void)
{
#if CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG_ENABLED
    usb_serial_jtag_driver_config_t config = {
        .rx_buffer_size = 2048,
        .tx_buffer_size = 4096,
    };
    esp_err_t error = usb_serial_jtag_driver_install(&config);
    if (error != ESP_OK) return error;
    usb_serial_jtag_vfs_use_driver();
    /* Blocking getchar would stop standalone polling whenever no host sends
     * commands. The driver buffers bytes, but EOF must keep yielding as before. */
    int flags = fcntl(STDIN_FILENO, F_GETFL);
    if (flags < 0 || fcntl(STDIN_FILENO, F_SETFL, flags | O_NONBLOCK) < 0)
        return ESP_FAIL;
    if (setvbuf(stdin, NULL, _IONBF, 0) != 0) return ESP_FAIL;
#endif
    return ESP_OK;
}

bool usb_console_write_frame(const char *wire, size_t bytes)
{
    if (!bytes) return true;
    if (!wire) return false;
    flockfile(stdout);
    fflush(stdout);
    bool ok;
#if CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG_ENABLED
    /* IDF's driver-backed stdio path enqueues one character per call. Protocol
     * replies can be several KiB: batch those bytes instead of generating an
     * interrupt/short USB packet for each character. Telemetry keeps stdio. */
    int64_t deadline = esp_timer_get_time() + 50000;
    size_t at = 0;
    bool prefix = true;
    while (prefix || at < bytes) {
        if (esp_timer_get_time() >= deadline) break;
        size_t count = prefix ? 1 : bytes - at;
        if (count > 256) count = 256;
        int sent = usb_serial_jtag_write_bytes(prefix ? "\n" : wire + at, count, 0);
        if (sent < 0 || (size_t)sent > count) break;
        if (!sent) { vTaskDelay(1); continue; }
        if (prefix) prefix = false;
        else at += (size_t)sent;
    }
    ok = !prefix && at == bytes;
#else
    ok = fwrite(wire, 1, bytes, stdout) == bytes;
    if (fflush(stdout)) ok = false;
#endif
    funlockfile(stdout);
    return ok;
}
