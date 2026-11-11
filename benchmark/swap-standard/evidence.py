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
    summaries = ['# page_compress: pass:3 fail:0 skip:0 total:3',
                 '# Totals: pass:3 fail:0 skip:0 total:3']
    for line in lines:
        if (line.startswith(('# page_compress:', '# Totals:'))
                or re.search(r'\b(?:pass|fail|skip|total):', line, re.I)):
            require(line in summaries, 'invalid or contradictory KUnit summary')
    require(not any(re.search(r'\b(?:SKIP|TODO)\b', line, re.I)
                    for line in lines if line not in summaries),
            'KUnit skip or TODO is incomplete coverage')
    lines = [line for line in lines
             if not line.startswith('#') or line.startswith('# Subtest:') or line in summaries]
    expected = ['KTAP version 1', '1..1', 'KTAP version 1', '# Subtest: page_compress', '1..3',
                *[f'ok {i + 1} {name}' for i, name in enumerate(UNIT_TESTS)], 'ok 1 page_compress']
    return lines == expected or lines == expected[:-1] + summaries + expected[-1:]



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
    expected_nodes = {0, 1} if topology_id in ('numa2', 'numa2-sockets-v2', 'numa2-nehalem-v3') else {0}
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


def compression_evidence(text, mode, expected_case, *, _trusted_subcases=None):
    """Strict ordered records. Enclosed KTAP is opaque to control-record parsing."""
    GROUPS = configuration_groups()
    group = expected_case.get('group') if isinstance(expected_case, dict) else None
    require(group in GROUPS and GROUPS[group]['workload'] == 'compression', 'unknown compression group')
    expected = GROUPS[group]['subcases']
    if _trusted_subcases is not None:
        require(group == "legacy-lifecycle" and _trusted_subcases and
                all(name in expected for name in _trusted_subcases), "invalid trusted legacy subset")
        expected = _trusted_subcases
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
        if line == 'zswap: compressor swap_next_invalid_codec_7d83 not available':
            require(state == 'observations' and current['id'] == 'invalid_codec'
                    and 'expected_diagnostics' not in current,
                    'duplicate or misplaced invalid-codec diagnostic')
            current['expected_diagnostics'] = [{'kind': 'invalid_codec_rejected', 'message': line}]
            continue
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


def nehalem_cpu_identity(text):
    """Bind the new auxiliary topology to numeric CPU0 identity in dmesg."""
    lines = text.splitlines()
    if any(lines.count(marker) != 1 for marker in ('KERNEL_LOG_BEGIN', 'KERNEL_LOG_END')):
        return False
    log = block(text, 'KERNEL_LOG_BEGIN', 'KERNEL_LOG_END') or ''
    cpu0 = [line for line in log.splitlines() if 'smpboot: CPU0:' in line]
    if len(cpu0) != 1:
        return False
    match = re.fullmatch(
        r'(?:\[\s*\d+(?:\.\d+)?\]\s*)?smpboot: CPU0: Intel(?:\(R\))?\s+[^\n]+'
        r' \(family: 0x([0-9a-fA-F]+), model: 0x([0-9a-fA-F]+), stepping: 0x([0-9a-fA-F]+)\)',
        cpu0[0])
    return bool(match and tuple(int(value, 16) for value in match.groups()) == (6, 26, 3))


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
        spec = catalog.correctness_group(group, config_id, topology_id)
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
    nodes = {'0-1'} if topology_id in ('numa2', 'numa2-sockets-v2', 'numa2-nehalem-v3') else {'0'}
    if topology_id == 'single' and config_id in {'c1-common', 'c1-legacy', 'c1-kcsan'}:
        nodes.add('flat')
    observed_nodes = [line for line in text.splitlines() if line.startswith('ONLINE_NODES')]
    good &= len(observed_nodes) == 1 and observed_nodes[0] in {'ONLINE_NODES ' + value for value in nodes}
    if topology_id == 'numa2-nehalem-v3':
        good &= nehalem_cpu_identity(text)
    return bool(good)



# Revision 9 diagnostics are a separate grammar. Legacy schema-1 parsing stays
# byte-for-byte compatible; neither printed PASS nor a debug request is evidence.
C2_SNAPSHOT_KEYS = tuple("""
ram_pages cap_pages cap_updates cap_rejects bypasses incompressible_rejects raw_admitted
entries_live compressed_live raw_live handles_live index_live lru_live stored_bytes owner_refs
charged_bytes inflight store_token_active store_token_peak store_retries
retained_folios_live retained_folio_gets retained_folio_puts
pool_backing_pages peak_backing_pages allocator_chain_pages cap_headroom_pages entry_allocs entry_frees handle_allocs handle_frees
published retired rollback_objects charge_calls charge_ok charge_fail charge_injected
charged_total_bytes uncharge_calls uncharged_total_bytes compressed_loads raw_loads load_misses
decode_errors backing_live backing_allocs backing_frees backing_charge_denials read_submitted
write_submitted read_completed write_completed read_errors write_errors pool_create_ok
pool_destroy_returned test_windows events_lost
""".split())
C2_EVENT_KEYS = tuple("""
schema seq token type generation op kind event stage key count order subpage peer result length
owner requested_nid actual_node_mask node_pages allocated charged published retired rollback
physical_type physical_key data_generation flags
""".split())
C2_EVENTS = set("""
op_begin store_alloc charge_call charge_return publish detach release decode_return
backing_alloc backing_free bio_submit bio_complete hook_hit hold_enter hold_release overlap op_end
pool_create_return pool_destroy_return retained_folio_get retained_folio_put
retained_rewrite_begin retained_rewrite_end folio_redirty folio_uptodate folio_end_writeback
folio_unlock completion_owner_return
""".split())
C2_KINDS = {"init", "store", "load", "invalidate", "destroy", "backing_swapoff", "control"}
C2_TERMINAL_ZERO = tuple("""
entries_live compressed_live raw_live handles_live index_live lru_live stored_bytes owner_refs
charged_bytes inflight store_token_active pool_backing_pages backing_live retained_folios_live
""".split())
C2_LEGACY_PHASES = {
    "legacy_roundtrip": "roundtrip", "legacy_codec_switch": "codec_switch",
    "legacy_invalid_codec": "invalid_codec", "legacy_memcg_balance": "memcg_balance",
    "legacy_memcg_offline": "memcg_offline", "legacy_memcg_limit": "memcg_limits",
}
C2_FAILPOINTS = {
    "init_refusal": "pool_create", "entry_refusal": "entry_alloc", "charge_refusal": "charge",
    "publish_refusal": "publish", "rollback_first": "publish", "rollback_middle": "publish",
    "rollback_last": "publish", "decode_old_backing": "decode",
    "write_completion_error": "bio_write_complete", "read_completion_error": "bio_read_complete",
}
C2_RACES = {"mixed_load_free", "legacy_pool_offline", "mixed_live_destroy",
            "fault_cow_invalidate", "reused_slot_overlap", "live_destroy_overlap", "backing_swapoff_overlap"}


def c2_fields(line, prefix, keys):
    """Exact order and canonical scalar syntax; no permissive key dictionary."""
    parts = line.split(" ")
    require(parts[0] == prefix and len(parts) == len(keys) + 1,
            "malformed " + prefix)
    result = {}
    for word, key in zip(parts[1:], keys):
        require(word.startswith(key + "=") and len(word) > len(key) + 1,
                "missing, duplicate or unordered " + prefix + " field: " + key)
        result[key] = word[len(key) + 1:]
    return result


def c2_uint(value, label, maximum=(1 << 64) - 1):
    require(isinstance(value, str) and re.fullmatch(r"0|[1-9][0-9]*", value),
            "noncanonical unsigned " + label)
    number = int(value)
    require(number <= maximum, "out-of-range " + label)
    return number


