#!/bin/bash
# SPDX-License-Identifier: GPL-2.0-only
# Runs inside the read-only benchmark root. One backend, one swap mode, one
# workload per boot; parameters come from params.sh, which is part of the image.
set -euo pipefail
backend=$1 mode=$2 workload=$3
export PATH=/opt/bench/bin:/usr/bin:/usr/sbin LC_ALL=C HOME=/tmp
. /opt/bench/params.sh

fail() { echo "BENCH_FAIL $1"; exit 1; }
cg=/sys/fs/cgroup/bench

meminfo() {
	echo "MEMINFO_BEGIN $1"
	grep -E '^(MemTotal|MemFree|MemAvailable|Slab|SUnreclaim|VmallocUsed|Percpu|PageTables|SwapTotal|SwapFree|Zswap|Zswapped):' /proc/meminfo
	echo "MEMINFO_END $1"
}

vmstat() {
	echo "VMSTAT_BEGIN $1"
	grep -E '^(pswpin|pswpout|zswpin|zswpout|zswpwb|pgmajfault|swpin_zero|swpout_zero|swap_ra|swap_ra_hit) ' /proc/vmstat || true
	echo "VMSTAT_END $1"
}

cgstat() {
	echo "CGSTAT_BEGIN $1"
	cat $cg/cpu.stat
	grep -E '^(anon|file|shmem|zswap|zswapped|pswpin|pswpout|zswpin|zswpout|pgmajfault) ' $cg/memory.stat || true
	echo "memory.peak $(cat $cg/memory.peak)"
	echo "memory.swap.peak $(cat $cg/memory.swap.peak 2>/dev/null || echo 0)"
	echo "CGSTAT_END $1"
}

zswap_enable() { echo "$1" > /sys/module/zswap/parameters/enabled; }

setup_swap() {
	local dev
	case $backend in
	zram)
		echo "$ZRAM_COMP" > /sys/block/zram0/comp_algorithm
		echo "$ZRAM_SIZE" > /sys/block/zram0/disksize
		dev=/dev/zram0 ;;
	zswap|disk)
		dev=/dev/vda ;;
	brd)
		dev=/dev/ram0 ;;
	*) fail backend ;;
	esac
	echo "$ZSWAP_COMP" > /sys/module/zswap/parameters/compressor
	zswap_enable Y
	mkswap "$dev" >/dev/null
	swapon -p 0 "$dev"
	if [ "$mode" = xswap ]; then
		# Creating xswap requires zswap; drop it afterwards unless it is the backend.
		echo 32767 > /sys/kernel/mm/xswap/create
		set -- /sys/kernel/debug/xswap/type*
		[ "$#" -eq 1 ] && [ -f "$1" ] || fail xswap_create
		echo "XSWAP_TYPE ${1##*/type}"
	elif [ "$mode" != plain ]; then
		fail mode
	fi
	[ "$backend" = zswap ] || zswap_enable N
	echo "ZSWAP_ENABLED $(cat /sys/module/zswap/parameters/enabled)"
	echo SWAPS_BEGIN
	cat /proc/swaps
	echo SWAPS_END
}

# Record the peak use of every swap device; a workload result counts only if
# the intended device carried it.
sample_swaps() {
	while :; do
		tail -n +2 /proc/swaps | awk '{print $1, $4}'
		sleep 0.5
	done > /tmp/swaps.samples
}

report_swap_peaks() {
	echo SWAP_PEAK_BEGIN
	awk '{if ($2 > m[$1]) m[$1] = $2} END {for (d in m) print d, m[d]}' /tmp/swaps.samples | sort
	echo SWAP_PEAK_END
}

enter_cgroup() {
	echo +memory > /sys/fs/cgroup/cgroup.subtree_control
	mkdir $cg
	echo "$1" > $cg/memory.max
	echo $$ > $cg/cgroup.procs
}

run_usemem() {
	enter_cgroup "$USEMEM_MEMCG"
	echo "USEMEM_EXPECT nproc=$USEMEM_NPROC bytes_per_worker=$(numfmt --from=iec "$USEMEM_SIZE")"
	echo USEMEM_BEGIN
	usemem --init-time -O -y -x $1 -n "$USEMEM_NPROC" "$USEMEM_SIZE"
	echo USEMEM_END
}

run_build() {
	enter_cgroup "$BUILD_MEMCG"
	mkdir /tmp/linux
	tar -xf /opt/bench/linux.tar -C /tmp/linux
	make -s -C /tmp/linux defconfig >/dev/null
	cgstat build_start
	vmstat build_start
	local t0 t1
	t0=$(date +%s%N)
	make -s -C /tmp/linux -j"$BUILD_JOBS" "$BUILD_TARGET" >/tmp/build.log 2>&1 || { tail -20 /tmp/build.log; fail build; }
	t1=$(date +%s%N)
	vmstat build_end
	[ -f /tmp/linux/$BUILD_TARGET ] || fail build_output
	echo "BUILD_REAL_USEC $(( (t1 - t0) / 1000 ))"
}

redis_benchmark() {
    local label=$1 operation=$2
    valkey-benchmark -r "$REDIS_KEYS" -n "$REDIS_KEYS" -d "$REDIS_VALUE" -c 12 -P 32 -t "$operation" -q > /tmp/client.log 2>&1 || { cat /tmp/client.log; fail redis_client; }
    if grep -qi 'error' /tmp/client.log; then
        cat /tmp/client.log
        fail redis_client_error
    fi
    tr '\r' '\n' < /tmp/client.log | grep -a 'requests per second' | tail -1 | sed "s/^/$label /"
}

