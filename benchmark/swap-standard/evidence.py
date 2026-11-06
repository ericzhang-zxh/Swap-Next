# SPDX-License-Identifier: GPL-2.0-only
"""Parse one swap-standard guest serial log into metrics and fail-closed gates."""
import re

DIAGNOSTIC = re.compile(
    r"WARNING:|BUG:|Oops:|Kernel panic|page allocation failure:|Out of memory:|Killed process|UBSAN:|"
    r"KASAN:|KCSAN:|kernel BUG|possible circular locking|INFO: task .*blocked")
# Physical swap devices per backend; the first one must carry the workload.
PHYSICAL = {'zram': ('/dev/zram0', '/dev/zram1'), 'zram-64k': ('/dev/zram0',),
            'zswap': ('/dev/zram1',), 'disk': ('/dev/vda',), 'brd': ('/dev/ram0',)}
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


# Swapon metadata that stays put on /proc/meminfo. MemFree and MemAvailable move
# with unrelated free pages. Slab includes SReclaimable and would double-count
# SUnreclaim. VmallocUsed is the swapon table; a decrease there is not a sample.
ATTRIBUTABLE_FIELDS = ("SUnreclaim", "VmallocUsed", "PageTables", "Percpu")
EXCLUDED_METADATA_FIELDS = ("MemFree", "MemAvailable", "Slab")
SIGNED_METADATA_FIELDS = ("SUnreclaim", "PageTables", "Percpu")


def _protocol_revision(protocol_revision):
    if isinstance(protocol_revision, bool) or not isinstance(protocol_revision, int) or protocol_revision < 1:
        raise ValueError("protocol_revision")
    return protocol_revision


def attributable_kib(delta):
    """Sum the attributable counters. Missing data, a VmallocUsed decrease, or a
    negative sum cannot be scored. The other counters stay signed."""
    if not isinstance(delta, dict):
        raise ValueError("metadata delta missing")
    missing = [name for name in ATTRIBUTABLE_FIELDS if type(delta.get(name)) is not int]
    if missing:
        raise ValueError("metadata attributable counters missing: " + ",".join(missing))
    if delta["VmallocUsed"] < 0:
        raise ValueError("metadata VmallocUsed decreased")
    total = sum(delta[name] for name in ATTRIBUTABLE_FIELDS)
    if total < 0:
        raise ValueError("metadata attributable sum is negative")
    return total


def bytes_per_capacity_slot(used_kib, capacity_kib):
    if type(used_kib) is not int or type(capacity_kib) is not int or capacity_kib <= 0:
        raise ValueError("metadata capacity missing")
    return used_kib * 4096 / capacity_kib


def rescore_metadata_metrics(metrics, protocol_revision):
    """Recompute the scored ratio from a stored meminfo delta. No guest is read.
    Revisions before 7 keep the stored MemAvailable ratio."""
    revision = _protocol_revision(protocol_revision)
    if not isinstance(metrics, dict):
        raise ValueError("metadata metrics missing")
    if revision < 7:
        if "metadata_delta_bytes_per_capacity_slot" not in metrics:
            raise ValueError("missing metadata ratio")
        return metrics
    delta = metrics.get("metadata_delta_kib")
    used = attributable_kib(delta)
    ratio = bytes_per_capacity_slot(used, delta.get("SwapTotal"))
    rescored = dict(metrics)
    new_delta = dict(delta)
    new_delta["used_kib"] = used
    if type(delta.get("MemAvailable")) is int:
        new_delta["memavailable_kib"] = -delta["MemAvailable"]
    rescored["metadata_delta_kib"] = new_delta
    rescored["metadata_delta_bytes_per_capacity_slot"] = ratio
    return rescored


def stats(line):
    return {k: float(v) for k, v in re.findall(r'(\w+)=([\d.]+)', line)}


def thp_policy(text):
    """The selected THP size is always; the global switch and all others are never."""
    m = re.search(r'^THP_BEGIN (\S+)\n(.*?)^THP_END$', text, re.M | re.S)
    if not m:
        return False
    selected = dict(re.findall(r'^(\S+):.*\[(\w+)\]', m.group(2), re.M))
    sizes = {k.split('/')[0][len('hugepages-'):]: v for k, v in selected.items() if k.startswith('hugepages-')}
    return (selected.get('enabled') == 'never' and sizes.get(m.group(1)) == 'always'
            and all(v == 'never' for k, v in sizes.items() if k != m.group(1)))


