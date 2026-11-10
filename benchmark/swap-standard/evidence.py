# SPDX-License-Identifier: GPL-2.0-only
"""Parse one swap-standard guest serial log into metrics and fail-closed gates."""
import re
import math
import importlib.util
from pathlib import Path

DIAGNOSTIC = re.compile(
    r"WARNING:|BUG:|Oops:|Kernel panic|page allocation failure:|Out of memory:|Killed process|UBSAN:|"
    r"KASAN:|KCSAN:|kernel BUG|possible circular locking|INFO: task .*blocked")
# Physical swap devices per backend; the first one must carry the workload.
PHYSICAL = {'zram': ('/dev/zram0', '/dev/zram1'), 'zram-64k': ('/dev/zram0',),
            'zswap': ('/dev/zram1',), 'disk': ('/dev/vda',), 'brd': ('/dev/ram0',), 'compressed': ()}
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
    route = ('zswpin', 'zswpout') if backend in ('zswap', 'compressed') else ('pswpin', 'pswpout')
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



COMPRESSED_OBSERVER = 'pid_kretprobe_zswap_load_v1'
COMPRESSED_TARGET_BYTES = 134217728


def configuration_catalog():
    path = Path(__file__).resolve().with_name('configurations.py')
    spec = importlib.util.spec_from_file_location('swap_standard_bound_configurations', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configuration_groups():
    return configuration_catalog().GROUPS


UNIT_TESTS = ('page_compress_alloc_rollback', 'page_compress_partial_cleanup',
              'page_compress_numa_placement')


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def exactly(text, pattern):
    matches = re.findall(pattern, text, re.M)
    require(len(matches) == 1, 'missing or duplicate evidence: ' + pattern)
    return matches[0]


def _valid_ktap(raw):
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    require(not any(re.search(r'\b(?:SKIP|TODO)\b', line, re.I) for line in lines),
            'KUnit skip or TODO is incomplete coverage')
    lines = [line for line in lines if not line.startswith('#') or line.startswith('# Subtest:')]
    expected = ['KTAP version 1', '1..1', 'KTAP version 1', '# Subtest: page_compress', '1..3',
                *[f'ok {i + 1} {name}' for i, name in enumerate(UNIT_TESTS)], 'ok 1 page_compress']
    return lines == expected



def numa_ktap_observations(raw, topology_id):
    """Read only the fixed diagnostic comments inside the already validated KTAP."""
    placements, totals = [], []
    for line in raw.splitlines():
        if 'PAGE_COMPRESS_NUMA' not in line:
            continue
        placement = re.fullmatch(r'\s*#\s*(?:.*?\s)?PAGE_COMPRESS_NUMA requested=(\d+) actual=(\d+) pages=(\d+)\s*', line)
        total = re.fullmatch(r'\s*#\s*(?:.*?\s)?PAGE_COMPRESS_NUMA_TOTAL nodes=(\d+) placements=(\d+) mismatches=(\d+)\s*', line)
        require(bool(placement or total), 'malformed KUnit NUMA observation')
        if placement:
            requested, actual, pages = map(int, placement.groups())
            require(requested == actual and pages > 0, 'KUnit NUMA placement mismatch or empty allocation')
            placements.append({'requested': requested, 'actual': actual, 'pages': pages})
        else:
            totals.append(tuple(map(int, total.groups())))
    expected_nodes = {0, 1} if topology_id == 'numa2' else {0}
    observed_nodes = {entry['requested'] for entry in placements}
    require(observed_nodes == expected_nodes and len(totals) == 1, 'missing required per-node KUnit observations')
    require(totals[0] == (len(expected_nodes), len(placements), 0) and len(placements) >= len(expected_nodes),
            'KUnit NUMA totals differ from observed placements')
    return {'placements': placements, 'nodes': totals[0][0], 'placement_count': totals[0][1], 'mismatches': 0}

def _compression_case_observations(record, mode, target_type, topology_id):
    """Derive a PASS from raw state; marker assertions alone never suffice."""
    name, obs, size = record['id'], record['observations'], record['bytes']
    pages = size // 4096

    def value(phase, key):
        result = obs.get(phase, {}).get(key)
        require(type(result) is int and result >= 0, f'{name}: missing {phase}.{key}')
        return result

    def equals(phase, key, expected):
        require(value(phase, key) == expected, f'{name}: inconsistent {phase}.{key}')

    def topology(phase):
        for key, expected in {'swap_devices': 1, 'virtual_devices': int(mode == 'xswap'),
                              'physical_devices': int(mode == 'plain'), 'no_backing': int(mode == 'xswap'),
                              'intended_device_matches': 1}.items():
            equals(phase, key, expected)
        if mode == 'xswap':
            equals(phase, 'xswap_priority', 32767)

    def snapshot(phase, memcg):
        for key in ('stored_pages', 'pool_bytes', 'incompressible_pages', 'zswpin',
                    'zswpout', 'pswpin', 'pswpout'):
            value(phase, key)
        equals(phase, 'memcg_present', int(memcg))
        if memcg:
            value(phase, 'memcg_zswap_bytes')
            value(phase, 'memcg_zswapped_bytes')
        else:
            require(not any(k in obs.get(phase, {}) for k in ('memcg_zswap_bytes', 'memcg_zswapped_bytes')),
                    name + ': removed memcg evidence fabricated')

    def residency(phase, compressed=True):
        equals(phase, 'target_pages', pages)
        swapped, absent = value(phase, 'swapped_pages'), value(phase, 'absent_swapcache_pages')
        require(0 <= absent <= swapped <= pages, name + ': invalid residency')
        if compressed:
            require(absent * 10 >= pages * 9, name + ': compressed residency below required coverage')
            kind = value(phase, 'target_type')
            require(kind < 32 and (mode != 'xswap' or kind == target_type), name + ': wrong target type')

    topology('before')
    if name == 'library_unit':
        require(record['untouched'] and _valid_ktap(record['ktap']), 'invalid complete KUnit result')
        record['numa_observations'] = numa_ktap_observations(record['ktap'], topology_id)
        for key, expected in {'kunit_expected': 3, 'kunit_observed': 3,
                              'kunit_failed': 0, 'kunit_skipped': 0,
                              **{test: 1 for test in UNIT_TESTS}}.items():
            equals('case', key, expected)
        return
    require(not record['untouched'] and not record['ktap'], name + ': invalid untouched or KUnit record')
    require(record['codec'] is not None, name + ': runtime codec absent')
    equals('configuration', 'zswap_enabled', 1)
    equals('configuration', 'shrinker_enabled', 0)
    equals('fixture', 'isolated_memcg', 1)
    snapshot('before', True)
    equals('before', 'memcg_zswap_bytes', 0)
    equals('before', 'memcg_zswapped_bytes', 0)
    topology('reset')
    equals('reset', 'objects_and_charges_drained', 1)
    equals('reset', 'temporary_memcg_removed', 1)
    offline = name == 'memcg_offline'
    snapshot('decoded', not offline)
    snapshot('cleanup', not offline)
    equals('cleanup', 'stored_pages', value('before', 'stored_pages'))
    require(value('cleanup', 'pool_bytes') <= value('before', 'pool_bytes'), name + ': backing pages retained')
    if not offline:
        equals('cleanup', 'memcg_zswap_bytes', 0)
        equals('cleanup', 'memcg_zswapped_bytes', 0)
    copies = 2 if name in ('codec_switch', 'guest_hotplug') else 1
    equals('decoded', 'verified_words', copies * size // 8)
    equals('mapping_a', 'nonzero_pages', pages)
    if copies == 2:
        equals('mapping_b', 'nonzero_pages', pages)

    if name == 'memcg_limits':
        equals('case', 'zswap_quota_bytes', 0)
        equals('case', 'quota_pageout_attempts', 4)
        equals('case', 'quota_data_verified', 1)
        snapshot('quota', True)
        residency('quota', compressed=False)
        for phase in ('quota', 'decoded'):
            equals(phase, 'memcg_zswap_bytes', 0)
            equals(phase, 'memcg_zswapped_bytes', 0)
        for key in ('zswpout', 'stored_pages'):
            equals('quota', key, value('before', key))
        if mode == 'xswap':
            equals('quota', 'swapped_pages', 0)
            equals('quota', 'pswpout', value('before', 'pswpout'))
        return

    phases = ('stored_old', 'stored_new') if copies == 2 else ('stored_a',)
    for phase in phases:
        residency(phase)
    snapshot('stored', True)
    require(value('stored', 'stored_pages') > value('before', 'stored_pages') and
            value('stored', 'zswpout') > value('before', 'zswpout') and
            value('stored', 'memcg_zswap_bytes') > 0 and value('stored', 'memcg_zswapped_bytes') > 0,
            name + ': compressed store or charge unobserved')
    require(value('decoded', 'zswpin') > value('before', 'zswpin'), name + ': decoder traffic unobserved')
    for phase in ('stored', 'decoded'):
        equals(phase, 'incompressible_pages', value('before', 'incompressible_pages'))
        equals(phase, 'pswpin', value('before', 'pswpin'))
        equals(phase, 'pswpout', value('before', 'pswpout'))
    one = {
        'codec_switch': ('codec_switched', 'old_and_new_data_verified'),
        'invalid_codec': ('codec_unchanged',),
        'concurrent_fault': ('cow_parent_verified',),
        'live_destroy': ('destroy_observed', 'concurrent_destroy_reader_verified', 'original_type_recreated'),
        'memcg_offline': ('live_memcg_removed',),
        'guest_hotplug': ('cpu_offline_observed', 'cpu_online_observed'),
    }
    for key in one.get(name, ()):
        equals('case', key, 1)
    if name == 'codec_switch':
        residency('old_after_switch')
        snapshot('old_pool', True)
    if name in ('codec_switch', 'invalid_codec'):
        equals('reset', 'codec_restored', 1)
    if name == 'invalid_codec':
        require(value('case', 'invalid_codec_errno') in (2, 22), 'invalid codec was not semantically rejected')
    if name == 'concurrent_fault':
        for key, expected in {'workers': 8, 'concurrent_target_pages': 32, 'concurrent_absent_swapcache_pages': 32}.items():
            equals('case', key, expected)
    if name == 'live_destroy':
        require(value('case', 'destroy_live_swapped_pages') > 0, 'live destroy had no live targets')
    if offline:
        require(value('case', 'offline_live_compressed_bytes') > 0, 'memcg offlined without live charges')
    if name == 'guest_hotplug':
        require(0 < value('case', 'target_cpu') < 4, 'invalid guest hotplug target')
        equals('reset', 'cpu_restored', 1)
    if name == 'large_folio':
        equals('case', 'huge_input_bytes', size)
        require(value('case', 'large_zswpout_after') > value('case', 'large_zswpout_before'),
                'no observed large-folio store')


def compression_evidence(text, mode, expected_case):
    """Strict ordered records. Enclosed KTAP is opaque to control-record parsing."""
    GROUPS = configuration_groups()
    group = expected_case.get('group') if isinstance(expected_case, dict) else None
    require(group in GROUPS and GROUPS[group]['workload'] == 'compression', 'unknown compression group')
    expected = GROUPS[group]['subcases']
    require(expected_case.get('subcases') == expected, 'compression subcases differ from trusted catalog')
    begin, end = 'COMPRESSION_GROUP_BEGIN ' + group, 'COMPRESSION_GROUP_END ' + group
    require(text.splitlines().count(begin) == text.splitlines().count(end) == 1, 'incomplete compression group')
    prefix, rest = text.split(begin + '\n', 1)
    body, suffix = rest.split('\n' + end, 1)
    require(not re.search(r'^COMPRESS(?:ION)?_', prefix + suffix, re.M), 'compression record outside group')
    records, current, state, raw, in_ktap = [], None, 'begin', [], False
    for line in body.splitlines():
        if in_ktap:
            if line == 'COMPRESS_KTAP_END suite=page_compress':
                current['ktap'] = '\n'.join(raw) + '\n'
                in_ktap = False
            else:
                raw.append(line)
            continue
        m = re.fullmatch(r'COMPRESS_BEGIN schema=1 mode=(xswap|plain) case=([a-z][a-z0-9_]*) bytes=(\d+)', line)
        if m:
            require(state == 'begin' and len(records) < len(expected), 'duplicate or misplaced compression begin')
            require(m[1] == mode and m[2] == expected[len(records)] and int(m[3]) == 33554432,
                    'compression invocation differs from frozen case')
            current = {'id': m[2], 'bytes': int(m[3]), 'observations': {}, 'codec': None,
                       'ktap': '', 'untouched': False}
            state = 'observations'
            continue
        require(current is not None, 'compression record before begin')
        m = re.fullmatch(r'COMPRESS_OBS case=([a-z][a-z0-9_]*) phase=([a-z][a-z0-9_]*) key=([a-z][a-z0-9_]*) value=(\d+)', line)
        if m:
            require(state == 'observations' and m[1] == current['id'], 'observation case or order mismatch')
            phase = current['observations'].setdefault(m[2], {})
            require(m[3] not in phase, 'duplicate compression observation')
            phase[m[3]] = int(m[4])
            continue
        m = re.fullmatch(r'COMPRESS_CONFIG case=([a-z][a-z0-9_]*) codec=([A-Za-z0-9_-]+)', line)
        if m:
            require(state == 'observations' and m[1] == current['id'] and current['codec'] is None,
                    'duplicate or misplaced runtime codec')
            current['codec'] = m[2]
            continue
        if line == 'COMPRESS_KTAP_BEGIN suite=page_compress':
            require(state == 'observations' and current['id'] == 'library_unit' and not current['ktap'],
                    'duplicate or misplaced KUnit body')
            in_ktap, raw = True, []
            continue
        m = re.fullmatch(r'COMPRESS_RESET case=([a-z][a-z0-9_]*) status=(PASS|FAIL)( untouched=1)?', line)
        if m:
            require(state == 'observations' and m[1] == current['id'], 'reset order or case mismatch')
            current.update(reset=m[2] == 'PASS', untouched=bool(m[3]))
            state = 'case'
            continue
        m = re.fullmatch(r'COMPRESS_CASE case=([a-z][a-z0-9_]*) status=(PASS|FAIL|INCOMPLETE) reason=([a-z][a-z0-9_]*)', line)
        if m:
            require(state == 'case' and m[1] == current['id'], 'case outcome order or identity mismatch')
            require(m[2] != 'PASS' or (current['reset'] and m[3] == 'ok'), 'contradictory case pass')
            current.update(status=m[2], reason=m[3])
            state = 'end'
            continue
        m = re.fullmatch(r'COMPRESS_END schema=1 status=(PASS|FAIL|INCOMPLETE) cases=1', line)
        if m:
            require(state == 'end' and m[1] == current['status'], 'inconsistent compression end')
            records.append(current)
            current, state = None, 'begin'
            continue
        raise ValueError('unknown compression record: ' + line[:120])
    require(not in_ktap and state == 'begin' and len(records) == len(expected), 'truncated compression records')
    kind = int(exactly(text, r'^XSWAP_TYPE (\d+)$')) if mode == 'xswap' else None
    gates, results = {}, {}
    for record in records:
        valid = record['status'] == 'PASS' and record['reset']
        if valid:
            try:
                _compression_case_observations(record, mode, kind, expected_case["topology_id"])
            except ValueError as exc:
                valid = False
                record['evidence_error'] = str(exc)
        name = record.pop('id')
        record['evidence_valid'] = valid
        gates['compression_' + name] = valid
        results[name] = record
    gates['compression_evidence'] = all(gates.values())
    gates['compression_reset'] = all(record['reset'] for record in records)
    return gates, results



def complete_counter_block(text, kind, tag, required):
    begin, end = f'{kind}_BEGIN {tag}', f'{kind}_END {tag}'
    if text.splitlines().count(begin) != 1 or text.splitlines().count(end) != 1:
        return False
    body = block(text, begin, end)
    if body is None:
        return False
    entries = re.findall(r'^(\w+) (\d+)$', body, re.M)
    return (len(entries) == len(body.splitlines()) == len({key for key, value in entries})
            and set(required) <= {key for key, value in entries})

def compressed_timing_evidence(text, metrics):
    observer = exactly(text, r'^COMPRESSED_OBSERVER id=(\S+) instrumented=(\d+) clock=(\S+) maxactive=(\d+)$')
    observer_ok = observer == (COMPRESSED_OBSERVER, '1', 'monotonic_raw', '64')
    types = re.findall(r'^XSWAP_TYPE (\d+)$', text, re.M)
    topology = re.findall(r'^COMPRESSED_TOPOLOGY phase=(before|after) devices=(\d+) physical=(\d+) type=(\d+)$', text, re.M)
    topology_ok = len(types) == 1 and topology == [('before', '1', '0', types[0]), ('after', '1', '0', types[0])]
    raw = exactly(text, r'^COMPRESSED_SAMPLES seq=(\d+) rand=(\d+) target_checks=(\d+) decoded=(\d+) trace_lost=(\d+) probe_missed=(\d+) probe_hits=(\d+)$')
    seq, rand, checks, decoded, lost, missed, hits = map(int, raw)
    counts_ok = (seq > 0 and rand > 0 and checks == decoded == seq + rand and lost == missed == 0 and hits >= decoded
                 and seq == (metrics.get('swapin_seq') or {}).get('samples')
                 and rand == (metrics.get('swapin_rand') or {}).get('samples'))
    swapped = metrics.get('swapin_swapped') or {}
    half = COMPRESSED_TARGET_BYTES // 4096 // 2
    counts_ok &= (swapped.get('pages') == half * 2 and swapped.get('swapped') == checks
                  and seq * 10 >= half * 9 and rand * 10 >= half * 9
                  and seq <= half and rand <= half)
    counts_ok &= all(len(re.findall(r'^' + marker + r' ', text, re.M)) == 1
                     for marker in ('SWAPIN_SEQ', 'SWAPIN_RAND', 'SWAPIN_SWAPPED'))
    snapshots = re.findall(r'^COMPRESSED_STATE phase=(before|stored) stored_pages=(\d+) pool_bytes=(\d+) incompressible_pages=(\d+)$', text, re.M)
    states = {phase: dict(zip(('stored_pages', 'pool_bytes', 'incompressible_pages'), map(int, values)))
              for phase, *values in snapshots}
    storage_ok = len(snapshots) == 2 and [s[0] for s in snapshots] == ['before', 'stored']
    if storage_ok:
        before, stored = states['before'], states['stored']
        storage_ok = (stored['stored_pages'] - before['stored_pages'] >= checks
                      and stored['pool_bytes'] > before['pool_bytes']
                      and stored['incompressible_pages'] == before['incompressible_pages'])
    phase = metrics.get('swapin_vmstat_delta') or {}
    total_activity = metrics.get('vmstat_delta') or {}
    route_ok = (bool(total_activity) and all(value >= 0 for value in total_activity.values())
                and all(value >= 0 for value in phase.values())
                and phase.get('zswpin', 0) >= decoded and phase.get('zswpout', 0) >= checks
                and all(phase.get(key) == 0 for key in ('pswpin', 'pswpout', 'zswpwb')))
    swaps = (block(text, 'SWAPS_BEGIN', 'SWAPS_END') or '').splitlines()
    topology_ok &= (len(swaps) == 2 and bool(types) and swaps[1].split()[0] == 'xswap' + types[0]
                    and text.splitlines().count('BACKEND_DEVICE none') == 1)
    # Global zero-page counts can include calloc/observer pages. Per-target
    # eviction, successful zswap_load and full pattern verification bind origin.
    data_ok = text.splitlines().count('SWAPIN_DATA_PASS') == 1 and not re.search(r'^SWAPIN_FAIL', text, re.M)
    metrics_ok = all(isinstance((metrics.get(order) or {}).get(key), (int, float))
                     and math.isfinite(metrics[order][key]) and (metrics[order][key] > 0)
                     for order in ('swapin_seq', 'swapin_rand') for key in ('mean_ns', 'p99_ns'))
    counters_ok = all(complete_counter_block(text, 'VMSTAT', tag,
                      ('pswpin', 'pswpout', 'zswpin', 'zswpout', 'zswpwb', 'swpin_zero', 'swpout_zero', 'swap_ra', 'swap_ra_hit'))
                      for tag in ('before', 'end', 'swapin_start', 'swapin_end'))
    metrics.update(compressed_observer={'id': observer[0], 'instrumented': True, 'clock': observer[2]},
                   compressed_samples={'seq': seq, 'rand': rand, 'target_checks': checks, 'decoded': decoded,
                                       'trace_lost': lost, 'probe_missed': missed, 'probe_hits': hits},
                   compressed_states=states)
    return {'compressed_observer': observer_ok, 'compressed_no_backing': topology_ok,
            'compressed_target_decode': counts_ok, 'compressed_storage': bool(storage_ok),
            'compressed_no_fallback': route_ok, 'compressed_counter_integrity': counters_ok,
            'compressed_data': bool(data_ok), 'compressed_latency_metrics': metrics_ok}


def revision8_identity(text, words, backend, mode, workload, config_id, correctness_case,
                       topology_id, expected_case):
    catalog = configuration_catalog()
    GROUPS = catalog.GROUPS
    identity = {'bench.protocol_revision': '8', 'bench.config_id': config_id,
                'bench.topology_id': topology_id}
    if correctness_case:
        require(isinstance(expected_case, dict) and expected_case.get('id') == correctness_case,
                'missing frozen correctness identity')
        group = expected_case.get('group')
        require(group in GROUPS, 'unknown correctness group')
        spec = catalog.correctness_group(group, config_id)
        for key, value in {'backend': backend, 'mode': mode, 'workload': workload,
                           'config_id': config_id, 'topology_id': topology_id}.items():
            require(spec[key] == value and expected_case.get(key) == value, 'correctness identity mismatch: ' + key)
        identity.update({'bench.correctness_case': correctness_case, 'bench.correctness_group': group})
        if spec['subcases']:
            identity['bench.compression_cases'] = ','.join(spec['subcases'])
    else:
        require(workload not in ('compression', 'correctness') and config_id == 'c1-common'
                and topology_id == 'single', 'revision 8 timing identity')
    if backend == 'compressed' and workload == 'swapin':
        identity['bench.compression_target_bytes'] = str(COMPRESSED_TARGET_BYTES)
    tokens = (block(text, 'CMDLINE_BEGIN', 'CMDLINE_END') or '').split()
    expected_keys = set(identity)
    relevant_keys = {'bench.protocol_revision', 'bench.config_id', 'bench.topology_id',
                     'bench.correctness_case', 'bench.correctness_group', 'bench.compression_cases',
                     'bench.compression_target_bytes'}
    got = [token for token in tokens if token.split('=', 1)[0] in relevant_keys]
    good = len(got) == len(identity) and all(tokens.count(key + '=' + str(value)) == 1 for key, value in identity.items())
    good &= {token.split('=', 1)[0] for token in got} == expected_keys
    good &= all(text.splitlines().count(marker) == 1 for marker in
                ('CMDLINE_BEGIN', 'CMDLINE_END', 'BENCH_BOOT', 'BENCH_WORKLOAD_PASS', 'BENCH_PASS'))
    good &= text.splitlines().count('GUEST_TOPOLOGY ' + topology_id) == 1
    nodes = {'0-1'} if topology_id == 'numa2' else {'0'}
    if topology_id == 'single' and config_id in {'c1-common', 'c1-legacy', 'c1-kcsan'}:
        nodes.add('flat')
    observed_nodes = [line for line in text.splitlines() if line.startswith('ONLINE_NODES')]
    good &= len(observed_nodes) == 1 and observed_nodes[0] in {'ONLINE_NODES ' + value for value in nodes}
    return bool(good)


def parse(text, image_sha, backend, mode, workload, protocol_revision=1, *,
          config_id="standard", correctness_case=None, topology_id="single", expected_case=None):
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
    if protocol_revision == 8:
        gates['configuration_identity'] = revision8_identity(text, words, backend, mode, workload, config_id,
                                                            correctness_case, topology_id, expected_case)
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
                                 if backend in ('zswap', 'compressed') else
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
        if backend == 'compressed':
            gates['swap_routing'] &= len(peaks) == 1 and all(re.fullmatch(r'xswap\d+', name) for name in peaks)
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

        if protocol_revision == 8 and backend == 'compressed':
            gates.update(compressed_timing_evidence(text, metrics))

    elif workload == 'compression':
        extra_gates, subcases = compression_evidence(text, mode, expected_case)
        gates.update(extra_gates)
        gates['no_new_kernel_warnings'] = gates['no_kernel_warnings']
        return dict(metrics=metrics, gates=gates, correctness_subcases=subcases)
    elif workload == 'correctness':
        if protocol_revision == 8:
            device = PHYSICAL[backend][0]
            gates['correctness_backend_device'] = all(text.splitlines().count(marker + device) == 1 for marker in
                ('BACKEND_DEVICE ', 'CORRECTNESS_BACKEND_DEVICE ', 'PHYSICAL_SWAPOFF_DEVICE '))
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
