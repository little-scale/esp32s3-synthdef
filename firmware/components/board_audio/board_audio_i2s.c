/* SPDX-License-Identifier: GPL-3.0-or-later */
/* XIAO ESP32-S3: Philips stereo, no codec or display dependency. */
#include "board_audio.h"
#include "driver/i2s_std.h"
#include "driver/gpio.h"
#include "esp_check.h"
#include "esp_heap_caps.h"
#include "esp_random.h"
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>

static i2s_chan_handle_t tx;
static atomic_uint dma_errors,capture_state,capture_frames;
static unsigned capture_requested;
static uint32_t capture_id;
static int16_t *capture;
static uint32_t sample_rate;
enum { CAPTURE_FRAMES=44100,LED_GPIO=21 };
static const char *TAG="board_audio";
static bool IRAM_ATTR dma_error(i2s_chan_handle_t h,i2s_event_data_t *event,void *ctx)
{(void)h;(void)event;(void)ctx;atomic_fetch_add(&dma_errors,1);return false;}
esp_err_t board_audio_init(uint32_t rate)
{
    if(tx)return ESP_ERR_INVALID_STATE;
    if(CONFIG_SYNTHDEF_I2S_BCLK==CONFIG_SYNTHDEF_I2S_WS || CONFIG_SYNTHDEF_I2S_BCLK==CONFIG_SYNTHDEF_I2S_DOUT || CONFIG_SYNTHDEF_I2S_WS==CONFIG_SYNTHDEF_I2S_DOUT)return ESP_ERR_INVALID_ARG;
    capture=heap_caps_malloc(CAPTURE_FRAMES*2*sizeof(int16_t),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!capture)return ESP_ERR_NO_MEM;
    sample_rate=rate;
    capture_id=esp_random();
    i2s_chan_config_t channel=I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0,I2S_ROLE_MASTER);
    channel.dma_desc_num=6;channel.dma_frame_num=128;channel.auto_clear=true;
    ESP_RETURN_ON_ERROR(i2s_new_channel(&channel,&tx,NULL),TAG,"I2S channel");
    i2s_std_config_t standard={
        .clk_cfg=I2S_STD_CLK_DEFAULT_CONFIG(rate),
        .slot_cfg=I2S_STD_PHILIP_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT,I2S_SLOT_MODE_STEREO),
        .gpio_cfg={.mclk=I2S_GPIO_UNUSED,.bclk=CONFIG_SYNTHDEF_I2S_BCLK,.ws=CONFIG_SYNTHDEF_I2S_WS,.dout=CONFIG_SYNTHDEF_I2S_DOUT,.din=I2S_GPIO_UNUSED}
    };
    ESP_RETURN_ON_ERROR(i2s_channel_init_std_mode(tx,&standard),TAG,"I2S format");
    i2s_event_callbacks_t callbacks={.on_send_q_ovf=dma_error};
    ESP_RETURN_ON_ERROR(i2s_channel_register_event_callback(tx,&callbacks,NULL),TAG,"I2S events");
    gpio_config_t led={.pin_bit_mask=1ULL<<LED_GPIO,.mode=GPIO_MODE_OUTPUT};
    ESP_RETURN_ON_ERROR(gpio_config(&led),TAG,"activity LED");gpio_set_level(LED_GPIO,1);
    ESP_LOGI(TAG,"Stereo I2S: rate=%lu BCLK=%d WS=%d DOUT=%d; no MCLK; DMA=6x128; capture=1 second",(unsigned long)rate,CONFIG_SYNTHDEF_I2S_BCLK,CONFIG_SYNTHDEF_I2S_WS,CONFIG_SYNTHDEF_I2S_DOUT);
    return ESP_OK;
}
esp_err_t board_audio_write(const int16_t *pcm,size_t frames,size_t *written)
{
    *written=0;
    esp_err_t result=i2s_channel_write(tx,pcm,frames*2*sizeof *pcm,written,100);
    if(result==ESP_OK && *written==frames*2*sizeof *pcm && atomic_load_explicit(&capture_state,memory_order_acquire)==1){
        unsigned at=atomic_load_explicit(&capture_frames,memory_order_relaxed),count=capture_requested-at;
        if(count>frames)count=frames;
        memcpy(capture+at*2,pcm,count*2*sizeof *pcm);
        atomic_store_explicit(&capture_frames,at+count,memory_order_release);
        if(at+count==capture_requested)atomic_store_explicit(&capture_state,2,memory_order_release);
    }
    return result;
}
void board_audio_activity(bool active){gpio_set_level(LED_GPIO,active?0:1);}
esp_err_t board_audio_pause(void){return ESP_OK;}
esp_err_t board_audio_resume(void){return ESP_OK;}
esp_err_t board_audio_stop_dma(void){return i2s_channel_disable(tx);}
esp_err_t board_audio_start_dma(void){return i2s_channel_enable(tx);}
esp_err_t board_audio_mute(void){return i2s_channel_disable(tx);}
uint32_t board_audio_dma_errors(void){return atomic_load(&dma_errors);}
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
        return snprintf(out,size,"{\"state\":%u,\"frames\":%u,\"requested\":%u,\"channels\":2,\"rate\":%lu,\"bytes\":%u,\"capture_id\":%lu}",state,atomic_load(&capture_frames),capture_requested,(unsigned long)sample_rate,capture_requested*4,(unsigned long)capture_id)>0;
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
