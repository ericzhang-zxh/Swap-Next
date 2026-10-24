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
#include <errno.h>
#include <string.h>
#define PAGES 16384
static uint64_t samples[PAGES], order[PAGES], types[PAGES];
static int xswap_type;
static char debugpath[128];
static const char *reclaim_path;
static uint64_t pattern(size_t i) { return ((i/512)*8+i%8)*UINT64_C(0x9e3779b97f4a7c15)^UINT64_C(0xa5a5a5a5a5a5a5a5); }
/* Explicit pageout works without relying on host-sized global pressure. */
static size_t swapped_pages(uint64_t *data, int require_targets) {
 int fd=open("/proc/self/pagemap",O_RDONLY);if(fd<0)exit(31);
 size_t count=0,targets=0;
 for(size_t pg=0;pg<PAGES;pg++){
  uint64_t pte;off_t pos=((uintptr_t)data/4096+pg)*8;
  if(pread(fd,&pte,8,pos)!=8)exit(32);
  if((pte&(UINT64_C(1)<<62))&&!(pte&(UINT64_C(1)<<63))){
   if((pte&31)!=(uint64_t)xswap_type)exit(33);
   count++;if(pg<16)targets++;
  }
 }
 close(fd);
 return require_targets&&targets!=16?0:count;
}
static size_t pageout_verified(uint64_t *data, size_t bytes, int targets) {
 size_t count=0;
 for(int attempt=0;attempt<16;attempt++){
  if(madvise(data,bytes,MADV_PAGEOUT))exit(34);
  /* Reclaim swap-cache folios too, so later accesses exercise the backend. */
  int fd=open(reclaim_path,O_WRONLY);if(fd<0){perror("memory.reclaim open");exit(42);}
  char amount[32];int len=snprintf(amount,sizeof amount,"%zu",bytes);
  ssize_t written=write(fd,amount,len);int saved_errno=errno;close(fd);
  if(written!=len&&!(written<0&&saved_errno==EAGAIN)){
   errno=saved_errno;perror("memory.reclaim write");exit(43);
  }
  usleep(125000);
  count=swapped_pages(data,targets);
  if(count>=1000)return count;
 }
 fprintf(stderr,"CORRECTNESS_FAIL insufficient swapped target PTEs\n");exit(35);
}
static uint64_t clock_ns(void) { struct timespec t; if(clock_gettime(CLOCK_MONOTONIC_RAW,&t)) exit(10); return t.tv_sec*UINT64_C(1000000000)+t.tv_nsec; }
static void metadata(const char *phase) {
 char line[256]; FILE *f=fopen(debugpath,"r"); if(!f)exit(11);
 printf("META_BEGIN %s\n",phase);while(fgets(line,sizeof line,f))fputs(line,stdout);
 fclose(f);puts("META_END");
}
int main(int argc, char **argv) {
 uint64_t workload_start=clock_ns();
 if(argc!=3)return 20;
 reclaim_path=argv[2];
 char *end;long type=strtol(argv[1],&end,10);if(*end||type<0||type>31)return 21;
 xswap_type=(int)type;
 snprintf(debugpath,sizeof debugpath,"/sys/kernel/debug/xswap/type%d",xswap_type);
 metadata("before");
 size_t bytes=PAGES*4096UL; uint64_t *data=mmap(0,bytes,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
 if(data==MAP_FAILED)return 1;
 if(sysconf(_SC_PAGESIZE)!=4096)return 36;
 /* The guest disables THP globally; EINVAL is expected without CONFIG_THP. */
 if(madvise(data,bytes,MADV_NOHUGEPAGE)){
  if(errno!=EINVAL){perror("MADV_NOHUGEPAGE");return 36;}
  puts("NOHUGEPAGE_UNAVAILABLE");
 }
 for(size_t i=0;i<bytes/8;i++)data[i]=pattern(i);
 for(size_t i=0;i<PAGES;i++){order[i]=i;samples[i]=0;}
 uint64_t seed=0x51a9;
 for(size_t i=PAGES-1;i>0;i--){seed^=seed<<13;seed^=seed>>7;seed^=seed<<17;size_t j=seed%(i+1);uint64_t t=order[i];order[i]=order[j];order[j]=t;}
 size_t initial=pageout_verified(data,bytes,1);
 printf("FORK_TARGET_XSWAP_PTES 16 TOTAL %zu\n",initial);
 int st;
 metadata("after_pressure");
 int gate[2];if(pipe(gate))return 5;pid_t kids[48];
 for(int i=0;i<48;i++){
  kids[i]=fork();if(kids[i]<0)return 6;
  if(!kids[i]){close(gate[1]);char c;if(read(gate[0],&c,1)!=1)_exit(7);
   size_t off=(size_t)(i%16)*512;
   if(data[off]!=pattern(off))_exit(8);
   data[off]^=UINT64_C(0x123456);
   for(size_t j=off;j<off+512;j++)
    if(data[j]!=(pattern(j)^(j==off?UINT64_C(0x123456):0)))_exit(8);
   _exit(0);}
 }
 close(gate[0]);metadata("fork_shared");
 uint64_t teardown_start=clock_ns();
 char release[48];memset(release,1,sizeof release);if(write(gate[1],release,sizeof release)!=sizeof release)return 7;close(gate[1]);
 for(int i=0;i<48;i++)if(waitpid(kids[i],&st,0)<0||!WIFEXITED(st)||WEXITSTATUS(st))return 8;
 printf("FORK_EXIT_NS %llu\n",(unsigned long long)(clock_ns()-teardown_start));
 puts("FORK_SHARED_PASS");puts("CONCURRENT_FAULT_PASS workers=48 targets=16");metadata("after_children");
 int fd=open("/proc/self/pagemap",O_RDONLY);if(fd<0)return 9;
 size_t n=0,skipped=0;struct rusage before,after;getrusage(RUSAGE_SELF,&before);
 for(size_t k=0;k<PAGES;k++){
  size_t page=order[k];uint64_t pte;
  off_t pos=((uintptr_t)data/4096+page)*8;
  if(pread(fd,&pte,8,pos)!=8)return 10;
  if(!(pte&(UINT64_C(1)<<62))||(pte&(UINT64_C(1)<<63))){skipped++;continue;}
  if((pte&31)!=(uint64_t)xswap_type)return 22;
  types[n]=pte&31;
  __asm__ __volatile__("":::"memory");
  uint64_t t=clock_ns();uint64_t v=*(volatile uint64_t*)(data+page*512);uint64_t d=clock_ns()-t;
  __asm__ __volatile__("":::"memory");
  if(v!=pattern(page*512))return 11;
  samples[n++]=d;
 }
 getrusage(RUSAGE_SELF,&after);close(fd);
 for(size_t i=0;i<bytes/8;i++)if(data[i]!=pattern(i))return 12;
 printf("LATENCY_BEGIN samples=%zu skipped=%zu minor=%ld major=%ld\n",n,skipped,after.ru_minflt-before.ru_minflt,after.ru_majflt-before.ru_majflt);
 for(size_t i=0;i<n;i++)printf("LATENCY_NS %llu TYPE %llu\n",(unsigned long long)samples[i],(unsigned long long)types[i]);
 puts("LATENCY_END");metadata("after_reads");
 sleep(2);metadata("after_settle");
 if(n<1000)return 13;
 pid_t cow=fork();if(cow<0)return 14;
 if(!cow){data[0]^=UINT64_C(0x123456);_exit(data[0]==(pattern(0)^UINT64_C(0x123456))?0:1);}
 if(waitpid(cow,&st,0)<0||!WIFEXITED(st)||WEXITSTATUS(st)||data[0]!=pattern(0))return 15;
 puts("COW_PASS");
 /* Exercise physical backend removal while xswap still owns live PTEs. */
 size_t backend_live=pageout_verified(data,bytes,0);
 FILE *swaps=fopen("/proc/swaps","r");if(!swaps)return 37;
 char swapline[512],device[128],kind[32];unsigned long size_kib,used_kib=0;int priority,found=0;
 while(fgets(swapline,sizeof swapline,swaps)){
  unsigned long used;
  if(sscanf(swapline,"%127s %31s %lu %lu %d",device,kind,&size_kib,&used,&priority)==5&&!strcmp(device,"/dev/vda")){
   used_kib=used;found++;
  }
 }
 fclose(swaps);if(found!=1)return 38;
 printf("PHYSICAL_SWAPOFF_LIVE_XSWAP_PTES %zu BACKEND_USED_KIB %lu\n",backend_live,used_kib);
 if(access(debugpath,F_OK)||swapoff("/dev/vda"))return 39;
 for(size_t i=0;i<bytes/8;i++)if(data[i]!=pattern(i))return 40;
 puts("PHYSICAL_SWAPOFF_LIVE_PASS");
 if(swapon("/dev/vda",SWAP_FLAG_PREFER))return 41;
 pageout_verified(data,bytes,0);
 int livefd=open("/proc/self/pagemap",O_RDONLY);if(livefd<0)return 27;
 size_t live=0;
 for(size_t page=0;page<PAGES;page++){
  uint64_t pte;off_t pos=((uintptr_t)data/4096+page)*8;
  if(pread(livefd,&pte,8,pos)!=8)return 28;
  if((pte&(UINT64_C(1)<<62))&&!(pte&(UINT64_C(1)<<63))){
   if((pte&31)!=(uint64_t)xswap_type)return 29;
   live++;
  }
 }
 close(livefd);if(!live)return 30;
 printf("DESTROY_LIVE_XSWAP_PTES %zu\n",live);
 int destroy=open("/sys/kernel/mm/xswap/destroy",O_WRONLY);
 if(destroy<0)return 23;
 char value[16];int len=snprintf(value,sizeof value,"%d\n",xswap_type);
 if(write(destroy,value,len)!=len||close(destroy))return 24;
 for(size_t i=0;i<bytes/8;i++)if(data[i]!=pattern(i))return 25;
 puts("DESTROY_LIVE_PASS");
 if(access(debugpath,F_OK)==0)return 26;
 if(swapoff("/dev/vda"))return 17;
 for(size_t i=0;i<bytes/8;i++)if(data[i]!=pattern(i))return 18;
 puts("SWAPOFF_LIVE_PASS");
 if(munmap(data,bytes))return 19;
 printf("WORKLOAD_NS %llu\n",(unsigned long long)(clock_ns()-workload_start));
 puts("KERNEL_WORKLOAD_PASS");return 0;
}
