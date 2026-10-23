# SPDX-License-Identifier: GPL-2.0-only
"""Parse one swap-standard guest serial log into metrics and fail-closed gates."""
import re

DIAGNOSTIC = re.compile(
    r"WARNING:|BUG:|Oops:|Kernel panic|page allocation failure:|Out of memory:|Killed process|UBSAN:|"
    r"KASAN:|KCSAN:|kernel BUG|possible circular locking|INFO: task .*blocked")
PHYSICAL = {'zram': '/dev/zram0', 'zswap': '/dev/vda', 'disk': '/dev/vda', 'brd': '/dev/ram0'}
SWAP_EVENTS = ('pswpout', 'zswpout')


def block(text, begin, end):
    match = re.search(re.escape(begin) + r'\n(.*?)\n' + re.escape(end), text, re.S)
    return match.group(1) if match else None


def kv_block(text, kind, tag, sep=None):
    body = block(text, f'{kind}_BEGIN {tag}', f'{kind}_END {tag}')
    if body is None:
        return None
    out = {}
    for line in body.splitlines():
        parts = line.replace(':', ' ', 1).split() if sep == ':' else line.split()
        if len(parts) >= 2 and re.fullmatch(r'-?\d+', parts[1]):
            out[parts[0]] = int(parts[1])
    return out


def delta(after, before, keys=None):
    if after is None or before is None:
        return None
    keys = keys or after.keys()
    return {k: after.get(k, 0) - before.get(k, 0) for k in keys}


def stats(line):
    return {k: float(v) for k, v in re.findall(r'(\w+)=([\d.]+)', line)}


def parse_usemem(text):
    body = block(text, 'USEMEM_BEGIN', 'USEMEM_END') or ''
    tput = [int(x) for x in re.findall(r'bytes / \d+ usecs = (\d+) KB/s', body)]
    free = [int(x) for x in re.findall(r'^(\d+) usecs to free memory', body, re.M)]
    return {'throughput_kbps_sum': sum(tput), 'throughput_kbps': tput, 'nproc': len(tput),
            'free_count': len(free), 'bytes': [int(x) for x in re.findall(r'(\d+) bytes / \d+ usecs = \d+ KB/s', body)], 'free_usec_max': max(free, default=None), 'free_usec_mean': sum(free) / len(free) if free else None}


