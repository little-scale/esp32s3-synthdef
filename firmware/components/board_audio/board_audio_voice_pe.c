/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Voice PE: XMOS clocks, stereo S16 application contract / S32 wire slots. */
#include "board_audio.h"
#include "voice_pe_board.h"
#include "voice_pe_pins.h"
#include "voice_pe_survey.h"
#include "voice_pe_codec.h"
#include "voice_pe_format.h"
#ifdef CONFIG_SYNTHDEF_VOICE_PE_LOW_RATE
#include "voice_pe_resampler.h"
#endif
#include "driver/gpio.h"
#include "esp_heap_caps.h"
#include "esp_random.h"
#include "esp_log.h"
#include "esp_timer.h"
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>

static i2s_chan_handle_t tx;
static i2s_std_config_t standard;
static voice_pe_codec_device codec;
static atomic_uint dma_errors,capture_state,capture_frames;
static atomic_bool running,mute_pending;
static unsigned capture_requested;
static uint32_t capture_id,sample_rate;
static int16_t *capture;
#ifdef CONFIG_SYNTHDEF_VOICE_PE_LOW_RATE
static vpe_resampler resampler;
#endif
static uint32_t processing_us;
static uint64_t conversion_clips;
static float startup_ws_hz,startup_bclk_hz;
enum { CAPTURE_FRAMES=48000 };
static const char *TAG="voice_pe_audio";
static bool IRAM_ATTR dma_error(i2s_chan_handle_t h,i2s_event_data_t *e,void *ctx)
{(void)h;(void)e;(void)ctx;atomic_fetch_add(&dma_errors,1);return false;}
static esp_err_t idle_data(void)
{
    esp_err_t err=gpio_set_level(VPE_TX_DATA,0);
    if(err!=ESP_OK)return err;
    gpio_config_t cfg={.pin_bit_mask=1ULL<<VPE_TX_DATA,.mode=GPIO_MODE_OUTPUT};
    return gpio_config(&cfg);
}
esp_err_t board_audio_early_init(void){return voice_pe_safe_init();}
esp_err_t board_audio_start_dma(void)
{
    if(!tx)return ESP_ERR_INVALID_STATE;
    if(atomic_load(&running))return ESP_OK;
#ifdef CONFIG_SYNTHDEF_VOICE_PE_LOW_RATE
    vpe_resampler_reset(&resampler);
#endif
    esp_err_t err=i2s_channel_reconfig_std_gpio(tx,&standard.gpio_cfg);
    if(err!=ESP_OK)return err;
    static const int32_t zeros[128*2]={0};
    for(unsigned i=0;i<6;++i){
        size_t loaded=0;
        err=i2s_channel_preload_data(tx,zeros,sizeof zeros,&loaded);
        if(err!=ESP_OK || loaded!=sizeof zeros)return err==ESP_OK?ESP_ERR_INVALID_SIZE:err;
    }
    err=i2s_channel_enable(tx);
    if(err==ESP_OK)atomic_store(&running,true);
    return err;
}
esp_err_t board_audio_stop_dma(void)
{
    if(!tx)return ESP_ERR_INVALID_STATE;
    esp_err_t err=ESP_OK;
    if(atomic_exchange(&running,false))err=i2s_channel_disable(tx);
#ifdef CONFIG_SYNTHDEF_VOICE_PE_LOW_RATE
    vpe_resampler_reset(&resampler);
#endif
    esp_err_t idle=idle_data();return err==ESP_OK?idle:err;
}
esp_err_t board_audio_init(uint32_t rate)
{
    if(tx || rate!=SYNTHDEF_SAMPLE_RATE || rate>SYNTHDEF_OUTPUT_SAMPLE_RATE ||
       SYNTHDEF_OUTPUT_SAMPLE_RATE%rate)return ESP_ERR_INVALID_ARG;
    esp_err_t err=voice_pe_safe_init();if(err!=ESP_OK)return err;
    voice_pe_survey_result clocks;
    err=voice_pe_survey(&clocks);
    if(err!=ESP_OK)return err;
    const float output_rate=SYNTHDEF_OUTPUT_SAMPLE_RATE;
    if(clocks.codec!=ESP_OK || clocks.xmos!=ESP_OK || clocks.ws.hz<output_rate*.98f ||
       clocks.ws.hz>output_rate*1.02f || clocks.bclk.hz<output_rate*64*.98f || clocks.bclk.hz>output_rate*64*1.02f)
        return ESP_ERR_INVALID_RESPONSE;
    startup_ws_hz=clocks.ws.hz;startup_bclk_hz=clocks.bclk.hz;
    err=voice_pe_codec_init_playback_at_rate(&codec,SYNTHDEF_OUTPUT_SAMPLE_RATE);if(err!=ESP_OK)return err;
    capture=heap_caps_malloc(CAPTURE_FRAMES*2*sizeof(int16_t),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!capture){voice_pe_codec_close(&codec);return ESP_ERR_NO_MEM;}
    sample_rate=rate;capture_id=esp_random();
    i2s_chan_config_t channel;
    err=voice_pe_i2s_config(SYNTHDEF_OUTPUT_SAMPLE_RATE,&channel,&standard);
    if(err==ESP_OK)err=i2s_new_channel(&channel,&tx,NULL);
    if(err==ESP_OK)err=i2s_channel_init_std_mode(tx,&standard);
    i2s_event_callbacks_t callbacks={.on_send_q_ovf=dma_error};
    if(err==ESP_OK)err=i2s_channel_register_event_callback(tx,&callbacks,NULL);
    if(err==ESP_OK)err=board_audio_start_dma();
    if(err==ESP_OK && !vpe_codec_unmute(&codec.sequence))err=ESP_ERR_INVALID_RESPONSE;
    if(err==ESP_OK)err=gpio_set_level(VPE_AMP_ENABLE,1);
    if(err!=ESP_OK){
        gpio_set_level(VPE_AMP_ENABLE,0);
        if(tx){board_audio_stop_dma();i2s_del_channel(tx);tx=NULL;}
        voice_pe_codec_close(&codec);heap_caps_free(capture);capture=NULL;return err;
    }
    ESP_LOGI(TAG,"DSP=%lu output=%u slave stereo S32; S16 input; codec 0dB; WS=%.1f BCLK=%.1f",(unsigned long)rate,SYNTHDEF_OUTPUT_SAMPLE_RATE,clocks.ws.hz,clocks.bclk.hz);
    return ESP_OK;
}
esp_err_t board_audio_write(const int16_t *pcm,size_t frames,size_t *written)
{
    if(!written)return ESP_ERR_INVALID_ARG;
    *written=0;
    processing_us=0;
    if(!pcm || !tx || !atomic_load(&running) || frames>SIZE_MAX/4)return ESP_ERR_INVALID_ARG;
    enum { ratio=SYNTHDEF_OUTPUT_SAMPLE_RATE/SYNTHDEF_SAMPLE_RATE };
    int32_t wire[128*ratio*2];size_t at=0;
    while(at<frames){
        size_t count=frames-at;if(count>128)count=128;
        int64_t convert_begin=esp_timer_get_time();
#ifdef CONFIG_SYNTHDEF_VOICE_PE_LOW_RATE
        {
            uint64_t before=resampler.clipped;
            if(vpe_resampler_process(&resampler,pcm+at*2,count,wire,384)!=(int)(count*3))return ESP_ERR_INVALID_SIZE;
            conversion_clips+=resampler.clipped-before;
        }
#else
        if(voice_pe_pack_s16(pcm+at*2,count,wire,128*2)!=(int)(count*2))return ESP_ERR_INVALID_SIZE;
#endif
        processing_us+=(uint32_t)(esp_timer_get_time()-convert_begin);
        size_t output_frames=count*ratio,bytes=0;
        esp_err_t err=i2s_channel_write(tx,wire,output_frames*8,&bytes,100);
        *written+=(bytes/8/ratio)*4;at+=count;
        if(err!=ESP_OK || bytes!=output_frames*8 || bytes%8){
            atomic_fetch_add(&dma_errors,1);return err==ESP_OK?ESP_ERR_INVALID_SIZE:err;
        }
    }
    if(atomic_load_explicit(&capture_state,memory_order_acquire)==1){
        int64_t capture_begin=esp_timer_get_time();
        unsigned at_frame=atomic_load(&capture_frames),count=capture_requested-at_frame;
        if(count>frames)count=(unsigned)frames;
        memcpy(capture+at_frame*2,pcm,count*4);
        atomic_store_explicit(&capture_frames,at_frame+count,memory_order_release);
        if(at_frame+count==capture_requested)atomic_store_explicit(&capture_state,2,memory_order_release);
        processing_us+=(uint32_t)(esp_timer_get_time()-capture_begin);
    }
    return ESP_OK;
}
/* Ordinary graph replacement already drains a faded zero stream. Leave the
 * codec/amp on, with data held at zero, to avoid amplifier power-up clicks. */