def swapin_latency(text):
    """kbench memory.swapin_latency buckets ("lo-hi count") per cgstat tag."""
    out = {}
    for tag, body in re.findall(r'^SWAPIN_LATENCY_BEGIN (\S+)\n(.*?)^SWAPIN_LATENCY_END \1$', text, re.M | re.S):
        out[tag] = {f'{lo}-{hi}': int(n) for lo, hi, n in re.findall(r'^(\d+)-(\d+) (\d+)', body, re.M)}
    return out or None


def parse_usemem(text):
    body = block(text, 'USEMEM_BEGIN', 'USEMEM_END') or ''
    tput = [int(x) for x in re.findall(r'bytes / \d+ usecs = (\d+) KB/s', body)]
    free = [int(x) for x in re.findall(r'^(\d+) usecs to free memory', body, re.M)]
    return {'throughput_kbps_sum': sum(tput), 'throughput_kbps': tput, 'nproc': len(tput),
            'free_count': len(free), 'bytes': [int(x) for x in re.findall(r'(\d+) bytes / \d+ usecs = \d+ KB/s', body)], 'free_usec_max': max(free, default=None), 'free_usec_mean': sum(free) / len(free) if free else None}


def correctness_evidence(text, backend, mode):
    """Require the complete trusted workload, live PTEs and backend roundtrip."""
    def once(marker):
        return text.splitlines().count(marker) == 1
    types = re.findall(r'^XSWAP_TYPE (\d+)$', text, re.M)
    kind = int(types[0]) if len(types) == 1 else -1
    headers = re.findall(r'^LATENCY_BEGIN samples=(\d+) skipped=(\d+) minor=(\d+) major=(\d+)$', text, re.M)
    bodies = re.findall(r'^LATENCY_BEGIN [^\n]+\n(.*?)^LATENCY_END$', text, re.M | re.S)
    samples = re.findall(r'^LATENCY_NS (\d+) TYPE (\d+)$', text, re.M)
    valid_samples = (len(headers) == len(bodies) == 1 and 0 <= kind < 32
                     and len(samples) >= 1000 and len(samples) == int(headers[0][0])
                     and sum(map(int, headers[0][:2])) == 16384
                     and len(bodies[0].splitlines()) == len(samples)
                     and all(int(n) > 0 and int(t) == kind for n, t in samples))
    targets = re.findall(r'^FORK_TARGET_XSWAP_PTES 16 TOTAL (\d+)$', text, re.M)
    live = re.findall(r'^DESTROY_LIVE_XSWAP_PTES (\d+)$', text, re.M)
    target_ok = len(targets) == 1 and 1000 <= int(targets[0]) <= 16384
    live_ok = len(live) == 1 and 1000 <= int(live[0]) <= 16384
    physical = re.findall(r'^PHYSICAL_SWAPOFF_LIVE_XSWAP_PTES (\d+) BACKEND_USED_KIB (\d+)$', text, re.M)
    physical_ok = (len(physical) == 1 and 1000 <= int(physical[0][0]) <= 16384
                   and (backend != 'disk' or int(physical[0][1]) > 0)
                   and once('PHYSICAL_SWAPOFF_LIVE_PASS'))
    phases = ('before', 'after_pressure', 'fork_shared', 'after_children', 'after_reads', 'after_settle')
    blocks = re.findall(r'^META_BEGIN (\w+)\n(.*?)^META_END$', text, re.M | re.S)
    fields = {'clusters_max', 'clusters_mapped', 'usage_pages', 'tail_free', 'grows', 'shrinks'}
    snapshots = {}
    snapshots_ok = [phase for phase, body in blocks] == list(phases)
    for phase, body in blocks:
        entries = re.findall(r'^(\w+) (\d+)$', body, re.M)
        values = {k: int(v) for k, v in entries}
        snapshots_ok &= (len(entries) == len(values) == len(body.splitlines())
                         and set(values) == fields
                         and values.get('clusters_mapped', 0) <= values.get('clusters_max', 0))
        snapshots[phase] = values
    counters = [kv_block(text, 'VMSTAT', 'correctness_' + phase) for phase in ('start', 'end')]
    counter_keys = {'pswpin', 'pswpout', 'zswpin', 'zswpout'}
    counters_ok = all(v is not None and counter_keys <= v.keys() for v in counters)
    counters_ok &= all(once('VMSTAT_' + edge + ' correctness_' + phase)
                       for edge in ('BEGIN', 'END') for phase in ('start', 'end'))
    activity = delta(counters[1], counters[0])
    counters_ok &= bool(activity) and all(v >= 0 for v in activity.values())
    route = ('zswpin', 'zswpout') if backend == 'zswap' else ('pswpin', 'pswpout')
    backend_ok = mode == 'xswap' and backend in ('disk', 'zswap') and bool(activity) and all(activity.get(k, 0) > 0 for k in route)
    common = valid_samples and snapshots_ok and counters_ok and backend_ok and 'CORRECTNESS_FAIL' not in text
    gates = {
        'correctness_evidence': common,
        'data_roundtrip': common and once('KERNEL_WORKLOAD_PASS'),
        'fork_cow': common and target_ok and once('COW_PASS') and once('FORK_SHARED_PASS'),
        'concurrent_fault': common and target_ok and once('CONCURRENT_FAULT_PASS workers=48 targets=16'),
        'destroy_live_pages': common and live_ok and once('DESTROY_LIVE_PASS'),
        'swapoff_live_pages': common and live_ok and physical_ok and once('DESTROY_LIVE_PASS') and once('SWAPOFF_LIVE_PASS') and once('EMPTY_SWAPS_PASS'),
    }
    return gates, {'correctness_vmstat_delta': activity, 'correctness_snapshots': snapshots,
                   'correctness_samples': len(samples),
                   'physical_swapoff_live_ptes': int(physical[0][0]) if len(physical) == 1 else None,
                   'physical_swapoff_used_kib': int(physical[0][1]) if len(physical) == 1 else None}


