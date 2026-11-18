/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <assert.h>
typedef int esp_err_t;
enum {ESP_OK=0,I2C_CLK_SRC_DEFAULT=1,I2C_ADDR_BIT_LEN_7=7,GPIO_MODE_OUTPUT=2};
typedef struct {uint64_t pin_bit_mask;int mode;} gpio_config_t;
typedef void *i2c_master_bus_handle_t;
typedef void *i2c_master_dev_handle_t;
typedef struct {int i2c_port,sda_io_num,scl_io_num,clk_source,glitch_ignore_cnt;struct {bool enable_internal_pullup;} flags;} i2c_master_bus_config_t;
typedef struct {int dev_addr_length,device_address,scl_speed_hz;} i2c_device_config_t;
static int64_t fake_now;
static int fail_at,init_step,power_level,write_count,read_count,deleted;
static bool read_fail;
static uint16_t fake_raw=240;
static int next_init(void){return ++init_step==fail_at?-1:0;}
static int gpio_set_level(int pin,int level){assert(pin==46);power_level=level;return 0;}
static int gpio_config(const gpio_config_t *p){assert(p->pin_bit_mask==(1ULL<<46));return next_init();}
static int i2c_new_master_bus(const i2c_master_bus_config_t *c,i2c_master_bus_handle_t *b)
{assert(c->sda_io_num==1 && c->scl_io_num==2 && c->i2c_port==-1);int e=next_init();if(!e)*b=(void *)1;return e;}
static int i2c_master_bus_add_device(i2c_master_bus_handle_t b,const i2c_device_config_t *c,i2c_master_dev_handle_t *d)
{assert(b && c->device_address==35 && c->scl_speed_hz==100000);int e=next_init();if(!e)*d=(void *)2;return e;}
static int i2c_del_master_bus(i2c_master_bus_handle_t b){assert(b);++deleted;return 0;}
static int i2c_master_transmit(i2c_master_dev_handle_t d,const uint8_t *p,size_t n,int ms)
{assert(d && n==1 && ms==5);static const uint8_t ops[]={1,0x42,0x65,0x10};assert(*p==ops[(write_count++)%4]);return 0;}
static int i2c_master_receive(i2c_master_dev_handle_t d,uint8_t *p,size_t n,int ms)
{assert(d && n==2 && ms==5);++read_count;p[0]=(uint8_t)(fake_raw>>8);p[1]=(uint8_t)fake_raw;return read_fail?-2:0;}
static int64_t esp_timer_get_time(void){return fake_now;}
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGI(...) ((void)0)
