# SPDX-License-Identifier: GPL-2.0-only
"""Strict evidence for controlled high-anchor diagnostics, never performance acceptance."""
import re

FIELDS = {'clusters_max', 'clusters_mapped', 'usage_pages', 'tail_free', 'grows', 'shrinks',
          'clusters_nonempty', 'clusters_free', 'highest_nonempty_plus1', 'highest_blocker_plus1',
          'cache_only_pages', 'referenced_pages', 'highest_cache_only_plus1',
          'highest_referenced_plus1', 'cache_only_clusters'}
BOUND_FIELDS = {'clusters_nonempty', 'clusters_free', 'highest_nonempty_plus1',
                'highest_blocker_plus1', 'highest_cache_only_plus1',
                'highest_referenced_plus1', 'cache_only_clusters', 'tail_free'}
PLACEMENT = re.compile(r'PLACEMENT (\w+) cycle=(\d+) swapped=(\d+) total=(\d+) min_cluster=(\d+) max_cluster=(\d+)')


def expected_events():
    events = [('META_BEGIN', 'before')]
    for cycle in range(3):
        events += [('HOLE_CYCLE_BEGIN', str(cycle)), ('PLACEMENT', 'filler_swapout', cycle),
                   ('META_BEGIN', f'cycle{cycle}_filler_swapped')]
        if cycle == 0:
            events += [('PLACEMENT', 'anchor_initial', cycle), ('META_BEGIN', 'anchor_high_placement')]
        else:
            events += [('PLACEMENT', 'anchor_after_filler_swapout', cycle)]
        events += [('FILLER_DATA_PASS', str(cycle)), ('META_BEGIN', f'cycle{cycle}_after_unmap'),
                   ('PLACEMENT', 'anchor_after_unmap', cycle),
                   ('META_BEGIN', f'cycle{cycle}_after_settle'),
                   ('PLACEMENT', 'anchor_after_settle', cycle), ('HOLE_CYCLE_PASS', str(cycle))]
    return events + [('ANCHOR_DATA_PASS',), ('COW_PASS',),
                     ('PLACEMENT', 'anchor_before_destroy', 3), ('DESTROY_LIVE_XSWAP_PTES',),
                     ('DESTROY_LIVE_PASS',), ('SWAPOFF_LIVE_PASS',), ('KERNEL_WORKLOAD_PASS',)]


