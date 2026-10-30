/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "patch_service.h"
#include "catalog_generated.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_spiffs.h"
#include "esp_timer.h"
#include "mbedtls/sha256.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include <stdlib.h>
#include <string.h>

typedef struct { unsigned slot; bool save; } library_request;
typedef struct {
    patch_hooks hooks;
    fm_graph *graph[2]; unsigned active;
    unsigned char *active_blob,*stage_blob,*work;
    patch_meta active_meta,stage_meta,factory_meta;
    const unsigned char *factory; size_t factory_bytes;
    uint32_t received; unsigned state; /* 0 idle, 1 receiving, 2 ready, 3 activated */
    int active_slot; bool mounted,provisioned,faulted;
    nvs_handle_t nvs;
    char names[PATCH_SLOTS+1][32];
    uint32_t generations[PATCH_SLOTS][2];
    uint64_t last_rx;
    QueueHandle_t requests;
    uint32_t last_id,last_crc;
    bool cached;
    char wire[9000],cached_wire[9000],reply[4000],error[160];
} patch_state;
static patch_state *s;
static const char *TAG="patches";
static int sha(const void *p,size_t n,unsigned char out[32]) { return mbedtls_sha256(p,n,out,0)==0; }
static void path_for(unsigned slot,unsigned bank,char path[64]) { snprintf(path,64,"/patches/slot%02u_%c.wsp",slot,bank?'b':'a'); }
static void reply_send(uint32_t id,const char *op,const char *text,bool cache,uint32_t crc)
{
    size_t n=patch_frame_encode(id,op,text,strlen(text),s->wire,sizeof s->wire);
    if(!n)return;
    flockfile(stdout);fwrite(s->wire,1,n,stdout);fflush(stdout);funlockfile(stdout);
    if(cache) {memcpy(s->cached_wire,s->wire,n+1);s->last_id=id;s->last_crc=crc;s->cached=true;}
}
static void publish(void) {if(s->hooks.display)s->hooks.display(&s->active_meta,s->graph[s->active],s->names,s->active_slot);}
void patches_publish(void) {if(s)publish();}
static void busy(bool yes,const char *text) {if(s->hooks.busy)s->hooks.busy(yes,text);}
static int begin_maintenance(const char *text)
{
    busy(true,text);
    if(!s->hooks.pause(true)) {s->faulted=true;busy(true,"RESET REQUIRED");snprintf(s->error,160,"Audio did not acknowledge maintenance; reset required");return 0;}
    return 1;
}
static int end_maintenance(void)
{
    if(s->faulted)return 0;
    int ok=s->hooks.pause(false);if(!ok)s->faulted=true;
    busy(!ok,ok?"READY":"RESET REQUIRED");return ok;
}
static int scan_slot(unsigned slot,patch_meta *winner,bool copy_blob)
{
    uint32_t best=0;int bank=-1;
    for(unsigned b=0;b<2;++b) {
        char path[64];patch_meta m;uint32_t generation=0;
        path_for(slot,b,path);
        int valid=patch_record_read(path,&m,&generation,s->work,PATCH_BLOB_BYTES,sha,s->error) &&
                  fm_load(s->graph[1-s->active],s->work,m.graph_bytes,s->error,160) &&
                  patch_validate(s->graph[1-s->active],&m,s->error);
        s->generations[slot-1][b]=valid?generation:0;
        if(valid && generation>best) {best=generation;bank=(int)b;*winner=m;}
    }
    if(bank<0)return 0;
    if(copy_blob) {
        char path[64];uint32_t generation;path_for(slot,(unsigned)bank,path);
        if(!patch_record_read(path,winner,&generation,s->stage_blob,PATCH_BLOB_BYTES,sha,s->error))return 0;
    }
    return 1;
}
static int persist_selection(unsigned slot)
{
    return s->mounted && nvs_set_u8(s->nvs,"selected",(uint8_t)slot)==ESP_OK && nvs_commit(s->nvs)==ESP_OK;
}
static int mount_store(void)
{
    esp_err_t err=nvs_flash_init();
    if(err!=ESP_OK || nvs_open("wsynth4",NVS_READWRITE,&s->nvs)!=ESP_OK) {ESP_LOGE(TAG,"Settings unavailable; factory recovery retained");return 0;}
    uint8_t provisioned=0;nvs_get_u8(s->nvs,"provisioned",&provisioned);s->provisioned=provisioned==1;
    esp_vfs_spiffs_conf_t cfg={.base_path="/patches",.partition_label="storage",.max_files=4,.format_if_mount_failed=false};
    err=esp_vfs_spiffs_register(&cfg);
    if(err!=ESP_OK && !s->provisioned) {
        /* One-time initialization of this project's dedicated data partition.
         * Never auto-format after it has contained project patches. */
        ESP_LOGW(TAG,"Initializing dedicated patch partition for first use");
        if(esp_spiffs_format("storage")==ESP_OK)err=esp_vfs_spiffs_register(&cfg);
    }
    if(err!=ESP_OK) {ESP_LOGE(TAG,"Patch store unavailable; no erase attempted after provisioning");return 0;}
    if(nvs_set_u8(s->nvs,"provisioned",1)!=ESP_OK || nvs_commit(s->nvs)!=ESP_OK)return 0;
    s->mounted=true;
    for(unsigned slot=1;slot<=PATCH_SLOTS;++slot) {
        patch_meta m;
        if(scan_slot(slot,&m,false))snprintf(s->names[slot],32,"%s",m.name);
    }
    s->error[0]=0;
    return 1;
}
static int activate_stage(int slot)
{
    unsigned next=1-s->active;
    if(!s->hooks.activate(s->graph[next])) {s->faulted=true;snprintf(s->error,160,"Activation acknowledgement failed; reset required");return 0;}
    unsigned char *old=s->active_blob;s->active_blob=s->stage_blob;s->stage_blob=old;
    s->active_meta=s->stage_meta;s->active=next;s->active_slot=slot;s->state=3;
    publish();return 1;
}
static int load_slot(unsigned slot)
{
    if(slot>PATCH_SLOTS || (slot && !s->mounted)) {snprintf(s->error,160,"Slot unavailable");return 0;}
    if(!begin_maintenance("LOADING"))return 0;
    int ok=1;
    if(!slot) {s->stage_meta=s->factory_meta;memcpy(s->stage_blob,s->factory,s->factory_bytes);}
    else ok=scan_slot(slot,&s->stage_meta,true);
    if(ok)ok=fm_load(s->graph[1-s->active],s->stage_blob,s->stage_meta.graph_bytes,s->error,160) &&
             patch_validate(s->graph[1-s->active],&s->stage_meta,s->error);
    if(ok && s->mounted && !persist_selection(slot)) {snprintf(s->error,160,"Boot selection update failed; active patch retained");ok=0;}
    if(ok)ok=activate_stage((int)slot);
    int resumed=end_maintenance();return ok && resumed;
}
static int save_slot(unsigned slot)
{
    if(!slot || slot>PATCH_SLOTS || !s->mounted) {snprintf(s->error,160,"Writable slot unavailable");return 0;}
    if(!begin_maintenance("SAVING"))return 0;
    patch_meta existing;int exists=scan_slot(slot,&existing,false);
    if(exists && existing.graph_bytes==s->active_meta.graph_bytes && existing.source_bytes==s->active_meta.source_bytes &&
       !memcmp(existing.graph_hash,s->active_meta.graph_hash,32) && !memcmp(existing.source_hash,s->active_meta.source_hash,32) &&
       !strcmp(existing.name,s->active_meta.name) && !memcmp(existing.label,s->active_meta.label,48) && existing.mapping==s->active_meta.mapping) {
        int ok=persist_selection(slot);if(ok)s->active_slot=(int)slot;publish();
        if(!ok)snprintf(s->error,160,"Boot selection update failed");
        int resumed=end_maintenance();return ok && resumed;
    }
    unsigned bank=s->generations[slot-1][0]<=s->generations[slot-1][1]?0:1;
    uint32_t gen=s->generations[slot-1][0]>s->generations[slot-1][1]?s->generations[slot-1][0]:s->generations[slot-1][1];
    char path[64];path_for(slot,bank,path);
    int ok=gen!=UINT32_MAX && patch_record_write(path,&s->active_meta,gen+1,s->active_blob,s->error);
    patch_meta check;uint32_t readgen=0;
    if(ok)ok=patch_record_read(path,&check,&readgen,s->work,PATCH_BLOB_BYTES,sha,s->error) && readgen==gen+1;
    if(ok) {
        s->generations[slot-1][bank]=readgen;snprintf(s->names[slot],32,"%s",check.name);
        ok=persist_selection(slot);if(ok)s->active_slot=(int)slot;publish();
        if(!ok)snprintf(s->error,160,"Generation saved; boot selection update failed");
    }
    int resumed=end_maintenance();return ok && resumed;
}
int patches_init(fm_graph *first,fm_graph *spare,const void *factory,size_t bytes,const patch_hooks *hooks)
{
    s=heap_caps_calloc(1,sizeof *s,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);if(!s)return 0;
    s->active_blob=heap_caps_malloc(PATCH_BLOB_BYTES,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    s->stage_blob=heap_caps_malloc(PATCH_BLOB_BYTES,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    s->work=heap_caps_malloc(PATCH_BLOB_BYTES,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    s->requests=xQueueCreate(4,sizeof(library_request));
    if(!s->active_blob||!s->stage_blob||!s->work||!s->requests)return 0;
    s->hooks=*hooks;s->graph[0]=first;s->graph[1]=spare;s->factory=factory;s->factory_bytes=bytes;s->active_slot=0;
    patch_meta *m=&s->factory_meta;m->graph_bytes=bytes;sha(factory,bytes,m->graph_hash);sha("",0,m->source_hash);
    snprintf(m->name,32,"Touch Sine");
    const char *labels[]={"PITCH","LEVEL","ATTACK","RELEASE"};
    for(unsigned k=0;k<4;++k)snprintf(m->label[k],12,"%s",labels[k]);
    m->mapping=1;
    s->active_meta=*m;memcpy(s->active_blob,factory,bytes);snprintf(s->names[0],32,"Factory Sine");
    mount_store();return 1;
}
void patches_restore(bool factory_only)
{
    uint8_t selected=0;
    if(!factory_only && s->mounted && nvs_get_u8(s->nvs,"selected",&selected)==ESP_OK && selected>0 && selected<=PATCH_SLOTS)
        if(!load_slot(selected))ESP_LOGE(TAG,"Saved selection rejected: %s; factory retained",s->error);
    publish();
}
bool patches_request(unsigned slot,bool save)
{
    if(!s || slot>PATCH_SLOTS || (save && !slot))return false;
    library_request request={slot,save};return xQueueSend(s->requests,&request,0)==pdTRUE;
}
static uint64_t now_ms(void) {return (uint64_t)esp_timer_get_time()/1000;}
void patches_tick(void)
{
    if(!s)return;
    if((s->state==1||s->state==2) && now_ms()-s->last_rx>10000) {s->state=0;snprintf(s->error,160,"Upload timed out; active patch retained");}
    library_request request;
    if(xQueueReceive(s->requests,&request,0)==pdTRUE) {
        if(s->faulted)return;
        if(s->state==1 || s->state==2) {ESP_LOGW(TAG,"Library operation deferred: upload pending");return;}
        int ok=request.save?save_slot(request.slot):load_slot(request.slot);
        if(!ok && !s->faulted)busy(false,request.save?"SAVE FAILED":"LOAD FAILED");
        ESP_LOGI(TAG,"Library %s slot %u: %s",request.save?"save":"load",request.slot,ok?"OK":s->error);
    }
}
void patches_line(const char *line)
{
    if(!s)return;
    unsigned char payload[PATCH_FRAME_PAYLOAD];size_t length=sizeof payload;uint32_t id=0;
    char op[16];
    if(!patch_frame_decode(line,&id,op,payload,&length,s->error)) {reply_send(0,"ERR",s->error,false,0);return;}
    uint32_t crc=patch_crc32(line,strlen(line));
    if(s->cached && id==s->last_id) {
        if(crc==s->last_crc) {flockfile(stdout);fputs(s->cached_wire,stdout);fflush(stdout);funlockfile(stdout);}
        else reply_send(id,"ERR","Request ID reused with different content",false,0);
        return;
    }
    s->last_rx=now_ms();s->reply[0]=0;s->error[0]=0;int ok=1;
    if(s->faulted && strcmp(op,"HELLO") && strcmp(op,"STATUS") && strcmp(op,"LIST")) {
        reply_send(id,"ERR","Audio ownership uncertain; reset required",true,crc);return;
    }
    if(!strcmp(op,"HELLO") && !length) {
        size_t total=0,used=0;if(s->mounted)esp_spiffs_info("storage",&total,&used);
        snprintf(s->reply,sizeof s->reply,"{\"protocol\":1,\"model\":\"Waveshare AMOLED 1.8 V2\",\"build\":\"%s\",\"engine\":\"%s\",\"profile\":\"%s\",\"rate\":44100,\"block\":64,\"voices\":1,\"effects\":0,\"transports\":[\"usb-serial-jtag\"],\"graph_max\":65536,\"source_max\":65536,\"chunk\":256,\"slots\":8,\"storage\":%s,\"storage_total\":%u,\"storage_free\":%u,\"policy\":\"%s\",\"catalog\":%s}",s->hooks.build_id,s->hooks.engine_commit,s->hooks.profile_hash,s->mounted?"true":"false",(unsigned)total,(unsigned)(total-used),PATCH_POLICY,PATCH_CATALOG_JSON);
    } else if(!strcmp(op,"STATUS") && !length) {
        char hash[65];for(unsigned k=0;k<32;++k)snprintf(hash+2*k,3,"%02x",s->active_meta.graph_hash[k]);
        snprintf(s->reply,sizeof s->reply,"{\"state\":%u,\"reset_required\":%s,\"received\":%lu,\"transfer\":%lu,\"slot\":%d,\"name\":\"%s\",\"graph_sha256\":\"%s\"}",s->state,s->faulted?"true":"false",(unsigned long)s->received,(unsigned long)s->stage_meta.transfer,s->active_slot,s->active_meta.name,hash);
    } else if(!strcmp(op,"INFO") && !length) {
        unsigned char meta[PATCH_META_BYTES];char hex[PATCH_META_BYTES*2+1];patch_meta_encode(&s->active_meta,meta);
        for(unsigned k=0;k<PATCH_META_BYTES;++k)snprintf(hex+2*k,3,"%02x",meta[k]);
        snprintf(s->reply,sizeof s->reply,"{\"slot\":%d,\"manifest\":\"%s\"}",s->active_slot,hex);
    } else if(!strcmp(op,"READ") && length==6) {
        uint32_t offset=patch_get32(payload),count=(unsigned)payload[4]|(unsigned)payload[5]<<8;
        uint32_t total=s->active_meta.graph_bytes+s->active_meta.source_bytes;
        if(!count || count>256 || offset>total || count>total-offset)ok=0;
        else {
            char hex[513];for(unsigned k=0;k<count;++k)snprintf(hex+2*k,3,"%02x",s->active_blob[offset+k]);
            snprintf(s->reply,sizeof s->reply,"{\"offset\":%lu,\"data\":\"%s\"}",(unsigned long)offset,hex);
        }
    } else if(!strcmp(op,"LIST") && !length) {
        size_t at=0;at+=snprintf(s->reply,sizeof s->reply,"[");
        for(unsigned k=0;k<=PATCH_SLOTS;++k)at+=snprintf(s->reply+at,sizeof s->reply-at,"%s{\"slot\":%u,\"name\":\"%s\",\"generations\":[%lu,%lu]}",k?",":"",k,s->names[k],k?(unsigned long)s->generations[k-1][0]:0,k?(unsigned long)s->generations[k-1][1]:0);
        snprintf(s->reply+at,sizeof s->reply-at,"]");
    } else if(!strcmp(op,"BEGIN")) {
        patch_meta m;
        ok=patch_meta_decode(payload,length,&m,s->error) && m.transfer!=0;
        if(ok) {
            if(!(s->state==1 && !memcmp(&m,&s->stage_meta,sizeof m))) {s->stage_meta=m;s->received=0;s->state=1;}
            snprintf(s->reply,sizeof s->reply,"{\"received\":%lu}",(unsigned long)s->received);
        }
    } else if(!strcmp(op,"DATA") && length>=9) {
        uint32_t tx=patch_get32(payload),offset=patch_get32(payload+4);size_t count=length-8;
        uint32_t total=s->stage_meta.graph_bytes+s->stage_meta.source_bytes;
        if(s->state!=1 || tx!=s->stage_meta.transfer || count>256 || offset>total || count>total-offset)ok=0;
        else if(offset<s->received)ok=offset+count<=s->received && !memcmp(s->stage_blob+offset,payload+8,count);
        else if(offset!=s->received)ok=0;
        else {memcpy(s->stage_blob+offset,payload+8,count);s->received+=count;}
        if(!ok)snprintf(s->error,160,"Invalid/conflicting DATA offset or transfer");
        else snprintf(s->reply,sizeof s->reply,"{\"received\":%lu}",(unsigned long)s->received);
    } else if(!strcmp(op,"COMMIT") && length==4) {
        if(patch_get32(payload)!=s->stage_meta.transfer || (s->state!=1 && s->state!=2))ok=0;
        else if(s->state==1)ok=s->received==s->stage_meta.graph_bytes+s->stage_meta.source_bytes &&
            patch_verify(&s->stage_meta,s->stage_blob,sha,s->error) &&
            fm_load(s->graph[1-s->active],s->stage_blob,s->stage_meta.graph_bytes,s->error,160) &&
            patch_validate(s->graph[1-s->active],&s->stage_meta,s->error);
        if(ok) {s->state=2;snprintf(s->reply,sizeof s->reply,"{\"ready\":true}");}
        else {s->state=0;s->received=0;}
    } else if(!strcmp(op,"ACTIVATE") && length==4) {
        if(patch_get32(payload)!=s->stage_meta.transfer || (s->state!=2 && s->state!=3))ok=0;
        else if(s->state==2) {
            ok=begin_maintenance("LOADING");
            if(ok) {ok=activate_stage(-1);int resumed=end_maintenance();ok=ok&&resumed;}
        }
        if(ok)snprintf(s->reply,sizeof s->reply,"{\"active\":true}");
    } else if(!strcmp(op,"ABORT") && !length) {s->state=0;s->received=0;snprintf(s->reply,sizeof s->reply,"{\"aborted\":true}");
    } else if((!strcmp(op,"SAVE") || !strcmp(op,"LOAD")) && length==1) {
        if(s->state==1 || s->state==2)ok=0;
        else ok=!strcmp(op,"SAVE")?save_slot(payload[0]):load_slot(payload[0]);
        if(ok)snprintf(s->reply,sizeof s->reply,"{\"slot\":%u}",payload[0]);
    } else if(!strcmp(op,"PANIC") && !length) {
        ok=begin_maintenance("STOPPED");if(ok)ok=end_maintenance();
        if(ok)snprintf(s->reply,sizeof s->reply,"{\"stopped\":true}");
    } else {ok=0;snprintf(s->error,160,"Unsupported operation or payload");}
    if(!ok && !s->error[0])snprintf(s->error,160,"Invalid transfer state or incomplete package");
    reply_send(id,ok?"OK":"ERR",ok?s->reply:s->error,true,crc);
}
