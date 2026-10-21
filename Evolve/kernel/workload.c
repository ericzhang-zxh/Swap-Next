// SPDX-License-Identifier: GPL-2.0-only
#define _GNU_SOURCE
#include <sys/mman.h>
#include <sys/wait.h>
#include <sys/resource.h>
#include <sys/swap.h>
#include <time.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
#include <string.h>
#define PAGES 16384
static uint64_t samples[PAGES], order[PAGES];
static uint64_t pattern(size_t i) { return i*UINT64_C(0x9e3779b97f4a7c15)^UINT64_C(0xa5a5a5a5a5a5a5a5); }
static uint64_t clock_ns(void) { struct timespec t; if(clock_gettime(CLOCK_MONOTONIC_RAW,&t)) exit(10); return t.tv_sec*UINT64_C(1000000000)+t.tv_nsec; }
static void metadata(const char *phase) {
 char line[256]; FILE *f=fopen("/proc/swap_next_metrics","r"); if(!f)exit(11);
 printf("META_BEGIN %s\n",phase);while(fgets(line,sizeof line,f))fputs(line,stdout);
 fclose(f);puts("META_END");
}
int main(void) {
 size_t bytes=PAGES*4096UL; uint64_t *data=mmap(0,bytes,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
 if(data==MAP_FAILED)return 1;
 for(size_t i=0;i<bytes/8;i++)data[i]=pattern(i);
 for(size_t i=0;i<PAGES;i++){order[i]=i;samples[i]=0;}
 uint64_t seed=0x51a9;
 for(size_t i=PAGES-1;i>0;i--){seed^=seed<<13;seed^=seed>>7;seed^=seed<<17;size_t j=seed%(i+1);uint64_t t=order[i];order[i]=order[j];order[j]=t;}
 if(madvise(data,bytes,MADV_PAGEOUT))return 2;
 sleep(2);
 pid_t pressure=fork();if(pressure<0)return 3;
 if(!pressure){execl("/bin/usemem","usemem","-O","5G",(char*)0);_exit(127);}
 int st;if(waitpid(pressure,&st,0)<0||!WIFEXITED(st)||WEXITSTATUS(st))return 4;
 int gate[2];if(pipe(gate))return 5;pid_t kids[48];
 for(int i=0;i<48;i++){
  kids[i]=fork();if(kids[i]<0)return 6;
  if(!kids[i]){close(gate[1]);char c;if(read(gate[0],&c,1)!=1)_exit(7);
   size_t off=(size_t)(i%16)*512;
   _exit(data[off]==pattern(off)?0:8);}
 }
 close(gate[0]);metadata("fork_shared");
 uint64_t teardown_start=clock_ns();
 char release[48];memset(release,1,sizeof release);if(write(gate[1],release,sizeof release)!=sizeof release)return 7;close(gate[1]);
 for(int i=0;i<48;i++)if(waitpid(kids[i],&st,0)<0||!WIFEXITED(st)||WEXITSTATUS(st))return 8;
 printf("FORK_EXIT_NS %llu\n",(unsigned long long)(clock_ns()-teardown_start));
 puts("FORK_SHARED_PASS");metadata("after_children");
 int fd=open("/proc/self/pagemap",O_RDONLY);if(fd<0)return 9;
 size_t n=0,skipped=0;struct rusage before,after;getrusage(RUSAGE_SELF,&before);
 for(size_t k=0;k<PAGES;k++){
  size_t page=order[k];uint64_t pte;
  off_t pos=((uintptr_t)data/4096+page)*8;
  if(pread(fd,&pte,8,pos)!=8)return 10;
  if(!(pte&(UINT64_C(1)<<62))||(pte&(UINT64_C(1)<<63))){skipped++;continue;}
  __asm__ __volatile__("":::"memory");
  uint64_t t=clock_ns();uint64_t v=*(volatile uint64_t*)(data+page*512);uint64_t d=clock_ns()-t;
  __asm__ __volatile__("":::"memory");
  if(v!=pattern(page*512))return 11;
  samples[n++]=d;
 }
 getrusage(RUSAGE_SELF,&after);close(fd);
 for(size_t i=0;i<bytes/8;i++)if(data[i]!=pattern(i))return 12;
 printf("LATENCY_BEGIN samples=%zu skipped=%zu minor=%ld major=%ld\n",n,skipped,after.ru_minflt-before.ru_minflt,after.ru_majflt-before.ru_majflt);
 for(size_t i=0;i<n;i++)printf("LATENCY_NS %llu\n",(unsigned long long)samples[i]);
 puts("LATENCY_END");metadata("after_reads");
 if(n<1000)return 13;
 pid_t cow=fork();if(cow<0)return 14;
 if(!cow){data[0]^=UINT64_C(0x123456);_exit(data[0]==(pattern(0)^UINT64_C(0x123456))?0:1);}
 if(waitpid(cow,&st,0)<0||!WIFEXITED(st)||WEXITSTATUS(st)||data[0]!=pattern(0))return 15;
 puts("COW_PASS");
 if(madvise(data,bytes,MADV_PAGEOUT))return 16;
 sleep(2);
 if(swapoff("/dev/vda"))return 17;
 for(size_t i=0;i<bytes/8;i++)if(data[i]!=pattern(i))return 18;
 puts("SWAPOFF_LIVE_PASS");
 if(munmap(data,bytes))return 19;
 puts("KERNEL_WORKLOAD_PASS");return 0;
}
