/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <inttypes.h>
#include <math.h>
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_app_desc.h"
#include "esp_chip_info.h"
#include "esp_flash.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_psram.h"
#include "esp_timer.h"
#include "bsp/esp-bsp.h"
#include "board_audio.h"
#include "instrument.h"
#include "touch_ui.h"
#include "patch_service.h"
#include "generated.h"
#include "diagnostics.h"

#define SAMPLE_RATE 44100u
#define EVENT_CAPACITY 16
#define AUDIO_STACK_BYTES 16384
static const char *TAG = "synthdef";
static instrument synth;
static QueueHandle_t events, telemetry;
static atomic_bool panic_requested;
static atomic_uint overflow_count;
static atomic_uint note_sequence, control_dirty, controls_coalesced;
static atomic_uint control_words[INST_CONTROL_COUNT];
static atomic_bool audio_started,reject_events;
#ifdef CONFIG_SYNTHDEF_DIAGNOSTICS
static atomic_uint profile_epoch;
#endif
static QueueHandle_t audio_commands,audio_ack;
static float controller_frequency=440.0f,controller_amplitude=0.5f;
typedef struct { unsigned kind; fm_graph *graph; } audio_command;
enum { AUDIO_PARK=1,AUDIO_ACTIVATE,AUDIO_RESUME,AUDIO_BENCH };
#ifdef CONFIG_SYNTHDEF_TOUCH_UI
static atomic_bool snapshot_requested;
#endif

static uint64_t audio_clock_us(void) { return (uint64_t)esp_timer_get_time(); }

#ifdef CONFIG_SYNTHDEF_OFFLINE_CAPTURE
static void offline_capture(fm_graph *graph, fm_voice *voice, fm_scratch *scratch)
{
    enum { BLOCKS = 345, GATE_OFF = 172 };
    const size_t samples = BLOCKS * FM_BLOCK * 2;
    float *capture = heap_caps_calloc(samples, sizeof(float), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!capture || !fm_start(voice, graph, SAMPLE_RATE) ||
        !fm_bind_delay(voice, graph, NULL, 0) || !fm_seed(voice, 0)) {
        ESP_LOGE(TAG, "Offline capture allocation/start failed"); return;
    }
    int64_t begin = esp_timer_get_time();
    for (unsigned b = 0; b < BLOCKS; ++b) {
        if (b == GATE_OFF) fm_set(voice, graph, "gate", 0);
        fm_render(graph, voice, scratch, capture + b * FM_BLOCK * 2);
        if (voice->fault) { ESP_LOGE(TAG, "Offline DSP fault at block %u", b); heap_caps_free(capture); return; }
    }
    int64_t elapsed = esp_timer_get_time() - begin;
    printf("CAPTURE_BEGIN blocks=%d gate_off=%d rate=%u seed=0 bytes=%u render_us=%" PRId64 "\n",
           BLOCKS, GATE_OFF, SAMPLE_RATE, (unsigned)(samples * sizeof(float)), elapsed);
    static const char hex[] = "0123456789abcdef";
    for (unsigned b = 0; b < BLOCKS; ++b) {
        char line[FM_BLOCK * 2 * sizeof(float) * 2 + 1];
        const unsigned char *bytes = (const unsigned char *)(capture + b * FM_BLOCK * 2);
        for (unsigned j = 0; j < FM_BLOCK * 2 * sizeof(float); ++j) {
            line[2*j] = hex[bytes[j] >> 4]; line[2*j+1] = hex[bytes[j] & 15];
        }
        line[sizeof line - 1] = 0;
        printf("CAPTURE_BLOCK %u %s\n", b, line);
        if (b % 8 == 0) vTaskDelay(1);
    }
    puts("CAPTURE_END");
    heap_caps_free(capture);
}
#endif

typedef struct {
    uint64_t frame, faults, clips, nonfinite, rejected, write_failures, partial_writes;
    uint64_t budget_exceeded;
    uint32_t render_max_us, prep_max_us, combined_max_us, write_max_us, queue_high;
    uint32_t audio_stack_free_bytes, active;
    uint32_t pcm_peak, pcm_peak_max,current_fault;
    float base_frequency;
    uint32_t worst_reset,worst_controls,worst_prepare,worst_dsp,worst_pcm;
    float worst_knobs[4];
#ifdef CONFIG_SYNTHDEF_DIAGNOSTICS
    uint32_t epoch,profile_render,profile_prep,profile_combined,profile_budget;
    uint32_t profile_worst[5];
    float profile_knobs[4];
#endif
} audio_stats;

