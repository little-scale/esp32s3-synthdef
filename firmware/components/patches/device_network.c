/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "device_network.h"
#include "patch_format.h"
#include "cJSON.h"
#include "esp_event.h"
#include "esp_heap_caps.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "lwip/sockets.h"
#include "nvs.h"
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>

#define DISCOVERY_PORT 32101
#define DISCOVERY_QUERY "SYNTHDEF_DISCOVER_V1"
typedef struct {
    char id[24],name[32],key[65],ssid[33],password[65];
    char request[PATCH_FRAME_BYTES],response[9000];
    char lease[33];int64_t lease_until;atomic_int_fast64_t retry_at;
    network_exchange_fn exchange;
    int (*pause)(bool);
    SemaphoreHandle_t done;
    atomic_int work; /* 0 idle, 1 queued, 2 executing, 3 completed */
    atomic_bool online,configured;
    bool initialized,started,pending;
    atomic_uint reason;
    atomic_uint stage;
    atomic_int error;
    atomic_int rssi;
    int64_t signal_next;
    esp_netif_t *netif;httpd_handle_t server;nvs_handle_t store;
} network_state;
static network_state *net;
static const char *TAG="device_network";
static portMUX_TYPE identity_lock=portMUX_INITIALIZER_UNLOCKED;
static atomic_int_fast64_t received_at;
static atomic_uint received_count;

void device_network_received(void)
{atomic_store(&received_at,esp_timer_get_time());atomic_fetch_add(&received_count,1);}
void device_network_snapshot(device_network_status *out)
{
    memset(out,0,sizeof *out);out->rssi=-127;
    if(net){
        portENTER_CRITICAL(&identity_lock);memcpy(out->id,net->id,sizeof out->id);memcpy(out->name,net->name,sizeof out->name);portEXIT_CRITICAL(&identity_lock);
        out->online=atomic_load(&net->online);if(out->online)out->rssi=atomic_load(&net->rssi);
    }
    int64_t last=atomic_load(&received_at);out->receiving=last>0 && esp_timer_get_time()-last<140000;
    out->received=atomic_load(&received_count);
}

