/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
typedef struct {
    char id[24],name[32];
    bool online,receiving;
    int rssi; /* dBm, -127 when unavailable. */
    uint32_t received;
} device_network_status;
typedef void (*network_exchange_fn)(const char *,char *,size_t);
int device_network_init(network_exchange_fn exchange,int (*pause)(bool));
void device_network_tick(void);
const char *device_network_id(void);
const char *device_network_name(void);
void device_network_snapshot(device_network_status *);
/* Authenticated/valid protocol traffic, excluding background status queries. */
void device_network_received(void);
/* Configuration and pairing are called only from the USB control owner. */
int device_network_command(const char *op,const void *data,size_t bytes,char *out,size_t size);
