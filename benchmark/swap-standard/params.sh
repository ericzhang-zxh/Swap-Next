# SPDX-License-Identifier: GPL-2.0-only
# Workload parameters, scaled from upstream swap threads to an 8-vCPU, 8-GiB guest.
# Changing any value is a new protocol revision and needs fresh calibration.
SETTLE_SEC=3
ZRAM_COMP=lz4
ZRAM_SIZE=16G
ZSWAP_COMP=zstd

# vm-scalability usemem: "usemem --init-time -O -y -x [-R] -n N 1G" under a memcg.
USEMEM_NPROC=8
USEMEM_SIZE=1G
USEMEM_MEMCG=4G

# Kernel build under a memcg, source and objects on tmpfs.
BUILD_MEMCG=3G
BUILD_JOBS=16
BUILD_TARGET=vmlinux

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
LIFETIME_SEC=150
LIFETIME_ZSWAP_POOL_PERCENT=4
# Only instrumented kernels expose this; it widens the writeback race window.
LIFETIME_WB_DELAY_MS=50