def c2_identifier(value):
    require(bool(re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", value)), "invalid C2 identifier")
    return value


def c2_snapshot(lines):
    """Materialized kernel scalars, including a retained post-destroy record."""
    begin_keys = ("schema", "type", "generation", "pool", "snapshot", "state", "codec", "driver", "test")
    require(len(lines) == len(C2_SNAPSHOT_KEYS) + 2, "incomplete frontend snapshot")
    header = c2_fields(lines[0], "XSWAP_FRONTEND_BEGIN", begin_keys)
    require(header["schema"] == "1" and header["state"] in ("active", "destroyed", "init_failed")
            and header["codec"] == "lzo" and header["test"] in ("0", "1"), "frontend snapshot schema/state")
    for key in ("type", "generation", "pool", "snapshot", "test"):
        header[key] = c2_uint(header[key], key, 31 if key == "type" else (1 << 64) - 1)
    require(header["generation"] > 0 and header["pool"] == header["generation"]
            and header["snapshot"] > 0, "frontend ownership identity")
    c2_identifier(header["driver"])
    result = dict(header)
    for key, line in zip(C2_SNAPSHOT_KEYS, lines[1:-1]):
        parts = line.split(" ")
        require(len(parts) == 2 and parts[0] == key, "snapshot missing/duplicate/unordered key: " + key)
        result[key] = c2_uint(parts[1], key)
    end = c2_fields(lines[-1], "XSWAP_FRONTEND_END", ("schema", "type", "generation", "snapshot"))
    require(all(end[key] == str(header[key]) for key in end), "frontend snapshot end mismatch")
    require(result["ram_pages"] > 0 and result["cap_pages"] <= result["ram_pages"], "invalid admission cap")
    require(result["store_token_active"] <= result["store_token_peak"] <= 1, "store token exclusion failed")
    require(result["allocator_chain_pages"] > 0
            and result["cap_headroom_pages"] >= result["allocator_chain_pages"]
            and result["pool_backing_pages"] <= result["cap_pages"] + result["cap_headroom_pages"],
            "registered allocator-page headroom violated")
    require(result["retained_folio_gets"] >= result["retained_folio_puts"]
            and result["retained_folios_live"] == result["retained_folio_gets"] - result["retained_folio_puts"],
            "debug retained-folio ownership mismatch")
    require(result["events_lost"] == 0 and result["raw_live"] == result["raw_admitted"] == 0,
            "raw admission or lost frontend events")
    require(result["charged_total_bytes"] >= result["uncharged_total_bytes"]
            and result["charged_bytes"] == result["charged_total_bytes"] - result["uncharged_total_bytes"],
            "frontend charge arithmetic")
    require(result["charge_calls"] == result["charge_ok"] + result["charge_fail"],
            "generic charge call/return arithmetic")
    for alloc, freed, live in (("entry_allocs", "entry_frees", "entries_live"),
                               ("handle_allocs", "handle_frees", "handles_live"),
                               ("backing_allocs", "backing_frees", "backing_live")):
        require(result[alloc] >= result[freed], "negative frontend ownership balance")
        if result["inflight"] == 0:
            require(result[alloc] - result[freed] == result[live], "frontend live ownership mismatch: " + live)
    require(result["peak_backing_pages"] >= result["pool_backing_pages"], "allocator peak below current backing")
    for direction in ("read", "write"):
        require(result[direction + "_errors"] <= result[direction + "_completed"]
                <= result[direction + "_submitted"], "BIO completion arithmetic")
    if result["inflight"] == 0:
        require(result["store_token_active"] == 0, "quiescent snapshot retains store token")
        require(len({result[key] for key in ("entries_live", "compressed_live", "handles_live",
                    "index_live", "lru_live")}) == 1, "quiescent publication mismatch")
        require(result["published"] >= result["retired"]
                and result["published"] - result["retired"] == result["entries_live"],
                "published/retired balance")
        if result["compressed_live"]:
            require(result["compressed_live"] <= result["stored_bytes"] < result["compressed_live"] * 4096,
                    "positive compressed objects are zero or raw")
        else:
            require(result["stored_bytes"] == 0, "bytes without compressed objects")
    if result["state"] in ("destroyed", "init_failed"):
        require(all(result[key] == 0 for key in C2_TERMINAL_ZERO), "terminal frontend retains ownership")
        require(result["published"] == result["retired"], "terminal frontend retains publication")
        if result["state"] == "destroyed":
            require(result["pool_create_ok"] == result["pool_destroy_returned"] == 1,
                    "pool destructor return unobserved")
        else:
            require(result["pool_create_ok"] == result["pool_destroy_returned"] == 0,
                    "init refusal contains a fictitious pool")
    else:
        require(result["pool_create_ok"] == 1 and result["pool_destroy_returned"] == 0,
                "active frontend pool lifetime mismatch")
    return result


def c2_events(lines, token):
    require(len(lines) >= 3, "empty targeted event journal")
    envelope_keys = ("schema", "first", "last", "lost")
    begin = c2_fields(lines[0], "XSWAP_EVENTS_BEGIN", envelope_keys)
    end = c2_fields(lines[-1], "XSWAP_EVENTS_END", envelope_keys)
    require(begin == end and begin["schema"] == "1" and begin["lost"] == "0", "journal loss/envelope mismatch")
    first, last = (c2_uint(begin[key], key) for key in ("first", "last"))
    require(first > 0 and first <= last and last - first + 1 == len(lines) - 2 <= 4096,
            "journal gap or overflow")
    records, active, finished = [], {}, set()
    for sequence, line in enumerate(lines[1:-1], first):
        record = c2_fields(line, "XSWAP_EVENT", C2_EVENT_KEYS)
        require(record["schema"] == "1", "unknown event schema")
        for key in C2_EVENT_KEYS:
            if key in ("kind", "event", "stage"):
                c2_identifier(record[key])
            elif key == "result":
                require(bool(re.fullmatch(r"0|-?[1-9][0-9]*", record[key])), "noncanonical event result")
                record[key] = int(record[key])
                require(-(1 << 31) <= record[key] < (1 << 31), "event result range")
            else:
                record[key] = c2_uint(record[key], key)
        require(record["seq"] == sequence and record["token"] == token
                and record["type"] < 32 and record["generation"] > 0 and record["op"] > 0
                and record["kind"] in C2_KINDS and record["event"] in C2_EVENTS
                and record["flags"] < 1024 and record["order"] < 16
                and record["subpage"] < 1 << record["order"], "event identity/range mismatch")
        key = record["generation"], record["op"]
        event = record["event"]
        if event == "op_begin":
            require(key not in active and key not in finished, "duplicate operation begin")
            active[key] = record
        else:
            require(key in active and active[key]["kind"] == record["kind"]
                    and active[key]["type"] == record["type"], "event outside its actual operation")
        if event == "overlap":
            peer = (record["generation"], record["peer"])
            require(peer != key and peer in active, "overlap has no other active kernel operation")
            other = active[peer]
            size, peer_size = 1 << record["order"], 1 << other["order"]
            require(record["key"] < other["key"] + peer_size
                    and other["key"] < record["key"] + size, "overlap key ranges do not intersect")
        if event == "charge_call":
            require(record["flags"] & 32 and not record["flags"] & 16, "charge call is only injected")
        if event == "bio_complete":
            require(record["flags"] & 64, "completion event is a submission mock")
        if event == "op_end":
            active.pop(key)
            finished.add(key)
        records.append(record)
    require(not active, "journal ends with an unfinished operation")
    return records


def c2_source_identity(text, backend, mode, workload, config_id, correctness_case,
                       topology_id, expected_case, binding):
    catalog = configuration_catalog()
    require(isinstance(binding, dict) and set(binding) == set(catalog.C2_BINDING_KEYS),
            "missing exact source-role observer binding")
    require(binding["contract_id"] == catalog.C2_CONTRACT
            and binding["source_role"] in ("baseline", "candidate")
            and bool(re.fullmatch(r"[0-9a-f]{40}", binding["source_commit"]))
            and bool(re.fullmatch(r"[0-9a-f]{40}", binding["source_tree"]))
            and (binding["source_commit"] == catalog.C2_BASELINE) == (binding["source_role"] == "baseline")
            and binding["observer_id"] == catalog.C2_OBSERVER["id"]
            and binding["observer_symbol"] == catalog.C2_OBSERVER["arms"][binding["source_role"]]["symbol"],
            "C2 source-role observer mismatch")
    identity = {"bench.protocol_revision": "9", "bench.config_id": config_id,
                "bench.topology_id": topology_id, "bench.contract_id": binding["contract_id"],
                "bench.source_role": binding["source_role"], "bench.source_commit": binding["source_commit"],
                "bench.frontend": binding["frontend"], "bench.observer": binding["observer_id"]}
    if correctness_case:
        require(isinstance(expected_case, dict) and expected_case.get("id") == correctness_case,
                "missing C2 correctness case")
        spec = catalog.c2_correctness_group(expected_case["group"], config_id, topology_id)
        require(all(expected_case.get(key) == value for key, value in spec.items())
                and expected_case["role"] == binding["source_role"]
                and all(spec[key] == value for key, value in (
                    ("backend", backend), ("mode", mode), ("workload", workload), ("frontend", binding["frontend"]))),
                "C2 frozen correctness binding mismatch")
        identity.update({"bench.correctness_case": correctness_case,
                         "bench.correctness_group": expected_case["group"],
                         "bench.compression_cases": ",".join(spec["subcases"])})
    else:
        require(workload not in ("compression", "correctness") and config_id == "c1-common"
                and topology_id == "single", "C2 timing requires common/single identity")
        frontend = "physical" if backend != "compressed" else (
            "legacy" if binding["source_role"] == "baseline" else "independent")
        require(binding["frontend"] == frontend, "timing frontend binding mismatch")
    if workload == "swapin" and backend == "compressed":
        identity["bench.compression_target_bytes"] = str(COMPRESSED_TARGET_BYTES)
    require(text.splitlines().count("CMDLINE_BEGIN") == text.splitlines().count("CMDLINE_END") == 1,
            "missing or duplicate actual command-line block")
    tokens = (block(text, "CMDLINE_BEGIN", "CMDLINE_END") or "").split()
    recognized = set(identity) | {"bench.correctness_case", "bench.correctness_group",
                                  "bench.compression_cases", "bench.compression_target_bytes"}
    selected = [word for word in tokens if word.split("=", 1)[0] in recognized]
    require(len(selected) == len(identity)
            and all(tokens.count(key + "=" + value) == 1 for key, value in identity.items()),
            "missing or duplicate C2 command-line identity")
    nodes = {"0-1"} if topology_id == catalog.C2_TOPOLOGY else {"0"}
    if topology_id == "single" and catalog.CONFIGS[config_id]["required"].get("NUMA") != "y":
        nodes.add("flat")
    observed = [line for line in text.splitlines() if line.startswith("ONLINE_NODES")]
    require(len(observed) == 1 and observed[0] in {"ONLINE_NODES " + node for node in nodes},
            "C2 node topology mismatch")
    require([line for line in text.splitlines() if line.startswith("GUEST_TOPOLOGY")]
            == ["GUEST_TOPOLOGY " + topology_id]
            and (topology_id != catalog.C2_TOPOLOGY or nehalem_cpu_identity(text)), "C2 CPU topology mismatch")
    return True




C2_POLICY_KEYS = ("phase", "point", "zswap_present", "zswap_enabled", "zswap_pool_percent",
                  "zswap_shrinker", "zswap_codec", "zswap_quota", "swap_quota",
                  "cgroup_inode", "parent_inode", "cgroup_errno", "memory_current", "memory_swap_current")
C2_LEGACY_STATE_KEYS = ("phase", "point", "epoch", "type", "stored_pages", "pool_bytes",
                        "incompressible_pages", "zswpin", "zswpout", "pswpin", "pswpout",
                        "zswap_bytes", "zswapped_bytes", "owner")


def c2_swap_table(lines):
    require(lines and lines[0].split() == ["Filename", "Type", "Size", "Used", "Priority"],
            "missing complete /proc/swaps header")
    rows = {}
    for line in lines[1:]:
        parts = line.split()
        require(len(parts) == 5 and bool(re.fullmatch(r"xswap[0-9]+|/dev/(?:vda|zram[01]|ram0)", parts[0]))
                and parts[0] not in rows and bool(re.fullmatch(r"[a-z]+", parts[1])),
                "unknown or duplicate raw swap device")
        size, used = c2_uint(parts[2], "swap size"), c2_uint(parts[3], "swap used")
        require(bool(re.fullmatch(r"0|-?[1-9][0-9]*", parts[4])), "noncanonical swap priority")
        priority = int(parts[4])
        require(0 < size and used <= size and -32768 <= priority <= 32767, "invalid raw swap row")
        rows[parts[0]] = {"kind": parts[1], "size_kib": size, "used_kib": used, "priority": priority}
    return rows


def c2_policy(line):
    values = c2_fields(line, "COMPRESS_POLICY", C2_POLICY_KEYS)
    require(values["point"] in ("before", "effect", "after", "reset")
            and values["zswap_present"] in ("0", "1")
            and values["cgroup_errno"] in ("0", "2"), "policy identity or errno")
    for key in ("cgroup_inode", "parent_inode", "cgroup_errno", "zswap_present"):
        values[key] = c2_uint(values[key], key)
    require(values["parent_inode"] > 0, "actual parent cgroup inode missing")
    module_fields = ("zswap_enabled", "zswap_pool_percent", "zswap_shrinker", "zswap_codec")
    if values["zswap_present"]:
        require(values["zswap_enabled"] in ("0", "1") and values["zswap_shrinker"] in ("0", "1"),
                "missing actual legacy module booleans")
        c2_identifier(values["zswap_codec"])
        require(c2_uint(values["zswap_pool_percent"], "legacy cap", 100) > 0, "invalid legacy cap")
    else:
        require(all(values[key] == "absent" for key in (*module_fields, "zswap_quota")),
                "ZSWAP=n policy fabricates legacy controls")
    if values["cgroup_errno"] == 2:
        require(values["cgroup_inode"] == 0 and all(values[key] == "absent"
                for key in ("zswap_quota", "swap_quota", "memory_current", "memory_swap_current")),
                "removed cgroup fabricates readback")
    else:
        require(values["cgroup_inode"] > 0, "actual temporary cgroup missing")
        for key in ("memory_current", "memory_swap_current"):
            values[key] = c2_uint(values[key], key)
        for key in ("zswap_quota", "swap_quota"):
            if values[key] in ("max", "absent"):
                require(values[key] != "absent" or (key == "zswap_quota" and not values["zswap_present"]),
                        "missing existing cgroup quota")
            else:
                c2_uint(values[key], key)
    return values


def c2_cpu_list(value):
    require(bool(re.fullmatch(r"[0-9]+(?:-[0-9]+)?(?:,[0-9]+(?:-[0-9]+)?)*", value)), "invalid CPU range list")
    cpus, last = set(), -1
    for item in value.split(","):
        ends = item.split("-")
        lo, hi = int(ends[0]), int(ends[-1])
        require(str(lo) == ends[0] and str(hi) == ends[-1] and last < lo <= hi < 4,
                "noncanonical CPU range")
        cpus.update(range(lo, hi + 1))
        last = hi
    return cpus


def c2_legacy_events(lines, token):
    keys = ("schema", "token", "epoch", "type", "pool", "owner", "first", "last", "lost")
    require(len(lines) >= 3, "empty legacy operation journal")
    header = c2_fields(lines[0], "XSWAP_LEGACY_EVENTS_BEGIN", keys)
    require(header == c2_fields(lines[-1], "XSWAP_LEGACY_EVENTS_END", keys)
            and header["schema"] == "1", "legacy journal envelope mismatch")
    header = {key: c2_uint(value, key) for key, value in header.items()}
    require(header["token"] == token and header["lost"] == 0 and header["epoch"] > 0
            and header["type"] < 32 and header["pool"] > 0 and header["owner"] > 0
            and 0 < header["first"] <= header["last"]
            and header["last"] - header["first"] + 1 == len(lines) - 2 <= 4096,
            "legacy journal identity/loss mismatch")
    event_keys = ("schema", "seq", "token", "epoch", "type", "op", "kind", "event", "stage",
                  "pool", "owner", "peer", "result")
    records, active, done = [], {}, set()
    for seq, line in enumerate(lines[1:-1], header["first"]):
        event = c2_fields(line, "XSWAP_LEGACY_EVENT", event_keys)
        for key in event_keys:
            if key in ("kind", "event", "stage"):
                c2_identifier(event[key])
            elif key == "result":
                require(event[key] == "0", "legacy operation/hold did not complete successfully")
                event[key] = 0
            else:
                event[key] = c2_uint(event[key], key)
        require(event["schema"] == 1 and event["seq"] == seq and event["op"] > 0
                and event["kind"] in ("pool_release", "memcg_offline")
                and all(event[key] == header[key] for key in ("token", "epoch", "type", "pool", "owner")),
                "legacy event identity mismatch")
        op, kind = event["op"], event["kind"]
        if event["event"] == "op_begin":
            require(op not in active and op not in done and event["stage"] == kind + "_enter",
                    "legacy operation begin mismatch")
            active[op] = kind
        else:
            require(op in active and active[op] == kind, "legacy event outside actual operation")
            if event["event"] == "overlap":
                require(event["peer"] in active and active[event["peer"]] != kind,
                        "legacy overlap lacks two distinct actual intervals")
            elif event["event"] in ("hold_enter", "hold_release"):
                require(kind == "pool_release" and event["stage"] == "pool_release_enter",
                        "legacy hold at an unreviewed location")
            elif event["event"] == "op_end":
                require(event["stage"] == kind + "_returned", "legacy operation return unobserved")
                active.pop(op)
                done.add(op)
            else:
                raise ValueError("unknown legacy operation event")
        records.append(event)
    require(not active and {event["kind"] for event in records} == {"pool_release", "memcg_offline"}
            and any(event["event"] == "overlap" for event in records), "legacy overlap incomplete")
    holds = [event for event in records if event["event"] == "hold_enter"]
    releases = [event for event in records if event["event"] == "hold_release"]
    require(len(holds) == len(releases) == 1 and holds[0]["op"] == releases[0]["op"]
            and holds[0]["seq"] < releases[0]["seq"]
            and any(event["event"] == "overlap" and holds[0]["seq"] < event["seq"] < releases[0]["seq"]
                    for event in records), "legacy overlap lacks its actual bounded hold interval")
    return {"identity": header, "events": records}


def c2_control(line):
    """Only successful exact kernel readbacks; failures never become acknowledgements."""
    words = line.split(" ")
    require(len(words) >= 4 and words[:2] == ["XSWAP_CONTROL", "schema=1"]
            and words[2].startswith("command="), "malformed control readback")
    command = words[2][8:]
    common = ("schema", "command", "type", "generation", "token", "status")
    suffixes = {
        "begin": ("key", "count"), "arm": ("point", "key", "count", "order", "subpage", "errno"),
        "hold": ("point", "key", "count", "timeout_ms"), "release": (),
        "retain_write": ("key", "count", "timeout_ms"),
        "rewrite_retained": ("key", "pattern_generation", "timeout_ms"),
        "release_retained": ("key",), "end": ("last",),
    }
    if command in suffixes:
        keys = common + suffixes[command]
    elif command == "cap":
        keys = ("schema", "command", "type", "generation", "status", "pages")
    elif command == "ack":
        keys = ("schema", "command", "generation", "status")
    elif command in ("ack_events", "legacy_ack"):
        keys = ("schema", "command", "token", "status", "last")
    elif command in ("prepare_create", "cancel_create"):
        keys = ("schema", "command", "token", "status")
    elif command in ("legacy_begin", "legacy_hold", "legacy_release", "legacy_end"):
        keys = ("schema", "command", "type", "epoch", "token", "status") + {
            "legacy_begin": ("owner",), "legacy_hold": ("point", "pool", "timeout_ms"),
            "legacy_release": (), "legacy_end": ("last",)}[command]
    else:
        raise ValueError("unknown C2 control command")
    values = c2_fields(line, "XSWAP_CONTROL", keys)
    require(values["status"] == {"prepare_create": "armed", "cancel_create": "cancelled"}.get(command, "ok"),
            "control has no successful exact acknowledgement")
    for key in keys:
        if key in ("schema", "command", "status", "point", "errno"):
            continue
        if key == "key" and values[key] == "next":
            require(command in ("begin", "arm", "hold", "retain_write"), "unresolved key after capture")
        else:
            values[key] = c2_uint(values[key], key)
    if "timeout_ms" in values:
        require(values["timeout_ms"] == 1000, "debug wait deadline differs from contract")
    if "token" in values:
        require(values["token"] > 0, "zero control token")
    if "type" in values:
        require(values["type"] < 32, "control type range")
    if "generation" in values:
        require(values["generation"] > 0, "control generation range")
    if command == "arm":
        require(values["point"] in set(C2_FAILPOINTS.values())
                and values["errno"] == ("EIO" if values["point"] in
                    ("decode", "bio_write_complete", "bio_read_complete") else "ENOMEM"),
                "unapproved failure selector")
        require(values["order"] < 16 and values["subpage"] < 1 << values["order"], "failure selector range")
    if command == "hold":
        require(values["point"] in ("load_after_lookup", "store_before_publish",
                "destroy_before_unuse", "backing_swapoff_enter"), "unreviewed hold location")
    if command == "legacy_hold":
        require(values["point"] == "pool_release_enter", "unreviewed legacy hold")
    return values



def c2_phase_readbacks(record):
    name, identity = record["phase"], record["identity"]
    swaps, policies = record["swaps"], record["policies"]
    require("effect" in swaps and "reset" in swaps and not swaps["reset"],
            name + ": actual empty swap reset missing")
    residency = record.get("residency")
    routes = record["residencies"]
    require(len({row["type"] for row in routes.values()}) == len(routes), "mixed target type alias")
    for row in routes.values():
        require(row["pattern_generation"] > 0 and row["type"] < 32 and row["pages"] > 0
                and 0 <= row["nonresident"] <= row["swapped"] <= row["pages"]
                and row["key_first"] <= row["key_last"], "invalid actual target residency")
    legacy_only = name in C2_LEGACY_PHASES or name == "legacy_lifecycle"
    if legacy_only:
        require(identity["frontend"] == "legacy" and identity["generation"] == 0
                and set(swaps["effect"]) == {"/dev/zram1"},
                name + ": actual ordinary-only topology missing")
        return
    if name == "physical_regression" and identity["role"] == "baseline":
        require(set(swaps["effect"]) == {"xswap" + str(identity["type"]), "/dev/vda"},
                "baseline physical regression topology missing")
        return
    if name != "library_unit":
        require(all(point in policies for point in ("before", "effect", "after", "reset")),
                name + ": complete actual policy/reset readback missing")
        before, effect, after, reset = (policies[point] for point in ("before", "effect", "after", "reset"))
        require(before["cgroup_errno"] == effect["cgroup_errno"] == 0
                and before["cgroup_inode"] == effect["cgroup_inode"]
                and reset["cgroup_errno"] == 2 and reset["cgroup_inode"] == 0,
                name + ": temporary owner lifecycle/reset unobserved")
        module_keys = ("zswap_present", "zswap_enabled", "zswap_pool_percent", "zswap_shrinker", "zswap_codec")
        require(all(before[key] == reset[key] for key in module_keys), "legacy module policy not restored")
        config = record["config_id"]
        independent_config = config == "c2-independent" or config.endswith("-independent")
        require(effect["zswap_present"] == int(not independent_config),
                "linked frontend configuration differs from actual policy readback")
        if name in ("xswap_legacy_disabled", "ordinary_legacy_disabled"):
            require(effect["zswap_enabled"] == "0", "legacy disable policy was not effective")
        if name in ("xswap_legacy_quota_zero", "ordinary_legacy_quota_zero"):
            require(effect["zswap_enabled"] == "1" and effect["zswap_quota"] == "0",
                    "zero legacy quota was not effective")
        if name == "swap_charge_denied":
            require(effect["swap_quota"] == "0", "physical swap-charge refusal lacks zero quota")
    virtual = "xswap" + str(identity["type"])
    positive = {"independent_roundtrip", "xswap_legacy_disabled", "xswap_legacy_quota_zero",
                "independent_node0", "independent_node1", "live_cpu_hotplug", "owner_balance",
                "independent_large_folio", "zero_control", "incompressible_control", "no_target_retention"}
    if name in positive:
        require(set(swaps["effect"]) == {virtual} and swaps["effect"][virtual]["priority"] == 32767,
                name + ": independent proof is not exclusive and unbacked")
    physical = {"physical_regression", "physical_fallback", "incompressible_fallback",
                "swap_charge_denied", "decode_old_backing", "write_completion_error", "read_completion_error"}
    if name in physical:
        require(set(swaps["effect"]) == {virtual, "/dev/vda"}, name + ": real disk target topology missing")
    mixed = name == "both_live" or name in ("mixed_load_free", "legacy_pool_offline", "mixed_live_destroy")
    if mixed:
        actual = swaps["effect"]
        require(set(actual) == {virtual, "/dev/zram1"} and all(item["used_kib"] > 0 for item in actual.values()),
                name + ": both actual swap devices were not live")
    ordinary = name in ("ordinary_legacy_disabled", "ordinary_legacy_quota_zero")
    separation = name in ("xswap_legacy_disabled", "xswap_legacy_quota_zero")
    if ordinary or separation or mixed:
        old = record["legacy_states"]
        require(all(point in old for point in ("before", "effect", "after")), "complete ordinary state missing")
        b, e, a = (old[point] for point in ("before", "effect", "after"))
        require(len({row["epoch"] for row in (b, e, a)}) == 1
                and len({row["type"] for row in (b, e, a)}) == 1,
                "ordinary epoch/type changed within phase")
        for key in ("zswpin", "zswpout", "pswpin", "pswpout"):
            require(b[key] <= e[key] <= a[key], "ordinary lifetime counter decreased")
        if ordinary or separation:
            require(a["zswpin"] == b["zswpin"] and a["zswpout"] == b["zswpout"]
                    and e["stored_pages"] == b["stored_pages"]
                    and e["zswap_bytes"] == e["zswapped_bytes"] == 0,
                    "legacy frontend handled a disabled/quota-zero/separated target")
        if ordinary:
            target = routes.get("physical") or routes.get("legacy")
            require(identity["generation"] == 0 and target and target["type"] == e["type"]
                    and target["pattern"] == "nonzero" and target["nonresident"] * 10 >= target["pages"] * 9
                    and set(swaps["effect"]) == {"/dev/zram1"}
                    and a["pswpin"] > b["pswpin"] and a["pswpout"] > b["pswpout"],
                    "ordinary disabled/quota-zero route lacks actual physical fault traffic")
        if mixed:
            target = routes.get("legacy")
            require(record.get("data") and record["data"]["checked_words"] >=
                    sum(row["pages"] for row in routes.values()) * 512,
                    "mixed phase did not verify complete data from both actual mappings")
            require(target and target["type"] == e["type"] and target["type"] != identity["type"]
                    and target["pattern"] == "nonzero" and target["nonresident"] * 10 >= target["pages"] * 9
                    and e["stored_pages"] > b["stored_pages"] and e["pool_bytes"] > b["pool_bytes"]
                    and e["incompressible_pages"] == b["incompressible_pages"]
                    and e["zswap_bytes"] > 0 and e["zswapped_bytes"] > 0
                    and a["zswpin"] > b["zswpin"] and a["zswpout"] > b["zswpout"]
                    and a["pswpin"] == b["pswpin"] and a["pswpout"] == b["pswpout"],
                    "mixed phase lacks separate ordinary compressed storage/decode")
    if name == "live_cpu_hotplug":
        cpu = record["cpu"]
        require(set(cpu) == {"before", "offline", "online", "reset"}
                and len({row["target"] for row in cpu.values()}) == 1, "complete CPU hotplug readback missing")
        initial = c2_cpu_list(cpu["before"]["online"])
        target = cpu["before"]["target"]
        require(initial == {0, 1, 2, 3}
                and c2_cpu_list(cpu["offline"]["online"]) == initial - {target}
                and c2_cpu_list(cpu["online"]["online"]) == c2_cpu_list(cpu["reset"]["online"]) == initial,
                "CPU offline/online/reset effect missing")
        positions = record["positions"]
        require(positions["snapshot:effect"] < positions["cpu:offline"] < positions["cpu:online"]
                < positions["snapshot:after"], "CPU hotplug did not retain the observed compressed residence")
    if name == "owner_balance":
        before, after = policies["before"], policies["after"]
        require(after["cgroup_errno"] == 2 and after["parent_inode"] == before["parent_inode"],
                "actual owner removal/reparent target missing")
        require(any(event["event"] == "charge_return" and event["result"] == 0
                    and event["flags"] & 32 and event["owner"] == before["cgroup_inode"]
                    for event in record["events"])
                and any(event["event"] == "decode_return" and event["result"] == 0
                        and event["owner"] == before["parent_inode"] for event in record["events"]),
                "held generic owner did not show actual before/after reparent identity")
    if name == "legacy_pool_offline":
        require(record.get("legacy_events") and set(record["legacy_pools"]) == {"before", "switched"}
                and record.get("legacy_store"), "actual old-pool/offline lifetime binding missing")
        old, new = (record["legacy_pools"][point] for point in ("before", "switched"))
        stored, journal = record["legacy_store"], record["legacy_events"]["identity"]
        require(old["pool"] > 0 and new["pool"] > 0 and old["pool"] != new["pool"]
                and old["codec"] != new["codec"] and 0 < stored["length"] < 4096 and stored["order"] < 16,
                "old pool did not come from actual distinct pool/store observations")
        for key in ("token", "epoch", "type", "owner"):
            require(old[key] == new[key] == stored[key] == journal[key], "legacy selected ownership mismatch")
        require(old["token"] == identity["token"] and old["pool"] == stored["pool"] == journal["pool"],
                "legacy overlap targets an unobserved pool")
        target = routes["legacy"]
        require(target["key_first"] <= stored["key"] <= target["key_last"]
                and old["type"] == target["type"], "old-pool publication was outside tested ordinary targets")
        require(old["epoch"] == record["legacy_states"]["before"]["epoch"]
                and old["owner"] == record["legacy_states"]["before"]["owner"],
                "old-pool operation owner differs from actual ordinary state")
        selected = {}
        for command in ("legacy_begin", "legacy_hold", "legacy_release", "legacy_end", "legacy_ack"):
            rows = [item for item in record["controls"] if item["command"] == command]
            require(len(rows) == 1, "missing or duplicate legacy control acknowledgement")
            selected[command] = rows[0]
        for command in ("legacy_begin", "legacy_hold", "legacy_release", "legacy_end"):
            require(all(selected[command][key] == old[key] for key in ("type", "epoch", "token")),
                    "legacy control selected a different actual device epoch")
        require(selected["legacy_begin"]["owner"] == old["owner"]
                and selected["legacy_hold"]["pool"] == old["pool"]
                and selected["legacy_end"]["last"] == selected["legacy_ack"]["last"] == journal["last"],
                "legacy control owner, pool or copied journal end mismatch")
        positions = [selected[command]["_position"] for command in
                     ("legacy_begin", "legacy_hold", "legacy_release", "legacy_end")]
        require(positions == sorted(set(positions))
                and positions[-1] < record["positions"]["legacy_events"] < selected["legacy_ack"]["_position"],
                "legacy window was not closed, copied and acknowledged in order")


def c2_phase_semantics(record):
    """Require observed effects, ordered real transitions, data, and reset."""
    name, header = record["phase"], record["identity"]
    snapshots, events = record["snapshots"], record["events"]
    data, residency = record.get("data"), record.get("residency")
    require(record["status"] == "PASS" and record["reset"], name + ": incomplete phase/reset")
    c2_phase_readbacks(record)
    if name in ("ordinary_legacy_disabled", "ordinary_legacy_quota_zero"):
        target = record["residencies"].get("physical") or record["residencies"].get("legacy")
        require(data and target and data["checked_words"] >= target["pages"] * 512
                and data["corrupt_words"] == 0 and data["completed_faults"] > 0 and data["child_signal"] == 0,
                "ordinary physical route lacks verified full data and actual completed touches")
        return
    if name == "physical_regression":
        require(header["frontend"] == "physical" and record.get("physical")
                and all(record["physical"]["gates"].values()),
                "preserved physical regression raw evidence missing")
        if header["role"] == "baseline":
            require(header["generation"] == 0, "baseline invented an independent generation")
            return
    if name in C2_LEGACY_PHASES or name == "legacy_lifecycle":
        require(header["frontend"] == "legacy" and header["generation"] == 0
                and record.get("legacy"), name + ": legacy observation missing")
        raw = record["legacy"]
        old = ([C2_LEGACY_PHASES[name]] if name in C2_LEGACY_PHASES else
               configuration_groups()["legacy-lifecycle"]["subcases"])
        case = {"group": "legacy-lifecycle", "subcases": old, "topology_id": "single"}
        wrapped = "COMPRESSION_GROUP_BEGIN legacy-lifecycle\n" + raw["body"] + "\nCOMPRESSION_GROUP_END legacy-lifecycle"
        gates, parsed = compression_evidence(wrapped, "plain", case, _trusted_subcases=old)
        require(all(gates.values()) and raw["type"] == header["type"] and raw["epoch"] > 0,
                name + ": legacy raw evidence failed")
        record["legacy"]["parsed"] = parsed
        return
    require(header["generation"] > 0 and header["frontend"] in ("independent", "mixed", "physical"),
            name + ": independent generation missing")
    final = snapshots.get("reset", [])
    require(final and all(item["state"] in ("destroyed", "init_failed") for item in final),
            name + ": actual terminal reset missing")
    observed = [item for point in snapshots.values() for item in point]
    generations = {item["generation"] for item in observed}
    require(header["generation"] in generations and generations == {item["generation"] for item in final},
            name + ": unclosed or substituted frontend generation")
    require(all(event["generation"] in generations for event in events), name + ": event generation has no lifecycle")
    owners, sequence = {}, {}
    for point in ("before", "effect", "after", "reset"):
        for item in snapshots.get(point, []):
            generation = item["generation"]
            require(generation not in owners or owners[generation] == item["type"], "generation changed logical type")
            owners[generation] = item["type"]
            previous = sequence.get(generation)
            require(previous is None or item["snapshot"] > previous["snapshot"]
                    or (item["state"] != "active" and item == previous), "snapshot sequence reused or decreased")
            sequence[generation] = item
    require(all(event["type"] == owners[event["generation"]] for event in events), "event uses wrong generation/type pair")
    controls = record["controls"]
    require(all(item["generation"] in owners and
                ("type" not in item or item["type"] == owners[item["generation"]])
                for item in controls if "generation" in item),
            "control acknowledgement uses an unobserved generation/type")
    if events:
        end = [item for item in controls if item["command"] == "end"]
        acknowledgements = [item for item in controls if item["command"] == "ack_events"]
        require(len(end) == len(acknowledgements) == 1 and end[0]["generation"] == header["generation"]
                and end[0]["last"] == acknowledgements[0]["last"] == events[-1]["seq"]
                and end[0]["_position"] < record["positions"]["events"] < acknowledgements[0]["_position"],
                "actual event window not closed/copied/acknowledged")
        opens = [item for item in controls if item["command"] in ("begin", "prepare_create")]
        require(len(opens) == 1 and (opens[0]["command"] == "prepare_create" if name == "init_refusal"
                else opens[0].get("generation") == header["generation"]), "targeted window begin missing")
    if record["test_config"]:
        acknowledged = [item["generation"] for item in controls if item["command"] == "ack"]
        require(set(acknowledged) == generations and len(acknowledged) == len(generations)
                and all(item["_position"] > record["positions"]["snapshot:reset"] for item in controls
                        if item["command"] == "ack"), "terminal records not copied before exactly-once ack")
    require(all(item["test"] == int(record["test_config"]) for item in observed),
            name + ": snapshot test configuration mismatch")
    if name == "library_unit":
        require(record.get("ktap") and _valid_ktap(record["ktap"]), "complete library KUnit output missing")
        numa_ktap_observations(record["ktap"], "single")
        return
    require(data is not None and data["checked_words"] > 0 and data["corrupt_words"] == 0,
            name + ": full data verification absent")
    failed_fault = name in ("decode_old_backing", "read_completion_error")
    require(data["child_signal"] == (7 if failed_fault else 0),
            name + ": unexpected child fault result")
    if name == "init_refusal":
        failed = [item for item in final if item["state"] == "init_failed"]
        require(len(failed) == 1 and failed[0]["generation"] == header["generation"],
                "actual failed initialization generation missing")
    else:
        require(all(point in snapshots for point in ("before", "effect", "after")),
                name + ": before/effect/after snapshots missing")
        before, effect, after = [
            next((item for item in snapshots[point] if item["generation"] == header["generation"]), None)
            for point in ("before", "effect", "after")]
        require(all(item is not None for item in (before, effect, after)),
                name + ": initial generation substituted")
        require(before["inflight"] == effect["inflight"] == after["inflight"] == 0,
                name + ": unquiesced effect accounting")
        counters = ("published", "retired", "compressed_loads", "raw_loads", "charge_calls", "charge_ok",
                    "charged_total_bytes", "uncharged_total_bytes", "cap_rejects", "bypasses",
                    "incompressible_rejects", "read_submitted", "write_submitted", "read_completed",
                    "write_completed", "read_errors", "write_errors", "backing_charge_denials",
                    "store_retries")
        require(all(before[key] <= effect[key] <= after[key] for key in counters),
                name + ": lifetime counters moved backward")
        changes = {key: after[key] - before[key] for key in counters}
        require(changes["raw_loads"] == 0, name + ": raw load cannot prove compression")
        if residency:
            require(residency["type"] == header["type"]
                    and 0 <= residency["nonresident"] <= residency["swapped"] <= residency["pages"]
                    and residency["key_first"] <= residency["key_last"], name + ": target residency mismatch")
        positive = name in {
            "independent_roundtrip", "xswap_legacy_disabled", "xswap_legacy_quota_zero", "both_live",
            "independent_node0", "independent_node1", "live_cpu_hotplug", "owner_balance",
            "independent_large_folio", "mixed_load_free", "legacy_pool_offline", "mixed_live_destroy",
        }
        if positive:
            require(residency and residency["pattern"] == "nonzero" and residency["pattern_generation"] > 0
                    and residency["pages"] == 8192 and residency["nonresident"] * 10 >= residency["pages"] * 9
                    and data["checked_words"] >= residency["pages"] * 512,
                    name + ": positive compressed target absent")
            require(effect["compressed_live"] > before["compressed_live"]
                    and effect["pool_backing_pages"] > before["pool_backing_pages"]
                    and changes["compressed_loads"] > 0 and residency["nonresident"] > 0
                    and changes["charge_calls"] >= changes["charge_ok"] > 0
                    and changes["charged_total_bytes"] > 0 and data["completed_faults"] > 0
                    and effect["owner_refs"] == effect["entries_live"],
                    name + ": real nonzero object/charge/decoder proof missing")
            require(all(changes[key] == 0 for key in ("cap_rejects", "read_submitted", "write_submitted",
                                                     "read_completed", "write_completed"))
                    and effect["backing_live"] == before["backing_live"] == 0,
                    name + ": independent target used a physical backing route")
            require(effect["cap_pages"] == effect["ram_pages"] * 20 // 100,
                    name + ": independent finite cap differs from contract")
        if name == "zero_control":
            require(residency and residency["pattern"] == "zero" and residency["pages"] == 8192
                    and residency["nonresident"] * 10 >= residency["pages"] * 9
                    and data["checked_words"] >= residency["pages"] * 512 and data["completed_faults"] > 0,
                    "zero control lacks actual swapped nonresident targets and full data")
            require(all(changes[key] == 0 for key in ("compressed_loads", "raw_loads", "published",
                    "charge_calls", "charged_total_bytes", "read_submitted", "write_submitted",
                    "read_completed", "write_completed"))
                    and effect["compressed_live"] == before["compressed_live"] == 0
                    and effect["backing_live"] == before["backing_live"] == 0,
                    "zero pages counted as compressed decoder proof")
        if name in ("incompressible_control", "incompressible_fallback"):
            require(residency and residency["pattern"] == "incompressible"
                    and changes["incompressible_rejects"] > 0 and changes["compressed_loads"] == 0,
                    name + ": real incompressible refusal absent")
        if name in ("no_target_retention", "incompressible_control", "swap_charge_denied"):
            require(all(changes[key] == 0 for key in ("read_completed", "write_completed"))
                    and after["backing_live"] == 0, name + ": retention used a physical target")
            require(any(event["event"] == "op_end" and event["kind"] == "store"
                        and event["flags"] & 512 and event["flags"] & 1 for event in events),
                    name + ": authoritative locked input retention unobserved")
        if name == "cap_bound":
            require(changes["cap_rejects"] > 0 and effect["pool_backing_pages"] <= effect["cap_pages"],
                    "allocator-page cap effect missing")
        if name == "swap_charge_denied":
            require(changes["backing_charge_denials"] > 0, "physical swap charge denial missing")
        if name in ("physical_fallback", "incompressible_fallback", "physical_regression"):
            require(changes["write_completed"] > 0 and changes["read_completed"] > 0
                    and changes["compressed_loads"] == 0, name + ": actual physical completions missing")
            if name in ("physical_fallback", "physical_regression"):
                require(effect["cap_pages"] == 0 and changes["bypasses"] > 0
                        and changes["published"] == 0, name + ": physical admission bypass missing")
        if name == "independent_large_folio":
            require(any(event["kind"] == "store" and event["event"] == "op_begin" and event["order"] > 0
                        for event in events), "actual higher-order frontend input absent")
        if name in ("independent_node0", "independent_node1"):
            node = int(name[-1])
            require(any(event["event"] == "store_alloc" and event["requested_nid"] == node
                        and event["actual_node_mask"] == 1 << node and event["node_pages"] > 0
                        for event in events), "actual allocator node placement absent")
    if name in C2_FAILPOINTS:
        point = C2_FAILPOINTS[name]
        hits = [event for event in events if event["event"] == "hook_hit" and event["stage"] == point]
        require(len(hits) == 1 and hits[0]["flags"] & 16
                and hits[0]["result"] == (-5 if "error" in name or name == "decode_old_backing" else -12),
                name + ": exact once-only injection not exercised")
        hit = hits[0]
        armed = [item for item in record["controls"] if item["command"] == "arm" and item["point"] == point]
        if name == "init_refusal":
            require(any(item["command"] == "prepare_create" for item in record["controls"]), "init ticket absent")
        else:
            require(len(armed) == 1 and armed[0]["generation"] == hit["generation"]
                    and armed[0]["count"] == hit["count"] > 0
                    and armed[0]["order"] == hit["order"] and armed[0]["subpage"] == hit["subpage"]
                    and (armed[0]["key"] == "next" or armed[0]["key"] == hit["key"]),
                    "injected effect differs from its exact once-only selector")
        operation = [event for event in events if
                     (event["generation"], event["op"]) == (hit["generation"], hit["op"])]
        require(operation[0]["event"] == "op_begin" and operation[-1]["event"] == "op_end",
                name + ": injected operation incomplete")
        end = operation[-1]
        if name == "charge_refusal":
            require(not hit["flags"] & 32
                    and not any(event["event"] == "charge_call" and event["subpage"] == hit["subpage"]
                                for event in operation), "injected charge refusal mislabeled as a core call")
        if name in ("entry_refusal", "charge_refusal", "publish_refusal",
                    "rollback_first", "rollback_middle", "rollback_last"):
            require(end["allocated"] == end["rollback"] and end["published"] == end["retired"]
                    and end["flags"] & 512, name + ": incomplete rollback/input preservation")
        if name.startswith("rollback_"):
            pages = 1 << hit["order"]
            selected = {"rollback_first": 0, "rollback_middle": pages // 2, "rollback_last": pages - 1}[name]
            require(hit["order"] > 0 and hit["subpage"] == selected
                    and operation[0]["order"] == hit["order"], "actual high-order rollback position missing")
            if selected:
                require(end["allocated"] > 1 and end["charged"] > 0, "preceding subpage ownership unobserved")
        if name == "decode_old_backing":
            require(hit["flags"] & 128 and end["flags"] & 256
                    and not end["flags"] & 2
                    and any(event["event"] == "folio_unlock" for event in operation)
                    and not any(event["event"] == "bio_submit" and event["kind"] == "load" for event in operation),
                    "decode error fell through or lost the newer compressed source")
            older = [event for event in events if event["kind"] == "store" and event["event"] == "bio_complete"
                     and event["result"] == 0 and event["key"] == hit["key"] and event["seq"] < hit["seq"]]
            require(older and any(event["event"] == "publish" and event["key"] == hit["key"]
                    and older[-1]["seq"] < event["seq"] < hit["seq"] for event in events),
                    "same-key older completed physical then newer compressed version absent")
            prior = older[-1]
            newer = [event for event in events if event["event"] == "publish"
                     and event["key"] == hit["key"] and prior["seq"] < event["seq"] < hit["seq"]]
            require(prior["data_generation"] > 0 and newer[-1]["data_generation"] > prior["data_generation"]
                    and hit["data_generation"] == newer[-1]["data_generation"],
                    "retained overwrite data generation missing")
            selected = [event for event in events if event["key"] == hit["key"]]
            names = [event["event"] for event in selected]
            for required_event in ("retained_folio_get", "retained_rewrite_begin",
                                   "retained_rewrite_end", "retained_folio_put"):
                require(names.count(required_event) == 1, "retained preparation ownership transition missing")
            retained = {event["event"]: event for event in selected if event["event"].startswith("retained_")}
            require(retained["retained_folio_get"]["seq"] < prior["seq"]
                    < retained["retained_rewrite_begin"]["seq"] < newer[-1]["seq"]
                    < retained["retained_rewrite_end"]["seq"] < retained["retained_folio_put"]["seq"] < hit["seq"]
                    and retained["retained_rewrite_end"]["result"] == 0,
                    "retained preparation did not follow real physical completion then compressed publication")
            require(not any(event["event"] == "bio_complete" and event["kind"] == "store"
                            and prior["seq"] < event["seq"] < hit["seq"] for event in selected),
                    "second physical write substituted for retained compressed rewrite")
        if name in ("write_completion_error", "read_completion_error"):
            index = operation.index(hit)
            require(index > 0 and operation[index - 1]["event"] == "bio_complete"
                    and operation[index - 1]["flags"] & 64 and hit["physical_key"] > 0
                    and operation[index - 1]["physical_key"] == hit["physical_key"],
                    "injected error never reached a real BIO completion")
            require(any(event["event"] == "bio_submit" for event in operation[:index]),
                    "BIO completion lacks its submitted request")
            actions = [event["event"] for event in operation[index + 1:]
                       if event["event"] in {"folio_redirty", "folio_uptodate", "folio_end_writeback",
                                             "folio_unlock", "completion_owner_return"}]
            expected_actions = (["folio_redirty", "folio_end_writeback", "completion_owner_return"]
                                if name == "write_completion_error" else
                                ["folio_unlock", "completion_owner_return"])
            require(actions == expected_actions, "actual completion-owner action sequence missing")
            if name == "write_completion_error":
                require(any(event["event"] == "bio_complete" and event["kind"] == "store"
                        and event["seq"] > end["seq"] and event["key"] == hit["key"] and event["result"] == 0
                        for event in events), "write redirty/recovery not observed")
            else:
                require("folio_uptodate" not in actions, "failed read was marked uptodate")
    if name in C2_RACES and name != "legacy_pool_offline":
        begins = {(event["generation"], event["op"]): event for event in events if event["event"] == "op_begin"}
        overlaps = [event for event in events if event["event"] == "overlap"]
        required_pairs = {
            "mixed_load_free": {frozenset(("load", "invalidate"))},
            "mixed_live_destroy": {frozenset(("load", "destroy"))},
            "fault_cow_invalidate": {frozenset(("load", "invalidate"))},
            "reused_slot_overlap": {frozenset(("load", "invalidate")), frozenset(("load", "store"))},
            "live_destroy_overlap": {frozenset(("load", "destroy"))},
            "backing_swapoff_overlap": {frozenset(("load", "backing_swapoff")),
                                        frozenset(("store", "backing_swapoff"))},
        }
        require(overlaps and any(frozenset((event["kind"], begins[(event["generation"], event["peer"])]["kind"]))
                                 in required_pairs[name] for event in overlaps),
                name + ": required actual operation-kind overlap absent")
        holds = [event for event in events if event["event"] == "hold_enter"]
        released = [event for event in events if event["event"] == "hold_release"]
        selectors = [item for item in controls if item["command"] == "hold"]
        require(len(holds) == len(released) == len(selectors) == 1
                and holds[0]["op"] == released[0]["op"]
                and released[0]["result"] == 0 and selectors[0]["point"] == holds[0]["stage"]
                and selectors[0]["generation"] == holds[0]["generation"]
                and (selectors[0]["key"] == "next" or selectors[0]["key"] == holds[0]["key"])
                and any(holds[0]["seq"] < event["seq"] < released[0]["seq"] for event in overlaps),
                name + ": actual selected bounded hold interval absent")
        if name == "backing_swapoff_overlap":
            require(effect["backing_live"] > 0 and any(event["event"] == "backing_free"
                    and event["physical_key"] > 0 for event in events),
                    "backing swapoff had no live actual association and retirement")
    if name in ("live_destroy", "live_destroy_overlap", "mixed_live_destroy"):
        require(effect["entries_live"] > 0 and residency and residency["nonresident"] > 0
                and any(event["kind"] == "destroy" and event["event"] == "op_end"
                        and event["result"] == 0 for event in events),
                name + ": destruction had no live tested objects or actual completed operation")
    if name in ("reused_slot", "reused_slot_overlap"):
        reuse = record.get("reuse", {})
        require(reuse and reuse["type"] == header["type"] and reuse["generation"] == header["generation"]
                and reuse["old_key"] == reuse["new_key"]
                and 0 < reuse["old_pattern_generation"] < reuse["new_pattern_generation"]
                and reuse["old_nonresident"] == reuse["new_nonresident"] == 1
                and reuse["checked_old_words"] == reuse["checked_new_words"] == 512
                and reuse["corrupt_words"] == 0 and residency
                and residency["pattern_generation"] == reuse["new_pattern_generation"]
                and residency["key_first"] <= reuse["new_key"] <= residency["key_last"],
                name + ": actual old/new key, data and nonresident observations missing")
        publications = [event for event in events if event["event"] == "publish"
                        and event["key"] == reuse["new_key"]]
        require(len(publications) >= 2 and publications[0]["key"] == publications[-1]["key"]
                and any(event["event"] == "release" and event["key"] == publications[0]["key"]
                        and publications[0]["seq"] < event["seq"] < publications[-1]["seq"]
                        for event in events), name + ": real key retirement/reuse absent")


def c2_compression_evidence(text, expected_case, binding):
    catalog = configuration_catalog()
    require(isinstance(expected_case, dict), "missing C2 phase contract")
    group = expected_case["group"]
    spec = catalog.c2_correctness_group(group, expected_case["config_id"], expected_case["topology_id"])
    expected = spec["subcases"]
    begin, end = "COMPRESSION_GROUP_BEGIN " + group, "COMPRESSION_GROUP_END " + group
    require(text.splitlines().count(begin) == text.splitlines().count(end) == 1, "incomplete C2 group")
    prefix, body = text.split(begin + "\n", 1)
    body, suffix = body.split("\n" + end, 1)
    require(not re.search(r"^COMPRESS(?:ION)?_", prefix + suffix, re.M), "C2 phase outside its group")
    lines, cursor, records, tokens = body.splitlines(), 0, [], set()
    begin_keys = ("schema", "contract", "role", "source", "case", "phase", "frontend", "type", "generation", "token")
    while cursor < len(lines):
        header = c2_fields(lines[cursor], "COMPRESS_BEGIN", begin_keys)
        cursor += 1
        require(len(records) < len(expected) and header["schema"] == "2"
                and header["contract"] == binding["contract_id"] and header["role"] == binding["source_role"]
                and header["source"] == binding["source_commit"] and header["case"] == expected_case["id"]
                and header["phase"] == expected[len(records)], "C2 phase identity/order mismatch")
        name = header["phase"]
        require(header["frontend"] in ("legacy", "independent", "physical", "mixed"), "unknown phase frontend")
        for key in ("type", "generation", "token"):
            header[key] = c2_uint(header[key], key, 31 if key == "type" else (1 << 64) - 1)
        require(header["token"] > 0 and header["token"] not in tokens, "duplicate C2 phase token")
        tokens.add(header["token"])
        record = {"phase": name, "identity": header, "snapshots": {}, "events": [],
                  "reset": False, "test_config": expected_case["config_id"].startswith(("c2-debug-", "c2-race-")),
                  "swaps": {}, "policies": {}, "cpu": {}, "legacy_states": {}, "legacy_pools": {},
                  "config_id": expected_case["config_id"],
                  "controls": [], "residencies": {}, "positions": {}}
        state, points = "observations", []
        while cursor < len(lines):
            line = lines[cursor]
            cursor += 1
            if line.startswith("COMPRESS_SWAPS "):
                values = c2_fields(line, "COMPRESS_SWAPS", ("phase", "point"))
                point = values["point"]
                require(state == "observations" and values["phase"] == name
                        and point in ("before", "effect", "after", "reset") and point not in record["swaps"],
                        "duplicate or misplaced raw topology")
                marker = "COMPRESS_SWAPS_END phase=" + name + " point=" + point
                raw = []
                while cursor < len(lines) and lines[cursor] != marker:
                    raw.append(lines[cursor])
                    cursor += 1
                require(cursor < len(lines), "truncated raw topology")
                cursor += 1
                record["swaps"][point] = c2_swap_table(raw)
                record["positions"]["swaps:" + point] = cursor
            elif line.startswith("COMPRESS_POLICY "):
                values = c2_policy(line)
                point = values.pop("point")
                require(state == "observations" and values.pop("phase") == name
                        and point not in record["policies"], "duplicate or misplaced policy readback")
                record["policies"][point] = values
            elif line.startswith("COMPRESS_CPU "):
                values = c2_fields(line, "COMPRESS_CPU", ("phase", "point", "target", "online"))
                point = values.pop("point")
                require(state == "observations" and values.pop("phase") == name
                        and point in ("before", "offline", "online", "reset") and point not in record["cpu"],
                        "duplicate or misplaced CPU observation")
                values["target"] = c2_uint(values["target"], "CPU target", 3)
                require(values["target"] > 0, "CPU0 may not be offlined")
                c2_cpu_list(values["online"])
                record["cpu"][point] = values
                record["positions"]["cpu:" + point] = cursor
            elif line.startswith("COMPRESS_LEGACY_STATE "):
                values = c2_fields(line, "COMPRESS_LEGACY_STATE", C2_LEGACY_STATE_KEYS)
                point = values.pop("point")
                require(state == "observations" and values.pop("phase") == name
                        and point in ("before", "effect", "after") and point not in record["legacy_states"],
                        "duplicate or misplaced ordinary state")
                values = {key: c2_uint(value, key) for key, value in values.items()}
                require(values["epoch"] > 0 and values["owner"] > 0 and values["type"] < 32,
                        "ordinary state identity missing")
                record["legacy_states"][point] = values
            elif line.startswith("COMPRESS_LEGACY_POOL_BEGIN "):
                values = c2_fields(line, "COMPRESS_LEGACY_POOL_BEGIN", ("phase", "point"))
                point = values["point"]
                require(state == "observations" and values["phase"] == name
                        and point in ("before", "switched") and point not in record["legacy_pools"]
                        and cursor + 1 < len(lines), "duplicate or misplaced actual pool observation")
                raw = c2_fields(lines[cursor], "XSWAP_LEGACY_POOL",
                                ("schema", "token", "epoch", "type", "owner", "pool", "codec"))
                require(raw["schema"] == "1" and lines[cursor + 1] ==
                        "COMPRESS_LEGACY_POOL_END phase=" + name + " point=" + point,
                        "ordinary pool observation envelope")
                c2_identifier(raw["codec"])
                record["legacy_pools"][point] = {key: value if key == "codec" else c2_uint(value, key)
                                                for key, value in raw.items()}
                cursor += 2
            elif line.startswith("COMPRESS_LEGACY_STORE_BEGIN "):
                values = c2_fields(line, "COMPRESS_LEGACY_STORE_BEGIN", ("phase",))
                require(state == "observations" and values["phase"] == name
                        and "legacy_store" not in record and cursor + 1 < len(lines),
                        "duplicate or misplaced ordinary publication")
                raw = c2_fields(lines[cursor], "XSWAP_LEGACY_STORE",
                                ("schema", "token", "epoch", "type", "owner", "pool", "key", "order", "length"))
                require(raw["schema"] == "1" and lines[cursor + 1] == "COMPRESS_LEGACY_STORE_END phase=" + name,
                        "ordinary publication envelope")
                record["legacy_store"] = {key: c2_uint(value, key) for key, value in raw.items()}
                cursor += 2
            elif line.startswith("XSWAP_LEGACY_EVENTS_BEGIN "):
                require(state == "observations" and "legacy_events" not in record,
                        "duplicate or misplaced ordinary journal")
                raw = [line]
                while cursor < len(lines) and not lines[cursor].startswith("XSWAP_LEGACY_EVENTS_END "):
                    raw.append(lines[cursor])
                    cursor += 1
                require(cursor < len(lines), "truncated ordinary journal")
                raw.append(lines[cursor])
                cursor += 1
                record["legacy_events"] = c2_legacy_events(raw, header["token"])
                record["positions"]["legacy_events"] = cursor
            elif line.startswith("XSWAP_CONTROL "):
                require(state == "observations", "control acknowledgement after phase end")
                values = c2_control(line)
                require("token" not in values or values["token"] == header["token"], "control token mismatch")
                values["_position"] = cursor
                record["controls"].append(values)
            elif line.startswith("COMPRESS_SNAPSHOT "):
                values = c2_fields(line, "COMPRESS_SNAPSHOT", ("phase", "point"))
                point = values["point"]
                require(state == "observations" and values["phase"] == name
                        and point in ("before", "effect", "after", "reset") and point not in points,
                        "duplicate or misplaced C2 snapshot")
                require(not points or ("before", "effect", "after", "reset").index(point)
                        > ("before", "effect", "after", "reset").index(points[-1]), "C2 snapshot order")
                points.append(point)
                scalars = []
                while cursor < len(lines) and lines[cursor].startswith("XSWAP_FRONTEND_BEGIN "):
                    start = cursor
                    cursor += len(C2_SNAPSHOT_KEYS) + 2
                    require(cursor <= len(lines), "truncated frontend snapshot")
                    scalars.append(c2_snapshot(lines[start:cursor]))
                require(scalars and cursor < len(lines)
                        and lines[cursor] == "COMPRESS_SNAPSHOT_END phase=" + name + " point=" + point,
                        "C2 snapshot terminator missing")
                cursor += 1
                require(len({item["generation"] for item in scalars}) == len(scalars),
                        "duplicate frontend generation in one snapshot point")
                record["snapshots"][point] = scalars
                record["positions"]["snapshot:" + point] = cursor
            elif line.startswith("XSWAP_EVENTS_BEGIN "):
                require(state == "observations" and not record["events"], "duplicate C2 journal window")
                raw = [line]
                while cursor < len(lines) and not lines[cursor].startswith("XSWAP_EVENTS_END "):
                    raw.append(lines[cursor])
                    cursor += 1
                require(cursor < len(lines), "truncated C2 journal")
                raw.append(lines[cursor])
                cursor += 1
                record["events"] = c2_events(raw, header["token"])
                record["positions"]["events"] = cursor
            elif line.startswith("COMPRESS_RESIDENCY "):
                values = c2_fields(line, "COMPRESS_RESIDENCY",
                    ("phase", "frontend", "pattern", "pattern_generation", "pages", "swapped", "nonresident", "type", "key_first", "key_last"))
                frontend = values.pop("frontend")
                require(state == "observations" and values.pop("phase") == name
                        and frontend in ("independent", "legacy", "physical") and frontend not in record["residencies"]
                        and values["pattern"] in ("nonzero", "zero", "incompressible"), "C2 residency identity")
                record["residencies"][frontend] = {key: value if key == "pattern" else c2_uint(value, key)
                                                    for key, value in values.items()}
            elif line.startswith("COMPRESS_REUSE "):
                values = c2_fields(line, "COMPRESS_REUSE", ("phase", "type", "generation", "old_key",
                    "new_key", "old_pattern_generation", "new_pattern_generation", "old_nonresident",
                    "new_nonresident", "checked_old_words", "checked_new_words", "corrupt_words"))
                require(state == "observations" and values.pop("phase") == name
                        and name in ("reused_slot", "reused_slot_overlap") and "reuse" not in record,
                        "duplicate or misplaced actual key reuse observation")
                record["reuse"] = {key: c2_uint(value, key) for key, value in values.items()}
            elif line.startswith("COMPRESS_DATA "):
                values = c2_fields(line, "COMPRESS_DATA",
                                   ("phase", "checked_words", "corrupt_words", "completed_faults", "child_signal"))
                require(state == "observations" and "data" not in record and values.pop("phase") == name,
                        "duplicate or misplaced C2 data result")
                record["data"] = {key: c2_uint(value, key) for key, value in values.items()}
            elif line == "COMPRESS_KTAP_BEGIN suite=page_compress":
                require(state == "observations" and name == "library_unit" and "ktap" not in record,
                        "unexpected C2 KUnit block")
                raw = []
                while cursor < len(lines) and lines[cursor] != "COMPRESS_KTAP_END suite=page_compress":
                    raw.append(lines[cursor])
                    cursor += 1
                require(cursor < len(lines), "truncated C2 KUnit block")
                cursor += 1
                record["ktap"] = "\n".join(raw) + "\n"
            elif line == "COMPRESS_PHYSICAL_BEGIN":
                require(state == "observations" and name == "physical_regression"
                        and "physical" not in record, "unexpected physical regression block")
                raw = []
                while cursor < len(lines) and lines[cursor] != "COMPRESS_PHYSICAL_END":
                    raw.append(lines[cursor])
                    cursor += 1
                require(cursor < len(lines), "truncated physical regression block")
                cursor += 1
                physical_gates, physical_metrics = correctness_evidence("\n".join(raw), "disk", "xswap")
                record["physical"] = {"gates": physical_gates, "metrics": physical_metrics}
            elif line.startswith("COMPRESS_LEGACY_BEGIN "):
                values = c2_fields(line, "COMPRESS_LEGACY_BEGIN", ("epoch", "type"))
                require(state == "observations" and "legacy" not in record, "duplicate legacy block")
                marker = "COMPRESS_LEGACY_END epoch=" + values["epoch"] + " type=" + values["type"]
                raw = []
                while cursor < len(lines) and lines[cursor] != marker:
                    raw.append(lines[cursor])
                    cursor += 1
                require(cursor < len(lines), "truncated legacy epoch observation")
                cursor += 1
                record["legacy"] = {"epoch": c2_uint(values["epoch"], "legacy epoch"),
                                    "type": c2_uint(values["type"], "legacy type", 31), "body": "\n".join(raw)}
            elif line.startswith("COMPRESS_RESET "):
                values = c2_fields(line, "COMPRESS_RESET", ("schema", "case", "phase", "status"))
                require(state == "observations" and values["schema"] == "2" and values["case"] == header["case"]
                        and values["phase"] == name and values["status"] in ("PASS", "FAIL", "INCOMPLETE"),
                        "C2 reset identity/order")
                record["reset"] = values["status"] == "PASS"
                state = "end"
            elif line.startswith("COMPRESS_END "):
                values = c2_fields(line, "COMPRESS_END", ("schema", "case", "phase", "status"))
                require(state == "end" and values["schema"] == "2" and values["case"] == header["case"]
                        and values["phase"] == name and values["status"] in ("PASS", "FAIL", "INCOMPLETE"),
                        "C2 end identity/order")
                record["status"] = values["status"]
                routes = record["residencies"]
                primary = "independent" if header["frontend"] in ("independent", "mixed") else header["frontend"]
                record["residency"] = routes.get(primary)
                records.append(record)
                break
            else:
                raise ValueError("unknown C2 phase record: " + line[:120])
        else:
            raise ValueError("truncated C2 phase")
    require([record["phase"] for record in records] == expected, "missing C2 phase coverage")
    gates, result, used_generations, used_epochs = {}, {}, set(), set()
    for record in records:
        try:
            phase_generations = {item["generation"] for values in record["snapshots"].values() for item in values}
            require(not phase_generations & used_generations, "frontend generation reused across completed phases")
            used_generations.update(phase_generations)
            epochs = {item["epoch"] for item in record["legacy_states"].values()}
            if record.get("legacy"):
                epochs.add(record["legacy"]["epoch"])
            if record.get("legacy_events"):
                epochs.add(record["legacy_events"]["identity"]["epoch"])
            require(len(epochs) <= 1 and not epochs & used_epochs,
                    "ordinary swapon epoch substituted or reused across completed phases")
            used_epochs.update(epochs)
            c2_phase_semantics(record)
        except ValueError as exc:
            record["evidence_error"] = str(exc)
            record["evidence_valid"] = False
        else:
            record["evidence_valid"] = True
        name = record["phase"]
        gates["compression_" + name] = record["evidence_valid"]
        result[name] = record
    gates["compression_evidence"] = all(gates.values())
    gates["compression_reset"] = all(record["reset"] for record in records)
    return gates, result


C2_ISOLATION_STRATEGY = "mlockall_current_future_target_munlock_v1"
C2_SMAPS_MAX_BYTES = 262142


def c2_hex_bytes(lines, size, maximum):
    require(0 < size <= maximum and lines and all(re.fullmatch(r"[0-9a-f]+", line)
            and len(line) % 2 == 0 and len(line) <= 128 for line in lines)
            and all(len(line) == 128 for line in lines[:-1]), "malformed bounded raw hex")
    raw = bytes.fromhex("".join(lines))
    require(len(raw) == size and raw.endswith(b"\n") and b"\x00" not in raw,
            "raw byte count, termination or encoding mismatch")
    try:
        return raw.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("raw evidence is not ASCII") from exc


def c2_smaps(raw, target_start, target_bytes):
    """Replay actual VMA permissions/flags; aggregate assertions are insufficient."""
    require(type(target_start) is int and 0 < target_start < (1 << 64)
            and target_start % 4096 == 0 and target_bytes == COMPRESSED_TARGET_BYTES
            and target_start + target_bytes < (1 << 64), "invalid isolation target")
    header = re.compile(r"^([0-9a-f]+)-([0-9a-f]+) ([r-][w-][x-][ps]) ([0-9a-f]+) "
                        r"([0-9a-f]+:[0-9a-f]+) ([0-9]+)(?:[ \t]+(.*))?$")
    maps, current = [], None
    for line in raw.splitlines():
        match = header.fullmatch(line)
        if match:
            lo, hi = int(match[1], 16), int(match[2], 16)
            require(0 < lo < hi < (1 << 64) and lo % 4096 == hi % 4096 == 0
                    and (not maps or maps[-1]["end"] <= lo), "unordered or malformed smaps range")
            current = {"start": lo, "end": hi, "perms": match[3], "offset": int(match[4], 16),
                       "device": match[5], "inode": int(match[6]), "name": match[7] or "", "fields": {}}
            maps.append(current)
            continue
        require(current is not None and ":" in line, "smaps field outside VMA")
        key, value = line.split(":", 1)
        require(re.fullmatch(r"[A-Za-z_]+", key) and key not in current["fields"],
                "duplicate or malformed smaps field")
        current["fields"][key] = value.strip()
    require(maps, "empty smaps proof")
    result = dict(locked_mappings=0, locked_mapping_bytes=0, locked_resident_bytes=0,
                  target_mappings=0, target_unlocked_bytes=0, special_mappings=0,
                  inaccessible_mappings=0)
    cursor, target_end = target_start, target_start + target_bytes
    specials = {"[vvar]", "[vvar_vclock]", "[vdso]", "[vsyscall]"}
    for mapping in maps:
        attrs = mapping["fields"]
        require("VmFlags" in attrs and bool(re.fullmatch(r"(?:[a-z]{2}(?: [a-z]{2})*)?", attrs["VmFlags"])),
                "missing or malformed smaps VmFlags")
        flags = attrs["VmFlags"].split()
        require(len(flags) == len(set(flags)), "duplicate smaps VmFlags")
        require(all((mapping["perms"][index] == letter) == (flag in flags)
                    for index, letter, flag in ((0, "r", "rd"), (1, "w", "wr"), (2, "x", "ex"), (3, "s", "sh"))),
                "smaps header permissions differ from actual VmFlags")

        def kib(name):
            value = attrs.get(name, "")
            require(bool(re.fullmatch(r"(?:0|[1-9][0-9]*) kB", value)), "missing actual smaps " + name)
            return int(value.split()[0]) * 1024

        length = mapping["end"] - mapping["start"]
        require(kib("Size") == length and kib("Locked") <= length, "smaps size/locked arithmetic")
        intersects = mapping["start"] < target_end and mapping["end"] > target_start
        if intersects:
            require(mapping["start"] == cursor and mapping["end"] <= target_end
                    and mapping["perms"] == "rw-p" and mapping["device"] == "00:00"
                    and mapping["inode"] == mapping["offset"] == 0 and not mapping["name"]
                    and "lo" not in flags and "lf" not in flags and "nh" in flags
                    and kib("Locked") == 0 and kib("AnonHugePages") == 0
                    and kib("KernelPageSize") == kib("MMUPageSize") == 4096,
                    "target VMA is not exact unlocked anonymous base-page coverage")
            cursor = mapping["end"]
            result["target_mappings"] += 1
            result["target_unlocked_bytes"] += length
        elif mapping["name"] in specials:
            result["special_mappings"] += 1
        elif mapping["perms"][:3] == "---":
            result["inaccessible_mappings"] += 1
        else:
            require(mapping["perms"][3] == "p" and "lo" in flags and "lf" not in flags,
                    "accessible observer VMA is shared or unlocked")
            result["locked_mappings"] += 1
            result["locked_mapping_bytes"] += length
            result["locked_resident_bytes"] += kib("Locked")
    require(cursor == target_end and result["target_unlocked_bytes"] == target_bytes
            and result["locked_mappings"] > 0, "incomplete target or observer isolation coverage")
    return result


def c2_isolation_evidence(text):
    setup = "COMPRESSED_ISOLATION_SETUP mlockall=0 munlock=0 flags=current_future target_bytes=134217728"
    lines = text.splitlines()
    require([line for line in lines if line.startswith("COMPRESSED_ISOLATION_SETUP")] == [setup],
            "missing exact observer isolation syscalls")
    keys = ("phase", "strategy", "target_start", "target_bytes", "bytes", "encoding")
    end_keys = ("phase", "locked_mappings", "locked_mapping_bytes", "locked_resident_bytes",
                "target_mappings", "target_unlocked_bytes", "special_mappings", "inaccessible_mappings")
    records, i = [], 0
    while i < len(lines):
        if not lines[i].startswith("COMPRESSED_ISOLATION_BEGIN"):
            require(not lines[i].startswith("COMPRESSED_ISOLATION_END"), "unpaired isolation terminator")
            i += 1
            continue
        begin = c2_fields(lines[i], "COMPRESSED_ISOLATION_BEGIN", keys)
        require(begin["strategy"] == C2_ISOLATION_STRATEGY and begin["encoding"] == "hex",
                "unknown isolation strategy or encoding")
        values = {key: c2_uint(begin[key], key) for key in ("target_start", "target_bytes", "bytes")}
        i += 1
        encoded = []
        while i < len(lines) and not lines[i].startswith("COMPRESSED_ISOLATION_END"):
            encoded.append(lines[i])
            i += 1
        require(i < len(lines), "truncated raw smaps proof")
        end = c2_fields(lines[i], "COMPRESSED_ISOLATION_END", end_keys)
        require(end.pop("phase") == begin["phase"], "isolation phase terminator mismatch")
        raw = c2_hex_bytes(encoded, values["bytes"], C2_SMAPS_MAX_BYTES)
        derived = c2_smaps(raw, values["target_start"], values["target_bytes"])
        require({key: c2_uint(value, key) for key, value in end.items()} == derived,
                "isolation aggregates differ from actual smaps")
        records.append(dict(phase=begin["phase"], **values, **derived))
        i += 1
    require([record["phase"] for record in records] == ["before_reclaim", "after_measurement"]
            and len({record["target_start"] for record in records}) == 1,
            "missing, duplicate, substituted or reordered isolation proof")
    return records


def c2_probe_evidence(text, binding):
    names = ("kprobe_events", "current_tracer", "buffer_size_kb", "event_filter",
             "event_enable", "tracing_on", "event_format", "trace_options")
    lines, records, i = text.splitlines(), {}, 0
    while i < len(lines):
        if not lines[i].startswith("COMPRESSED_PROBE_READBACK_BEGIN"):
            require(not lines[i].startswith("COMPRESSED_PROBE_READBACK_END"), "unpaired probe readback")
            i += 1
            continue
        begin = c2_fields(lines[i], "COMPRESSED_PROBE_READBACK_BEGIN",
                          ("phase", "name", "bytes", "encoding"))
        name = begin["name"]
        require(begin["phase"] == "setup" and begin["encoding"] == "hex"
                and len(records) < len(names) and name == names[len(records)],
                "missing, duplicate or unordered probe readback")
        size = c2_uint(begin["bytes"], "probe readback bytes")
        encoded, i = [], i + 1
        while i < len(lines) and not lines[i].startswith("COMPRESSED_PROBE_READBACK_END"):
            encoded.append(lines[i])
            i += 1
        require(i < len(lines) and lines[i] == "COMPRESSED_PROBE_READBACK_END name=" + name,
                "probe readback terminator mismatch")
        records[name] = c2_hex_bytes(encoded, size, 65534)
        i += 1
    require(tuple(records) == names, "incomplete probe registration proof")
    registration = "r64:swap_next_timing/decode_return " + binding["observer_symbol"] + " ret=$retval:s64"
    selected = [line for line in records["kprobe_events"].splitlines()
                if ":swap_next_timing/decode_return" in line]
    require(selected == [registration], "probe registered against wrong symbol, fetch type or maxactive")
    for name, expected in (("current_tracer", "nop\n"), ("buffer_size_kb", "16\n"),
                           ("event_enable", "1\n"), ("tracing_on", "1\n")):
        require(records[name] == expected, "unexpected actual probe " + name)
    pid = re.fullmatch(r"common_pid == ([1-9][0-9]*)\n", records["event_filter"])
    require(pid and int(pid[1]) < (1 << 31), "probe is not filtered to one actual PID")
    fmt = records["event_format"].splitlines()
    require([line for line in fmt if line.startswith("name:")] == ["name: decode_return"],
            "wrong actual probe event format")
    returns = [line for line in fmt if " ret;" in line]
    require(len(returns) == 1 and re.fullmatch(
        r"\s*field:s64 ret;\s*offset:24;\s*size:8;\s*signed:1;", returns[0]),
        "return format is not signed 64-bit at the actual event offset")
    options = records["trace_options"].splitlines()
    required = ("context-info", "nolatency-format", "nohex", "nobin", "noraw", "noverbose")
    require(all(options.count(value) == 1 and (value[2:] if value.startswith("no")
                else "no" + value) not in options for value in required), "ambiguous trace rendering options")
    return {"pid": int(pid[1]), "symbol": binding["observer_symbol"], "maxactive": 64,
            "buffer_size_kb": 16, "return_type": "s64", "readbacks": list(records)}


def c2_compressed_timing_evidence(text, metrics, binding):
    keys = ("id", "instrumented", "clock", "maxactive", "contract", "role", "source",
            "frontend", "symbol", "buffer_kb", "success_return")
    lines = text.splitlines()
    observers = [line for line in lines if line.startswith("COMPRESSED_OBSERVER")]
    require(len(observers) == 1, "missing or duplicate matched observer")
    observer = c2_fields(observers[0], "COMPRESSED_OBSERVER", keys)
    expected = dict(id=binding["observer_id"], instrumented="1", clock="monotonic_raw", maxactive="64",
                    contract=binding["contract_id"], role=binding["source_role"], source=binding["source_commit"],
                    frontend=binding["frontend"], symbol=binding["observer_symbol"], buffer_kb="16", success_return="0")
    require(observer == expected, "matched observer source/frontend identity mismatch")
    probe = c2_probe_evidence(text, binding)
    isolation = c2_isolation_evidence(text)
    types = [c2_uint(value, "timing type", 31) for value in re.findall(r"^XSWAP_TYPE ([0-9]+)$", text, re.M)]
    require(len(types) == 1 and len([line for line in lines if line.startswith("XSWAP_TYPE")]) == 1,
            "missing actual timing swap type")
    kind = types[0]
    topology = re.findall(r"^COMPRESSED_TOPOLOGY phase=(before|after) devices=(\d+) physical=(\d+) type=(\d+)$", text, re.M)
    require(topology == [("before", "1", "0", str(kind)), ("after", "1", "0", str(kind))]
            and len([line for line in lines if line.startswith("COMPRESSED_TOPOLOGY")]) == 2,
            "timed frontend has backing or substituted topology")
    require(lines.count("SWAPS_BEGIN") == lines.count("SWAPS_END") == 1,
            "missing or duplicate actual timing swap table")
    swaps = c2_swap_table((block(text, "SWAPS_BEGIN", "SWAPS_END") or "").splitlines())
    topology_ok = (set(swaps) == {"xswap" + str(kind)} and swaps["xswap" + str(kind)]["priority"] == 32767
                   and lines.count("BACKEND_DEVICE none") == 1)
    raw = exactly(text, r"^COMPRESSED_SAMPLES seq=(\d+) rand=(\d+) target_checks=(\d+) decoded=(\d+) trace_lost=(\d+) probe_missed=(\d+) probe_hits=(\d+)$")
    seq, rand, checks, decoded, lost, missed, hits = map(int, raw)
    counts_ok = (seq > 0 and rand > 0 and checks == decoded == seq + rand and lost == missed == 0
                 and hits >= decoded and seq == (metrics.get("swapin_seq") or {}).get("samples")
                 and rand == (metrics.get("swapin_rand") or {}).get("samples"))
    swapped = metrics.get("swapin_swapped") or {}
    half = COMPRESSED_TARGET_BYTES // 4096 // 2
    counts_ok &= (swapped.get("pages") == half * 2 and swapped.get("swapped") == checks
                  and seq * 10 >= half * 9 and rand * 10 >= half * 9 and seq <= half and rand <= half)
    counts_ok &= all(len([line for line in lines if line.startswith(marker)]) == 1 for marker in
                     ("COMPRESSED_SAMPLES", "SWAPIN_SEQ ", "SWAPIN_RAND ", "SWAPIN_SWAPPED "))
    states = {}
    for line in [line for line in lines if line.startswith("COMPRESSED_STATE")]:
        row = c2_fields(line, "COMPRESSED_STATE", ("phase", "stored_pages", "pool_bytes", "incompressible_pages"))
        phase = row.pop("phase")
        require(phase not in states, "duplicate timing state")
        states[phase] = {key: c2_uint(value, key) for key, value in row.items()}
    require(list(states) == ["before", "stored", "after"], "missing or reordered timing states")
    before, stored, after = (states[phase] for phase in ("before", "stored", "after"))
    storage_ok = (stored["stored_pages"] - before["stored_pages"] >= checks
                  and stored["pool_bytes"] > before["pool_bytes"]
                  and before["incompressible_pages"] == stored["incompressible_pages"] == after["incompressible_pages"] == 0)
    phase = metrics.get("swapin_vmstat_delta") or {}
    total = metrics.get("vmstat_delta") or {}
    counters_ok = all(complete_counter_block(text, "VMSTAT", tag,
        ("pswpin", "pswpout", "zswpin", "zswpout", "zswpwb", "swpin_zero", "swpout_zero", "swap_ra", "swap_ra_hit"))
        for tag in ("before", "end", "swapin_start", "swapin_end"))
    route_ok = (bool(total) and all(value >= 0 for value in total.values())
                and all(value >= 0 for value in phase.values())
                and all(phase.get(key) == 0 for key in ("pswpin", "pswpout", "zswpwb")))
    actual = {}
    if binding["source_role"] == "candidate":
        snapshots, cursor = {}, 0
        while cursor < len(lines):
            if not lines[cursor].startswith("COMPRESSED_FRONTEND_BEGIN"):
                require(not lines[cursor].startswith("COMPRESSED_FRONTEND_END"), "unpaired timing frontend snapshot")
                cursor += 1
                continue
            header = c2_fields(lines[cursor], "COMPRESSED_FRONTEND_BEGIN", ("phase",))
            point = header["phase"]
            require(point not in snapshots, "duplicate timing frontend snapshot")
            end = cursor + len(C2_SNAPSHOT_KEYS) + 3
            require(end < len(lines) and lines[end] == "COMPRESSED_FRONTEND_END phase=" + point,
                    "truncated timing frontend snapshot")
            snapshots[point] = c2_snapshot(lines[cursor + 1:end])
            cursor = end + 1
        require(list(snapshots) == ["before", "stored", "after"], "missing raw timing frontend snapshots")
        zero = ("raw_live", "raw_admitted", "raw_loads", "cap_updates", "cap_rejects", "bypasses",
                "incompressible_rejects", "inflight", "store_token_active", "retained_folios_live",
                "backing_live", "backing_allocs", "backing_frees", "backing_charge_denials",
                "read_submitted", "write_submitted", "read_completed", "write_completed",
                "read_errors", "write_errors", "decode_errors", "load_misses", "pool_destroy_returned",
                "test_windows", "events_lost", "test")
        previous = None
        for point, snapshot in snapshots.items():
            require(snapshot["type"] == kind and snapshot["state"] == "active"
                    and all(snapshot[key] == 0 for key in zero)
                    and snapshot["cap_pages"] == snapshot["ram_pages"] * 20 // 100
                    and snapshot["pool_backing_pages"] < snapshot["cap_pages"],
                    "candidate timing had admission failure, test hooks, raw objects or physical traffic")
            require(states[point] == {"stored_pages": snapshot["compressed_live"],
                    "pool_bytes": snapshot["pool_backing_pages"] * 4096, "incompressible_pages": snapshot["raw_live"]},
                    "normalized timing state differs from actual frontend snapshot")
            if previous:
                require(all(snapshot[key] == previous[key] for key in
                        ("generation", "pool", "driver", "ram_pages", "cap_pages"))
                        and snapshot["snapshot"] > previous["snapshot"], "timing frontend lifetime substituted")
            previous = snapshot
        first, resident, last = (snapshots[point] for point in ("before", "stored", "after"))
        require(first["entries_live"] == first["pool_backing_pages"] == 0, "timing frontend was not initially empty")
        loads = last["compressed_loads"] - resident["compressed_loads"]
        route_ok &= (loads >= decoded and all(phase.get(key) == 0 for key in ("zswpin", "zswpout"))
                     and not any(line.startswith("COMPRESSED_LEGACY_") for line in lines))
        actual = {"frontend_snapshots": snapshots, "independent_loads": loads}
    else:
        require(not any(line.startswith("COMPRESSED_FRONTEND_") for line in lines),
                "baseline observer supplied candidate frontend proof")
        configs, limits = {}, {}
        for line in [line for line in lines if line.startswith("COMPRESSED_LEGACY_")]:
            if line.startswith("COMPRESSED_LEGACY_CONFIG "):
                row = c2_fields(line, "COMPRESSED_LEGACY_CONFIG",
                    ("phase", "codec", "max_pool_percent", "ram_pages", "cap_pages", "shrinker_enabled"))
                point = row.pop("phase")
                require(point not in configs and row["codec"] == "lzo" and row["max_pool_percent"] == "20"
                        and row["shrinker_enabled"] == "0", "legacy timing policy differs from fixed contract")
                ram, cap = c2_uint(row["ram_pages"], "legacy RAM"), c2_uint(row["cap_pages"], "legacy cap")
                require(ram > 0 and cap == ram * 20 // 100 and states.get(point, {}).get("pool_bytes", cap * 4096) < cap * 4096,
                        "legacy timing cap is binding or invalid")
                configs[point] = row
            elif line.startswith("COMPRESSED_LEGACY_LIMITS "):
                row = c2_fields(line, "COMPRESSED_LEGACY_LIMITS",
                    ("phase", "pool_limit_hit", "written_back_pages", "reject_compress_poor"))
                point = row.pop("phase")
                require(point not in limits, "duplicate legacy timing limits")
                limits[point] = {key: c2_uint(value, key) for key, value in row.items()}
            else:
                raise ValueError("unknown legacy timing record")
        require(list(configs) == list(limits) == ["before", "stored", "after"]
                and configs["before"] == configs["stored"] == configs["after"]
                and limits["before"] == limits["stored"] == limits["after"],
                "missing legacy limits or cap rejection, writeback or incompressible fallback")
        route_ok &= phase.get("zswpin", 0) >= decoded and phase.get("zswpout", 0) >= checks
        actual = {"legacy_configs": configs, "legacy_limits": limits}
    # Actual observer proof occurs outside t0-touch-t1 and brackets the reclaim/measurement.
    require(text.index("COMPRESSED_ISOLATION_BEGIN phase=before_reclaim")
            < text.index("SWAPIN_SWAPPED ")
            < text.index("COMPRESSED_STATE phase=stored")
            < text.index("COMPRESSED_STATE phase=after")
            < text.index("COMPRESSED_ISOLATION_BEGIN phase=after_measurement")
            < text.index("COMPRESSED_SAMPLES "), "isolation did not bracket target reclaim and measurement")
    data_ok = lines.count("SWAPIN_DATA_PASS") == 1 and not re.search(r"^SWAPIN_FAIL", text, re.M)
    metrics_ok = all(isinstance((metrics.get(order) or {}).get(key), (int, float))
                    and not isinstance(metrics[order][key], bool)
                    and math.isfinite(metrics[order][key]) and metrics[order][key] > 0
                    for order in ("swapin_seq", "swapin_rand") for key in ("mean_ns", "p99_ns"))
    metrics.update(compressed_observer=dict(observer, instrumented=True, maxactive=64,
                    buffer_kb=16, success_return=0), compressed_probe=probe, compressed_isolation=isolation,
                   compressed_samples=dict(seq=seq, rand=rand, target_checks=checks, decoded=decoded,
                                           trace_lost=lost, probe_missed=missed, probe_hits=hits),
                   compressed_states=states, c2_timing_actual=actual)
    return {"compressed_observer": True, "compressed_no_backing": topology_ok,
            "compressed_target_decode": bool(counts_ok), "compressed_storage": bool(storage_ok),
            "compressed_no_fallback": bool(route_ok), "compressed_counter_integrity": counters_ok,
            "compressed_data": bool(data_ok), "compressed_latency_metrics": metrics_ok,
            "compressed_observer_isolation": True, "c2_timing_adapter": True,
            "swap_activity": bool(storage_ok and route_ok), "backend_exercised": bool(storage_ok and route_ok)}


def c2_activity_evidence(records):
    """Keep independent/ordinary/physical traffic distinct at the phase boundary."""
    activity = {"independent_loads": 0, "physical_reads": 0, "physical_writes": 0,
                "legacy_loads": 0, "legacy_stores": 0}
    valid = bool(records) and all(record["evidence_valid"] for record in records.values())
    if valid:
        for record in records.values():
            snapshots = record["snapshots"]
            before = {item["generation"]: item for item in snapshots.get("before", [])}
            for after in snapshots.get("after", []):
                previous = before.get(after["generation"])
                if previous:
                    for output, key in (("independent_loads", "compressed_loads"),
                                        ("physical_reads", "read_completed"),
                                        ("physical_writes", "write_completed")):
                        activity[output] += after[key] - previous[key]
            legacy = record.get("legacy", {}).get("parsed", {})
            for old in legacy.values():
                values = old["observations"]
                for output, key in (("legacy_loads", "zswpin"), ("legacy_stores", "zswpout")):
                    activity[output] += values.get("decoded", {}).get(key, 0) - values.get("before", {}).get(key, 0)
            old = record["legacy_states"]
            if "before" in old and "after" in old:
                for output, key in (("legacy_loads", "zswpin"), ("legacy_stores", "zswpout"),
                                    ("physical_reads", "pswpin"), ("physical_writes", "pswpout")):
                    activity[output] += old["after"][key] - old["before"][key]
    traffic = valid and any(value > 0 for value in activity.values()) and all(value >= 0 for value in activity.values())
    return {"swap_activity": traffic, "backend_exercised": traffic,
            "swap_routing": valid}, activity


def parse(text, image_sha, backend, mode, workload, protocol_revision=1, *,
          config_id="standard", correctness_case=None, topology_id="single", expected_case=None, source_binding=None):
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
    if protocol_revision == 9:
        identity_ok = c2_source_identity(text, backend, mode, workload, config_id, correctness_case,
                                         topology_id, expected_case, source_binding)
        gates["configuration_identity"] = identity_ok
        gates["source_role_identity"] = identity_ok
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
        if protocol_revision == 9:
            if backend == "compressed":
                gates.update(c2_compressed_timing_evidence(text, metrics, source_binding))
            else:
                # Physical-case source/cap readback is still missing. Preserve
                # an explicit block until its independent adapter is complete.
                gates["c2_timing_adapter"] = False

    elif workload == 'compression':
        if protocol_revision == 9:
            extra_gates, subcases = c2_compression_evidence(text, expected_case, source_binding)
        else:
            extra_gates, subcases = compression_evidence(text, mode, expected_case)
        gates.update(extra_gates)
        if protocol_revision == 9:
            actual_gates, actual_activity = c2_activity_evidence(subcases)
            gates.update(actual_gates)
            metrics["c2_activity"] = actual_activity
        gates['no_new_kernel_warnings'] = gates['no_kernel_warnings']
        return dict(metrics=metrics, gates=gates, correctness_subcases=subcases)
    elif workload == 'correctness':
        if protocol_revision == 9:
            c2_gates, subcases = c2_compression_evidence(text, expected_case, source_binding)
            gates.update(c2_gates)
            metrics["c2_phases"] = subcases
        if protocol_revision in (8, 9):
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