static void *internal_alloc(size_t size)
{
    void *p = heap_caps_calloc(1, size, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    if (!p) ESP_LOGE(TAG, "Internal allocation failed: %u bytes", (unsigned)size);
    return p;
}

static void audio_task(void *unused)
{
    (void)unused;
    audio_stats stats = {0};
    ESP_ERROR_CHECK(board_audio_start_dma());
    /* One internal PCM buffer reused only after the blocking driver copies it. */
    int16_t mono[FM_BLOCK];
    uint64_t next_snapshot = SAMPLE_RATE;
    unsigned parking=0;
    bool parked=false;
    uint64_t faults_base=0,clips_base=0,nonfinite_base=0,rejected_base=0;
    for (;;) {
#ifdef CONFIG_SYNTHDEF_DIAGNOSTICS
        unsigned epoch=atomic_load_explicit(&profile_epoch,memory_order_relaxed);
        if(epoch!=stats.epoch) {
            stats.epoch=epoch;stats.profile_render=stats.profile_prep=stats.profile_combined=stats.profile_budget=0;
            memset(stats.profile_worst,0,sizeof stats.profile_worst);
            memset(stats.profile_knobs,0,sizeof stats.profile_knobs);
            synth.preparation_max_us=0;
        }
#endif
        audio_command command;
        if(parked) {
            if(xQueueReceive(audio_commands,&command,portMAX_DELAY)!=pdTRUE)continue;
            int ok=1;
            if(command.kind==AUDIO_ACTIVATE) {
                faults_base+=synth.faults;clips_base+=synth.clipped;
                nonfinite_base+=synth.nonfinite;rejected_base+=synth.rejected;
                ok=instrument_init(&synth,command.graph,synth.voice,synth.scratch,NULL,0,SAMPLE_RATE);
                synth.clock_us=audio_clock_us;
            }
#ifdef CONFIG_SYNTHDEF_DIAGNOSTICS
            else if(command.kind==AUDIO_BENCH)diagnostic_benchmark(&synth);
#endif
            else if(command.kind==AUDIO_RESUME) {ok=board_audio_start_dma()==ESP_OK;if(ok)parked=false;}
            else ok=0;
            xQueueOverwrite(audio_ack,&ok);
            continue;
        }
        if(xQueueReceive(audio_commands,&command,0)==pdTRUE) {
            if(command.kind==AUDIO_PARK) {parking=14;xQueueReset(events);atomic_store(&control_dirty,0);}
            else {int ok=0;xQueueOverwrite(audio_ack,&ok);}
        }
        int64_t begin = esp_timer_get_time();
        synth.reset_us=synth.controls_us=synth.prepare_us=0;
        unsigned queued = uxQueueMessagesWaiting(events);
        if (queued > stats.queue_high) stats.queue_high = queued;
        if(parking) { /* Fade two blocks, then drain a DMA queue of silence. */
            if(parking==12)instrument_panic(&synth);
        } else if (atomic_exchange_explicit(&panic_requested, false, memory_order_relaxed)) {
            xQueueReset(events);
            instrument_panic(&synth);
        } else {
            inst_event pending[EVENT_CAPACITY + INST_CONTROL_COUNT];
            unsigned count = 0;
            while (count < EVENT_CAPACITY && xQueueReceive(events, &pending[count], 0) == pdTRUE) ++count;
            unsigned dirty=atomic_exchange_explicit(&control_dirty,0,memory_order_acquire);
            for (unsigned k=0;k<INST_CONTROL_COUNT;++k) {
                if (!(dirty & (1u<<k))) continue;
                uint32_t bits=atomic_load_explicit(&control_words[k],memory_order_relaxed);
                float value; memcpy(&value,&bits,sizeof value);
                pending[count++]=(inst_event){(inst_event_type)(INST_FREQ+k),0,value};
            }
            instrument_apply_batch(&synth, pending, count);
            if(synth.preparation_max_us>stats.prep_max_us)stats.prep_max_us=synth.preparation_max_us;
        }
        int64_t render_begin = esp_timer_get_time();
        instrument_render(&synth, mono);
        if(parking>=13) {
            unsigned block=14-parking;
            for(unsigned i=0;i<FM_BLOCK;++i)mono[i]=(int16_t)((int32_t)mono[i]*(int32_t)(127-block*64-i)/128);
        }
        stats.pcm_peak = 0;
        for (unsigned i = 0; i < FM_BLOCK; ++i) {
            uint32_t magnitude = mono[i] < 0 ? -(int32_t)mono[i] : mono[i];
            if (magnitude > stats.pcm_peak) stats.pcm_peak = magnitude;
        }
        if (stats.pcm_peak > stats.pcm_peak_max) stats.pcm_peak_max = stats.pcm_peak;
        uint32_t render_us = (uint32_t)(esp_timer_get_time() - render_begin);
        uint32_t combined_us = (uint32_t)(esp_timer_get_time() - begin);
        if (render_us > stats.render_max_us) stats.render_max_us = render_us;
        if (combined_us > stats.combined_max_us) {
            stats.combined_max_us=combined_us;stats.worst_reset=synth.reset_us;stats.worst_controls=synth.controls_us;
            stats.worst_prepare=synth.prepare_us;stats.worst_dsp=synth.dsp_us;stats.worst_pcm=synth.pcm_us;
            memcpy(stats.worst_knobs,synth.knob,sizeof stats.worst_knobs);
        }
        bool over_budget=(uint64_t)combined_us * SAMPLE_RATE * 10 > (uint64_t)FM_BLOCK * 1000000 * 7;
        if (over_budget)
            ++stats.budget_exceeded;
#ifdef CONFIG_SYNTHDEF_DIAGNOSTICS
        if(render_us>stats.profile_render)stats.profile_render=render_us;
        if(synth.preparation_max_us>stats.profile_prep)stats.profile_prep=synth.preparation_max_us;
        if(combined_us>stats.profile_combined) {
            stats.profile_combined=combined_us;
            const uint32_t phases[]={synth.reset_us,synth.controls_us,synth.prepare_us,synth.dsp_us,synth.pcm_us};
            memcpy(stats.profile_worst,phases,sizeof phases);memcpy(stats.profile_knobs,synth.knob,sizeof stats.profile_knobs);
        }
        if(over_budget)++stats.profile_budget;
#endif
        size_t written = 0;
        int64_t write_begin = esp_timer_get_time();
        esp_err_t err = board_audio_write(mono, FM_BLOCK, &written);
        uint32_t write_us = (uint32_t)(esp_timer_get_time() - write_begin);
        if (write_us > stats.write_max_us) stats.write_max_us = write_us;
        if (err != ESP_OK || written != sizeof mono) {
            if (err != ESP_OK) ++stats.write_failures;
            if (written != sizeof mono) ++stats.partial_writes;
            instrument_panic(&synth);
            board_audio_mute();
            xQueueOverwrite(telemetry, &stats);
            /* Stop after a failed transfer; a reset restores a known pipeline. */
            vTaskDelete(NULL);
        }
        if(parking && !--parking) {
            parked=true;instrument_panic(&synth);
            int ok=board_audio_stop_dma()==ESP_OK;xQueueOverwrite(audio_ack,&ok);
        }
        stats.frame += FM_BLOCK;
        if (stats.frame >= next_snapshot) {
            stats.faults = faults_base+synth.faults;
            stats.clips = clips_base+synth.clipped; stats.nonfinite = nonfinite_base+synth.nonfinite;
            stats.rejected = rejected_base+synth.rejected; stats.active = synth.voice->active;
            stats.current_fault=synth.voice->fault;
            stats.base_frequency = synth.frequency;
            stats.audio_stack_free_bytes = uxTaskGetStackHighWaterMark(NULL);
            xQueueOverwrite(telemetry, &stats);
            next_snapshot = stats.frame + SAMPLE_RATE;
        }
    }
}

static uint32_t new_note(void)
{
    return atomic_fetch_add_explicit(&note_sequence,1,memory_order_relaxed)+1;
}

static void request_panic(void)
{
    atomic_store_explicit(&panic_requested,true,memory_order_relaxed);
}

static bool send_event(inst_event_type type, uint32_t note, float value)
{
    if(atomic_load_explicit(&reject_events,memory_order_relaxed))return false;
    if (type>=INST_FREQ && type<=INST_KNOB4) {
        unsigned k=(unsigned)type-INST_FREQ;
        uint32_t bits; memcpy(&bits,&value,sizeof bits);
        atomic_store_explicit(&control_words[k],bits,memory_order_relaxed);
        unsigned old=atomic_fetch_or_explicit(&control_dirty,1u<<k,memory_order_release);
        if (old & (1u<<k)) atomic_fetch_add_explicit(&controls_coalesced,1,memory_order_relaxed);
        return true;
    }
    inst_event e = { .type = type, .note_id = note, .value = value };
    if (xQueueSend(events, &e, 0) != pdTRUE) {
        atomic_fetch_add_explicit(&overflow_count, 1, memory_order_relaxed);
        request_panic();
        return false;
    }
    return true;
}

static int audio_call(unsigned kind,fm_graph *graph)
{
    audio_command command={kind,graph};int ok=0;
    xQueueReset(audio_ack);
    if(xQueueSend(audio_commands,&command,pdMS_TO_TICKS(100))!=pdTRUE)return 0;
    return xQueueReceive(audio_ack,&ok,pdMS_TO_TICKS(kind==AUDIO_BENCH?10000:1000))==pdTRUE && ok;
}
static int service_pause(bool pause)
{
    if(!atomic_load(&audio_started)) {atomic_store(&reject_events,pause);return 1;}
    if(pause) {
        atomic_store(&reject_events,true);
        if(!audio_call(AUDIO_PARK,NULL)) {board_audio_mute();return 0;}
        return board_audio_pause()==ESP_OK;
    }
    if(!audio_call(AUDIO_RESUME,NULL) || board_audio_resume()!=ESP_OK) {board_audio_mute();return 0;}
    atomic_store(&reject_events,false);return 1;
}
static int service_activate(fm_graph *graph)
{
    if(atomic_load(&audio_started))return audio_call(AUDIO_ACTIVATE,graph);
    int ok=instrument_init(&synth,graph,synth.voice,synth.scratch,NULL,0,SAMPLE_RATE);
    synth.clock_us=audio_clock_us;return ok;
}
static void service_display(const patch_meta *meta,const fm_graph *graph,const char names[PATCH_SLOTS+1][32],int slot)
{
    for(unsigned i=0;i<graph->names;++i) {
        if(!strcmp(graph->control_name[i].name,"freq"))controller_frequency=graph->defaults[graph->control_name[i].index];
        if(!strcmp(graph->control_name[i].name,"amp"))controller_amplitude=graph->defaults[graph->control_name[i].index];
    }
#ifdef CONFIG_SYNTHDEF_TOUCH_UI
    float knobs[4]={0};
    for(unsigned k=0;k<4;++k)for(unsigned i=0;i<graph->names;++i) {
        char name[8];snprintf(name,sizeof name,"knob%u",k+1);
        if(!strcmp(graph->control_name[i].name,name))knobs[k]=graph->defaults[graph->control_name[i].index];
    }
    touch_ui_patch(meta->name,meta->label,meta->mapping,knobs,controller_frequency,names,slot);
#else
    (void)meta;(void)names;(void)slot;
#endif
}
static void service_busy(bool yes,const char *text)
{
#ifdef CONFIG_SYNTHDEF_TOUCH_UI
    touch_ui_busy(yes,text);
#else
    (void)yes;(void)text;
#endif
}

static void console_task(void *unused)
{
    (void)unused;
    uint32_t note = 0;
    char frame[PATCH_FRAME_BYTES];size_t frame_size=0;bool framing=false,discard=false;
    for (;;) {
        patches_tick();
        int c = getchar();
        if(framing) {
            if(c=='@') {frame_size=1;frame[0]='@';discard=false;continue;}
            if(c=='!') {request_panic();framing=false;frame_size=0;discard=false;continue;}
            if(c=='\n') {
                if(!discard) {frame[frame_size]=0;patches_line(frame);}
                framing=false;frame_size=0;discard=false;
            } else if(c!=EOF && c!='\r') {
                if(frame_size+1<sizeof frame)frame[frame_size++]=(char)c;else discard=true;
            }
            if(c==EOF) {clearerr(stdin);vTaskDelay(pdMS_TO_TICKS(1));}
            continue;
        }
        if(c=='@') {framing=true;frame_size=1;frame[0]='@';continue;}
        switch (c) {
        case 'n': note=new_note(); send_event(INST_NOTE_ON, note, 0); break;
        case 'o': send_event(INST_NOTE_OFF, note, 0); break;
        case '!': request_panic(); break;
        case '+': controller_frequency = fminf(controller_frequency * 1.0594631f, 20000.0f); send_event(INST_FREQ, 0, controller_frequency); break;
        case '-': controller_frequency = fmaxf(controller_frequency / 1.0594631f, 20.0f); send_event(INST_FREQ, 0, controller_frequency); break;
        case ']': controller_amplitude = fminf(controller_amplitude + 0.05f, 1.0f); send_event(INST_AMP, 0, controller_amplitude); break;
        case '[': controller_amplitude = fmaxf(controller_amplitude - 0.05f, 0.0f); send_event(INST_AMP, 0, controller_amplitude); break;
#ifdef CONFIG_SYNTHDEF_DIAGNOSTICS
        case 'b': {
            service_busy(true,"MEASURING AUDIO");
            if(service_pause(true) && audio_call(AUDIO_BENCH,NULL) && service_pause(false)) {
                service_busy(false,"READY");diagnostic_report();
            } else {board_audio_mute();service_busy(true,"RESET REQUIRED");}
            break;
        }
#endif
#ifdef CONFIG_SYNTHDEF_TOUCH_UI
#ifdef CONFIG_SYNTHDEF_DIAGNOSTICS
        case 't': {
            unsigned epoch=atomic_fetch_add_explicit(&profile_epoch,1,memory_order_relaxed)+1;
            touch_ui_exercise(true);ESP_LOGI(TAG,"EXERCISE_BEGIN epoch=%u duration_ms=30000",epoch);break;
        }
        case 'x': touch_ui_exercise(false);ESP_LOGI(TAG,"EXERCISE_STOP");break;
#endif
        case 's': request_panic(); atomic_store_explicit(&snapshot_requested,true,memory_order_relaxed); break;
        case 'd': {
            static bool enabled;
            enabled=!enabled; touch_ui_stress(enabled); break;
        }
#endif
        default: break;
        }
        if (c == EOF) { clearerr(stdin); vTaskDelay(pdMS_TO_TICKS(10)); }
    }
}

void app_main(void)
{
    const esp_app_desc_t *app = esp_app_get_description();
    uint32_t flash_bytes = 0;
    ESP_ERROR_CHECK(esp_flash_get_size(NULL, &flash_bytes));
    ESP_LOGI(TAG, "V2 target (user-confirmed; display/touch not probed) IDF=%s compiler=%s", esp_get_idf_version(), __VERSION__);
    ESP_LOGI(TAG, "build=%s engine=%s profile=%s", BUILD_ID, ENGINE_COMMIT, CAPABILITY_HASH);
    ESP_LOGI(TAG, "app=%s version=%s ELF=%02x%02x%02x%02x flash=%" PRIu32 " PSRAM=%u", app->project_name,
             app->version, app->app_elf_sha256[0], app->app_elf_sha256[1], app->app_elf_sha256[2], app->app_elf_sha256[3],
             flash_bytes, (unsigned)esp_psram_get_size());
    ESP_LOGI(TAG, "requested_rate=%u block=%d mono S16 Philips slot=left MCLK=256fs DMA=6x128", SAMPLE_RATE, FM_BLOCK);
    ESP_LOGW(TAG, "Actual clocks, channel packing, continuity and latency require hardware measurement");
    ESP_LOGI(TAG, "graph=%u voice=%u scratch=%u arena=0 baseline_patch=%s touch_patch=%s", (unsigned)sizeof(fm_graph),
             (unsigned)sizeof(fm_voice), (unsigned)sizeof(fm_scratch), PATCH_SHA256, TOUCH_PATCH_SHA256);
    fm_graph *graph = internal_alloc(sizeof *graph);
    fm_voice *voice = internal_alloc(sizeof *voice);
    fm_scratch *scratch = internal_alloc(sizeof *scratch);
    fm_graph *spare = internal_alloc(sizeof *spare);
    if (!graph || !voice || !scratch || !spare) return;
    char error[192];
#if defined(CONFIG_SYNTHDEF_TOUCH_UI) || !defined(CONFIG_SYNTHDEF_OFFLINE_CAPTURE)
    int loaded=fm_load(graph,touch_patch,sizeof touch_patch,error,sizeof error);
#else
    int loaded=fm_load(graph, embedded_patch, sizeof embedded_patch, error, sizeof error);
#endif
    if (!loaded) {
        ESP_LOGE(TAG, "Factory patch rejected: %s", error); return;
    }
    ESP_LOGI(TAG,"Active graph=%s nodes=%u controls=%u",graph->name,graph->nodes,graph->controls);
#ifdef CONFIG_SYNTHDEF_OFFLINE_CAPTURE
    offline_capture(graph, voice, scratch);
    return;
#endif
    if (!instrument_init(&synth, graph, voice, scratch, NULL, 0, SAMPLE_RATE)) {
        ESP_LOGE(TAG, "Factory patch admission failed"); return;
    }
    synth.clock_us = audio_clock_us;
    events = xQueueCreate(EVENT_CAPACITY, sizeof(inst_event));
    telemetry = xQueueCreate(1, sizeof(audio_stats));
    audio_commands=xQueueCreate(1,sizeof(audio_command));audio_ack=xQueueCreate(1,sizeof(int));
    if (!events || !telemetry || !audio_commands || !audio_ack) { ESP_LOGE(TAG, "Queue allocation failed"); return; }
    patch_hooks hooks={.pause=service_pause,.activate=service_activate,.display=service_display,.busy=service_busy,
        .build_id=BUILD_ID,.engine_commit=ENGINE_COMMIT,.profile_hash=CAPABILITY_HASH};
    if(!patches_init(graph,spare,touch_patch,sizeof touch_patch,&hooks)) {ESP_LOGE(TAG,"Patch service allocation failed");return;}
#ifdef CONFIG_SYNTHDEF_TOUCH_UI
    touch_ui_actions actions={.post=send_event,.new_note=new_note,.panic=request_panic,.patch_action=patches_request};
    esp_err_t ui_error=touch_ui_start(&actions);
    if (ui_error!=ESP_OK) ESP_LOGE(TAG,"Touchscreen startup failed: %s; USB controls available",esp_err_to_name(ui_error));
    else ESP_LOGI(TAG,"V2 touchscreen ready: Pitch, Level, Attack, Release");
#endif
    patches_publish();
    service_busy(true,"TAP PANIC FOR FACTORY");
    vTaskDelay(pdMS_TO_TICKS(2000));
    patches_restore(atomic_exchange(&panic_requested,false));
    service_busy(false,"READY");
#ifdef CONFIG_SYNTHDEF_DIAGNOSTICS
    if(!diagnostic_init()) {ESP_LOGE(TAG,"Diagnostic PSRAM allocation failed");return;}
#endif
    /* Create the display before enabling codec DMA. Startup redraws must not
     * leave an already-running I2S channel without its producer. */
    ESP_ERROR_CHECK(board_audio_init(SAMPLE_RATE));
    ESP_LOGI(TAG, "Boots silent. Console: n note-on; o release; ! panic; +/- pitch; [/] amplitude");
    atomic_store(&audio_started,true);
    configASSERT(xTaskCreatePinnedToCore(audio_task, "audio", AUDIO_STACK_BYTES, NULL, 20, NULL, 1) == pdPASS);
    configASSERT(xTaskCreatePinnedToCore(console_task, "controls", 16384, NULL, 3, NULL, 0) == pdPASS);
    for (;;) {
        audio_stats s;
        if (xQueueReceive(telemetry, &s, pdMS_TO_TICKS(2000)) != pdTRUE) {
            ESP_LOGE(TAG, "Audio telemetry stopped; reset required if output failed");
            continue;
        }
        ESP_LOGI(TAG, "frame=%" PRIu64 " active=%" PRIu32 " render_max_us=%" PRIu32 " prep_max_us=%" PRIu32
                 " combined_max_us=%" PRIu32 " budget70_exceeded=%" PRIu64, s.frame, s.active,
                 s.render_max_us, s.prep_max_us, s.combined_max_us, s.budget_exceeded);
        ESP_LOGI(TAG, "write_fail=%" PRIu64 " partial=%" PRIu64 " dma_event_overflow=%" PRIu32
                 " write_max_us=%" PRIu32 " faults=%" PRIu64 " clips=%" PRIu64 " nonfinite=%" PRIu64
                 " pcm_peak=%" PRIu32 " pcm_peak_max=%" PRIu32,
                 s.write_failures, s.partial_writes, board_audio_dma_errors(), s.write_max_us, s.faults, s.clips, s.nonfinite,
                 s.pcm_peak, s.pcm_peak_max);
        ESP_LOGI(TAG, "queue_high=%" PRIu32 " overflow=%u coalesced=%u rejected=%" PRIu64 " stack_free_bytes=%" PRIu32
                 " internal_free=%u internal_min=%u internal_largest=%u psram_free=%u", s.queue_high,
                 atomic_load_explicit(&overflow_count, memory_order_relaxed),
                 atomic_load_explicit(&controls_coalesced,memory_order_relaxed),s.rejected, s.audio_stack_free_bytes,
                 (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
                 (unsigned)heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
                 (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
                 (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
        ESP_LOGI(TAG,"worst reset=%lu controls=%lu prepare=%lu dsp=%lu pcm=%lu knobs=%.4f,%.4f,%.4f,%.4f",
                 (unsigned long)s.worst_reset,(unsigned long)s.worst_controls,(unsigned long)s.worst_prepare,
                 (unsigned long)s.worst_dsp,(unsigned long)s.worst_pcm,
                 s.worst_knobs[0],s.worst_knobs[1],s.worst_knobs[2],s.worst_knobs[3]);
#ifdef CONFIG_SYNTHDEF_DIAGNOSTICS
        ESP_LOGI(TAG,"PROFILE epoch=%lu render_max_us=%lu prep_max_us=%lu combined_max_us=%lu budget70_exceeded=%lu reset=%lu controls=%lu prepare=%lu dsp=%lu pcm=%lu knobs=%.4f,%.4f,%.4f,%.4f",
                 (unsigned long)s.epoch,(unsigned long)s.profile_render,(unsigned long)s.profile_prep,
                 (unsigned long)s.profile_combined,(unsigned long)s.profile_budget,
                 (unsigned long)s.profile_worst[0],(unsigned long)s.profile_worst[1],(unsigned long)s.profile_worst[2],
                 (unsigned long)s.profile_worst[3],(unsigned long)s.profile_worst[4],
                 s.profile_knobs[0],s.profile_knobs[1],s.profile_knobs[2],s.profile_knobs[3]);
#endif
#ifdef CONFIG_SYNTHDEF_TOUCH_UI
        touch_ui_status(s.active,s.write_failures || s.partial_writes || s.current_fault,s.base_frequency);
        if (!s.active && atomic_exchange_explicit(&snapshot_requested,false,memory_order_relaxed)) {
            size_t bytes=0; unsigned char *pixels=touch_ui_snapshot(&bytes);
            if (pixels) {
                printf("SCREEN_BEGIN width=368 height=448 bytes=%u big_endian=1\n",(unsigned)bytes);
                static const char hex[]="0123456789abcdef";
                for (size_t offset=0;offset<bytes;offset+=512) {
                    char line[1025]; size_t n=bytes-offset>512?512:bytes-offset;
                    for (size_t j=0;j<n;++j) {line[2*j]=hex[pixels[offset+j]>>4];line[2*j+1]=hex[pixels[offset+j]&15];}
                    line[2*n]=0; printf("SCREEN_DATA %u %s\n",(unsigned)offset,line);
                    if (offset%2048==0) vTaskDelay(1);
                }
                puts("SCREEN_END"); heap_caps_free(pixels);
            } else ESP_LOGE(TAG,"Screen capture failed");
        }
#endif
    }
}