const char *device_network_id(void){return net?net->id:"";}
const char *device_network_name(void){return net?net->name:"";}
static void identity(char *out,size_t size,bool private)
{
    char name[32];portENTER_CRITICAL(&identity_lock);memcpy(name,net->name,sizeof name);portEXIT_CRITICAL(&identity_lock);
    esp_netif_ip_info_t ip={0};if(net->netif)esp_netif_get_ip_info(net->netif,&ip);
    snprintf(out,size,"{\"protocol\":1,\"device_id\":\"%s\",\"device_name\":\"%s\",\"address\":\"" IPSTR "\",\"port\":80,\"configured\":%s,\"online\":%s,\"rssi\":%d,\"rx_count\":%u,\"reason\":%u,\"stage\":%u,\"internal_free\":%u,\"internal_largest\":%u,\"error\":\"%s\"%s%s%s}",
        net->id,name,IP2STR(&ip.ip),atomic_load(&net->configured)?"true":"false",atomic_load(&net->online)?"true":"false",atomic_load(&net->online)?atomic_load(&net->rssi):-127,atomic_load(&received_count),atomic_load(&net->reason),atomic_load(&net->stage),(unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT),(unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT),esp_err_to_name(atomic_load(&net->error)),private?",\"key\":\"":"",private?net->key:"",private?"\"":"");
}
static bool same_key(const char *a,const char *b,size_t count)
{
    unsigned difference=0;for(size_t i=0;i<count;++i)difference|=(unsigned char)a[i]^(unsigned char)b[i];return difference==0;
}
static esp_err_t identify_http(httpd_req_t *req)
{
    char out[512];identity(out,sizeof out,false);httpd_resp_set_type(req,"application/json");
    httpd_resp_set_hdr(req,"X-Device-ID",net->id);httpd_resp_set_hdr(req,"Cache-Control","no-store");return httpd_resp_sendstr(req,out);
}
static esp_err_t unavailable(httpd_req_t *req,const char *message)
{
    httpd_resp_set_status(req,"503 Service Unavailable");return httpd_resp_sendstr(req,message);
}
static esp_err_t exchange_http(httpd_req_t *req)
{
    char id[32]={0},key[80]={0},client[40]={0};
    httpd_req_get_hdr_value_str(req,"X-Device-ID",id,sizeof id);
    httpd_req_get_hdr_value_str(req,"X-Device-Key",key,sizeof key);
    httpd_req_get_hdr_value_str(req,"X-Client-ID",client,sizeof client);
    httpd_resp_set_hdr(req,"X-Device-ID",net->id);httpd_resp_set_hdr(req,"Cache-Control","no-store");
    if(strcmp(id,net->id))return httpd_resp_send_err(req,HTTPD_400_BAD_REQUEST,"Wrong device identity");
    if(strlen(key)!=64 || !same_key(key,net->key,64))return httpd_resp_send_err(req,HTTPD_403_FORBIDDEN,"Pair this device over USB first");
    if(strlen(client)!=32 || strspn(client,"0123456789abcdef")!=32)return httpd_resp_send_err(req,HTTPD_400_BAD_REQUEST,"Invalid client identity");
    if(!req->content_len || req->content_len>=sizeof net->request)return httpd_resp_send_err(req,HTTPD_400_BAD_REQUEST,"Frame too large");
    int work=atomic_load(&net->work);
    if(work==3)atomic_store(&net->work,0);
    else if(work)return unavailable(req,"Control owner busy; inspect STATUS");
    size_t at=0;while(at<req->content_len){int n=httpd_req_recv(req,net->request+at,req->content_len-at);if(n<=0)return ESP_FAIL;at+=(unsigned)n;}
    net->request[at]=0;
    if(strlen(net->request)!=at)return httpd_resp_send_err(req,HTTPD_400_BAD_REQUEST,"Invalid frame encoding");
    unsigned char payload[PATCH_FRAME_PAYLOAD];size_t bytes=sizeof payload;uint32_t request;char op[16],error[160];
    if(!patch_frame_decode(net->request,&request,op,payload,&bytes,error))return httpd_resp_send_err(req,HTTPD_400_BAD_REQUEST,"Invalid protocol frame");
    if(!strncmp(op,"NET",3))return httpd_resp_send_err(req,HTTPD_403_FORBIDDEN,"Network setup is USB only");
    bool read=!strcmp(op,"HELLO") || !strcmp(op,"STATUS") || !strcmp(op,"LIST") || !strcmp(op,"FXLIST") || !strcmp(op,"INFO") || !strcmp(op,"FXINFO") || !strcmp(op,"READ") || !strcmp(op,"FXREAD") || !strcmp(op,"CAPINFO") || !strcmp(op,"CAPREAD") || !strcmp(op,"INPUTS") || !strcmp(op,"PINFO");
    int64_t now=esp_timer_get_time();
    if(net->lease_until>now && strcmp(client,net->lease) && !read)return unavailable(req,"Another uploader owns this transfer");
    if(net->lease_until>now && !strcmp(client,net->lease))net->lease_until=now+30000000;
    xSemaphoreTake(net->done,0);atomic_store(&net->work,1);
    if(xSemaphoreTake(net->done,pdMS_TO_TICKS(20000))!=pdTRUE){
        int queued=1;atomic_compare_exchange_strong(&net->work,&queued,0);
        return unavailable(req,"Control timeout; inspect STATUS before retrying");
    }
    atomic_store(&net->work,0);
    /* Completed transfers must not be reacquired by subsequent readback/status. */
    if((!strcmp(op,"BEGIN") || !strcmp(op,"FXBEGIN") || !strcmp(op,"PBEGIN")) && strstr(net->response," OK ")){strcpy(net->lease,client);net->lease_until=esp_timer_get_time()+30000000;}
    if(!strcmp(client,net->lease) && (!strcmp(op,"INSTALL") || !strcmp(op,"SAVE") || !strcmp(op,"FXSAVE") || !strcmp(op,"ABORT") || !strcmp(op,"PSAVE") || !strcmp(op,"PABORT")))net->lease_until=0;
    httpd_resp_set_type(req,"text/plain");return httpd_resp_sendstr(req,net->response);
}
static void discover_task(void *unused)
{
    (void)unused;int fd=socket(AF_INET,SOCK_DGRAM,IPPROTO_UDP);
    struct sockaddr_in local={.sin_family=AF_INET,.sin_port=htons(DISCOVERY_PORT),.sin_addr.s_addr=htonl(INADDR_ANY)};
    if(fd<0 || bind(fd,(struct sockaddr *)&local,sizeof local)<0){if(fd>=0)close(fd);vTaskDelete(NULL);return;}
    char input[64],out[512];struct sockaddr_in from;socklen_t size;
    for(;;){size=sizeof from;int count=recvfrom(fd,input,sizeof input,0,(struct sockaddr *)&from,&size);
        if(count==(int)strlen(DISCOVERY_QUERY) && !memcmp(input,DISCOVERY_QUERY,count) && atomic_load(&net->online)){
            identity(out,sizeof out,false);sendto(fd,out,strlen(out),0,(struct sockaddr *)&from,size);
        }
        if(count<0)vTaskDelay(pdMS_TO_TICKS(100));
    }
}
static void network_event(void *arg,esp_event_base_t base,int32_t event,void *data)
{
    (void)arg;
    if(base==IP_EVENT && event==IP_EVENT_STA_GOT_IP){atomic_store(&net->online,true);net->reason=0;net->error=ESP_OK;net->stage=10;}
    else if(base==WIFI_EVENT && event==WIFI_EVENT_STA_DISCONNECTED){
        atomic_store(&net->online,false);net->reason=((wifi_event_sta_disconnected_t *)data)->reason;net->retry_at=esp_timer_get_time()+5000000;
    }
}
static esp_err_t start_network(void)
{
    esp_err_t err;
    if(!net->initialized){
        net->stage=1;
        if((err=esp_netif_init())!=ESP_OK)return err;
        err=esp_event_loop_create_default();if(err!=ESP_OK && err!=ESP_ERR_INVALID_STATE)return err;
        if(!net->netif)net->netif=esp_netif_create_default_wifi_sta();
        if(!net->netif)return ESP_ERR_NO_MEM;
        wifi_init_config_t config=WIFI_INIT_CONFIG_DEFAULT();
        net->stage=4;
        if((err=esp_wifi_init(&config))!=ESP_OK)return err;
        esp_event_handler_register(WIFI_EVENT,ESP_EVENT_ANY_ID,network_event,NULL);
        esp_event_handler_register(IP_EVENT,IP_EVENT_STA_GOT_IP,network_event,NULL);
        esp_wifi_set_storage(WIFI_STORAGE_RAM);esp_wifi_set_mode(WIFI_MODE_STA);net->initialized=true;
    }
    if(net->started)esp_wifi_disconnect();
    wifi_config_t config={0};memcpy(config.sta.ssid,net->ssid,strlen(net->ssid));memcpy(config.sta.password,net->password,strlen(net->password));
    net->stage=5;
    config.sta.threshold.authmode=net->password[0]?WIFI_AUTH_WPA2_PSK:WIFI_AUTH_OPEN;
    if((err=esp_wifi_set_config(WIFI_IF_STA,&config))!=ESP_OK)return err;
    if(!net->started){net->stage=6;if((err=esp_wifi_start())!=ESP_OK)return err;net->started=true;}
    esp_wifi_set_ps(WIFI_PS_NONE);
    if(!net->server){
        net->stage=7;
        httpd_config_t http=HTTPD_DEFAULT_CONFIG();http.core_id=0;http.stack_size=6144;http.task_caps=MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT;http.max_open_sockets=2;http.lru_purge_enable=true;http.recv_wait_timeout=5;http.send_wait_timeout=5;
        if((err=httpd_start(&net->server,&http))!=ESP_OK)return err;
        const httpd_uri_t info={.uri="/v1/identity",.method=HTTP_GET,.handler=identify_http};
        const httpd_uri_t request={.uri="/v1/request",.method=HTTP_POST,.handler=exchange_http};
        httpd_register_uri_handler(net->server,&info);httpd_register_uri_handler(net->server,&request);
        net->stage=8;if(xTaskCreatePinnedToCore(discover_task,"synth-discovery",3072,NULL,2,NULL,0)!=pdPASS)return ESP_ERR_NO_MEM;
    }
    net->stage=9;return net->ssid[0]?esp_wifi_connect():ESP_OK;
}
int device_network_init(network_exchange_fn exchange,int (*pause)(bool))
{
    net=heap_caps_calloc(1,sizeof *net,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);if(!net)return 0;
    net->exchange=exchange;net->pause=pause;atomic_store(&net->rssi,-127);net->done=xSemaphoreCreateBinary();if(!net->done)return 0;
    uint8_t mac[6];if(esp_read_mac(mac,ESP_MAC_WIFI_STA)!=ESP_OK)return 0;
    snprintf(net->id,sizeof net->id,"esp32-%02x%02x%02x%02x%02x%02x",mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);
    #ifdef CONFIG_SYNTHDEF_HEADLESS
    snprintf(net->name,sizeof net->name,"XIAO-%02x%02x%02x",mac[3],mac[4],mac[5]);
#else
    snprintf(net->name,sizeof net->name,"AMOLED-%02x%02x%02x",mac[3],mac[4],mac[5]);
#endif
    if(nvs_open("synthnet",NVS_READWRITE,&net->store)!=ESP_OK)return 0;
    size_t n=sizeof net->name;nvs_get_str(net->store,"name",net->name,&n);n=sizeof net->ssid;nvs_get_str(net->store,"ssid",net->ssid,&n);
    n=sizeof net->password;nvs_get_str(net->store,"password",net->password,&n);n=sizeof net->key;
    if(nvs_get_str(net->store,"key",net->key,&n)!=ESP_OK){unsigned char random[32];esp_fill_random(random,sizeof random);for(unsigned k=0;k<32;++k)snprintf(net->key+2*k,3,"%02x",random[k]);if(nvs_set_str(net->store,"key",net->key)!=ESP_OK || nvs_commit(net->store)!=ESP_OK)return 0;}
    net->pending=net->ssid[0]!=0;atomic_store(&net->configured,net->pending);return 1;
}
void device_network_tick(void)
{
    if(!net)return;
    int64_t now=esp_timer_get_time();
    if(now>=net->signal_next){
        net->signal_next=now+1000000;wifi_ap_record_t ap;
        atomic_store(&net->rssi,atomic_load(&net->online) && esp_wifi_sta_get_ap_info(&ap)==ESP_OK?ap.rssi:-127);
    }
    int queued=1;if(atomic_compare_exchange_strong(&net->work,&queued,2)){
        net->exchange(net->request,net->response,sizeof net->response);atomic_store(&net->work,3);xSemaphoreGive(net->done);
    }
    if(net->pending){
        net->pending=false;
        if(net->pause(true)){net->error=start_network();if(!net->pause(false))net->error=ESP_ERR_INVALID_STATE;}
        else net->error=ESP_ERR_INVALID_STATE;
        ESP_LOGI(TAG,"Wi-Fi start: %s",esp_err_to_name(net->error));
    }
    else if(net->started && net->ssid[0] && !atomic_load(&net->online) && esp_timer_get_time()>net->retry_at){net->retry_at=esp_timer_get_time()+5000000;esp_wifi_connect();}
}
int device_network_command(const char *op,const void *data,size_t bytes,char *out,size_t size)
{
    if(!net || !net->store)return 0;
    if(!strcmp(op,"NETINFO") && !bytes){identity(out,size,false);return 1;}
    if(!strcmp(op,"NETPAIR") && !bytes){identity(out,size,true);return 1;}
    if(!strcmp(op,"NETSCAN") && !bytes){
        if(!net->started){net->error=start_network();if(net->error!=ESP_OK)return 0;}
        wifi_ap_record_t *records=heap_caps_calloc(16,sizeof *records,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);if(!records)return 0;
        esp_wifi_disconnect();vTaskDelay(pdMS_TO_TICKS(100));
        wifi_scan_config_t scan={.show_hidden=true};uint16_t count=16;
        esp_err_t err=esp_wifi_scan_start(&scan,true);
        if(err==ESP_OK)err=esp_wifi_scan_get_ap_records(&count,records);
        bool visible=false;size_t at=snprintf(out,size,"{\"networks\":[");
        for(unsigned k=0;err==ESP_OK && k<count;++k){
            records[k].ssid[32]=0;cJSON *text=cJSON_CreateString((const char *)records[k].ssid);
            char *quoted=text?cJSON_PrintUnformatted(text):NULL;
            if(!quoted){err=ESP_ERR_NO_MEM;cJSON_Delete(text);break;}
            visible|=!strcmp((const char *)records[k].ssid,net->ssid);
            int written=snprintf(out+at,size-at,"%s{\"ssid\":%s,\"rssi\":%d,\"channel\":%u}",k?",":"",quoted,records[k].rssi,records[k].primary);
            cJSON_free(quoted);cJSON_Delete(text);
            if(written<0 || (size_t)written>=size-at){err=ESP_ERR_NO_MEM;break;}at+=(size_t)written;
        }
        if(err==ESP_OK)snprintf(out+at,size-at,"],\"configured_visible\":%s}",visible?"true":"false");
        else esp_wifi_clear_ap_list();
        heap_caps_free(records);net->retry_at=esp_timer_get_time()+1000000;return err==ESP_OK;
    }
    if(strcmp(op,"NETCFG") || !bytes || bytes>400)return 0;
    cJSON *root=cJSON_ParseWithLength(data,bytes);if(!root)return 0;
    const cJSON *ssid=cJSON_GetObjectItemCaseSensitive(root,"ssid"),*password=cJSON_GetObjectItemCaseSensitive(root,"password"),*name=cJSON_GetObjectItemCaseSensitive(root,"name");
    bool ok=cJSON_IsString(ssid) && cJSON_IsString(password) && cJSON_IsString(name) && strlen(ssid->valuestring)>0 && strlen(ssid->valuestring)<=32 && strlen(password->valuestring)<=63 && (!password->valuestring[0] || strlen(password->valuestring)>=8) && strlen(name->valuestring)>0 && strlen(name->valuestring)<32 && strspn(name->valuestring,"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -_")==strlen(name->valuestring);
    if(ok){
        ok=nvs_set_str(net->store,"ssid",ssid->valuestring)==ESP_OK && nvs_set_str(net->store,"password",password->valuestring)==ESP_OK && nvs_set_str(net->store,"name",name->valuestring)==ESP_OK && nvs_commit(net->store)==ESP_OK;
        if(ok){strcpy(net->ssid,ssid->valuestring);strcpy(net->password,password->valuestring);portENTER_CRITICAL(&identity_lock);strcpy(net->name,name->valuestring);portEXIT_CRITICAL(&identity_lock);atomic_store(&net->configured,true);net->pending=true;identity(out,size,false);}
    }
    cJSON_Delete(root);return ok;
}