run_redis() {
	enter_cgroup "$REDIS_MEMCG"
	ip link set lo up
	mkdir /tmp/valkey
	valkey-server --port 6379 --dir /tmp/valkey --save '' --appendonly no \
		--maxmemory "$REDIS_MAXMEMORY" --daemonize yes --logfile /tmp/valkey/log
	for i in $(seq 50); do valkey-cli ping >/dev/null 2>&1 && break; sleep 0.2; done
	valkey-cli ping | grep -q PONG || fail redis_start
	redis_benchmark REDIS_FILL set
	echo "REDIS_DBSIZE $(valkey-cli dbsize)"
	cgstat redis_get_start
	vmstat redis_get_start
	redis_benchmark REDIS_GET get
	cgstat redis_bgsave_start
	vmstat redis_get_end
	vmstat redis_bgsave_start
	valkey-cli bgsave | grep -qx 'Background saving started' || fail bgsave_start
	echo REDIS_BGSAVE_STARTED
	[ "$(valkey-cli info persistence | tr -d '\r' | sed -n 's/^rdb_bgsave_in_progress://p')" = 1 ] || fail bgsave_no_overlap
	echo REDIS_BGSAVE_ACTIVE
	redis_benchmark REDIS_GET_BGSAVE get
	vmstat redis_bgsave_end
	local completed=0
	for i in $(seq 600); do
		[ "$(valkey-cli info persistence | tr -d '\r' | sed -n 's/^rdb_bgsave_in_progress://p')" = 0 ] && { completed=1; break; }
		sleep 0.5
	done
	[ "$completed" = 1 ] && [ -s /tmp/valkey/dump.rdb ] || fail bgsave_incomplete
	echo REDIS_BGSAVE_COMPLETE
	echo "REDIS_BGSAVE_STATUS $(valkey-cli info persistence | tr -d '\r' | sed -n 's/^rdb_last_bgsave_status://p')"
	valkey-cli shutdown nosave >/dev/null 2>&1 || true
}

xswap_counters() {
	echo "XSWAP_BEGIN $1"
	cat /sys/kernel/debug/xswap/type*
	echo "XSWAP_END $1"
}

run_lifetime() {
	[ "$mode" = xswap ] && [ "$backend" = zswap ] || fail lifetime_mode
	local delay=/sys/module/zswap/parameters/debug_wb_delay_ms
	echo "$LIFETIME_ZSWAP_POOL_PERCENT" > /sys/module/zswap/parameters/max_pool_percent
	echo Y > /sys/module/zswap/parameters/shrinker_enabled
	if [ -f $delay ]; then
		echo "$LIFETIME_WB_DELAY_MS" > $delay
		echo "WB_DELAY_MS $(cat $delay)"
	else
		echo "WB_DELAY_MS none"
	fi
	enter_cgroup "$LIFETIME_MEMCG"
	xswap_counters lifetime_start
	vmstat lifetime_start
	churn "$LIFETIME_SIZE" "$LIFETIME_WORKERS" "$LIFETIME_SEC"
	sleep "$SETTLE_SEC"
	vmstat lifetime_end
	xswap_counters lifetime_end
}

run_correctness() {
	[ "$mode" = xswap ] || fail correctness_mode
	case $backend in disk|zswap) ;; *) fail correctness_backend ;; esac
	enter_cgroup max
	local path type
	set -- /sys/kernel/debug/xswap/type*
	[ "$#" -eq 1 ] && [ -f "$1" ] || fail correctness_type
	path=$1 type=${1##*/type}
	vmstat correctness_start
	correctness "$type" || { local status=$?; echo "CORRECTNESS_EXIT $status"; return "$status"; }
	vmstat correctness_end
	[ ! -e "$path" ] || fail correctness_destroy
	[ "$(wc -l < /proc/swaps)" -eq 1 ] || fail correctness_swapoff
	echo EMPTY_SWAPS_PASS
}

run_swapin() {
	enter_cgroup max
	vmstat swapin_start
	[ "$mode" != xswap ] || xswap_counters swapin_start
	swapin "$SWAPIN_SIZE" "$cg/memory.reclaim"
	vmstat swapin_end
	[ "$mode" != xswap ] || xswap_counters swapin_end
}

echo "BENCH_PARAMS backend=$backend mode=$mode workload=$workload ncpu=$(nproc)"
echo PARAMS_BEGIN
cat /opt/bench/params.sh
echo PARAMS_END
echo 0 > /proc/sys/kernel/randomize_va_space
# Fix THP policy explicitly; larger-folio testing needs its own protocol.
if [ -f /sys/kernel/mm/transparent_hugepage/enabled ]; then
	echo never > /sys/kernel/mm/transparent_hugepage/enabled
fi
vmstat before
meminfo before_swapon

if [ "$workload" = metadata ]; then
	[ "$backend" = brd ] || fail metadata_backend
	sleep "$SETTLE_SEC"
	meminfo metadata_before
	setup_swap
	sleep "$SETTLE_SEC"
	meminfo metadata_after
	echo BENCH_WORKLOAD_PASS
	exit 0
fi

setup_swap
meminfo after_swapon
sample_swaps &
sampler=$!
case $workload in
usemem)      run_usemem "" ;;
usemem-rand) run_usemem -R ;;
build)       run_build ;;
redis)       run_redis ;;
swapin)      run_swapin ;;
lifetime)    run_lifetime ;;
correctness) run_correctness ;;
*)           fail workload ;;
esac
sleep 1
kill $sampler
cgstat end
vmstat end
meminfo end
report_swap_peaks
echo BENCH_WORKLOAD_PASS
