/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Test-only access to the private quantiser, including invalid input paths. */
void miverb_probe(uint32_t value,uint32_t scale_bits,unsigned pos,unsigned offset,uint32_t out[4])
{
 static float arena[16384];static fm_voice voice;
 float scale,read;mi_context context={0};voice.fault=0;
 memcpy(&context.acc,&value,4);memcpy(&scale,&scale_bits,4);
 context.mem=(unsigned char *)arena;context.voice=&voice;context.pos=pos;
 mi_write(&context,offset,scale);
 unsigned at=2*((pos+offset)&32767u);
 out[0]=context.mem[at]|((uint32_t)context.mem[at+1]<<8);
 memcpy(out+1,&context.acc,4);out[2]=voice.fault;
 read=mi_read(&context,offset);memcpy(out+3,&read,4);
}
