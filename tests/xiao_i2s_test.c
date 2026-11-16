/* Test the actual adapter's clock setup and capture state machine, not a clone. */
#include "../firmware/components/board_audio/board_audio_i2s.c"
static void put32(unsigned char *p,unsigned n) {for(unsigned i=0;i<4;++i)p[i]=(unsigned char)(n>>(8*i));}
int main(int argc,char **argv)
{
    assert(argc==2);unsigned rate=(unsigned)atoi(argv[1]);
    assert(board_audio_init(rate==16000?44100:16000)==ESP_ERR_INVALID_ARG);
    fail_allocation=true;assert(board_audio_init(rate)==ESP_ERR_NO_MEM);
    fail_allocation=false;assert(board_audio_init(rate)==ESP_OK);
    assert(board_audio_init(rate)==ESP_ERR_INVALID_STATE);
    assert(allocated_bytes==rate*4u);
    assert(configured.clk_cfg.sample_rate_hz==rate);
    assert(configured.slot_cfg.data_bit_width==16 && configured.slot_cfg.slot_mode==2);
    unsigned slot=configured.slot_cfg.slot_bit_width?configured.slot_cfg.slot_bit_width:16;
    assert(slot==(rate==16000?32u:16u));
    assert(configured.slot_cfg.ws_width==slot && configured.slot_cfg.bit_shift);
    assert(rate*2u*slot==(rate==16000?1024000u:1411200u));
    assert(configured.gpio_cfg.mclk==-1 && configured.gpio_cfg.bclk==7 && configured.gpio_cfg.ws==8 && configured.gpio_cfg.dout==9);
    assert(configured_channel.role==I2S_ROLE_MASTER && configured_channel.dma_frame_num==128 && configured_channel.dma_desc_num==6);
    assert(callbacks.on_send_q_ovf(NULL,NULL,NULL)==false && board_audio_dma_errors()==1);
    unsigned char command[10]={0};char reply[BOARD_CAPTURE_CHUNK_BYTES*2+128];
    assert(!board_audio_capture_command("CAPBEGIN",command,4,reply,sizeof reply));
    put32(command,rate+1);assert(!board_audio_capture_command("CAPBEGIN",command,4,reply,sizeof reply));
    put32(command,rate);assert(board_audio_capture_command("CAPBEGIN",command,4,reply,sizeof reply));
    assert(!board_audio_capture_command("CAPBEGIN",command,4,reply,sizeof reply));
    int16_t pcm[128];for(unsigned i=0;i<128;++i)pcm[i]=(i%2)?-16384:8192;
    size_t written;
    write_error=ESP_ERR_INVALID_STATE;assert(board_audio_write(pcm,64,&written)==write_error);
    assert(atomic_load(&capture_frames)==0);
    write_error=0;short_write=true;assert(board_audio_write(pcm,64,&written)==ESP_OK);
    assert(atomic_load(&capture_frames)==0);short_write=false;
    for(unsigned i=0;i<rate;i+=64)assert(board_audio_write(pcm,64,&written)==ESP_OK);
    assert(written==256 && last_bytes==256 && last_write==pcm);
    assert(atomic_load(&capture_frames)==rate && atomic_load(&capture_state)==2);
    for(unsigned i=0;i<rate*2u;++i)assert(capture[i]==pcm[i%128]);
    assert(board_audio_capture_command("CAPINFO",NULL,0,reply,sizeof reply));
    char rate_json[32];snprintf(rate_json,sizeof rate_json,"\"rate\":%u",rate);assert(strstr(reply,rate_json));
    put32(command,capture_id+1);put32(command+4,rate*4-4);command[8]=4;
    assert(!board_audio_capture_command("CAPREAD",command,10,reply,sizeof reply));
    put32(command,capture_id);assert(board_audio_capture_command("CAPREAD",command,10,reply,sizeof reply));
    assert(strstr(reply,"002000c0"));
    command[8]=5;assert(!board_audio_capture_command("CAPREAD",command,10,reply,sizeof reply));
    put32(command,1);assert(board_audio_capture_command("CAPBEGIN",command,4,reply,sizeof reply));
    assert(board_audio_write(pcm,64,&written)==ESP_OK && atomic_load(&capture_frames)==1);
    free(capture);return 0;
}