def parse(text, image_sha, backend, mode, workload):
    text = text.replace('\r', '')
    log = block(text, 'KERNEL_LOG_BEGIN', 'KERNEL_LOG_END') or ''
    cmdline = block(text, 'CMDLINE_BEGIN', 'CMDLINE_END') or ''
    words = set(cmdline.split())
    diagnostics = list(dict.fromkeys(line for line in text.splitlines() if DIAGNOSTIC.search(line)))
    vm_before, vm_end = kv_block(text, 'VMSTAT', 'before'), kv_block(text, 'VMSTAT', 'end')
    metrics = {'vmstat_delta': delta(vm_end, vm_before)}
    gates = {
        'boot': 'BENCH_BOOT' in text,
        'cmdline_identity': {f'bench.image_sha={image_sha}', f'bench.backend={backend}',
                             f'bench.mode={mode}', f'bench.workload={workload}'} <= words,
        'workload_complete': 'BENCH_WORKLOAD_PASS' in text and 'BENCH_PASS' in text and 'BENCH_FAIL' not in text,
        'kernel_log_present': bool(log),
        'no_kernel_warnings': bool(log) and not diagnostics,
    }
    metrics['kernel_diagnostics'] = diagnostics[:20]

    if workload == 'metadata':
        before = kv_block(text, 'MEMINFO', 'metadata_before', ':')
        after = kv_block(text, 'MEMINFO', 'metadata_after', ':')
        d = delta(after, before)
        gates['meminfo_present'] = all(v is not None and {'MemAvailable', 'MemFree', 'SwapTotal'} <= v.keys() for v in (before, after))
        gates['swap_capacity'] = bool(after and before and after.get('SwapTotal', 0) - before.get('SwapTotal', 0) == (1 << 30) - 4)
        gates['swap_device'] = '/dev/ram0' in (block(text, 'SWAPS_BEGIN', 'SWAPS_END') or '')
        if gates['meminfo_present']:
            d['used_kib'] = -d.get('MemAvailable', 0)
            metrics['metadata_delta_kib'] = d
            capacity_kib = after['SwapTotal'] - before['SwapTotal']
            metrics['metadata_delta_bytes_per_capacity_slot'] = d['used_kib'] * 4096 / capacity_kib if capacity_kib > 0 else None
        metrics['swap_total_kib'] = (after or {}).get('SwapTotal')
        return dict(metrics=metrics, gates=gates)

    swapped = metrics['vmstat_delta'] and sum(metrics['vmstat_delta'].get(k, 0) for k in SWAP_EVENTS)
    gates['swap_activity'] = bool(swapped and swapped > 0)
    activity = metrics['vmstat_delta'] or {}
    gates['backend_exercised'] = (activity.get('zswpout', 0) > 0 and 'ZSWAP_ENABLED Y' in text
                                 if backend == 'zswap' else
                                 activity.get('zswpout', 0) == 0 and 'ZSWAP_ENABLED N' in text)

    peaks = {}
    for line in (block(text, 'SWAP_PEAK_BEGIN', 'SWAP_PEAK_END') or '').splitlines():
        name, used = line.split()
        peaks[name] = int(used)
    metrics['swap_peak_kib'] = peaks
    physical = PHYSICAL[backend]
    if mode == 'xswap':
        virtual = [v for k, v in peaks.items() if k != physical]
        gates['swap_routing'] = len(virtual) == 1 and virtual[0] > 0
    else:
        gates['swap_routing'] = peaks.get(physical, 0) > 0 and len(peaks) == 1

    cg_end = kv_block(text, 'CGSTAT', 'end')
    if workload in ('usemem', 'usemem-rand'):
        metrics.update(parse_usemem(text))
        # Pinned usemem do_unit accounts allocation as bytes/8, plus one full pass.
        expected = re.search(r'^USEMEM_EXPECT nproc=(\d+) bytes_per_worker=(\d+)$', text, re.M)
        gates['usemem_output'] = bool(expected) and metrics['nproc'] == int(expected[1]) and metrics['free_count'] == int(expected[1]) and all(n == int(expected[2]) * 9 // 8 for n in metrics['bytes'])
        if cg_end:
            metrics['cg_system_usec'], metrics['cg_user_usec'] = cg_end.get('system_usec'), cg_end.get('user_usec')
    elif workload == 'build':
        real = re.search(r'^BUILD_REAL_USEC (\d+)', text, re.M)
        d = delta(cg_end, kv_block(text, 'CGSTAT', 'build_start'), ('system_usec', 'user_usec', 'usage_usec'))
        gates['build_output'] = bool(real) and d is not None
        metrics['build_real_usec'] = int(real.group(1)) if real else None
        if d:
            metrics['build_system_usec'], metrics['build_user_usec'] = d['system_usec'], d['user_usec']
    elif workload == 'redis':
        for key in ('REDIS_FILL', 'REDIS_GET', 'REDIS_GET_BGSAVE'):
            m = re.search(rf'^{key} \S+: ([\d.]+) requests per second', text, re.M)
            metrics[key.lower() + '_rps'] = float(m.group(1)) if m else None
        status = re.search(r'^REDIS_BGSAVE_STATUS (\S+)', text, re.M)
        gates['redis_output'] = metrics['redis_get_rps'] is not None and metrics['redis_get_bgsave_rps'] is not None
        gates['redis_bgsave_ok'] = bool(status) and status.group(1) == 'ok' and 'REDIS_BGSAVE_STARTED' in text and 'REDIS_BGSAVE_COMPLETE' in text and 'REDIS_BGSAVE_ACTIVE' in text
        gates['redis_fill'] = bool(metrics['redis_fill_rps']) and bool(re.search(r'^REDIS_DBSIZE [1-9][0-9]*$', text, re.M))
    elif workload == 'swapin':
        for key in ('SWAPIN_SEQ', 'SWAPIN_RAND'):
            m = re.search(rf'^{key} (.*)$', text, re.M)
            metrics[key.lower()] = stats(m.group(1)) if m else None
        m = re.search(r'^SWAPIN_SWAPPED (.*)$', text, re.M)
        metrics['swapin_swapped'] = stats(m.group(1)) if m else None
        gates['swapin_data'] = 'SWAPIN_DATA_PASS' in text
        gates['swapin_output'] = all(metrics[k] and metrics[k].get('samples', 0) > 0 for k in ('swapin_seq', 'swapin_rand'))
    elif workload == 'lifetime':
        churn = re.search(r'^CHURN_PASS rounds=(\d+) workers=(\d+) bytes=(\d+) verified_workers=(\d+)$', text, re.M)
        xs = delta(kv_block(text, 'XSWAP', 'lifetime_end'), kv_block(text, 'XSWAP', 'lifetime_start'), ('grows', 'shrinks'))
        wb = delta(kv_block(text, 'VMSTAT', 'lifetime_end'), kv_block(text, 'VMSTAT', 'lifetime_start'), ('zswpwb', 'pswpout', 'zswpout'))
        delay = re.search(r'^WB_DELAY_MS (\S+)$', text, re.M)
        metrics.update(lifetime_rounds=int(churn[1]) if churn else None,
                       lifetime_verified_workers=int(churn[4]) if churn else None,
                       lifetime_xswap_delta=xs, lifetime_vmstat_delta=wb,
                       wb_delay_ms=delay[1] if delay else None)
        gates['lifetime_data'] = bool(churn) and int(churn[1]) >= 3 and 'CHURN_MISMATCH' not in text and 'CHURN_FAIL' not in text
        gates['lifetime_shrink'] = bool(xs) and xs['shrinks'] > 0 and xs['grows'] > 0
        gates['lifetime_writeback'] = bool(wb) and wb['zswpwb'] > 0
    else:
        gates['known_workload'] = False
    phases = ['build'] if workload == 'build' else ['redis_get', 'redis_bgsave'] if workload == 'redis' else []
    for phase in phases:
        change = delta(kv_block(text, 'VMSTAT', phase + '_end'), kv_block(text, 'VMSTAT', phase + '_start'))
        metrics[phase + '_vmstat_delta'] = change
        gates[phase + '_swap_activity'] = bool(change and sum(change.get(k, 0) for k in ('pswpin', 'pswpout', 'zswpin', 'zswpout')) > 0)
    return dict(metrics=metrics, gates=gates)
