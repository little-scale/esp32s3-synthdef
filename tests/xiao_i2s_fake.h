/* Fake IDF I/O for exercising the production adapter; no hardware access. */
#pragma once
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#define IRAM_ATTR
typedef int esp_err_t;
enum { ESP_OK=0, ESP_ERR_INVALID_STATE=1, ESP_ERR_INVALID_ARG=2, ESP_ERR_NO_MEM=3 };
#define ESP_RETURN_ON_ERROR(call,tag,...) do { (void)(tag); int e=(call); if(e)return e; } while(0)
#define ESP_LOGI(tag,...) ((void)(tag))
enum { MALLOC_CAP_SPIRAM=1, MALLOC_CAP_8BIT=2, I2S_NUM_0=0, I2S_ROLE_MASTER=1,
       I2S_DATA_BIT_WIDTH_16BIT=16, I2S_SLOT_MODE_STEREO=2, I2S_GPIO_UNUSED=-1,
       I2S_SLOT_BIT_WIDTH_32BIT=32, GPIO_MODE_OUTPUT=1 };
typedef void *i2s_chan_handle_t;
typedef struct {int unused;} i2s_event_data_t;
typedef struct {int role,dma_desc_num,dma_frame_num;bool auto_clear;} i2s_chan_config_t;
typedef struct {unsigned sample_rate_hz;} fake_clock;
typedef struct {unsigned data_bit_width,slot_bit_width,slot_mode,ws_width;bool bit_shift;} fake_slot;
typedef struct {int mclk,bclk,ws,dout,din;} fake_gpio;
typedef struct {fake_clock clk_cfg;fake_slot slot_cfg;fake_gpio gpio_cfg;} i2s_std_config_t;
typedef struct {bool (*on_send_q_ovf)(i2s_chan_handle_t,i2s_event_data_t *,void *);} i2s_event_callbacks_t;
typedef struct {uint64_t pin_bit_mask;int mode;} gpio_config_t;
#define I2S_CHANNEL_DEFAULT_CONFIG(num,role_value) ((i2s_chan_config_t){.role=(role_value)})
#define I2S_STD_CLK_DEFAULT_CONFIG(rate) ((fake_clock){(rate)})
#define I2S_STD_PHILIP_SLOT_DEFAULT_CONFIG(bits,mode) ((fake_slot){.data_bit_width=(bits),.slot_mode=(mode),.ws_width=(bits),.bit_shift=true})
static i2s_std_config_t configured;
static i2s_chan_config_t configured_channel;
static i2s_event_callbacks_t callbacks;
static const void *last_write;
static size_t last_bytes,allocated_bytes;
static int write_error;
static bool short_write,fail_allocation;
static void *heap_caps_malloc(size_t bytes,int caps) {(void)caps;allocated_bytes=bytes;return fail_allocation?NULL:malloc(bytes);}
static uint32_t esp_random(void) {return 123;}
static int i2s_new_channel(const i2s_chan_config_t *c,i2s_chan_handle_t *tx,void *rx) {(void)rx;configured_channel=*c;*tx=(void *)1;return 0;}
static int i2s_channel_init_std_mode(i2s_chan_handle_t tx,const i2s_std_config_t *c) {(void)tx;configured=*c;return 0;}
static int i2s_channel_register_event_callback(i2s_chan_handle_t tx,const i2s_event_callbacks_t *c,void *ctx) {(void)tx;(void)ctx;callbacks=*c;return 0;}
static int gpio_config(const gpio_config_t *c) {assert(c->pin_bit_mask==(1ULL<<21));return 0;}
static int gpio_set_level(int gpio,int value) {(void)gpio;(void)value;return 0;}
static int i2s_channel_write(i2s_chan_handle_t tx,const void *data,size_t bytes,size_t *written,int timeout) {
    (void)tx;assert(timeout==100);last_write=data;last_bytes=bytes;
    *written=short_write?0:bytes;return write_error;
}
static int i2s_channel_disable(i2s_chan_handle_t tx) {(void)tx;return 0;}
static int i2s_channel_enable(i2s_chan_handle_t tx) {(void)tx;return 0;}
