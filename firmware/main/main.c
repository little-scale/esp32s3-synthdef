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
#include "esp_random.h"
#include "board_audio.h"
#ifdef CONFIG_SYNTHDEF_HEADLESS
#include "headless_io.h"
#endif
#include "instrument.h"
#include "remote_control.h"
#include "master_delay.h"
#include "output_volume.h"
#include "nvs.h"
#ifdef CONFIG_SYNTHDEF_TOUCH_UI
#include "touch_ui.h"
#include "touch_display.h"
#endif
#include "patch_service.h"
#include "device_network.h"
#include "generated.h"
#include "diagnostics.h"

#define SAMPLE_RATE 44100u
#define EVENT_CAPACITY 16
#define AUDIO_STACK_BYTES 16384
#define CONTROL_STACK_BYTES 8192
static const char *TAG = "synthdef";
static float *synth_arena;
static uint32_t synth_arena_samples;
static float *synth_fast_arena;
#ifdef CONFIG_SYNTHDEF_INTERNAL_VOICE_ARENA_SAMPLES
static const uint32_t synth_fast_samples=CONFIG_SYNTHDEF_INTERNAL_VOICE_ARENA_SAMPLES;
#else
static const uint32_t synth_fast_samples=0;
#endif
static instrument synth;
static remote_control *remote;
/* Console serializes this mailbox; it is never reused after a timed-out RPC. */
static struct {rc_event event;unsigned info,stage,page;int result;rc_status status;} *remote_mail;
static bool remote_failed;
static StaticTask_t audio_task_state,console_task_state;
static master_delay delay_bus;
static atomic_uint effect_words[3],effect_dirty;
static atomic_bool effect_clear_needed,effect_save_requested;
static bool effect_maintenance_fault;
static atomic_uint volume_percent=OUTPUT_VOLUME_DEFAULT_PERCENT;
static atomic_bool volume_save_requested;
static unsigned saved_volume=OUTPUT_VOLUME_DEFAULT_PERCENT;
static atomic_uint observed_seed;
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
enum { AUDIO_PARK=1,AUDIO_ACTIVATE,AUDIO_RESUME,AUDIO_BENCH,AUDIO_DELAY_TEST,AUDIO_TRACE,AUDIO_BUS_TEST,AUDIO_STOP,AUDIO_MASTER_ACTIVATE,AUDIO_PARK_KEEP_FX,AUDIO_UGEN_PROFILE,AUDIO_REMOTE,AUDIO_DEFINE,AUDIO_DEFINE_PLAY,AUDIO_MASTER_DEFINE,AUDIO_MASTER_DEFINE_PLAY,AUDIO_INSTANCE };
#ifdef CONFIG_SYNTHDEF_TOUCH_UI
static atomic_bool snapshot_requested;
#endif

static uint64_t audio_clock_us(void) { return (uint64_t)esp_timer_get_time(); }

/* Called only at startup or while the audio owner is parked. Reserve arenas
 * once; note starts still clear only the required slice incrementally. */
static int initialize_synth_mode(fm_graph *graph,fm_voice *voice,fm_scratch *scratch,bool managed,bool start)
{
    uint32_t needed=fm_delay_required(graph,SAMPLE_RATE);
    bool internal=synth_fast_arena && needed && needed<=synth_fast_samples;
    float *arena=internal?synth_fast_arena:synth_arena;
    uint32_t capacity=internal?synth_fast_samples:synth_arena_samples;
    int ok=instrument_init_definition(&synth,graph,voice,scratch,arena,capacity,SAMPLE_RATE,managed);
    synth.clock_us=audio_clock_us;
    synth.defer_note_render=1;
    if(ok){
        static uint32_t previous;
        uint32_t seed=esp_random();if(seed==previous)seed+=0x9e3779b9u;previous=seed;
        instrument_randomize(&synth,seed);
    }
    if(ok && managed)instrument_preclear(&synth);
    if(ok && (!managed || start))ok=instrument_arm_bus(&synth);
    if(ok && remote)rc_bind(remote,0,graph,voice);
    atomic_store(&observed_seed,synth.seed_active);
    if(ok)ESP_LOGI(TAG,"Voice arena required=%u capacity=%u storage=%s",(unsigned)needed,(unsigned)capacity,internal?"internal":"PSRAM");
    return ok;
}
static int initialize_synth(fm_graph *g,fm_voice *v,fm_scratch *b)
{return initialize_synth_mode(g,v,b,false,true);}
static int initialize_master_mode(fm_graph *graph,bool define)
{
    fm_voice *voice=delay_bus.voice;float *arena=delay_bus.arena;
    int ok=define?master_effect_define(&delay_bus,graph,voice,arena,MASTER_DELAY_SAMPLES,SAMPLE_RATE,synth.scratch):
        master_effect_init(&delay_bus,graph,voice,arena,MASTER_DELAY_SAMPLES,SAMPLE_RATE,synth.scratch);
    if(ok){for(unsigned k=0;k<3;++k){uint32_t bits;memcpy(&bits,&delay_bus.value[k],sizeof bits);atomic_store(&effect_words[k],bits);}atomic_store(&effect_dirty,0);}
    if(ok && remote)rc_bind(remote,1,graph,voice);
    return ok;
}
static int initialize_master(fm_graph *g){return initialize_master_mode(g,false);}