def parse(log, expected_image, backend):
    log = log.replace('\r\n', '\n')
    lines, errors, snapshots, placements, events = log.splitlines(), [], {}, [], []
    def once(marker):
        return lines.count(marker) == 1
    blocks = list(re.finditer(r'^META_BEGIN (\w+)\n(.*?)^META_END$', log, re.M | re.S))
    for match in blocks:
        phase, body = match.groups()
        pairs = re.findall(r'^(\w+) ([0-9]+)$', body, re.M)
        values = {k: int(v) for k, v in pairs}
        if phase in snapshots or set(values) != FIELDS or len(pairs) != len(values) or len(body.splitlines()) != len(pairs):
            errors.append('invalid snapshot ' + phase)
        mapped = values.get('clusters_mapped', 0)
        if mapped > values.get('clusters_max', 0) or any(values.get(k, 0) > mapped for k in BOUND_FIELDS):
            errors.append('snapshot bounds ' + phase)
        snapshots[phase] = values
    if lines.count('META_END') != len(blocks):
        errors.append('unmatched metadata terminator')
    expected = expected_events()
    prefixes = {event[0] for event in expected}
    for line in lines:
        prefix = line.split(' ', 1)[0]
        if prefix not in prefixes:
            continue
        if prefix == 'PLACEMENT':
            match = PLACEMENT.fullmatch(line)
            if not match:
                errors.append('malformed placement')
                continue
            label = match[1]
            cycle, swapped, total, low, high = map(int, match.groups()[1:])
            row = dict(label=label, cycle=cycle, swapped=swapped, total=total,
                       min_cluster=low, max_cluster=high)
            placements.append(row)
            events.append((prefix, label, cycle))
            if not (0 < swapped <= total and low <= high < 8192):
                errors.append('placement bounds')
            if label == 'filler_swapout':
                if total != 262144 or swapped < 196608:
                    errors.append('filler pageout prerequisite')
            elif total != 16384 or (label != 'anchor_before_destroy' and (swapped < 1000 or low < 512)):
                errors.append('high anchor prerequisite')
        elif prefix == 'DESTROY_LIVE_XSWAP_PTES':
            events.append((prefix,))
        else:
            events.append(tuple(line.split(' ')))
    if events != expected:
        errors.append('missing, duplicate, malformed or out-of-order workload events')
    wanted_phases = [event[1] for event in expected if event[0] == 'META_BEGIN']
    if [m[1] for m in blocks] != wanted_phases:
        errors.append('snapshot sequence mismatch')
    types = re.findall(r'^XSWAP_TYPE ([0-9]+)$', log, re.M)
    swap_type = int(types[0]) if len(types) == 1 else None
    if swap_type is None or not 0 <= swap_type < 32 or sum(line.startswith('XSWAP_TYPE') for line in lines) != 1:
        errors.append('invalid xswap type')
    counts, disks = [], []
    for phase in ('BEFORE', 'AFTER'):
        matches = re.findall(r'^VMSTAT_' + phase + r'\n((?:(?:pswpin|pswpout|zswpin|zswpout) [0-9]+\n)+)', log, re.M)
        entries = re.findall(r'(\w+) ([0-9]+)', matches[0]) if len(matches) == 1 else []
        values = {k: int(v) for k, v in entries}
        if set(values) != {'pswpin', 'pswpout', 'zswpin', 'zswpout'} or len(entries) != 4 or not once('VMSTAT_' + phase):
            errors.append('invalid vmstat ' + phase)
        counts.append(values)
        matches = re.findall(r'^DISKSTAT_' + phase + r'\n([ 0-9]+)$', log, re.M)
        values = [int(v) for v in matches[0].split()] if len(matches) == 1 else []
        if len(values) < 11 or not once('DISKSTAT_' + phase):
            errors.append('invalid diskstat ' + phase)
            values = [0] * 11
        disks.append(values)
    delta = {k: counts[1].get(k, 0) - v for k, v in counts[0].items()}
    disk_delta = dict(sectors_read=disks[1][2]-disks[0][2], sectors_written=disks[1][6]-disks[0][6])
    if any(v < 0 for v in list(delta.values()) + list(disk_delta.values())):
        errors.append('decreasing activity counter')
    cmd = re.findall(r'^CMDLINE_BEGIN\n([^\n]+)\nCMDLINE_END$', log, re.M)
    image = re.findall(r'(?:^| )evolve.image_sha=([0-9a-f]{64})(?= |$)', cmd[0]) if len(cmd) == 1 else []
    backends = re.findall(r'(?:^| )evolve.backend=(\w+)(?= |$)', cmd[0]) if len(cmd) == 1 else []
    cmd_valid = (once('CMDLINE_BEGIN') and once('CMDLINE_END') and image == [expected_image]
                 and backends == [backend] and cmd[0].count('evolve.image_sha=') == 1
                 and cmd[0].count('evolve.backend=') == 1)
    bootids = re.findall(r'^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$', log, re.M)
    diagnostics = [line for line in lines if re.search(r'WARNING:|BUG:|Oops:|Kernel panic|page allocation failure:|Out of memory:|Killed process|UBSAN:|KASAN:|KCSAN:|kernel BUG|possible circular locking|INFO: task .*blocked', line)]
    swaps = re.findall(r'^SWAPS_BEGIN\n(.*?)^SWAPS_END$', log, re.M | re.S)
    empty = len(swaps) == 1 and len(swaps[0].splitlines()) == 1 and swaps[0].startswith('Filename')
    kernel_logs = re.findall(r'^KERNEL_LOG_BEGIN\n(.*?)^KERNEL_LOG_END$', log, re.M | re.S)
    live = re.findall(r'^DESTROY_LIVE_XSWAP_PTES ([0-9]+)$', log, re.M)
    final_placement = [p for p in placements if p['label'] == 'anchor_before_destroy']
    live_valid = (len(live) == len(final_placement) == 1 and 0 < int(live[0]) <= 16384
                  and int(live[0]) == final_placement[0]['swapped'])
    system_order = ['XSWAP_BOOT', 'CMDLINE_BEGIN', 'CMDLINE_END', 'XSWAP_RUNTIME_PASS',
                    'VMSTAT_BEFORE', 'DISKSTAT_BEFORE', 'META_BEGIN before', 'KERNEL_WORKLOAD_PASS',
                    'VMSTAT_AFTER', 'DISKSTAT_AFTER', 'EMPTY_SWAPS_PASS', 'SWAPS_BEGIN', 'SWAPS_END',
                    'KERNEL_LOG_BEGIN', 'KERNEL_LOG_END', 'XSWAP_PASS']
    if not all(once(marker) for marker in system_order) or [lines.index(marker) for marker in system_order if marker in lines] != sorted(lines.index(marker) for marker in system_order if marker in lines):
        errors.append('system evidence sequence mismatch')
    backend_valid = ((backend == 'disk' and all(delta.get(k, -1) == 0 for k in ('zswpin', 'zswpout'))
                      and all(v > 0 for v in disk_delta.values())) or
                     (backend == 'zswap' and all(delta.get(k, 0) > 0 for k in ('zswpin', 'zswpout'))))
    gates = dict(evidence_complete=not errors, placement_prerequisites=not errors,
                 data_roundtrip=once('KERNEL_WORKLOAD_PASS'), anchor_data=once('ANCHOR_DATA_PASS'),
                 resident_cow=once('COW_PASS'), destroy_live_data=once('DESTROY_LIVE_PASS') and live_valid,
                 backend_teardown_data=once('SWAPOFF_LIVE_PASS'),
                 empty_swaps=empty and once('EMPTY_SWAPS_PASS') and once('SWAPS_BEGIN') and once('SWAPS_END'),
                 runtime_xswap=once('XSWAP_RUNTIME_PASS'), boot_identity=len(bootids) == 1 and once('XSWAP_BOOT'),
                 image_identity=bool(re.fullmatch('[0-9a-f]{64}', expected_image)) and cmd_valid,
                 swap_activity=delta.get('pswpin', 0) > 0 and delta.get('pswpout', 0) > 0,
                 backend_exercised=backend_valid, no_kernel_warnings=not diagnostics,
                 kernel_log_complete=len(kernel_logs) == 1 and bool(kernel_logs[0].strip()) and once('KERNEL_LOG_BEGIN') and once('KERNEL_LOG_END'),
                 completed=once('XSWAP_PASS') and 'XSWAP_FAIL' not in log)
    topology = {phase: dict(clusters_free=values['clusters_free'], tail_free=values['tail_free'],
                           interior_free_estimate=values['clusters_free']-values['tail_free'])
                for phase, values in snapshots.items() if FIELDS <= set(values)}
    return dict(gates=gates, snapshots=snapshots, placements=placements, topology=topology,
                topology_limit='Rolling scan difference, descriptive estimate only; placement success is not a topology verdict.',
                swap_delta=delta, disk_delta=disk_delta, diagnostics=diagnostics, evidence_errors=errors,
                boot_id=bootids[0] if len(bootids) == 1 else None, xswap_type=swap_type,
                performance_accepted=False, auto_promote=False)