esp_err_t board_audio_pause(void){return ESP_OK;}
esp_err_t board_audio_resume(void){return codec.sequence.ready?ESP_OK:ESP_ERR_INVALID_STATE;}
esp_err_t board_audio_mute(void)
{
    gpio_set_level(VPE_AMP_ENABLE,0);
    atomic_store(&mute_pending,true);
    return tx?board_audio_stop_dma():ESP_OK;
}
void board_audio_maintenance(void)
{
    if(atomic_exchange(&mute_pending,false) && !vpe_codec_mute(&codec.sequence))
        ESP_LOGE(TAG,"Deferred codec mute failed; amplifier remains off");
}
void board_audio_activity(bool active){(void)active; /* Ring mapping remains separate. */}
uint32_t board_audio_dma_errors(void){return atomic_load(&dma_errors);}
uint32_t board_audio_processing_us(void){return processing_us;}
uint64_t board_audio_conversion_clips(void){return conversion_clips;}
static uint32_t get32(const unsigned char *p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
int board_audio_capture_command(const char *op,const unsigned char *p,size_t bytes,char *out,size_t size)
{
    if(!capture)return 0;
    if(!strcmp(op,"CAPBEGIN") && bytes==4){
        unsigned frames=get32(p),state=atomic_load_explicit(&capture_state,memory_order_acquire);
        if(!frames || frames>CAPTURE_FRAMES || state==1 || !atomic_compare_exchange_strong(&capture_state,&state,3))return 0;
        capture_requested=frames;if(!++capture_id)++capture_id;
        atomic_store(&capture_frames,0);atomic_store_explicit(&capture_state,1,memory_order_release);
        return snprintf(out,size,"{\"recording\":true,\"frames\":%u,\"capture_id\":%lu}",frames,(unsigned long)capture_id)>0;
    }
    if(!strcmp(op,"CAPINFO") && !bytes){
        unsigned state=atomic_load_explicit(&capture_state,memory_order_acquire);
        return snprintf(out,size,"{\"state\":%u,\"frames\":%u,\"requested\":%u,\"channels\":2,\"rate\":%lu,\"output_rate\":%u,\"source\":\"dsp-post-volume\",\"startup_ws_hz\":%.1f,\"startup_bclk_hz\":%.1f,\"bytes\":%u,\"capture_id\":%lu}",state,atomic_load(&capture_frames),capture_requested,(unsigned long)sample_rate,SYNTHDEF_OUTPUT_SAMPLE_RATE,startup_ws_hz,startup_bclk_hz,capture_requested*4,(unsigned long)capture_id)>0;
    }
    if(!strcmp(op,"CAPREAD") && (bytes==6 || bytes==10) && atomic_load_explicit(&capture_state,memory_order_acquire)==2){
        /* Six-byte reads remain valid for older hosts. New hosts bind every
         * read to the specific recording, including across other controllers. */
        if(bytes==10){if(get32(p)!=capture_id)return 0;p+=4;}
        unsigned offset=get32(p),count=(unsigned)p[4]|((unsigned)p[5]<<8);
        if(!count || count>BOARD_CAPTURE_CHUNK_BYTES || offset>capture_requested*4 || count>capture_requested*4-offset || size<count*2+96)return 0;
        int at=snprintf(out,size,"{\"offset\":%u,\"capture_id\":%lu,\"data\":\"",offset,(unsigned long)capture_id);static const char hex[]="0123456789abcdef";
        const unsigned char *data=(const unsigned char *)capture+offset;
        for(unsigned i=0;i<count;++i){out[at++]=hex[data[i]>>4];out[at++]=hex[data[i]&15];}
        strcpy(out+at,"\"}");return 1;
    }
    return 0;
}