static void process_remote(void)
{
    uint64_t now=audio_clock_us();
    remote_mail->result=remote_mail->info?
        rc_snapshot(remote,remote_mail->stage,now,&remote_mail->status):
        rc_enqueue(remote,&remote_mail->event,now);
}

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
    uint64_t cpu_busy_us;
    uint32_t cpu_blocks,cpu_peak_us;
    uint32_t audio_stack_free_bytes, active;
    uint32_t pcm_peak, pcm_peak_max,current_fault;
    float base_frequency;
    uint32_t worst_reset,worst_controls,worst_prepare,worst_dsp,worst_pcm;
    float worst_knobs[4];
    float effect_value[3];
    uint32_t effect_max_us,effect_resets,effect_reset_max_us,effect_tail_blocks;
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
static void *large_state_alloc(size_t size)
{
#ifdef CONFIG_SYNTHDEF_FM1_COMPAT
    return heap_caps_calloc(1,size,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
#else
    return internal_alloc(size);
#endif
}

static void audio_task(void *unused)
{
    (void)unused;
    audio_stats stats = {0};
    ESP_ERROR_CHECK(board_audio_start_dma());
    /* One internal PCM buffer reused only after the blocking driver copies it. */
    int16_t mono[FM_BLOCK*BOARD_AUDIO_CHANNELS];
    uint64_t next_snapshot = SAMPLE_RATE;
    unsigned parking=0;
    bool parked=false,keep_fx=false;
    output_volume volume;output_volume_init(&volume,atomic_load(&volume_percent),SAMPLE_RATE);
    uint64_t faults_base=0,clips_base=0,nonfinite_base=0,rejected_base=0;
    uint64_t window_busy_us=0;
    uint32_t window_blocks=0,window_peak_us=0;
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
                ok=initialize_synth(command.graph,synth.voice,synth.scratch);
            }
#ifdef CONFIG_SYNTHDEF_DIAGNOSTICS
            else if(command.kind==AUDIO_BENCH)diagnostic_benchmark(&synth);
            else if(command.kind==AUDIO_DELAY_TEST)diagnostic_delay(&delay_bus,synth.scratch);
            else if(command.kind==AUDIO_TRACE)diagnostic_trace(&synth);
            else if(command.kind==AUDIO_BUS_TEST)diagnostic_control_buses(&synth);
            else if(command.kind==AUDIO_UGEN_PROFILE)ok=diagnostic_ugen_profile(&synth);
#endif
            else if(command.kind==AUDIO_MASTER_ACTIVATE) {faults_base+=delay_bus.faults;ok=initialize_master(command.graph);}
            else if(command.kind==AUDIO_DEFINE || command.kind==AUDIO_DEFINE_PLAY)
                ok=initialize_synth_mode(command.graph,synth.voice,synth.scratch,true,command.kind==AUDIO_DEFINE_PLAY);
            else if(command.kind==AUDIO_MASTER_DEFINE || command.kind==AUDIO_MASTER_DEFINE_PLAY)
                ok=initialize_master_mode(command.graph,command.kind==AUDIO_MASTER_DEFINE);
            else if(command.kind==AUDIO_INSTANCE){remote_mail->result=rc_instance(remote,&synth,&delay_bus,remote_mail->event.kind==3,&remote_mail->event);ok=1;}
            else if(command.kind==AUDIO_STOP) {instrument_panic(&synth);rc_clear(remote);ok=1;}
            else if(command.kind==AUDIO_RESUME) {
                if(atomic_load_explicit(&panic_requested,memory_order_relaxed))instrument_panic(&synth);
                ok=instrument_resume(&synth) && board_audio_start_dma()==ESP_OK;if(ok)parked=false;
            }
            else ok=0;
            xQueueOverwrite(audio_ack,&ok);
            continue;
        }
        if(xQueueReceive(audio_commands,&command,0)==pdTRUE) {
            if(command.kind==AUDIO_PARK || command.kind==AUDIO_PARK_KEEP_FX) {keep_fx=command.kind==AUDIO_PARK_KEEP_FX;parking=14;xQueueReset(events);atomic_store(&control_dirty,0);}
            else if(command.kind==AUDIO_REMOTE){process_remote();int ok=1;xQueueOverwrite(audio_ack,&ok);}
            else {int ok=0;xQueueOverwrite(audio_ack,&ok);}
        }
        int64_t begin = esp_timer_get_time();
        synth.reset_us=synth.controls_us=synth.prepare_us=0;
        unsigned effect_changes=atomic_exchange_explicit(&effect_dirty,0,memory_order_acquire);
        for(unsigned k=0;k<3;++k)if(effect_changes&(1u<<k)) {
            uint32_t bits=atomic_load_explicit(&effect_words[k],memory_order_relaxed);float value;memcpy(&value,&bits,sizeof value);
            configASSERT(master_delay_set(&delay_bus,k,value));
        }
        unsigned queued = uxQueueMessagesWaiting(events);
        if (queued > stats.queue_high) stats.queue_high = queued;
        if(parking) { /* Fade two blocks, then drain a DMA queue of silence. */
            if(parking==12) {instrument_suspend(&synth);if(!keep_fx)master_delay_panic(&delay_bus);}
        } else if (atomic_exchange_explicit(&panic_requested, false, memory_order_relaxed)) {
            xQueueReset(events);
            instrument_panic(&synth);rc_clear(remote);
            master_delay_panic(&delay_bus);atomic_store(&effect_clear_needed,true);
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
#ifdef CONFIG_SYNTHDEF_HEADLESS
        float physical[3];headless_io_values(physical);
        for(unsigned i=0;i<3;++i)synth.buses[8+i]=physical[i];
#endif
        if(!parking)rc_tick(remote,&synth,audio_clock_us());
        int64_t render_begin = esp_timer_get_time();
        float dry[FM_BLOCK*2],effected[FM_BLOCK*2];
        instrument_render_stereo(&synth,dry);
        uint64_t effect_begin=audio_clock_us();
        master_delay_render(&delay_bus,synth.scratch,dry,effected);
        uint32_t effect_us=(uint32_t)(audio_clock_us()-effect_begin);
        if(effect_us>stats.effect_max_us)stats.effect_max_us=effect_us;
        uint64_t pcm_begin=audio_clock_us();
        atomic_store_explicit(&observed_seed,synth.seed_active,memory_order_relaxed);
#ifdef CONFIG_SYNTHDEF_HEADLESS
        output_volume_pcm_stereo(&volume,atomic_load_explicit(&volume_percent,memory_order_relaxed),effected,mono,synth.master_gain,&synth.nonfinite,&synth.clipped);
#else
        output_volume_pcm(&volume,atomic_load_explicit(&volume_percent,memory_order_relaxed),effected,mono,synth.master_gain,&synth.nonfinite,&synth.clipped);
#endif
        synth.pcm_us=(uint32_t)(audio_clock_us()-pcm_begin);
        if(parking>=13) {
            unsigned block=14-parking;
            for(unsigned i=0;i<FM_BLOCK*BOARD_AUDIO_CHANNELS;++i)mono[i]=(int16_t)((int32_t)mono[i]*(int32_t)(127-block*64-i/BOARD_AUDIO_CHANNELS)/128);
        }
        stats.pcm_peak = 0;
        for (unsigned i = 0; i < FM_BLOCK*BOARD_AUDIO_CHANNELS; ++i) {
            uint32_t magnitude = mono[i] < 0 ? -(int32_t)mono[i] : mono[i];
            if (magnitude > stats.pcm_peak) stats.pcm_peak = magnitude;
        }
        if (stats.pcm_peak > stats.pcm_peak_max) stats.pcm_peak_max = stats.pcm_peak;
        if(!synth.voice->active && stats.pcm_peak>4)++stats.effect_tail_blocks;
        uint32_t render_us = (uint32_t)(esp_timer_get_time() - render_begin);
        uint32_t combined_us = (uint32_t)(esp_timer_get_time() - begin);
        window_busy_us+=combined_us;++window_blocks;
        if(combined_us>window_peak_us)window_peak_us=combined_us;
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
            master_delay_panic(&delay_bus);
            board_audio_mute();
            xQueueOverwrite(telemetry, &stats);
            /* Stop after a failed transfer; a reset restores a known pipeline. */
            vTaskDelete(NULL);
        }
        if(parking && !--parking) {
            /* Already suspended at parking==12. A second Panic here would
             * discard the continuous program's saved resume state. */
            parked=true;
            int ok=board_audio_stop_dma()==ESP_OK;
            /* Large PSRAM clears run only after DMA stops, before the ACK. */
            uint64_t reset_begin=audio_clock_us();
            if(ok && !keep_fx)ok=master_delay_reset(&delay_bus,synth.scratch);
            uint32_t reset_us=(uint32_t)(audio_clock_us()-reset_begin);
            if(reset_us>stats.effect_reset_max_us)stats.effect_reset_max_us=reset_us;
            if(!keep_fx){++stats.effect_resets;atomic_store(&effect_clear_needed,false);}
            xQueueOverwrite(audio_ack,&ok);
        }
        stats.frame += FM_BLOCK;
        if (stats.frame >= next_snapshot) {
            stats.faults = faults_base+synth.faults+delay_bus.faults;
            stats.clips = clips_base+synth.clipped; stats.nonfinite = nonfinite_base+synth.nonfinite;
            stats.rejected = rejected_base+synth.rejected; stats.active = synth.voice->active;
            stats.current_fault=synth.voice->fault || delay_bus.voice->fault;
            memcpy(stats.effect_value,delay_bus.value,sizeof stats.effect_value);
            stats.base_frequency = synth.frequency;
            stats.audio_stack_free_bytes = uxTaskGetStackHighWaterMark(NULL);
            stats.cpu_busy_us=window_busy_us;stats.cpu_blocks=window_blocks;stats.cpu_peak_us=window_peak_us;
            xQueueOverwrite(telemetry, &stats);
            window_busy_us=0;window_blocks=window_peak_us=0;
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

static void effect_values(float value[3])
{
    for(unsigned k=0;k<3;++k) {uint32_t bits=atomic_load_explicit(&effect_words[k],memory_order_relaxed);memcpy(&value[k],&bits,sizeof bits);}
}
static bool effect_post(unsigned k,float value)
{
    static const float low[]={.02f,0,0},high[]={MASTER_DELAY_SECONDS,.8f,1};
    if(k>=3 || !isfinite(value) || value<low[k] || value>high[k] || atomic_load(&reject_events))return false;
    uint32_t bits;memcpy(&bits,&value,sizeof bits);atomic_store_explicit(&effect_words[k],bits,memory_order_relaxed);
    atomic_fetch_or_explicit(&effect_dirty,1u<<k,memory_order_release);return true;
}
static bool effect_save_request(void)
{
    if(atomic_load(&reject_events))return false;
    atomic_store(&effect_save_requested,true);return true;
}
static int effect_protocol(const float *input,float output[3])
{
    if(input) {
        if(!isfinite(input[0]) || input[0]<.02f || input[0]>5 || !isfinite(input[1]) || input[1]<0 || input[1]>.8f || !isfinite(input[2]) || input[2]<0 || input[2]>1 || atomic_load(&reject_events))return 0;
        for(unsigned k=0;k<3;++k)if(!effect_post(k,input[k]))return 0;
    }
    effect_values(output);
#ifdef CONFIG_SYNTHDEF_TOUCH_UI
    if(input)touch_ui_effect(output);
#endif
    return 1;
}

static bool send_event(inst_event_type type, uint32_t note, float value)
{
    if(atomic_load_explicit(&reject_events,memory_order_relaxed))return false;
    if (type>=INST_FREQ && type<=INST_TOUCH_Y) {
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
    return xQueueReceive(audio_ack,&ok,pdMS_TO_TICKS(kind==AUDIO_TRACE?60000:(kind==AUDIO_BENCH || kind==AUDIO_DELAY_TEST || kind==AUDIO_UGEN_PROFILE?15000:1000)))==pdTRUE && ok;
}
static int remote_protocol(const char *op,const unsigned char *payload,size_t bytes,char *reply,size_t size)
{
    if(remote_failed)return -1;
    if(!remote || !remote_mail || atomic_load(&reject_events))return 0;
    remote_mail->info=!strcmp(op,"RCINFO");
    if(remote_mail->info){if(bytes!=2 || payload[0]>1 || payload[1]>8)return 0;remote_mail->stage=payload[0];remote_mail->page=payload[1];}
    else if(!rc_decode(&remote_mail->event,payload,bytes))return 0;
    /* Formatting is bounded. No allocation, flash access or network I/O occurs on the audio owner. */
    if(!audio_call(AUDIO_REMOTE,NULL)){remote_failed=true;return -1;}
    if(!remote_mail->result)return 0;
    if(!remote_mail->info && remote_mail->result==RC_NEED_FULL){snprintf(reply,size,"{\"queued\":false,\"need_full\":true}");return 1;}
    if(remote_mail->info)return rc_info(&remote_mail->status,remote_mail->page,reply,size);
    snprintf(reply,size,"{\"queued\":true}");return 1;
}

static int service_pause_mode(bool pause,bool preserve_fx)
{
    if(!atomic_load(&audio_started)) {atomic_store(&reject_events,pause);return 1;}
    if(pause) {
        atomic_store(&reject_events,true);
        if(!audio_call(preserve_fx?AUDIO_PARK_KEEP_FX:AUDIO_PARK,NULL)) {board_audio_mute();return 0;}
        return board_audio_pause()==ESP_OK;
    }
    if(!audio_call(AUDIO_RESUME,NULL) || board_audio_resume()!=ESP_OK) {board_audio_mute();return 0;}
    atomic_store(&reject_events,false);return 1;
}
static int service_pause(bool pause){return service_pause_mode(pause,false);}
static int service_activate(fm_graph *graph)
{
    if(atomic_load(&audio_started))return audio_call(AUDIO_ACTIVATE,graph);
    return initialize_synth(graph,synth.voice,synth.scratch);
}
static int service_define(fm_graph *graph,bool start)
{
    if(atomic_load(&audio_started))return audio_call(start?AUDIO_DEFINE_PLAY:AUDIO_DEFINE,graph);
    return initialize_synth_mode(graph,synth.voice,synth.scratch,true,start);
}
static int service_master_define(fm_graph *graph,bool start)
{
    if(atomic_load(&audio_started))return audio_call(start?AUDIO_MASTER_DEFINE_PLAY:AUDIO_MASTER_DEFINE,graph);
    return initialize_master_mode(graph,!start);
}
static int service_instance(bool start,const unsigned char *payload,size_t bytes)
{
    if(remote_failed || !remote_mail || bytes<10 || payload[8]>1 || payload[9]>RC_PAIRS || bytes!=10u+5u*payload[9] || (!start && payload[9]))return 0;
    rc_event *e=&remote_mail->event;memset(e,0,sizeof *e);
    e->boot=patch_get32(payload);e->revision=patch_get32(payload+4);e->stage=payload[8];e->count=payload[9];e->kind=start?3:4;
    for(unsigned i=0;i<e->count;++i){e->index[i]=payload[10+5*i];uint32_t bits=patch_get32(payload+11+5*i);memcpy(&e->value[i],&bits,4);}
    if(!service_pause_mode(true,true))return -1;
    if(!audio_call(AUDIO_INSTANCE,NULL)){remote_failed=true;return -1;}
    int ok=remote_mail->result;
    if(!service_pause_mode(false,true))return -1;
    return ok;
}
static int service_stop(void)
{
    if(atomic_load(&audio_started))return audio_call(AUDIO_STOP,NULL);
    instrument_panic(&synth);return 1;
}
static int service_master_activate(fm_graph *graph)
{
    if(atomic_load(&audio_started))return audio_call(AUDIO_MASTER_ACTIVATE,graph);
    return initialize_master(graph);
}
static void service_master_display(const char *name,int slot)
{
#ifdef CONFIG_SYNTHDEF_TOUCH_UI
    touch_ui_master(name,slot);
#else
    (void)name;(void)slot;
#endif
}
static void service_display(const patch_meta *meta,const fm_graph *graph,const char names[PATCH_SLOTS+1][32],int slot,const char *source,size_t source_bytes)
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
    if(slot==0 && !source_bytes){source=(const char *)touch_patch_source;source_bytes=sizeof touch_patch_source;}
    touch_ui_patch(meta->name,meta->label,meta->mapping,knobs,controller_frequency,names,slot,source,source_bytes);
    /* Persistent SynthDef instances still wait for touch/SC notes. */
    touch_ui_playback(synth.continuous && !synth.managed_definition);
#else
    (void)meta;(void)names;(void)slot;(void)source;(void)source_bytes;
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

static int effect_save_now(void)
{
    service_busy(true,"SAVING DELAY");
    if(!service_pause(true)) {effect_maintenance_fault=true;service_busy(true,"RESET REQUIRED");return 0;}
    unsigned char record[16]={'D','L','Y','1'};float value[3];effect_values(value);memcpy(record+4,value,sizeof value);
    nvs_handle_t handle;int ok=nvs_open("wsynthfx",NVS_READWRITE,&handle)==ESP_OK;
    if(ok) {ok=nvs_set_blob(handle,"delay",record,sizeof record)==ESP_OK && nvs_commit(handle)==ESP_OK;nvs_close(handle);}
    if(!service_pause(false)) {effect_maintenance_fault=true;service_busy(true,"RESET REQUIRED");return 0;}
    service_busy(false,ok?"DELAY SAVED":"SAVE FAILED");return ok;
}

static bool volume_post(unsigned percent,bool save)
{
    if(percent>100 || atomic_load(&reject_events))return false;
    atomic_store_explicit(&volume_percent,percent,memory_order_relaxed);
    if(save)atomic_store(&volume_save_requested,true);
    return true;
}
static int volume_save_now(void)
{
    unsigned value=atomic_load(&volume_percent);if(value==saved_volume)return 1;
    service_busy(true,"SAVING VOLUME");
    if(!service_pause_mode(true,true)){effect_maintenance_fault=true;service_busy(true,"RESET REQUIRED");return 0;}
    nvs_handle_t handle;int ok=nvs_open("wsynthfx",NVS_READWRITE,&handle)==ESP_OK;
    if(ok){ok=nvs_set_u8(handle,"volume",(uint8_t)value)==ESP_OK && nvs_commit(handle)==ESP_OK;nvs_close(handle);}
    if(ok)saved_volume=value;
    if(!service_pause(false)){effect_maintenance_fault=true;service_busy(true,"RESET REQUIRED");return 0;}
    service_busy(false,ok?"VOLUME SAVED":"SAVE FAILED");return ok;
}
static uint32_t service_seed(void){return atomic_load_explicit(&observed_seed,memory_order_relaxed);}
static int volume_protocol(int percent,bool save)
{
    if(percent>=0 && !volume_post((unsigned)percent,false))return -1;
    if(save && !volume_save_now())return -1;
    unsigned value=atomic_load(&volume_percent);
#ifdef CONFIG_SYNTHDEF_TOUCH_UI
    if(percent>=0)touch_ui_volume(value);
#endif
    return (int)value;
}

static void console_task(void *unused)
{
    (void)unused;
    uint32_t note = 0;
    char frame[PATCH_FRAME_BYTES];size_t frame_size=0;bool framing=false,discard=false;
    for (;;) {
        patches_tick();
        device_network_tick();
#ifdef CONFIG_SYNTHDEF_HEADLESS
        headless_io_poll();
        device_network_status network;device_network_snapshot(&network);board_audio_activity(network.receiving);
#endif
#ifdef CONFIG_SYNTHDEF_TOUCH_UI
        static TickType_t battery_next;
        static TickType_t connectivity_next;
        TickType_t now=xTaskGetTickCount();
        if(!connectivity_next || (int32_t)(now-connectivity_next)>=0){
            device_network_status network;device_network_snapshot(&network);
            touch_ui_connectivity(network.name,network.id,network.online,network.rssi,network.receiving);
            connectivity_next=now+pdMS_TO_TICKS(40);
        }
        if(!battery_next || (int32_t)(now-battery_next)>=0){
            touch_ui_battery();battery_next=now+pdMS_TO_TICKS(5000);
        }
#endif
        if(!effect_maintenance_fault && atomic_load(&audio_started)) {
            if(atomic_exchange(&volume_save_requested,false))volume_save_now();
            else if(atomic_exchange(&effect_save_requested,false))effect_save_now();
            else if(atomic_load(&effect_clear_needed)) {
                service_busy(true,"CLEARING DELAY");
                if(!service_pause(true) || !service_pause(false)) {effect_maintenance_fault=true;service_busy(true,"RESET REQUIRED");}
                else service_busy(false,"READY");
            }
        }
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
        case 'j': {
            service_busy(true,"PROFILING UGens");
            if(service_pause(true) && audio_call(AUDIO_UGEN_PROFILE,NULL) && service_pause(false)){
                service_busy(false,"READY");diagnostic_ugen_report();
            }else {board_audio_mute();service_busy(true,"RESET REQUIRED");}
            break;
        }
        case 'u': {
            service_busy(true,"CHECKING BUSES");
            if(service_pause(true) && audio_call(AUDIO_BUS_TEST,NULL) && service_pause(false)){
                service_busy(false,"READY");diagnostic_control_buses_report();
            }else {board_audio_mute();service_busy(true,"RESET REQUIRED");}
            break;
        }
        case 'g': {
            service_busy(true,"LONG DSP CHECK");
            if(service_pause(true) && audio_call(AUDIO_TRACE,NULL) && service_pause(false)) {
                service_busy(false,"READY");diagnostic_trace_report();
            } else {board_audio_mute();service_busy(true,"RESET REQUIRED");}
            break;
        }
        case 'e': {
            service_busy(true,"MEASURING DELAY");
            if(service_pause(true) && audio_call(AUDIO_DELAY_TEST,NULL) && service_pause(false)) {
                service_busy(false,"READY");diagnostic_delay_report();
            } else {board_audio_mute();service_busy(true,"RESET REQUIRED");}
            break;
        }
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
        case 'c': touch_ui_code(true);break;
        case 'v': touch_ui_code(false);break;
#ifdef CONFIG_SYNTHDEF_DIAGNOSTICS
        case '>': touch_ui_step_patch(true);break;
        case '<': touch_ui_step_patch(false);break;
        case 'q': {
            touch_ui_code(false);service_busy(true,"TOUCH CHECK - MUTED");
            if(service_pause(true)){
                esp_err_t trace=touch_display_trace(60000);
                touch_ui_code(true);
                if(service_pause(false) && trace==ESP_OK)service_busy(false,"READY");
                else {board_audio_mute();service_busy(true,"RESET REQUIRED");}
            }else {board_audio_mute();service_busy(true,"RESET REQUIRED");}
            break;
        }
#endif
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
    ESP_LOGI(TAG, "Target=%s IDF=%s compiler=%s", BOARD_MODEL, esp_get_idf_version(), __VERSION__);
    ESP_LOGI(TAG, "build=%s engine=%s profile=%s", BUILD_ID, ENGINE_COMMIT, CAPABILITY_HASH);
    ESP_LOGI(TAG, "app=%s version=%s ELF=%02x%02x%02x%02x flash=%" PRIu32 " PSRAM=%u", app->project_name,
             app->version, app->app_elf_sha256[0], app->app_elf_sha256[1], app->app_elf_sha256[2], app->app_elf_sha256[3],
             flash_bytes, (unsigned)esp_psram_get_size());
    ESP_LOGI(TAG, "requested_rate=%u block=%d channels=%d S16 Philips DMA=6x128", SAMPLE_RATE, FM_BLOCK, BOARD_AUDIO_CHANNELS);
    ESP_LOGW(TAG, "Actual clocks, channel packing, continuity and latency require hardware measurement");
    ESP_LOGI(TAG, "graph=%u voice=%u scratch=%u baseline_patch=%s touch_patch=%s", (unsigned)sizeof(fm_graph),
             (unsigned)sizeof(fm_voice), (unsigned)sizeof(fm_scratch), PATCH_SHA256, TOUCH_PATCH_SHA256);
    /* Largest allocations first: the IDF internal reserve is only 64 KiB,
     * so the 66 KiB arena must use the other large block before it fragments. */
    if(synth_fast_samples) {
        synth_fast_arena=heap_caps_malloc(synth_fast_samples*sizeof(float),MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
        if(!synth_fast_arena)ESP_LOGW(TAG,"Internal voice arena unavailable; using PSRAM fallback");
    }
    fm_graph *graph = large_state_alloc(sizeof *graph);
    fm_voice *voice = internal_alloc(sizeof *voice);
    fm_scratch *scratch = large_state_alloc(sizeof *scratch);
    fm_graph *spare = large_state_alloc(sizeof *spare);
    fm_graph *effect_graph=large_state_alloc(sizeof *effect_graph);
    fm_graph *effect_spare=large_state_alloc(sizeof *effect_spare);
    /* Master state is cold for Bypass; PSRAM preserves internal RAM for Wi-Fi
     * while the instrument voice and audio stack keep their existing placement. */
    fm_voice *effect_voice=large_state_alloc(sizeof *effect_voice);
    if((!voice || !effect_voice) && synth_fast_arena) {
        heap_caps_free(synth_fast_arena);synth_fast_arena=NULL;
        if(!voice)voice=internal_alloc(sizeof *voice);
        if(!effect_voice)effect_voice=large_state_alloc(sizeof *effect_voice);
        ESP_LOGW(TAG,"Internal voice arena released for mandatory voice states; using PSRAM");
    }
    /* Reserve stacks after the larger voice states, before display/DMA/NVS
     * setup. Deferring these allocations until task creation fragments RAM. */
    StackType_t *audio_stack=internal_alloc(AUDIO_STACK_BYTES);
    StackType_t *console_stack=internal_alloc(CONTROL_STACK_BYTES);
    if((!audio_stack || !console_stack) && synth_fast_arena) {
        heap_caps_free(synth_fast_arena);synth_fast_arena=NULL;
        if(!audio_stack)audio_stack=internal_alloc(AUDIO_STACK_BYTES);
        if(!console_stack)console_stack=internal_alloc(CONTROL_STACK_BYTES);
        ESP_LOGW(TAG,"Internal voice arena released for mandatory task stacks; using PSRAM");
    }
    if(!audio_stack || !console_stack) {ESP_LOGE(TAG,"Audio/control stack allocation failed");return;}
    float *effect_arena=heap_caps_malloc(MASTER_DELAY_SAMPLES*sizeof(float),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
#ifdef CONFIG_SYNTHDEF_FM1_COMPAT
    synth_arena_samples=FM_DELAY_LIMIT;
    synth_arena=heap_caps_malloc(synth_arena_samples*sizeof(float),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!synth_arena)return;
    ESP_LOGW(TAG,"FM1 compatibility: graph/scratch in PSRAM, synth arena=%u bytes, fast arena=%u bytes; real-time graphs require qualification",(unsigned)(synth_arena_samples*sizeof(float)),(unsigned)(synth_fast_arena?synth_fast_samples*sizeof(float):0));
#endif
    if (!graph || !voice || !scratch || !spare || !effect_graph || !effect_spare || !effect_voice || !effect_arena) {
        ESP_LOGE(TAG,"Core state allocation failed; internal_free=%u largest=%u",(unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT),(unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT));return;
    }
    remote=large_state_alloc(sizeof *remote);remote_mail=large_state_alloc(sizeof *remote_mail);
    if(!remote || !remote_mail)return;
    rc_init(remote,esp_random());
    char error[192]={0};
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
    if (!initialize_synth(graph,voice,scratch)) {
        ESP_LOGE(TAG, "Factory patch admission failed"); return;
    }
    if(!fm_load(effect_graph,master_bypass_patch,sizeof master_bypass_patch,error,sizeof error) ||
       !master_effect_init(&delay_bus,effect_graph,effect_voice,effect_arena,MASTER_DELAY_SAMPLES,SAMPLE_RATE,scratch)) {
        ESP_LOGE(TAG,"Master delay admission/start failed: %s",error);return;
    }
    ESP_LOGI(TAG,"Master output graph=%s nodes=%u arena_bytes=%u storage=PSRAM default=Bypass",effect_graph->name,effect_graph->nodes,(unsigned)(MASTER_DELAY_SAMPLES*sizeof(float)));
    rc_bind(remote,1,effect_graph,effect_voice);
    for(unsigned k=0;k<3;++k) {uint32_t bits;memcpy(&bits,&delay_bus.value[k],sizeof bits);atomic_store(&effect_words[k],bits);}
    events = xQueueCreate(EVENT_CAPACITY, sizeof(inst_event));
    telemetry = xQueueCreate(1, sizeof(audio_stats));
    audio_commands=xQueueCreate(1,sizeof(audio_command));audio_ack=xQueueCreate(1,sizeof(int));
    if (!events || !telemetry || !audio_commands || !audio_ack) { ESP_LOGE(TAG, "Queue allocation failed"); return; }
    patch_hooks hooks={.remote=remote_protocol,.pause=service_pause,.activate=service_activate,.define=service_define,.master_define=service_master_define,.instance=service_instance,.stop=service_stop,.display=service_display,.busy=service_busy,
        .master_activate=service_master_activate,.master_display=service_master_display,
        .effect=effect_protocol,.effect_save=effect_save_now,.volume=volume_protocol,.seed=service_seed,
        .build_id=BUILD_ID,.engine_commit=ENGINE_COMMIT,.profile_hash=CAPABILITY_HASH};
    if(!patches_init(graph,spare,touch_patch,sizeof touch_patch,&hooks)) {ESP_LOGE(TAG,"Patch service allocation failed");return;}
    if(!patches_master_init(effect_graph,effect_spare,master_bypass_patch,sizeof master_bypass_patch,(const char *)master_bypass_source,sizeof master_bypass_source)) {ESP_LOGE(TAG,"Master slot allocation failed");return;}
    nvs_handle_t effect_store;
    if(nvs_open("wsynthfx",NVS_READONLY,&effect_store)==ESP_OK) {
        unsigned char record[16];size_t bytes=sizeof record;
        if(nvs_get_blob(effect_store,"delay",record,&bytes)==ESP_OK && bytes==sizeof record && !memcmp(record,"DLY1",4)) {
            float value[3],out[3];memcpy(value,record+4,sizeof value);effect_protocol(value,out);
        }
        uint8_t volume_value;
        if(nvs_get_u8(effect_store,"volume",&volume_value)==ESP_OK && volume_value<=100){saved_volume=volume_value;atomic_store(&volume_percent,volume_value);}
        nvs_close(effect_store);
    }
    for(unsigned k=0;k<3;++k) {float value[3];effect_values(value);master_delay_set(&delay_bus,k,value[k]);}
#ifdef CONFIG_SYNTHDEF_TOUCH_UI
    touch_ui_actions actions={.post=send_event,.new_note=new_note,.panic=request_panic,.patch_action=patches_request,.master_action=patches_master_request,.volume=volume_post,.effect=effect_post,.effect_save=effect_save_request};
    esp_err_t ui_error=touch_ui_start(&actions);
    if (ui_error!=ESP_OK) ESP_LOGE(TAG,"Touchscreen startup failed: %s; USB controls available",esp_err_to_name(ui_error));
    else ESP_LOGI(TAG,"V2 touchscreen ready: Pitch, Level, Attack, Release");
    float effect_display[3];effect_values(effect_display);touch_ui_effect(effect_display);touch_ui_volume(atomic_load(&volume_percent));
#endif
    patches_publish();
    service_busy(true,"TAP PANIC FOR FACTORY");
    vTaskDelay(pdMS_TO_TICKS(2000));
    bool factory_only=atomic_exchange(&panic_requested,false);
    patches_restore(factory_only);patches_master_restore(factory_only);
    service_busy(false,"READY");
#ifdef CONFIG_SYNTHDEF_DIAGNOSTICS
    if(!diagnostic_init()) {ESP_LOGE(TAG,"Diagnostic PSRAM allocation failed");return;}
#endif
    /* Create the display before enabling codec DMA. Startup redraws must not
     * leave an already-running I2S channel without its producer. */
    if(!device_network_init(patches_exchange,service_pause))ESP_LOGE(TAG,"Network setup unavailable; USB retained");
    ESP_ERROR_CHECK(board_audio_init(SAMPLE_RATE));
#ifdef CONFIG_SYNTHDEF_HEADLESS
    ESP_ERROR_CHECK(headless_io_init());
#endif
    ESP_LOGI(TAG, "Boots silent. Console: n note-on; o release; ! panic; +/- pitch; [/] amplitude");
    atomic_store(&audio_started,true);
    TaskHandle_t audio_handle=xTaskCreateStaticPinnedToCore(audio_task,"audio",AUDIO_STACK_BYTES,NULL,20,audio_stack,&audio_task_state,1);
    configASSERT(audio_handle!=NULL);
    TaskHandle_t console_handle=xTaskCreateStaticPinnedToCore(console_task,"controls",CONTROL_STACK_BYTES,NULL,3,console_stack,&console_task_state,0);
    configASSERT(console_handle!=NULL);
    for (;;) {
        audio_stats s;
        if (xQueueReceive(telemetry, &s, pdMS_TO_TICKS(2000)) != pdTRUE) {
#ifdef CONFIG_SYNTHDEF_TOUCH_UI
            touch_ui_cpu(UINT32_MAX,UINT32_MAX);
#endif
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
                 " internal_free=%u internal_min=%u internal_largest=%u psram_free=%u controls_stack_free_bytes=%u", s.queue_high,
                 atomic_load_explicit(&overflow_count, memory_order_relaxed),
                 atomic_load_explicit(&controls_coalesced,memory_order_relaxed),s.rejected, s.audio_stack_free_bytes,
                 (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
                 (unsigned)heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
                 (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
                 (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM),
                 (unsigned)uxTaskGetStackHighWaterMark(console_handle));
        ESP_LOGI(TAG,"worst reset=%lu controls=%lu prepare=%lu dsp=%lu pcm=%lu knobs=%.4f,%.4f,%.4f,%.4f",
                 (unsigned long)s.worst_reset,(unsigned long)s.worst_controls,(unsigned long)s.worst_prepare,
                 (unsigned long)s.worst_dsp,(unsigned long)s.worst_pcm,
                 s.worst_knobs[0],s.worst_knobs[1],s.worst_knobs[2],s.worst_knobs[3]);
        ESP_LOGI(TAG,"DELAY time=%.3f feedback=%.3f wet=%.3f fx_max_us=%lu resets=%lu reset_max_us=%lu tail_blocks=%lu",
                 s.effect_value[0],s.effect_value[1],s.effect_value[2],(unsigned long)s.effect_max_us,
                 (unsigned long)s.effect_resets,(unsigned long)s.effect_reset_max_us,(unsigned long)s.effect_tail_blocks);
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
#endif
        uint64_t cpu_divisor=(uint64_t)s.cpu_blocks*FM_BLOCK*1000;
        uint32_t cpu_average=cpu_divisor?(uint32_t)((s.cpu_busy_us*SAMPLE_RATE+cpu_divisor/2)/cpu_divisor):UINT32_MAX;
        uint32_t cpu_peak=(uint32_t)(((uint64_t)s.cpu_peak_us*SAMPLE_RATE+FM_BLOCK*500)/(FM_BLOCK*1000));
#ifdef CONFIG_SYNTHDEF_TOUCH_UI
        touch_ui_cpu(cpu_average,cpu_peak);
#endif
        ESP_LOGI(TAG,"CPU average_x10=%lu peak_x10=%lu busy_us=%llu blocks=%lu peak_us=%lu",
            (unsigned long)cpu_average,(unsigned long)cpu_peak,(unsigned long long)s.cpu_busy_us,
            (unsigned long)s.cpu_blocks,(unsigned long)s.cpu_peak_us);
#ifdef CONFIG_SYNTHDEF_TOUCH_UI
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
