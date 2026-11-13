/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "patch_service.h"
#include "device_network.h"
#include "board_audio.h"
#ifdef CONFIG_SYNTHDEF_HEADLESS
#include "headless_io.h"
#endif
#include "playback_mode.h"
#include "catalog_generated.h"
#include "patch_policy.h"
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

typedef struct { unsigned slot; bool save,master; } library_request;
typedef struct {
    patch_hooks hooks;
    fm_graph *graph[2]; unsigned active;
    unsigned char *active_blob,*stage_blob,*work;
    patch_meta active_meta,stage_meta,factory_meta;
    fm_graph *master_graph[2];unsigned master_active;int master_slot;
    unsigned char *master_blob;patch_meta master_meta,master_factory_meta;
    const unsigned char *master_factory;size_t master_factory_bytes;
    const char *master_source;size_t master_source_bytes;
    uint32_t master_generations[2];char master_name[32];bool stage_master;
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
    char *response;size_t response_size;unsigned channel,transfer_channel,cached_channel;
    char wire[9000],cached_wire[9000],reply[4000],error[160];
} patch_state;
static patch_state *s;
static const char *TAG="patches";
static void wire_send(const char *wire)
{
    if(s->response){snprintf(s->response,s->response_size,"%s",wire);return;}
    if(s->hooks.console_write){s->hooks.console_write(wire,strlen(wire));return;}
    flockfile(stdout);fputs(wire,stdout);fflush(stdout);funlockfile(stdout);
}
static int sha(const void *p,size_t n,unsigned char out[32]) { return mbedtls_sha256(p,n,out,0)==0; }
static void path_for(unsigned slot,unsigned bank,char path[64]) { snprintf(path,64,"/patches/slot%02u_%c.wsp",slot,bank?'b':'a'); }
static void reply_send(uint32_t id,const char *op,const char *text,bool cache,uint32_t crc)
{
    size_t n=patch_frame_encode(id,op,text,strlen(text),s->wire,sizeof s->wire);
    if(!n)return;
    wire_send(s->wire);
    if(cache) {memcpy(s->cached_wire,s->wire,n+1);s->last_id=id;s->last_crc=crc;s->cached_channel=s->channel;s->cached=true;}
}
static void publish(void) {if(s->hooks.display)s->hooks.display(&s->active_meta,s->graph[s->active],s->names,s->active_slot,(const char *)s->active_blob+s->active_meta.graph_bytes,s->active_meta.source_bytes);}
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
static int activate_stage(int slot,bool start)
{
    unsigned next=1-s->active;
    if(!((s->stage_meta.flags&PATCH_DEFINITION)?(s->hooks.define && s->hooks.define(s->graph[next],start)):s->hooks.activate(s->graph[next]))) {s->faulted=true;snprintf(s->error,160,"Activation acknowledgement failed; reset required");return 0;}
    unsigned char *old=s->active_blob;s->active_blob=s->stage_blob;s->stage_blob=old;
    s->active_meta=s->stage_meta;s->active=next;s->active_slot=slot;s->state=3;s->stage_master=false;
    publish();return 1;
}
static int load_slot(unsigned slot,bool start)
{
    if(slot>PATCH_SLOTS || (slot && !s->mounted)) {snprintf(s->error,160,"Slot unavailable");return 0;}
    if(!begin_maintenance("LOADING"))return 0;
    int ok=1;
    if(!slot) {s->stage_meta=s->factory_meta;memcpy(s->stage_blob,s->factory,s->factory_bytes);}
    else ok=scan_slot(slot,&s->stage_meta,true);
    if(ok)ok=fm_load(s->graph[1-s->active],s->stage_blob,s->stage_meta.graph_bytes,s->error,160) &&
             patch_validate(s->graph[1-s->active],&s->stage_meta,s->error);
    if(ok && s->mounted && !persist_selection(slot)) {snprintf(s->error,160,"Boot selection update failed; active patch retained");ok=0;}
    if(ok)ok=activate_stage((int)slot,start);
    int resumed=end_maintenance();return ok && resumed;
}
static int save_slot(unsigned slot)
{
    if(!slot || slot>PATCH_SLOTS || !s->mounted) {snprintf(s->error,160,"Writable slot unavailable");return 0;}
    if(!begin_maintenance("SAVING"))return 0;
    patch_meta existing;int exists=scan_slot(slot,&existing,false);
    if(exists && existing.graph_bytes==s->active_meta.graph_bytes && existing.source_bytes==s->active_meta.source_bytes &&
       !memcmp(existing.graph_hash,s->active_meta.graph_hash,32) && !memcmp(existing.source_hash,s->active_meta.source_hash,32) &&
       !strcmp(existing.name,s->active_meta.name) && !memcmp(existing.label,s->active_meta.label,48) && existing.mapping==s->active_meta.mapping && existing.flags==s->active_meta.flags) {
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
static void master_path(unsigned bank,char path[64]) {snprintf(path,64,"/patches/master01_%c.wsp",bank?'b':'a');}
static void master_publish(void)
{
    if(s->hooks.master_display)s->hooks.master_display(s->master_name,s->master_slot);
}
static int master_scan(patch_meta *winner,bool copy)
{
    uint32_t best=0;int bank=-1;
    for(unsigned b=0;b<2;++b){
        char path[64];patch_meta meta;uint32_t gen=0;master_path(b,path);
        int valid=patch_record_read(path,&meta,&gen,s->work,PATCH_BLOB_BYTES,sha,s->error) &&
            fm_load(s->master_graph[1-s->master_active],s->work,meta.graph_bytes,s->error,160) &&
            patch_validate_master(s->master_graph[1-s->master_active],&meta,s->error);
        s->master_generations[b]=valid?gen:0;
        if(valid && gen>best){best=gen;bank=(int)b;*winner=meta;}
    }
    if(bank<0)return 0;
    if(copy){char path[64];uint32_t gen;master_path((unsigned)bank,path);
        if(!patch_record_read(path,winner,&gen,s->stage_blob,PATCH_BLOB_BYTES,sha,s->error))return 0;}
    return 1;
}
static int master_persist(unsigned slot)
{
    return s->mounted && nvs_set_u8(s->nvs,"master",(uint8_t)slot)==ESP_OK && nvs_commit(s->nvs)==ESP_OK;
}
static int master_activate_stage(int slot,bool start,bool force)
{
    unsigned next=1-s->master_active;
    if(!s->hooks.master_activate || !(((s->stage_meta.flags&PATCH_DEFINITION) || force)?(s->hooks.master_define && s->hooks.master_define(s->master_graph[next],start)):s->hooks.master_activate(s->master_graph[next]))){
        s->faulted=true;snprintf(s->error,160,"Master activation failed; reset required");return 0;}
    unsigned char *old=s->master_blob;s->master_blob=s->stage_blob;s->stage_blob=old;
    s->master_meta=s->stage_meta;s->master_active=next;s->master_slot=slot;s->state=3;s->stage_master=true;master_publish();return 1;
}
static int master_load(unsigned slot,bool start,bool force)
{
    if(slot>1 || !s->master_blob || (slot && !s->mounted)){snprintf(s->error,160,"Master slot unavailable");return 0;}
    if(!begin_maintenance("LOADING MASTER"))return 0;
    int ok=1;
    if(!slot){s->stage_meta=s->master_factory_meta;
        memcpy(s->stage_blob,s->master_factory,s->master_factory_bytes);
        memcpy(s->stage_blob+s->master_factory_bytes,s->master_source,s->master_source_bytes);}
    else ok=master_scan(&s->stage_meta,true);
    if(ok)ok=fm_load(s->master_graph[1-s->master_active],s->stage_blob,s->stage_meta.graph_bytes,s->error,160) &&
        patch_validate_master(s->master_graph[1-s->master_active],&s->stage_meta,s->error);
    if(ok && s->mounted)ok=master_persist(slot);
    if(ok)ok=master_activate_stage((int)slot,start,force);
    int resumed=end_maintenance();return ok && resumed;
}
static int master_save(unsigned slot)
{
    if(slot!=1 || !s->mounted || !s->master_blob){snprintf(s->error,160,"Only master FX slot 1 is writable");return 0;}
    if(!begin_maintenance("SAVING MASTER"))return 0;
    patch_meta old;unsigned char a[160],b[160];int same=0;
    if(master_scan(&old,false)){patch_meta_encode(&old,a);patch_meta_encode(&s->master_meta,b);same=!memcmp(a+4,b+4,156);}
    int ok=1;
    if(!same){
        unsigned bank=s->master_generations[0]<=s->master_generations[1]?0:1;
        uint32_t gen=s->master_generations[0]>s->master_generations[1]?s->master_generations[0]:s->master_generations[1];
        char path[64];master_path(bank,path);patch_meta check;uint32_t readgen;
        ok=gen!=UINT32_MAX && patch_record_write(path,&s->master_meta,gen+1,s->master_blob,s->error) &&
            patch_record_read(path,&check,&readgen,s->work,PATCH_BLOB_BYTES,sha,s->error) && readgen==gen+1;
        if(ok){patch_meta_encode(&check,a);patch_meta_encode(&s->master_meta,b);ok=!memcmp(a+4,b+4,156);}
        if(ok)s->master_generations[bank]=readgen;
    }
    if(ok){snprintf(s->master_name,32,"%s",s->master_meta.name);ok=master_persist(1);if(ok)s->master_slot=1;master_publish();}
    int resumed=end_maintenance();return ok && resumed;
}
int patches_master_init(fm_graph *first,fm_graph *spare,const void *factory,size_t bytes,const char *source,size_t source_bytes)
{
    if(!s || !first || !spare || bytes>FM_FILE_BYTES || source_bytes>PATCH_SOURCE_BYTES)return 0;
    s->master_blob=heap_caps_malloc(PATCH_BLOB_BYTES,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);if(!s->master_blob)return 0;
    s->master_graph[0]=first;s->master_graph[1]=spare;s->master_factory=factory;s->master_factory_bytes=bytes;
    s->master_source=source;s->master_source_bytes=source_bytes;
    patch_meta *m=&s->master_factory_meta;memset(m,0,sizeof *m);m->graph_bytes=(uint32_t)bytes;m->source_bytes=(uint32_t)source_bytes;
    sha(factory,bytes,m->graph_hash);sha(source,source_bytes,m->source_hash);snprintf(m->name,32,"Bypass");
    for(unsigned k=0;k<4;++k)snprintf(m->label[k],12,"PARAM %u",k+1);
    s->master_meta=*m;memcpy(s->master_blob,factory,bytes);memcpy(s->master_blob+bytes,source,source_bytes);
    patch_meta stored;if(s->mounted && master_scan(&stored,false))snprintf(s->master_name,32,"%s",stored.name);
    master_publish();return 1;
}
void patches_master_restore(bool factory_only)
{
    uint8_t selected=0;if(s->mounted && !factory_only)nvs_get_u8(s->nvs,"master",&selected);
    if(selected==1 && s->master_name[0]){if(!master_load(1,false,false))master_load(0,false,false);}
    else master_load(0,false,false);
    master_publish();
}
bool patches_master_request(unsigned slot)
{
    if(!s || slot>1 || !s->master_blob)return false;
    library_request request={.slot=slot,.save=false,.master=true};return xQueueSend(s->requests,&request,0)==pdTRUE;
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
    /* One saved Main is authoritative. Legacy slot files are left untouched. */
    if(!factory_only && s->mounted && s->names[1][0])
        if(!load_slot(1,false))ESP_LOGE(TAG,"Saved Main rejected: %s; factory retained",s->error);
    publish();
}
bool patches_request(unsigned slot,bool save)
{
    if(!s || slot>PATCH_SLOTS || (save && !slot))return false;
    library_request request={.slot=slot,.save=save,.master=false};return xQueueSend(s->requests,&request,0)==pdTRUE;
}
static uint64_t now_ms(void) {return (uint64_t)esp_timer_get_time()/1000;}
void patches_tick(void)
{
    if(!s)return;
    if((s->state==1||s->state==2) && now_ms()-s->last_rx>10000) {s->state=0;snprintf(s->error,160,"Upload timed out; active patch retained");}
    if(s->state==1 || s->state==2)return; /* Keep queued touch loads out of the staging graph. */
    library_request request;
    if(xQueueReceive(s->requests,&request,0)==pdTRUE) {
        if(s->faulted)return;
        if(s->state==1 || s->state==2) {busy(false,"UPLOAD PENDING");ESP_LOGW(TAG,"Library operation rejected: upload pending");return;}
        int ok=request.master?master_load(request.slot,true,false):request.save?save_slot(request.slot):load_slot(request.slot,true);
        if(!ok && !s->faulted)busy(false,request.save?"SAVE FAILED":"LOAD FAILED");
        ESP_LOGI(TAG,"Library %s slot %u: %s",request.save?"save":"load",request.slot,ok?"OK":s->error);
    }
}
static void process_line(const char *line)
{
    if(!s)return;
    unsigned char payload[PATCH_FRAME_PAYLOAD];size_t length=sizeof payload;uint32_t id=0;
    char op[16];
    if(!patch_frame_decode(line,&id,op,payload,&length,s->error)) {reply_send(0,"ERR",s->error,false,0);return;}
    bool read=!strcmp(op,"HELLO") || !strcmp(op,"STATUS") || !strcmp(op,"LIST") || !strcmp(op,"FXLIST") || !strcmp(op,"INFO") || !strcmp(op,"FXINFO") || !strcmp(op,"READ") || !strcmp(op,"FXREAD") || !strcmp(op,"NETINFO") || !strcmp(op,"CAPINFO") || !strcmp(op,"CAPREAD") || !strcmp(op,"INPUTS");
    /* Queries stay dark; repeated valid data frames still count as reception. */
    if(!read && strcmp(op,"RCINFO") && strcmp(op,"NETPAIR") && strcmp(op,"NETSCAN") &&
       ((strcmp(op,"FX") && strcmp(op,"VOLUME")) || length))device_network_received();
    uint32_t crc=patch_crc32(line,strlen(line));
    if(s->cached && id==s->last_id && s->cached_channel==s->channel) {
        if(crc==s->last_crc)wire_send(s->cached_wire);
        else reply_send(id,"ERR","Request ID reused with different content",false,0);
        return;
    }
    s->last_rx=now_ms();s->reply[0]=0;s->error[0]=0;int ok=1;
    if((s->state==1 || s->state==2) && s->channel!=s->transfer_channel && !read){reply_send(id,"ERR","Another transport owns this transfer",true,crc);return;}
    if(s->faulted && strcmp(op,"HELLO") && strcmp(op,"STATUS") && strcmp(op,"LIST")) {
        reply_send(id,"ERR","Audio ownership uncertain; reset required",true,crc);return;
    }
    if(!strcmp(op,"HELLO") && !length) {
        size_t total=0,used=0;if(s->mounted)esp_spiffs_info("storage",&total,&used);
        snprintf(s->reply,sizeof s->reply,"{\"protocol\":1,\"model\":\"%s\",\"build\":\"%s\",\"engine\":\"%s\",\"profile\":\"%s\",\"rate\":44100,\"block\":64,\"voices\":1,\"effects\":1,\"continuous_blocks\":true,\"master_slots\":2,\"atomic_install\":true,\"global_volume\":true,\"remote_controls\":1,\"control_deltas\":1,\"definition_lifecycle\":1,\"transports\":[\"usb-serial-jtag\",\"wifi-http\"],\"graph_max\":65536,\"source_max\":65536,\"chunk\":256,\"slots\":1,\"main_slot\":1,\"fx_slot\":1,\"fx_bypass_slot\":0,\"storage\":%s,\"storage_total\":%u,\"storage_free\":%u,\"policy\":\"%s\",\"catalog\":%s}",BOARD_MODEL,s->hooks.build_id,s->hooks.engine_commit,s->hooks.profile_hash,s->mounted?"true":"false",(unsigned)total,(unsigned)(total-used),PATCH_POLICY,PATCH_CATALOG_JSON);
        /* Identity is also carried by USB so pairing never relies on an IP. */
        size_t end=strlen(s->reply);if(end && s->reply[end-1]=='}')snprintf(s->reply+end-1,sizeof s->reply-end+1,",\"device_id\":\"%s\",\"device_name\":\"%s\",\"wifi_upload\":true}",device_network_id(),device_network_name());
#ifdef FM_SIGNAL_REUSE
        end=strlen(s->reply);if(end && s->reply[end-1]=='}')snprintf(s->reply+end-1,sizeof s->reply-end+1,",\"graph_limits\":{\"nodes\":%u,\"signals\":%u,\"inputs\":%u,\"audio_buffers\":%u},\"signal_reuse\":1}",FM_NODES,FM_OUTPUTS,FM_INPUTS,FM_AUDIO_BUFFERS);
#endif
#ifdef CONFIG_SYNTHDEF_HEADLESS
        end=strlen(s->reply);if(end && s->reply[end-1]=='}')snprintf(s->reply+end-1,sizeof s->reply-end+1,",\"headless\":true,\"output_channels\":2,\"pcm_capture\":1,\"pcm_capture_chunk\":%u,\"pcm_capture_id\":1,\"input_buses\":[8,9,10]}",BOARD_CAPTURE_CHUNK_BYTES);
#endif
        const patch_program_usage *program = &s->hooks.program;
        end = strlen(s->reply);
        if (end && s->reply[end - 1] == '}' && s->hooks.identify)
            snprintf(s->reply + end - 1, sizeof s->reply - end + 1, ",\"identify_tone\":1}");
        end = strlen(s->reply);
        if (end && s->reply[end - 1] == '}') {
            snprintf(s->reply + end - 1, sizeof s->reply - end + 1,
                     ",\"program\":{\"iram_bytes\":%u,\"dram_bytes\":%u,"
                     "\"app_bytes\":%u,\"partition_bytes\":%u}}",
                     program->iram_bytes, program->dram_bytes,
                     program->app_bytes, program->partition_bytes);
        }

#ifdef CONFIG_SYNTHDEF_HEADLESS
    } else if(!strcmp(op,"INPUTS") && !length) {
        ok=headless_io_info(s->reply,sizeof s->reply);
    } else if(!strcmp(op,"CAPBEGIN") || !strcmp(op,"CAPINFO") || !strcmp(op,"CAPREAD")) {
        ok=board_audio_capture_command(op,payload,length,s->reply,sizeof s->reply);
        if(!ok)snprintf(s->error,sizeof s->error,"Capture busy, unavailable or invalid request");
#endif
    } else if(!strcmp(op,"RCINFO") || !strcmp(op,"RCEVENT")) {
        if(s->state==1 || s->state==2){reply_send(id,"ERR","Upload pending; controls unavailable",true,crc);return;}
        int result=s->hooks.remote?s->hooks.remote(op,payload,length,s->reply,sizeof s->reply):0;
        ok=result>0;if(result<0)s->faulted=true;
        if(!ok)snprintf(s->error,sizeof s->error,result<0?"Remote ownership uncertain; reset required":"Invalid, stale, late or full remote command");
    } else if((!strcmp(op,"START") || !strcmp(op,"STOP")) && length>=10) {
        if(s->state==1 || s->state==2){reply_send(id,"ERR","Upload pending; instances unavailable",true,crc);return;}
        int result=s->hooks.instance?s->hooks.instance(!strcmp(op,"START"),payload,length):0;
        ok=result>0;if(result<0)s->faulted=true;
        if(ok)snprintf(s->reply,sizeof s->reply,"{\"started\":%s}",!strcmp(op,"START")?"true":"false");
        else snprintf(s->error,sizeof s->error,result<0?"Instance ownership uncertain; reset required":"Invalid or stale instance request");
    } else if(!strncmp(op,"NET",3) && !s->channel) {
        bool setup=!strcmp(op,"NETCFG") || !strcmp(op,"NETSCAN");
        ok=!setup || begin_maintenance("WIFI SETTINGS");
        if(ok){ok=device_network_command(op,payload,length,s->reply,sizeof s->reply);if(setup){int resumed=end_maintenance();ok=ok && resumed;}}
        if(!ok)snprintf(s->error,sizeof s->error,"Invalid network settings or networking unavailable");
    } else if(!strcmp(op,"IDENTIFY") && !length) {
        ok=s->state!=1 && s->state!=2 && s->hooks.identify && s->hooks.identify();
        if(ok)snprintf(s->reply,sizeof s->reply,"{\"identifying\":true,\"frequency\":440,\"duration_ms\":500}");
        else snprintf(s->error,sizeof s->error,"Identify unavailable or audio busy");
    } else if((!strcmp(op,"VOLUME") && length<=1) || (!strcmp(op,"VOLSAVE") && !length)) {
        int value=s->hooks.volume?s->hooks.volume(length?(int)payload[0]:-1,!strcmp(op,"VOLSAVE")):-1;
        ok=value>=0;if(ok)snprintf(s->reply,sizeof s->reply,"{\"percent\":%d}",value);
        else snprintf(s->error,sizeof s->error,"Invalid volume or audio busy");
    } else if(!strcmp(op,"FX") && (length==0 || length==12)) {
        float input[3],output[3];
        for(unsigned k=0;k<3 && length;++k) {uint32_t bits=patch_get32(payload+4*k);memcpy(&input[k],&bits,sizeof bits);}
        ok=s->hooks.effect && s->hooks.effect(length?input:NULL,output);
        if(ok)snprintf(s->reply,sizeof s->reply,"{\"time\":%.6f,\"feedback\":%.6f,\"wet\":%.6f,\"max_time\":5,\"arena_bytes\":1048576}",output[0],output[1],output[2]);
        else snprintf(s->error,sizeof s->error,"Invalid delay controls or audio busy");
    } else if(!strcmp(op,"FXSAVE") && !length) {
        ok=s->hooks.effect_save && s->hooks.effect_save();if(ok)snprintf(s->reply,sizeof s->reply,"{\"saved\":true}");
    } else if(!strcmp(op,"STATUS") && !length) {
        char hash[65];for(unsigned k=0;k<32;++k)snprintf(hash+2*k,3,"%02x",s->active_meta.graph_hash[k]);
        snprintf(s->reply,sizeof s->reply,"{\"state\":%u,\"reset_required\":%s,\"received\":%lu,\"transfer\":%lu,\"slot\":%d,\"name\":\"%s\",\"graph_sha256\":\"%s\",\"continuous\":%s,\"seed\":%lu}",s->state,s->faulted?"true":"false",(unsigned long)s->received,(unsigned long)s->stage_meta.transfer,s->active_slot,s->active_meta.name,hash,graph_continuous_mode(s->graph[s->active])==1?"true":"false",(unsigned long)(s->hooks.seed?s->hooks.seed():0));
    } else if((!strcmp(op,"INFO") || !strcmp(op,"FXINFO")) && !length) {
        bool master=!strcmp(op,"FXINFO");if(master && !s->master_blob){reply_send(id,"ERR","Master slots unavailable",true,crc);return;}
        unsigned char meta[PATCH_META_BYTES];char hex[PATCH_META_BYTES*2+1];patch_meta_encode(master?&s->master_meta:&s->active_meta,meta);
        for(unsigned k=0;k<PATCH_META_BYTES;++k)snprintf(hex+2*k,3,"%02x",meta[k]);
        snprintf(s->reply,sizeof s->reply,"{\"slot\":%d,\"manifest\":\"%s\"}",master?s->master_slot:s->active_slot,hex);
    } else if((!strcmp(op,"READ") || !strcmp(op,"FXREAD")) && length==6) {
        bool master=!strcmp(op,"FXREAD");const patch_meta *meta=master?&s->master_meta:&s->active_meta;
        const unsigned char *blob=master?s->master_blob:s->active_blob;
        uint32_t offset=patch_get32(payload),count=(unsigned)payload[4]|(unsigned)payload[5]<<8;
        uint32_t total=meta->graph_bytes+meta->source_bytes;
        if(!blob || !count || count>256 || offset>total || count>total-offset)ok=0;
        else {
            char hex[513];for(unsigned k=0;k<count;++k)snprintf(hex+2*k,3,"%02x",blob[offset+k]);
            snprintf(s->reply,sizeof s->reply,"{\"offset\":%lu,\"data\":\"%s\"}",(unsigned long)offset,hex);
        }
    } else if(!strcmp(op,"LIST") && !length) {
        size_t at=0;at+=snprintf(s->reply,sizeof s->reply,"[");
        for(unsigned k=0;k<=PATCH_SLOTS;++k)at+=snprintf(s->reply+at,sizeof s->reply-at,"%s{\"slot\":%u,\"name\":\"%s\",\"generations\":[%lu,%lu]}",k?",":"",k,s->names[k],k?(unsigned long)s->generations[k-1][0]:0,k?(unsigned long)s->generations[k-1][1]:0);
        snprintf(s->reply+at,sizeof s->reply-at,"]");
    } else if(!strcmp(op,"FXLIST") && !length && s->master_blob) {
        snprintf(s->reply,sizeof s->reply,"[{\"slot\":0,\"name\":\"Bypass\",\"generations\":[0,0],\"selected\":%s},{\"slot\":1,\"name\":\"%s\",\"generations\":[%lu,%lu],\"selected\":%s}]",
            s->master_slot==0?"true":"false",s->master_name,(unsigned long)s->master_generations[0],(unsigned long)s->master_generations[1],s->master_slot==1?"true":"false");
    } else if((!strcmp(op,"FXLOAD") || !strcmp(op,"FXSELECT") || !strcmp(op,"FXSAVE")) && length==1 && s->master_blob) {
        if(s->state==1 || s->state==2)ok=0;
        else ok=strcmp(op,"FXSAVE")?master_load(payload[0],strcmp(op,"FXSELECT")!=0,!strcmp(op,"FXSELECT")):master_save(payload[0]);
        if(ok)snprintf(s->reply,sizeof s->reply,"{\"slot\":%u}",payload[0]);
    } else if(!strcmp(op,"BEGIN") || (!strcmp(op,"FXBEGIN") && s->master_blob)) {
        patch_meta m;
        bool master=!strcmp(op,"FXBEGIN");
        ok=patch_meta_decode(payload,length,&m,s->error) && m.transfer!=0;
        if(ok) {
            if(!(s->state==1 && s->stage_master==master && !memcmp(&m,&s->stage_meta,sizeof m))) {s->stage_meta=m;s->received=0;s->state=1;s->stage_master=master;s->transfer_channel=s->channel;}
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
            fm_load(s->stage_master?s->master_graph[1-s->master_active]:s->graph[1-s->active],s->stage_blob,s->stage_meta.graph_bytes,s->error,160) &&
            (s->stage_master?patch_validate_master(s->master_graph[1-s->master_active],&s->stage_meta,s->error):patch_validate(s->graph[1-s->active],&s->stage_meta,s->error));
        if(ok) {s->state=2;snprintf(s->reply,sizeof s->reply,"{\"ready\":true}");}
        else {s->state=0;s->received=0;}
    } else if(!strcmp(op,"INSTALL") && length==5) {
        unsigned slot=payload[4];bool master=s->stage_master;
        ok=s->state==2 && patch_get32(payload)==s->stage_meta.transfer && (master?slot==1:slot>=1 && slot<=PATCH_SLOTS);
        if(ok){
            ok=begin_maintenance("INSTALLING");
            if(ok){ok=master?master_activate_stage(-1,false,false):activate_stage(-1,false);int resumed=end_maintenance();ok=ok&&resumed;}
            /* One console transaction: queued screen/library changes cannot
             * replace the active package between activation and saving. */
            if(ok)ok=master?master_save(slot):save_slot(slot);
        }
        if(ok)snprintf(s->reply,sizeof s->reply,"{\"saved\":true,\"slot\":%u}",slot);
    } else if(!strcmp(op,"ACTIVATE") && length==4) {
        if(patch_get32(payload)!=s->stage_meta.transfer || (s->state!=2 && s->state!=3))ok=0;
        else if(s->state==2) {
            ok=begin_maintenance("LOADING");
            if(ok) {ok=s->stage_master?master_activate_stage(-1,false,false):activate_stage(-1,false);int resumed=end_maintenance();ok=ok&&resumed;}
        }
        if(ok)snprintf(s->reply,sizeof s->reply,"{\"active\":true}");
    } else if(!strcmp(op,"ABORT") && !length) {s->state=0;s->received=0;snprintf(s->reply,sizeof s->reply,"{\"aborted\":true}");
    } else if((!strcmp(op,"SAVE") || !strcmp(op,"LOAD")) && length==1) {
        if(s->state==1 || s->state==2)ok=0;
        else ok=!strcmp(op,"SAVE")?save_slot(payload[0]):load_slot(payload[0],true);
        if(ok)snprintf(s->reply,sizeof s->reply,"{\"slot\":%u}",payload[0]);
    } else if(!strcmp(op,"PANIC") && !length) {
        ok=begin_maintenance("STOPPED");
        if(ok){int stopped=s->hooks.stop && s->hooks.stop();int resumed=end_maintenance();ok=stopped && resumed;}
        if(ok)snprintf(s->reply,sizeof s->reply,"{\"stopped\":true}");
    } else {ok=0;snprintf(s->error,160,"Unsupported operation or payload");}
    if(!ok && !s->error[0])snprintf(s->error,160,"Invalid transfer state or incomplete package");
    reply_send(id,ok?"OK":"ERR",ok?s->reply:s->error,true,crc);
}
void patches_line(const char *line){if(s){s->channel=0;process_line(line);}}
void patches_exchange(const char *line,char *reply,size_t size)
{
    if(!s || !size)return;
    reply[0]=0;s->response=reply;s->response_size=size;s->channel=1;process_line(line);s->response=NULL;s->channel=0;
}
