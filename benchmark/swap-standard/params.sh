# SPDX-License-Identifier: GPL-2.0-only
# Workload parameters. Swap backends and the kernel build follow Chris Li's
# kbench scripts (kbench, kbench-setup-{zram,zram-64k,zswap}); the other
# workloads keep their upstream-thread sizes for an 8-vCPU, 8-GiB guest.
# Changing any value is a new protocol revision and needs fresh calibration.
# vm.page-cluster is not a parameter here. The guest keeps the kernel
# default of 3, prints PAGE_CLUSTER, and fails if that value is not 3.
SETTLE_SEC=3
SWAPPINESS=60

# zram: two lz4 devices, zram0 first (priority 100) and zram1 as overflow (priority 0).
# zswap: lzo/zsmalloc with the shrinker on, backed by zram1 alone.
# zram-64k: one lz4 device with only 64 KiB mTHP enabled.
ZRAM_COMP=lz4
ZRAM0_SIZE=3200M
ZRAM1_SIZE=20000M
ZRAM64K_SIZE=8G
ZSWAP_COMP=lzo
ZSWAP_ZPOOL=zsmalloc
# Anonymous THP size set to always; every other size is never.
THP_SIZE=2048kB
THP_SIZE_64K=64kB

# vm-scalability usemem: "usemem --init-time -O -y -x [-R] -n N 1G" under a memcg.
USEMEM_NPROC=8
USEMEM_SIZE=1G
USEMEM_MEMCG=4G

# kbench kernel build: extract outside the memcg, then defconfig and a full
# "make -j32" inside a 470M memcg, after a 10 s settle.
# TCG revision 6 excludes this workload. The 2026-10-27 smoke OOM-killed
# objtool inside 470M, and a full TCG build does not fit the guest timeout.
# These two values stay at the kbench settings.
BUILD_MEMCG=470M
BUILD_JOBS=32
BUILD_SETTLE_SEC=10

# Valkey + valkey-benchmark, the redis-benchmark setup from the swap table series.
REDIS_MEMCG=1536M
REDIS_MAXMEMORY=2560M
REDIS_KEYS=3000000
REDIS_VALUE=1024

# Swap-in latency, the zswapin_perf method: fill, reclaim through memory.reclaim, read back.
SWAPIN_SIZE=1G

# Slot lifetime churn (xswap correctness): workers fill past the memcg limit
# and exit together while zswap writes back to the physical backend.
LIFETIME_MEMCG=768M
LIFETIME_WORKERS=4
LIFETIME_SIZE=512M
LIFETIME_SEC=600
LIFETIME_ZSWAP_POOL_PERCENT=4
# Only instrumented kernels expose this; it widens the writeback race window.
LIFETIME_WB_DELAY_MS=2000
