/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "pattern_vm.h"
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <string.h>
static pg_vm vm;
static unsigned char bytes[32768];
static void value(pg_value x){
 if(x.kind==PG_NUMBER || x.kind==PG_REST){if(isfinite(x.number))printf("%.17g",x.number);else printf("null");}
 else if(x.kind==PG_SYMBOL)printf("\"%s\"",vm.symbol[x.at]);
 else if(x.kind==PG_ARRAY){putchar('[');for(unsigned i=0;i<x.count;i++){if(i)putchar(',');value(vm.arrays[x.at+i]);}putchar(']');}
 else printf("null");
}
int main(int argc,char **argv){
 if(argc!=3 && argc!=4)return 2;FILE *f=fopen(argv[1],"rb");if(!f)return 2;size_t n=fread(bytes,1,sizeof bytes,f);fclose(f);
 if(argc==4){
  static unsigned char original[32768];memcpy(original,bytes,n);uint32_t rng=42;
  for(unsigned trial=0;trial<10000;trial++){
   memcpy(bytes,original,n);rng=rng*1664525u+1013904223u;
   unsigned at=rng%(unsigned)n;bytes[at]^=(unsigned char)(1u<<(rng%8));
   if(pg_load(&vm,bytes,trial%5?n:at)){
    for(unsigned k=0;k<8;k++){pg_event e;if(pg_next(&vm,k,&e)<=0)break;}
   }
  }
  puts("PASS: 10000 deterministic malformed/mutated programs");return 0;
 }
 if(!pg_load(&vm,bytes,n)){fprintf(stderr,"%s\n",vm.error);return 3;}
 unsigned count=(unsigned)strtoul(argv[2],NULL,10);if(count>100000)return 2;
 printf("{\"vm_bytes\":%zu,\"events\":[",sizeof vm);double beat=0;unsigned emitted=0;
 for(unsigned i=0;i<count;i++){
  pg_event event;int ok=pg_next(&vm,beat,&event);
  if(ok<0){fprintf(stderr,"event %u: %s\n",i,vm.error);return 4;}if(!ok)break;
  if(emitted++)putchar(',');printf("{");
  for(unsigned k=0;k<event.count;k++){if(k)putchar(',');printf("\"%s\":",vm.symbol[event.field[k].key]);value(event.field[k].value);}
  printf("}");const pg_value *delta=pg_get(&vm,&event,"delta");if(!delta)delta=pg_get(&vm,&event,"dur");beat+=delta?pg_number(delta):1;
 }
 printf("],\"steps\":%llu}\n",(unsigned long long)vm.steps);return 0;
}