def parse(text, image_sha, backend, mode, workload, protocol_revision=1):
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
        'thp_policy': thp_policy(text),
    }
    metrics['kernel_diagnostics'] = diagnostics[:20]
    metrics['swapin_latency_hist'] = swapin_latency(text)

    if workload == 'metadata':
        before = kv_block(text, 'MEMINFO', 'metadata_before', ':')
        after = kv_block(text, 'MEMINFO', 'metadata_after', ':')
        d = delta(after, before)
        gates['meminfo_present'] = all(v is not None and {'MemAvailable', 'MemFree', 'SwapTotal'} <= v.keys() for v in (before, after))
        gates['swap_capacity'] = bool(after and before and after.get('SwapTotal', 0) - before.get('SwapTotal', 0) == (1 << 30) - 4)
        gates['swap_device'] = '/dev/ram0' in (block(text, 'SWAPS_BEGIN', 'SWAPS_END') or '')
        revision = _protocol_revision(protocol_revision)
        if gates['meminfo_present']:
            capacity_kib = after['SwapTotal'] - before['SwapTotal']
            if revision >= 7:
                present = all(type(side.get(name)) is int for side in (before, after) for name in ATTRIBUTABLE_FIELDS)
                try:
                    if not present:
                        raise ValueError("metadata attributable counters missing")
                    used = attributable_kib(d)
                    ratio = bytes_per_capacity_slot(used, capacity_kib)
                except ValueError:
                    gates['metadata_attributable'] = False
                else:
                    gates['metadata_attributable'] = True
                    d['used_kib'] = used
                    d['memavailable_kib'] = -d['MemAvailable']
                    metrics['metadata_delta_bytes_per_capacity_slot'] = ratio
            else:
                d['used_kib'] = -d.get('MemAvailable', 0)
                metrics['metadata_delta_bytes_per_capacity_slot'] = d['used_kib'] * 4096 / capacity_kib if capacity_kib > 0 else None
            metrics['metadata_delta_kib'] = d
        elif revision >= 7:
            gates['metadata_attributable'] = False
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
        virtual = [v for k, v in peaks.items() if k not in physical]
        gates['swap_routing'] = len(virtual) == 1 and virtual[0] > 0
    else:
        gates['swap_routing'] = peaks.get(physical[0], 0) > 0 and set(peaks) == set(physical)

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
        metrics['swapin_vmstat_delta'] = delta(kv_block(text, 'VMSTAT', 'swapin_end'), kv_block(text, 'VMSTAT', 'swapin_start'))
        gates['swapin_phase_counters'] = bool(metrics['swapin_vmstat_delta']) and all(k in metrics['swapin_vmstat_delta'] for k in ('swap_ra', 'swap_ra_hit'))
        if mode == 'xswap':
            snapshots = {phase: kv_block(text, 'XSWAP', phase) for phase in ('swapin_start', 'swapin_end')}
            metrics['swapin_xswap_snapshots'] = snapshots
            gates['swapin_xswap_counters'] = all(v and {'clusters_mapped', 'usage_pages', 'grows', 'shrinks'} <= v.keys() for v in snapshots.values())

    elif workload == 'correctness':
        extra_gates, extra_metrics = correctness_evidence(text, backend, mode)
        gates.update(extra_gates)
        gates['no_new_kernel_warnings'] = gates['no_kernel_warnings']
        metrics.update(extra_metrics)
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
