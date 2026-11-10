# SPDX-License-Identifier: GPL-2.0-only
"""Synthetic raw-evidence tests; these never claim executed kernel coverage."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import evidence
from configurations import GROUPS
from test_evidence import block, thp

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
PAGES = 8192
SIZE = PAGES * 4096
KTAP = ('KTAP version 1\n1..1\n    KTAP version 1\n    # Subtest: page_compress\n    1..3\n'
        '    ok 1 page_compress_alloc_rollback\n    ok 2 page_compress_partial_cleanup\n'
        '    ok 3 page_compress_numa_placement\nok 1 page_compress\n')


def unit_ktap(topology='single'):
    nodes = [0, 1] if topology in ('numa2', 'numa2-sockets-v2', 'numa2-nehalem-v3') else [0]
    comments = ''.join(f'    # page_compress_numa_placement: PAGE_COMPRESS_NUMA requested={node} actual={node} pages=1\n' for node in nodes)
    comments += f'    # page_compress_numa_placement: PAGE_COMPRESS_NUMA_TOTAL nodes={len(nodes)} placements={len(nodes)} mismatches=0\n'
    return KTAP.replace('    ok 3 page_compress_numa_placement', comments + '    ok 3 page_compress_numa_placement')


def row(group):
    return dict(copy.deepcopy(GROUPS[group]), id='test-' + group, group=group, role='candidate')


def case_log(name, mode, topology="single"):
    before_topology = dict(swap_devices=1, virtual_devices=int(mode == 'xswap'),
                           physical_devices=int(mode == 'plain'), no_backing=int(mode == 'xswap'),
                           intended_device_matches=1)
    if mode == 'xswap':
        before_topology['xswap_priority'] = 32767
    observations = {'before': dict(before_topology)}
    lines = [f'COMPRESS_BEGIN schema=1 mode={mode} case={name} bytes={SIZE}']
    if name == 'library_unit':
        observations['case'] = dict(kunit_expected=3, kunit_observed=3, kunit_failed=0, kunit_skipped=0,
                                    **{test: 1 for test in evidence.UNIT_TESTS})
    else:
        def snapshot(stored, pool, output, decoded, charge, memcg=True):
            result = dict(stored_pages=stored, pool_bytes=pool, incompressible_pages=0,
                          zswpin=decoded, zswpout=output, pswpin=0, pswpout=0,
                          memcg_present=int(memcg))
            if memcg:
                result.update(memcg_zswap_bytes=charge, memcg_zswapped_bytes=stored * 4096)
            return result
        def resident():
            return dict(target_pages=PAGES, swapped_pages=PAGES, absent_swapcache_pages=PAGES, target_type=1)
        offline = name == 'memcg_offline'
        double = name in ('codec_switch', 'guest_hotplug')
        quota = name == 'memcg_limits'
        observations['configuration'] = dict(zswap_enabled=1, shrinker_enabled=0)
        observations['fixture'] = {'isolated_memcg': 1}
        observations['before'].update(snapshot(0, 0, 0, 0, 0))
        observations['mapping_a'] = {'nonzero_pages': PAGES}
        if double:
            observations['mapping_b'] = {'nonzero_pages': PAGES}
        observations['decoded'] = snapshot(0, 0, 0 if quota else PAGES,
                                            0 if quota else PAGES, 0, not offline)
        observations['decoded']['verified_words'] = SIZE // 8 * (2 if double else 1)
        observations['cleanup'] = snapshot(0, 0, 0 if quota else PAGES,
                                            0 if quota else PAGES, 0, not offline)
        observations['reset'] = dict(before_topology, objects_and_charges_drained=1, temporary_memcg_removed=1)
        if quota:
            observations['case'] = dict(zswap_quota_bytes=0, quota_pageout_attempts=4, quota_data_verified=1)
            observations['quota'] = dict(snapshot(0, 0, 0, 0, 0), target_pages=PAGES,
                                         swapped_pages=0, absent_swapcache_pages=0)
        else:
            observations['stored'] = snapshot(PAGES, 65536, PAGES, 0, 32768)
            for phase in ('stored_old', 'stored_new') if double else ('stored_a',):
                observations[phase] = resident()
            observations['case'] = {}
        special = {
            'codec_switch': dict(codec_switched=1, old_and_new_data_verified=1),
            'invalid_codec': dict(invalid_codec_errno=22, codec_unchanged=1),
            'concurrent_fault': dict(workers=8, concurrent_target_pages=32,
                                     concurrent_absent_swapcache_pages=32, cow_parent_verified=1),
            'live_destroy': dict(destroy_live_swapped_pages=PAGES, destroy_observed=1,
                                concurrent_destroy_reader_verified=1, original_type_recreated=1),
            'memcg_offline': dict(offline_live_compressed_bytes=32768, live_memcg_removed=1),
            'guest_hotplug': dict(target_cpu=1, cpu_offline_observed=1, cpu_online_observed=1),
            'large_folio': dict(huge_input_bytes=SIZE, large_zswpout_before=0, large_zswpout_after=16),
        }
        observations['case'].update(special.get(name, {}))
        if name == 'codec_switch':
            observations['old_pool'] = snapshot(PAGES, 65536, PAGES, 0, 32768)
            observations['old_after_switch'] = resident()
        if name in ('codec_switch', 'invalid_codec'):
            observations['reset']['codec_restored'] = 1
        if name == 'guest_hotplug':
            observations['reset']['cpu_restored'] = 1
        lines.append(f'COMPRESS_CONFIG case={name} codec=lzo')
    for phase, values in observations.items():
        for key, value in values.items():
            lines.append(f'COMPRESS_OBS case={name} phase={phase} key={key} value={value}')
    if name == 'library_unit':
        lines += ['COMPRESS_KTAP_BEGIN suite=page_compress', unit_ktap(topology).rstrip(),
                  'COMPRESS_KTAP_END suite=page_compress']
    lines += [f'COMPRESS_RESET case={name} status=PASS' + (' untouched=1' if name == 'library_unit' else ''),
              f'COMPRESS_CASE case={name} status=PASS reason=ok', 'COMPRESS_END schema=1 status=PASS cases=1']
    return '\n'.join(lines) + '\n'


def group_log(group, *, topology=None, config=None):
    spec = row(group)
    if topology is not None:
        spec['topology_id'] = topology
    if config is not None:
        spec['config_id'] = config
    body = (f'COMPRESSION_GROUP_BEGIN {group}\n'
            + ''.join(case_log(name, spec['mode'], spec['topology_id']) for name in spec['subcases'])
            + f'COMPRESSION_GROUP_END {group}\n')
    return body, spec


def basic_log(backend, mode, workload, config='c1-common', topology='single', spec=None):
    command = (f'bench.image_sha=abc bench.backend={backend} bench.mode={mode} bench.workload={workload}'
               f' bench.protocol_revision=8 bench.config_id={config} bench.topology_id={topology}')
    if spec:
        command += (f" bench.correctness_case={spec['id']} bench.correctness_group={spec['group']}"
                    f" bench.compression_cases={','.join(spec['subcases'])}")
    elif backend == 'compressed':
        command += ' bench.compression_target_bytes=134217728'
    cpu = ('smpboot: CPU0: Intel fixture CPU (family: 0x6, model: 0x1a, stepping: 0x3)\n'
           if topology == 'numa2-nehalem-v3' else '')
    device = 'xswap1' if mode == 'xswap' else '/dev/zram1'
    vm0 = 'pswpin 0\npswpout 0\nzswpin 0\nzswpout 0\nzswpwb 0\nswpin_zero 0\nswpout_zero 0\nswap_ra 0\nswap_ra_hit 0'
    vm1 = vm0.replace('zswpin 0', 'zswpin 32768').replace('zswpout 0', 'zswpout 32768')
    return ('BENCH_BOOT\nCMDLINE_BEGIN\n' + command + '\nCMDLINE_END\n'
            f'GUEST_TOPOLOGY {topology}\nONLINE_NODES ' + ('0-1' if topology in ('numa2', 'numa2-sockets-v2', 'numa2-nehalem-v3') else '0') + '\n'
            'ZSWAP_ENABLED Y\n' + ('XSWAP_TYPE 1\n' if mode == 'xswap' else '')
            + 'BACKEND_DEVICE ' + ('none' if backend == 'compressed' else '/dev/zram1') + '\n'
            + f'SWAPS_BEGIN\nFilename Type Size Used Priority\n{device} partition 16384 0 32767\nSWAPS_END\n'
            + f'SWAP_PEAK_BEGIN\n{device} 131072\nSWAP_PEAK_END\n'
            + block('VMSTAT', 'before', vm0) + block('VMSTAT', 'end', vm1)
            + block('VMSTAT', 'swapin_start', vm0) + block('VMSTAT', 'swapin_end', vm1)
            + block('XSWAP', 'swapin_start', 'clusters_mapped 10\nusage_pages 0\ngrows 0\nshrinks 0')
            + block('XSWAP', 'swapin_end', 'clusters_mapped 10\nusage_pages 0\ngrows 1\nshrinks 0')
            + thp() + 'KERNEL_LOG_BEGIN\nLinux version fixture\n' + cpu
            + 'KERNEL_LOG_END\nBENCH_WORKLOAD_PASS\nBENCH_PASS\n')


def timing_log():
    return (basic_log('compressed', 'xswap', 'swapin')
            + 'COMPRESSED_OBSERVER id=pid_kretprobe_zswap_load_v1 instrumented=1 clock=monotonic_raw maxactive=64\n'
            + 'COMPRESSED_TOPOLOGY phase=before devices=1 physical=0 type=1\n'
            + 'COMPRESSED_STATE phase=before stored_pages=0 pool_bytes=0 incompressible_pages=0\n'
            + 'SWAPIN_SWAPPED pages=32768 swapped=32768 reclaim_rounds=1\n'
            + 'COMPRESSED_STATE phase=stored stored_pages=32768 pool_bytes=67108864 incompressible_pages=0\n'
            + 'COMPRESSED_TOPOLOGY phase=after devices=1 physical=0 type=1\n'
            + 'COMPRESSED_SAMPLES seq=16384 rand=16384 target_checks=32768 decoded=32768 trace_lost=0 probe_missed=0 probe_hits=32768\n'
            + 'SWAPIN_SEQ samples=16384 mean_ns=100 p99_ns=200\n'
            + 'SWAPIN_RAND samples=16384 mean_ns=110 p99_ns=220\nSWAPIN_DATA_PASS\n')


class CompressionEvidenceTests(unittest.TestCase):
    def test_every_scheduled_group_has_complete_positive_fixture(self):
        for group, spec in GROUPS.items():
            if spec['workload'] != 'compression':
                continue
            with self.subTest(group=group):
                body, expected = group_log(group)
                text = basic_log(spec['backend'], spec['mode'], 'compression', spec['config_id'], spec['topology_id'], expected) + body
                result = evidence.parse(text, 'abc', spec['backend'], spec['mode'], 'compression', 8,
                                        config_id=spec['config_id'], correctness_case=expected['id'],
                                        topology_id=spec['topology_id'], expected_case=expected)
                self.assertTrue(all(result['gates'].values()), result)
                self.assertTrue(all(r['status'] == 'PASS' and r['reset'] is True for r in result['correctness_subcases'].values()))

    def test_structural_corruption_fails_closed(self):
        text, expected = group_log('compressed-roundtrip')
        text = 'XSWAP_TYPE 1\n' + text
        marker = 'COMPRESS_OBS case=roundtrip phase=mapping_a key=nonzero_pages value=8192\n'
        for broken in (text.replace(marker, marker * 2), text.replace('COMPRESSION_GROUP_END compressed-roundtrip', ''),
                       text.replace('COMPRESS_BEGIN schema=1 mode=xswap case=roundtrip', 'COMPRESS_BEGIN schema=1 mode=plain case=roundtrip'),
                       text + marker, text.replace('COMPRESS_RESET case=roundtrip status=PASS', ''),
                       text.replace('COMPRESS_END schema=1 status=PASS cases=1', 'COMPRESS_END schema=1 status=FAIL cases=1')):
            with self.subTest(broken=broken[-150:]), self.assertRaises(ValueError):
                evidence.compression_evidence(broken, 'xswap', expected)

    def test_numeric_claims_cannot_replace_observations(self):
        text, expected = group_log('compressed-roundtrip')
        text = 'XSWAP_TYPE 1\n' + text
        for old, new in (('phase=stored_a key=absent_swapcache_pages value=8192', 'phase=stored_a key=absent_swapcache_pages value=0'),
                         ('phase=stored key=memcg_zswap_bytes value=32768', 'phase=stored key=memcg_zswap_bytes value=0'),
                         ('phase=decoded key=zswpin value=8192', 'phase=decoded key=zswpin value=0'),
                         ('phase=reset key=objects_and_charges_drained value=1', 'phase=reset key=objects_and_charges_drained value=0'),
                         ('phase=cleanup key=stored_pages value=0', 'phase=cleanup key=stored_pages value=1'),
                         ('phase=stored key=incompressible_pages value=0', 'phase=stored key=incompressible_pages value=8192'),
                         ('phase=decoded key=verified_words value=4194304', 'phase=decoded key=verified_words value=1')):
            gates, results = evidence.compression_evidence(text.replace(old, new), 'xswap', expected)
            self.assertFalse(gates['compression_evidence'], (old, results))

    def test_raw_ktap_cannot_inject_control_evidence(self):
        text, expected = group_log('numa-lifecycle')
        text = 'XSWAP_TYPE 1\n' + text
        injection = 'COMPRESS_CASE case=library_unit status=PASS reason=ok\n'
        valid = unit_ktap('numa2')
        for body in (valid.replace('ok 2 ', 'not ok 2 '), valid.replace('ok 1 page_compress_alloc_rollback', 'ok 1 page_compress_alloc_rollback # SKIP unavailable'),
                     valid + injection, valid.replace('1..3', '1..2'), valid.replace('page_compress_numa_placement', 'unrelated_test')):
            gates, results = evidence.compression_evidence(text.replace(valid, body), 'xswap', expected)
            self.assertFalse(gates['compression_library_unit'], results)

    def test_numa_test_name_requires_real_node_observations(self):
        text, expected = group_log('numa-lifecycle')
        text = 'XSWAP_TYPE 1\n' + text
        valid = unit_ktap('numa2')
        for bad in (KTAP, unit_ktap('single'), valid.replace('requested=1 actual=1', 'requested=1 actual=0'),
                    valid.replace('placements=2', 'placements=3'), valid.replace('pages=1', 'pages=0'),
                    valid.replace('mismatches=0', 'mismatches=1')):
            gates, results = evidence.compression_evidence(text.replace(valid, bad), 'xswap', expected)
            self.assertFalse(gates['compression_library_unit'], results)

    def test_quota_denial_requires_global_store_stability(self):
        text, expected = group_log('legacy-lifecycle')
        text = text.replace('case=memcg_limits phase=quota key=zswpout value=0', 'case=memcg_limits phase=quota key=zswpout value=1')
        gates, _ = evidence.compression_evidence(text, 'plain', expected)
        self.assertFalse(gates['compression_memcg_limits'])

    def test_fixed_catalog_cannot_drop_required_subcases(self):
        text, expected = group_log('legacy-lifecycle')
        expected['subcases'] = ['roundtrip']
        with self.assertRaises(ValueError):
            evidence.compression_evidence(text, 'plain', expected)

    def test_complete_instrumented_timing(self):
        result = evidence.parse(timing_log(), 'abc', 'compressed', 'xswap', 'swapin', 8, config_id='c1-common')
        self.assertTrue(all(result['gates'].values()), result)
        self.assertTrue(result['metrics']['compressed_observer']['instrumented'])

    def test_timing_loss_fallback_counts_and_wrong_identity_fail(self):
        for old, new in (('trace_lost=0', 'trace_lost=1'), ('probe_missed=0', 'probe_missed=1'),
                         ('decoded=32768', 'decoded=32767'), ('rand=16384', 'rand=1'),
                         ('physical=0', 'physical=1'), ('bench.config_id=c1-common', 'bench.config_id=standard'),
                         ('bench.compression_target_bytes=134217728', 'bench.compression_target_bytes=1073741824'),
                         ('stored_pages=32768', 'stored_pages=0'), ('zswpwb 0', 'zswpwb 1'),
                         ('SWAPIN_SEQ samples=16384', 'SWAPIN_SEQ samples=1')):
            broken = timing_log().replace(old, new, 1)
            result = evidence.parse(broken, 'abc', 'compressed', 'xswap', 'swapin', 8, config_id='c1-common')
            self.assertFalse(all(result['gates'].values()), (old, result))

    def test_unrelated_zero_page_counters_do_not_replace_target_proof(self):
        prefix, suffix = timing_log().split('VMSTAT_BEGIN swapin_end\n', 1)
        text = prefix + 'VMSTAT_BEGIN swapin_end\n' + suffix.replace('swpout_zero 0', 'swpout_zero 9', 1)
        result = evidence.parse(text, 'abc', 'compressed', 'xswap', 'swapin', 8, config_id='c1-common')
        self.assertTrue(all(result['gates'].values()), result)
        result = evidence.parse(text.replace('decoded=32768', 'decoded=32767'),
                                'abc', 'compressed', 'xswap', 'swapin', 8, config_id='c1-common')
        self.assertFalse(result['gates']['compressed_target_decode'])

    def test_flat_single_topology_for_non_numa_configurations(self):
        for group in ('compressed-roundtrip', 'legacy-roundtrip', 'race-lifecycle'):
            body, spec = group_log(group)
            text = basic_log(spec['backend'], spec['mode'], 'compression', spec['config_id'],
                             spec['topology_id'], spec).replace('ONLINE_NODES 0\n', 'ONLINE_NODES flat\n') + body
            with self.subTest(config=spec['config_id']):
                result = evidence.parse(text, 'abc', spec['backend'], spec['mode'], 'compression', 8,
                                        config_id=spec['config_id'], correctness_case=spec['id'],
                                        topology_id=spec['topology_id'], expected_case=spec)
                self.assertTrue(all(result['gates'].values()), result)
        result = evidence.parse(timing_log().replace('ONLINE_NODES 0\n', 'ONLINE_NODES flat\n'),
                                'abc', 'compressed', 'xswap', 'swapin', 8, config_id='c1-common')
        self.assertTrue(all(result['gates'].values()), result)

    def test_flat_topology_cannot_replace_numa_configuration_observations(self):
        for group in ('debug-failures', 'numa-lifecycle'):
            body, spec = group_log(group)
            text = basic_log(spec['backend'], spec['mode'], 'compression', spec['config_id'],
                             spec['topology_id'], spec) + body
            nodes = '0-1' if spec['topology_id'] == 'numa2' else '0'
            with self.subTest(topology=spec['topology_id']):
                result = evidence.parse(text.replace('ONLINE_NODES ' + nodes + '\n', 'ONLINE_NODES flat\n'),
                                        'abc', spec['backend'], spec['mode'], 'compression', 8,
                                        config_id=spec['config_id'], correctness_case=spec['id'],
                                        topology_id=spec['topology_id'], expected_case=spec)
                self.assertFalse(result['gates']['configuration_identity'])

    def test_online_nodes_requires_one_explicit_observation(self):
        markers = ('', 'ONLINE_NODES\n', 'ONLINE_NODES \n', 'ONLINE_NODES flat extra\n',
                   'ONLINE_NODES flat\nONLINE_NODES 0\n', 'ONLINE_NODES 0\nONLINE_NODES flat\n',
                   'ONLINE_NODES flat\nONLINE_NODES flat\n', 'ONLINE_NODES unknown\n')
        for marker in markers:
            with self.subTest(marker=marker):
                result = evidence.parse(timing_log().replace('ONLINE_NODES 0\n', marker),
                                        'abc', 'compressed', 'xswap', 'swapin', 8, config_id='c1-common')
                self.assertFalse(result['gates']['configuration_identity'])

    def test_flat_configurations_require_explicit_numa_disabled(self):
        import configurations
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.config'
            for config_id in ('c1-common', 'c1-legacy', 'c1-kcsan'):
                source = (ROOT / configurations.get_config(config_id)['path']).read_text()
                path.write_text(source)
                self.assertEqual(configurations.validate_final(config_id, path)['values']['NUMA'], 'n')
                for changed in (source.replace('# CONFIG_NUMA is not set', 'CONFIG_NUMA=y'),
                                source.replace('# CONFIG_NUMA is not set\n', '')):
                    path.write_text(changed)
                    with self.subTest(config=config_id), self.assertRaisesRegex(ValueError, 'CONFIG_NUMA=n'):
                        configurations.validate_final(config_id, path)

    def test_numa_topology_is_bound(self):
        text, expected = group_log('numa-lifecycle')
        spec = row('numa-lifecycle')
        text = basic_log('compressed', 'xswap', 'compression', 'c1-debug', 'numa2', spec) + text
        text = text.replace('ONLINE_NODES 0-1', 'ONLINE_NODES 0')
        result = evidence.parse(text, 'abc', 'compressed', 'xswap', 'compression', 8,
                                config_id='c1-debug', correctness_case=spec['id'], topology_id='numa2', expected_case=spec)
        self.assertFalse(result['gates']['configuration_identity'])


class CompressionFramingTests(unittest.TestCase):
    printk = 'zswap: compressor swap_next_invalid_codec_7d83 not available'
    summaries = ('# page_compress: pass:3 fail:0 skip:0 total:3\n'
                 '# Totals: pass:3 fail:0 skip:0 total:3\n')

    def summarized_ktap(self, topology='single'):
        return unit_ktap(topology).replace('ok 1 page_compress\n',
            '    # module: page_compress\n' + self.summaries + 'ok 1 page_compress\n')

    def observed_debug_log(self):
        body, spec = group_log('debug-failures')
        spec['config_id'] = 'c1-debug-v2'
        anchor = 'COMPRESS_OBS case=invalid_codec phase=case key=codec_unchanged value=1\n'
        self.assertEqual(body.count(anchor), 1)
        body = body.replace(anchor, anchor + self.printk + '\n')
        body = body.replace(unit_ktap(), self.summarized_ktap())
        header = basic_log('compressed', 'xswap', 'compression', 'c1-debug-v2', 'single', spec)
        # The observed printk is also retained by the final dmesg capture.
        header = header.replace('Linux version fixture\n', 'Linux version fixture\n' + self.printk + '\n')
        return header + body, spec

    def parse_debug(self, text, spec):
        return evidence.parse(text, 'abc', 'compressed', 'xswap', 'compression', 8,
            config_id='c1-debug-v2', correctness_case=spec['id'], topology_id='single', expected_case=spec)

    def unit_result(self, ktap):
        text, expected = group_log('numa-lifecycle')
        text = 'XSWAP_TYPE 1\n' + text.replace(unit_ktap('numa2'), ktap)
        return evidence.compression_evidence(text, 'xswap', expected)

    def test_observed_printk_and_zero_skip_summaries_preserve_six_valid_subcases(self):
        text, spec = self.observed_debug_log()
        result = self.parse_debug(text, spec)
        self.assertTrue(all(result['gates'].values()), result)
        self.assertEqual(result['metrics']['kernel_diagnostics'], [])
        self.assertEqual(len(result['correctness_subcases']), 6)
        invalid = result['correctness_subcases']['invalid_codec']
        self.assertEqual(invalid['expected_diagnostics'],
                         [{'kind': 'invalid_codec_rejected', 'message': self.printk}])
        self.assertTrue(all(case['status'] == 'PASS' and case['evidence_valid']
                            for case in result['correctness_subcases'].values()))

    def test_printk_is_exact_single_and_bound_to_invalid_codec_observations(self):
        body, expected = group_log('debug-failures')
        anchor = 'COMPRESS_OBS case=invalid_codec phase=case key=codec_unchanged value=1\n'
        reset = 'COMPRESS_RESET case=invalid_codec status=PASS\n'
        wrong_case = 'COMPRESS_BEGIN schema=1 mode=xswap case=library_unit bytes=33554432\n'
        begin = 'COMPRESS_BEGIN schema=1 mode=xswap case=invalid_codec bytes=33554432\n'
        broken = [
            body.replace(anchor, anchor + (self.printk + '\n') * 2),
            body.replace(reset, reset + self.printk + '\n'),
            body.replace(wrong_case, wrong_case + self.printk + '\n'),
            body.replace(begin, self.printk + '\n' + begin),
        ]
        for unknown in (self.printk.replace('7d83', '7d84'), self.printk + ' extra',
                        'zswap: compressor lzo not available', 'WARNING: synthetic fault',
                        'unrecognized observation'):
            broken.append(body.replace(anchor, anchor + unknown + '\n'))
        for text in broken:
            with self.subTest(tail=text[-120:]), self.assertRaises(ValueError):
                evidence.compression_evidence('XSWAP_TYPE 1\n' + text, 'xswap', expected)

    def test_expected_printk_never_replaces_semantic_failure_evidence(self):
        text, spec = self.observed_debug_log()
        text = text.replace('COMPRESS_OBS case=invalid_codec phase=case key=invalid_codec_errno value=22\n', '')
        result = self.parse_debug(text, spec)
        self.assertFalse(result['gates']['compression_invalid_codec'])
        self.assertFalse(result['gates']['compression_evidence'])

    def test_expected_printk_does_not_suppress_kernel_warnings(self):
        text, spec = self.observed_debug_log()
        text = text.replace('Linux version fixture\n', 'Linux version fixture\nWARNING: synthetic fault\n')
        result = self.parse_debug(text, spec)
        self.assertFalse(result['gates']['no_kernel_warnings'])
        self.assertFalse(result['gates']['no_new_kernel_warnings'])

    def test_ktap_accepts_exact_zero_skip_summary_pair_or_original_strict_fixture(self):
        for ktap in (unit_ktap('numa2'), self.summarized_ktap('numa2')):
            gates, result = self.unit_result(ktap)
            self.assertTrue(gates['compression_library_unit'], result)

    def test_ktap_rejects_nonzero_contradictory_partial_or_reordered_summaries(self):
        valid = self.summarized_ktap('numa2')
        first, second = self.summaries.splitlines(keepends=True)
        broken = [
            valid.replace('skip:0', 'skip:1', 1),
            valid.replace('pass:3', 'pass:2', 1),
            valid.replace('fail:0', 'fail:1', 1),
            valid.replace('total:3', 'total:4', 1),
            valid.replace(' skip:0', '', 1),
            valid.replace(first, ''),
            valid.replace(second, ''),
            valid.replace(first, first * 2),
            valid.replace(self.summaries, second + first),
            valid.replace(self.summaries, '').replace('    ok 2 page_compress_partial_cleanup\n',
                self.summaries + '    ok 2 page_compress_partial_cleanup\n'),
            valid.replace(self.summaries, '') + self.summaries,
            valid.replace('# page_compress: pass:', '# unrelated: pass:', 1),
            valid.replace('# Totals: pass:3 fail:0 skip:0 total:3', '# Totals: pass=3 fail=0 skip=0 total=3'),
        ]
        for ktap in broken:
            with self.subTest(ktap=ktap[-180:]):
                gates, result = self.unit_result(ktap)
                self.assertFalse(gates['compression_library_unit'], result)

    def test_ktap_rejects_directives_missing_duplicate_and_out_of_order_cases(self):
        valid = self.summarized_ktap('numa2')
        first = '    ok 1 page_compress_alloc_rollback\n'
        second = '    ok 2 page_compress_partial_cleanup\n'
        third = '    ok 3 page_compress_numa_placement\n'
        swapped = valid.replace(second, 'ORDER_SWAP\n').replace(third, second).replace('ORDER_SWAP\n', third)
        broken = [
            valid.replace(first, first.rstrip() + ' # SKIP unavailable\n'),
            valid.replace(second, second.rstrip() + ' # TODO later\n'),
            valid.replace(second, ''),
            valid.replace(first, first * 2),
            swapped,
            valid.replace('    ok 2 ', '    not ok 2 '),
        ]
        for ktap in broken:
            with self.subTest(ktap=ktap[-240:]):
                gates, result = self.unit_result(ktap)
                self.assertFalse(gates['compression_library_unit'], result)


class DebugConfigurationV2Tests(unittest.TestCase):
    def test_frozen_debug_bytes_are_preserved_and_v2_only_disables_tiny(self):
        old = (ROOT / 'benchmark/config/compression-debug.config').read_bytes()
        new = (ROOT / 'benchmark/config/compression-debug-v2.config').read_bytes()
        self.assertEqual(hashlib.sha256(old).hexdigest(),
                         'c58461570b79210f9d99c7eb2e3a6e492601960ea73394bb4e4c78b147cd0ba4')
        self.assertEqual(old.count(b'CONFIG_SLUB_TINY=y\n'), 1)
        self.assertEqual(new, old.replace(b'CONFIG_SLUB_TINY=y\n',
                                         b'# CONFIG_SLUB_TINY is not set\n'))

    def test_v2_keeps_all_debug_requirements_and_rejects_tiny(self):
        import configurations
        old, new = configurations.CONFIGS['c1-debug'], configurations.CONFIGS['c1-debug-v2']
        self.assertEqual(new['required'], old['required'])
        self.assertEqual(new['purposes'], ['correctness'])
        self.assertEqual(new['forbidden'], old['forbidden'] + ['SLUB_TINY'])
        self.assertEqual(GROUPS['debug-failures']['config_id'], 'c1-debug')
        self.assertEqual(GROUPS['numa-lifecycle']['config_id'], 'c1-debug')
        old_path = ROOT / old['path']
        new_path = ROOT / new['path']
        # Input-only fixtures exercise the final-config validator; no Kconfig
        # resolution or kernel compilation is claimed by this test.
        configurations.validate_final('c1-debug', old_path, 'correctness')
        configurations.validate_final('c1-debug-v2', new_path, 'correctness')
        with self.assertRaisesRegex(ValueError, 'forbidden final CONFIG_SLUB_TINY'):
            configurations.validate_final('c1-debug-v2', old_path, 'correctness')
        with self.assertRaisesRegex(ValueError, 'not allowed for timing'):
            configurations.get_config('c1-debug-v2', purpose='timing')

    def test_v2_final_config_still_requires_kasan_and_real_numa(self):
        import configurations
        original = (ROOT / 'benchmark/config/compression-debug-v2.config').read_text()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.config'
            for name in ('KASAN', 'NUMA'):
                for replacement in ('', '# CONFIG_' + name + ' is not set\n'):
                    path.write_text(original.replace('CONFIG_' + name + '=y\n', replacement))
                    with self.subTest(flag=name, replacement=replacement), \
                            self.assertRaisesRegex(ValueError, 'required final CONFIG_' + name + '=y'):
                        configurations.validate_final('c1-debug-v2', path, 'correctness')

    def test_versioned_input_is_accepted_only_for_the_two_existing_debug_groups(self):
        import configurations
        for group, default in GROUPS.items():
            self.assertEqual(configurations.correctness_group(group, default['config_id']), default)
            if group in ('debug-failures', 'numa-lifecycle'):
                expected = dict(default, config_id='c1-debug-v2')
                self.assertEqual(configurations.correctness_group(group, 'c1-debug-v2'), expected)
                for invalid in ('c1-common', 'c1-kcsan', 'c1-debug-v3'):
                    with self.subTest(group=group, config=invalid), self.assertRaises(ValueError):
                        configurations.correctness_group(group, invalid)
            else:
                with self.subTest(group=group), self.assertRaises(ValueError):
                    configurations.correctness_group(group, 'c1-debug-v2')

    def parse_debug(self, group, marker=None, expected_config='c1-debug-v2'):
        body, spec = group_log(group)
        spec['config_id'] = expected_config
        text = basic_log(spec['backend'], spec['mode'], 'compression', 'c1-debug-v2',
                         spec['topology_id'], spec) + body
        nodes = '0-1' if spec['topology_id'] == 'numa2' else '0'
        if marker is not None:
            text = text.replace('ONLINE_NODES ' + nodes + '\n', marker)
        return evidence.parse(text, 'abc', spec['backend'], spec['mode'], 'compression', 8,
                              config_id='c1-debug-v2', correctness_case=spec['id'],
                              topology_id=spec['topology_id'], expected_case=spec)

    def test_v2_parser_accepts_actual_numeric_nodes_for_each_debug_topology(self):
        for group in ('debug-failures', 'numa-lifecycle'):
            with self.subTest(group=group):
                result = self.parse_debug(group)
                self.assertTrue(all(result['gates'].values()), result)

    def test_v2_parser_rejects_missing_flat_duplicate_or_malformed_nodes(self):
        common = ('', 'ONLINE_NODES\n', 'ONLINE_NODES \n', 'ONLINE_NODES flat\n',
                  'ONLINE_NODES 0-2\n', 'ONLINE_NODES 0 extra\n',
                  'ONLINE_NODES 0\nONLINE_NODES 0-1\n')
        for group in ('debug-failures', 'numa-lifecycle'):
            good = '0-1' if group == 'numa-lifecycle' else '0'
            wrong = '0' if group == 'numa-lifecycle' else '0-1'
            markers = (*common, 'ONLINE_NODES ' + good + '\n' + 'ONLINE_NODES ' + good + '\n',
                       'ONLINE_NODES ' + wrong + '\n')
            for marker in markers:
                with self.subTest(group=group, marker=marker):
                    self.assertFalse(self.parse_debug(group, marker)['gates']['configuration_identity'])

    def test_v2_runtime_cannot_claim_the_old_frozen_configuration_id(self):
        for group in ('debug-failures', 'numa-lifecycle'):
            with self.subTest(group=group), self.assertRaisesRegex(ValueError, 'config_id'):
                self.parse_debug(group, expected_config='c1-debug')


class TraceObserverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='swap-next-timing-test-')
        cls.binary = Path(cls.temp.name) / 'trace-parser'
        wrapper = Path(cls.temp.name) / 'trace-parser.c'
        wrapper.write_text('#define main swapin_guest_main\n#include ' + json.dumps(str(BASE / 'swapin.c'))
                           + '\n#undef main\nint main(void) { char raw[32768]; size_t n=fread(raw,1,sizeof(raw)-1,stdin); raw[n]=0; return parse_decode_trace(raw) ? 1 : 0; }\n')
        subprocess.run(['gcc', '-O2', '-Wall', '-Wextra', '-Werror', str(wrapper), '-o', str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_compressed_workload_refuses_non_guest_execution(self):
        binary = Path(self.temp.name) / 'swapin'
        subprocess.run(['gcc', '-O2', '-Wall', '-Wextra', '-Werror', str(BASE / 'swapin.c'), '-o', str(binary)], check=True)
        result = subprocess.run([str(binary), '134217728', '/sys/fs/cgroup/bench/memory.reclaim',
                                 'compressed', '1', '/sys/fs/cgroup/bench'], text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(result.returncode, 1)
        self.assertIn('SWAPIN_FAIL compressed_observer_setup', result.stdout)

    def test_success_and_negative_trace_envelopes(self):
        valid = '# tracer: nop\n# entries-in-buffer/entries-written: 1/1   #P:4\n swapin-12 [000] ... 1.000: decode_return: (func <- ret) ret=0\n'
        self.assertEqual(subprocess.run([str(self.binary)], input=valid, text=True).returncode, 0)
        invalid = [valid.replace('1/1', '1/2'), valid.replace('ret=0', 'ret=-2'),
                   valid.replace('decode_return:', 'other:'), valid + valid.splitlines()[-1] + '\n',
                   valid.replace('# entries-in-buffer/entries-written: 1/1   #P:4\n', ''),
                   '# entries-in-buffer/entries-written: 0/0\n']
        for raw in invalid:
            self.assertNotEqual(subprocess.run([str(self.binary)], input=raw, text=True).returncode, 0)


class SocketNumaTopologyTests(unittest.TestCase):
    topology = 'numa2-sockets-v2'
    smp = '4,sockets=2,cores=2,threads=1'
    numa = ['-object', 'memory-backend-ram,id=c1-node0,size=2048M',
            '-object', 'memory-backend-ram,id=c1-node1,size=2048M',
            '-numa', 'node,nodeid=0,memdev=c1-node0,cpus=0-1',
            '-numa', 'node,nodeid=1,memdev=c1-node1,cpus=2-3']

    def protocol(self):
        return {'guest': {'vcpus': 4, 'mem_mib': 4096},
                'accelerator': {'qemu': ['-accel', 'tcg,thread=multi,tb-size=256',
                                        '-machine', 'pc', '-cpu', 'max']}}

    def record(self):
        return {'topology_id': self.topology, 'config_id': 'c1-debug-v2',
                'correctness_group': 'numa-lifecycle', 'topology_arguments': list(self.numa),
                'command': ['qemu-system-x86_64', *self.protocol()['accelerator']['qemu'],
                            '-smp', self.smp, '-m', '4096', *self.numa]}

    def test_new_socket_topology_and_legacy_defaults_are_distinct(self):
        import configurations
        protocol = self.protocol()
        self.assertEqual(configurations.topology_args('numa2', protocol), self.numa)
        self.assertEqual(configurations.topology_args(self.topology, protocol), self.numa)
        self.assertEqual(configurations.smp_argument('numa2', protocol), '4')
        self.assertEqual(configurations.smp_argument(self.topology, protocol), self.smp)
        configurations.validate_topology_record(protocol, self.record())
        legacy = self.record()
        legacy.update(topology_id='numa2', config_id='c1-debug')
        legacy['command'][legacy['command'].index('-smp') + 1] = '4'
        configurations.validate_topology_record(protocol, legacy)
        for cpus, memory in ((2, 4096), (8, 4096), (4, 2048), (4, 8192)):
            with self.subTest(cpus=cpus, memory=memory), self.assertRaises(ValueError):
                configurations.topology_args(self.topology, {'guest': {'vcpus': cpus, 'mem_mib': memory}})
        with self.assertRaisesRegex(ValueError, 'correctness-only'):
            configurations.topology_args(self.topology, protocol, 'timing')

    def test_new_id_resolves_only_for_versioned_numa_lifecycle(self):
        import configurations
        expected = dict(GROUPS['numa-lifecycle'], config_id='c1-debug-v2', topology_id=self.topology)
        self.assertEqual(configurations.correctness_group('numa-lifecycle', 'c1-debug-v2', self.topology), expected)
        for group, spec in GROUPS.items():
            self.assertEqual(configurations.correctness_group(group, spec['config_id'], spec['topology_id']), spec)
            if group != 'numa-lifecycle':
                with self.subTest(group=group), self.assertRaises(ValueError):
                    configurations.correctness_group(group, spec['config_id'], self.topology)
        for config in ('c1-debug', 'c1-common', 'c1-kcsan'):
            with self.subTest(config=config), self.assertRaises(ValueError):
                configurations.correctness_group('numa-lifecycle', config, self.topology)
        with self.assertRaises(ValueError):
            configurations.correctness_group('numa-lifecycle', 'c1-debug-v2', 'numa2-untrusted')

    def test_proof_rejects_cpu_topology_mismatch_duplicate_or_fake_cpu_argument(self):
        import configurations
        original = self.record()
        commands = []
        for value in ('4', '4,sockets=1,cores=4,threads=1', '4,sockets=2,cores=1,threads=2',
                      self.smp + ',sockets=1', self.smp + ',maxcpus=8'):
            command = list(original['command'])
            command[command.index('-smp') + 1] = value
            commands.append(command)
        commands += [original['command'] + ['-smp', self.smp],
                     original['command'] + ['--smp', self.smp],
                     original['command'] + ['-smp=' + self.smp],
                     original['command'] + ['-cpu', 'max,sockets=2,cores=2,threads=1'],
                     original['command'] + ['--cpu', 'max'],
                     original['command'] + ['-machine', 'pc'],
                     original['command'] + ['-m', '4096']]
        for flag, replacement in (('-smp', '4'), ('-cpu', 'max,sockets=2,cores=2,threads=1')):
            command = list(original['command'])
            command[command.index(flag) + 1] = replacement
            if flag == '-smp':
                command[command.index('-cpu') + 1] = 'max,sockets=2,cores=2,threads=1'
            commands.append(command)
        for index, command in enumerate(commands):
            with self.subTest(mutation=index), self.assertRaises(ValueError):
                configurations.validate_topology_record(self.protocol(), dict(original, command=command))

    def test_machine_alias_cannot_override_the_new_topology_proof(self):
        import configurations
        original = self.record()
        configurations.validate_topology_record(self.protocol(), original)
        for alias in (['-M', 'q35'], ['--M', 'q35'], ['-M=q35'], ['--M=q35'],
                      ['-Mq35'], ['--Mq35']):
            changed = dict(original, command=original['command'] + alias)
            with self.subTest(alias=alias), self.assertRaisesRegex(ValueError, 'machine alias'):
                configurations.validate_topology_record(self.protocol(), changed)
        legacy = self.record()
        legacy.update(topology_id='numa2', config_id='c1-debug')
        legacy['command'][legacy['command'].index('-smp') + 1] = '4'
        configurations.validate_topology_record(self.protocol(), legacy)
        configurations.validate_topology_record(
            self.protocol(), dict(legacy, command=legacy['command'] + ['-M', 'q35']))

    def test_proof_requires_exact_numa_arguments_and_identity(self):
        import configurations
        original = self.record()
        changed_node = list(original['command'])
        changed_node[-1] = 'node,nodeid=1,memdev=c1-node1,cpus=1-3'
        commands = [changed_node, original['command'][:-2],
                    original['command'] + self.numa[-2:],
                    original['command'] + self.numa[:2],
                    original['command'] + ['--numa', self.numa[-1]],
                    original['command'] + ['-object=' + self.numa[1]]]
        for command in commands:
            with self.subTest(command=command), self.assertRaises(ValueError):
                configurations.validate_topology_record(self.protocol(), dict(original, command=command))
        for values in ({'topology_arguments': []}, {'config_id': 'c1-debug'},
                       {'correctness_group': 'debug-failures'}, {'topology_id': 'numa2-untrusted'}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                configurations.validate_topology_record(self.protocol(), dict(original, **values))

    def parse_log(self, transform=lambda text: text):
        body, spec = group_log('numa-lifecycle', topology=self.topology, config='c1-debug-v2')
        text = basic_log('compressed', 'xswap', 'compression', 'c1-debug-v2', self.topology, spec) + body
        return evidence.parse(transform(text), 'abc', 'compressed', 'xswap', 'compression', 8,
                              config_id='c1-debug-v2', correctness_case=spec['id'],
                              topology_id=self.topology, expected_case=spec)

    def test_parser_requires_both_real_nodes_and_preserves_warning_gate(self):
        valid = self.parse_log()
        self.assertTrue(all(valid['gates'].values()), valid)
        self.assertEqual(valid['correctness_subcases']['library_unit']['numa_observations']['nodes'], 2)
        for value in ('0', '1', 'flat', '0-2', ''):
            result = self.parse_log(lambda text: text.replace('ONLINE_NODES 0-1', 'ONLINE_NODES ' + value))
            self.assertFalse(result['gates']['configuration_identity'], value)
        result = self.parse_log(lambda text: text.replace('GUEST_TOPOLOGY ' + self.topology, 'GUEST_TOPOLOGY numa2'))
        self.assertFalse(result['gates']['configuration_identity'])
        for ktap in (unit_ktap('single'), unit_ktap(self.topology).replace('requested=1 actual=1', 'requested=1 actual=0')):
            result = self.parse_log(lambda text: text.replace(unit_ktap(self.topology), ktap))
            self.assertFalse(result['gates']['compression_library_unit'])
        result = self.parse_log(lambda text: text.replace('Linux version fixture',
                               'WARNING: CPU: 2 PID: 0 at arch/x86/kernel/smpboot.c:329 topology_sane'))
        self.assertFalse(result['gates']['no_new_kernel_warnings'])


class NehalemNumaTopologyTests(SocketNumaTopologyTests):
    topology = 'numa2-nehalem-v3'
    cpu = 'Nehalem-v1,vme=off,enforce=on'
    cpu0 = 'smpboot: CPU0: Intel fixture CPU (family: 0x6, model: 0x1a, stepping: 0x3)'

    def protocol(self):
        value = super().protocol()
        value['accelerator']['require'] = 'tcg'
        return value

    def record(self):
        value = super().record()
        accelerator = [*self.protocol()['accelerator']['qemu'][:-1], self.cpu]
        value.update(qemu_accel=accelerator, accelerator='tcg', workload='compression',
                     backend='compressed', mode='xswap')
        value['command'][value['command'].index('-cpu') + 1] = self.cpu
        return value

    def test_effective_cpu_record_is_required_and_only_auxiliary_changes(self):
        import configurations
        original = self.protocol()['accelerator']['qemu']
        for topology in ('single', 'numa2', 'numa2-sockets-v2'):
            self.assertEqual(configurations.effective_accelerator(topology, original), original)
        expected = [*original[:-1], self.cpu]
        self.assertEqual(configurations.effective_accelerator(self.topology, original), expected)
        self.assertEqual(original[-1], 'max')
        for wrong in (original + ['-cpu', 'max'], original[:-1] + ['host'],
                      ['-enable-kvm', '-cpu', 'host'], original + ['--cpu=max']):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                configurations.effective_accelerator(self.topology, wrong)
        record = self.record()
        for changes in ({'qemu_accel': original}, {'qemu_accel': None},
                        {'qemu_accel': expected + ['-cpu', self.cpu]},
                        {'accelerator': 'kvm'}, {'workload': 'swapin'},
                        {'backend': 'disk'}, {'mode': 'plain'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                configurations.validate_topology_record(self.protocol(), dict(record, **changes))
        for cpu in ('max', 'Nehalem', 'Nehalem-v1', 'Nehalem-v1,enforce=on',
                    'Nehalem-v1,vme=off', self.cpu + ',invtsc=on'):
            changed = copy.deepcopy(record)
            changed['command'][changed['command'].index('-cpu') + 1] = cpu
            changed['qemu_accel'][-1] = cpu
            with self.subTest(cpu=cpu), self.assertRaises(ValueError):
                configurations.validate_topology_record(self.protocol(), changed)

    def test_new_topology_rejects_all_option_spellings_and_override_channels(self):
        import configurations
        record = self.record()
        for option, value in (('-cpu', self.cpu), ('-smp', self.smp), ('-m', '4096'),
                              ('-machine', 'pc'), ('-accel', 'tcg'),
                              ('-object', self.numa[1]), ('-numa', self.numa[-1])):
            variants = ([option, value], ['-' + option, value], [option + '=' + value],
                        ['-' + option + '=' + value], [option + value], ['-' + option + value])
            for extra in variants:
                with self.subTest(extra=extra), self.assertRaises(ValueError):
                    configurations.validate_topology_record(
                        self.protocol(), dict(record, command=record['command'] + extra))
        for extra in (['-global', 'Nehalem-v1-x86_64-cpu.vendor=AuthenticAMD'],
                      ['-set', 'cpu.0.vendor=AuthenticAMD'], ['-readconfig', 'other.ini'],
                      ['-device', 'Nehalem-v1-x86_64-cpu'], ['-enable-kvm']):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                configurations.validate_topology_record(
                    self.protocol(), dict(record, command=record['command'] + extra))

    def test_cpu_identity_is_numeric_unique_and_inside_kernel_log(self):
        for cpu0 in (self.cpu0, self.cpu0.replace('Intel fixture CPU', 'Intel(R) arbitrary brand'),
                     '[    0.123456] ' + self.cpu0,
                     self.cpu0.replace('0x1a', '0x1A')):
            result = self.parse_log(lambda text: text.replace(self.cpu0, cpu0))
            self.assertTrue(result['gates']['configuration_identity'], cpu0)
        for cpu0 in ('', self.cpu0.replace('Intel', 'AMD'), self.cpu0.replace('CPU0:', 'CPU1:'),
                     self.cpu0.replace('family: 0x6', 'family: 0x7'),
                     self.cpu0.replace('model: 0x1a', 'model: 0x6'),
                     self.cpu0.replace('stepping: 0x3', 'stepping: 0x2'),
                     self.cpu0 + '\n' + self.cpu0,
                     self.cpu0.replace('model: 0x1a', 'model: unknown')):
            result = self.parse_log(lambda text: text.replace(self.cpu0, cpu0))
            self.assertFalse(result['gates']['configuration_identity'], cpu0)
        result = self.parse_log(lambda text: text.replace(self.cpu0 + '\n', '') + self.cpu0 + '\n')
        self.assertFalse(result['gates']['configuration_identity'])
        result = self.parse_log(lambda text: text + 'KERNEL_LOG_BEGIN\n' + self.cpu0 + '\nKERNEL_LOG_END\n')
        self.assertFalse(result['gates']['configuration_identity'])

    def test_new_cpu_keeps_clocksource_and_sanitizer_rejections(self):
        from validity import clocksource_invalid
        for diagnostic in ('WARNING: fixture', 'BUG: KASAN: fixture', 'BUG: KCSAN: fixture'):
            result = self.parse_log(lambda text: text.replace('Linux version fixture', diagnostic))
            self.assertFalse(result['gates']['no_new_kernel_warnings'], diagnostic)
        for marker in ("Marking TSC unstable due to TSCs unsynchronized",
                       "clocksource: Switched to clocksource hpet"):
            serial = []
            self.parse_log(lambda text: serial.append(text.replace('Linux version fixture', marker)) or serial[-1])
            self.assertTrue(clocksource_invalid(serial[0]), marker)


class Revision8ProtocolTests(unittest.TestCase):
    def protocol(self):
        import configurations
        from validity import COMPRESSION_OBSERVER
        groups = [('baseline', 'regression'), ('baseline', 'legacy-roundtrip'),
                  ('candidate', 'regression'), ('candidate', 'legacy-lifecycle'),
                  ('candidate', 'compressed-roundtrip'), ('candidate', 'debug-failures'),
                  ('candidate', 'race-lifecycle'), ('candidate', 'numa-lifecycle')]
        rows = [dict(row(group), id=role + '-' + group, role=role) for role, group in groups]
        builds = [dict(id=name, role='candidate', config_id=name) for name in ('c1-noswap', 'c1-no-frontends')]
        configs = {name: {'input_config_sha256': configurations.get_config(name, ROOT)['input_config_sha256']}
                   for name in {item['config_id'] for item in rows + builds}}
        cases = {}
        for backend in ('compressed', 'disk', 'zram-64k'):
            cases['swapin-' + backend] = dict(backend=backend, mode='xswap', workload='swapin',
                config_id='c1-common', topology_id='single',
                primary='swapin_seq.mean_ns' if backend == 'compressed' else None,
                guard=['swapin_rand.mean_ns'] if backend == 'compressed' else ['swapin_seq.mean_ns', 'swapin_rand.mean_ns'],
                metrics={'swapin_seq.mean_ns': 'lower', 'swapin_rand.mean_ns': 'lower',
                         'swapin_seq.p99_ns': 'lower', 'swapin_rand.p99_ns': 'lower'},
                probe_signals=['swapin_vmstat_delta.swap_ra', 'swapin_vmstat_delta.swap_ra_hit', 'swapin_vmstat_delta.pgmajfault'])
        cases['metadata-brd'] = dict(backend='brd', mode='plain', workload='metadata', config_id='c1-common',
            topology_id='single', primary=None, probe_signals=['metadata_delta_bytes_per_capacity_slot'],
            metrics={'metadata_delta_bytes_per_capacity_slot': 'lower'},
            metadata_accounting={'numerator': 'attributable_meminfo', 'fields': list(evidence.ATTRIBUTABLE_FIELDS),
                'excluded_fields': ['MemFree', 'MemAvailable', 'Slab'], 'on_missing': 'fail',
                'on_vmalloc_decrease': 'fail', 'on_negative_sum': 'fail',
                'signed_fields': ['SUnreclaim', 'PageTables', 'Percpu']})
        order = ['swapin-compressed', 'swapin-disk', 'swapin-zram-64k']
        return dict(protocol_revision=8, baseline_build='c1-test-base',
            baseline_commit='5e84ca928deeacb4eee656806a003f27d1eca82f',
            guest={'vcpus': 4, 'mem_mib': 4096, 'swap_gib': 16},
            accelerator={'require': 'tcg', 'qemu': ['-accel', 'tcg,thread=multi,tb-size=256', '-machine', 'pc', '-cpu', 'max']},
            noise_envelope='p90', comparison_decision='median', noise_ceiling=0.25,
            advisory_metric_suffixes=['.p99_ns'], preallocate_swap=True, excluded={'build': 'excluded'},
            page_cluster={'value': 3}, input_config_sha256=configs['c1-common']['input_config_sha256'],
            budget={'probe_guest_attempts': 32, 'guest_attempts': 88, 'build_attempts': 10,
                    'wall_seconds': 64800, 'guest_timeout': 900},
            validity={'clocksource_fallback': 'invalid_and_rerun', 'host_load': 'loadavg and PSI', 'reruns_per_arm': 2},
            tiers={'probe': {'kind': 'probe', 'cases': order + ['metadata-brd'], 'calibration_runs': 3, 'candidate_runs': 1},
                   'fast': {'cases': order, 'calibration_pairs': 10, 'comparison_pairs': 4}},
            probe_band={'relative_padding': 0.01, 'integer_padding_floor': 1, 'metadata_spread_fraction': 0.01},
            cases=cases, configurations=configs, correctness_matrix={'schema_version': 1, 'cases': rows, 'build_only': builds},
            compression_observer=copy.deepcopy(COMPRESSION_OBSERVER), compression_workload={'target_bytes': 134217728})

    def test_complete_new_contract(self):
        from validity import protocol_rules
        self.assertEqual(protocol_rules(self.protocol())['protocol_revision'], 8)

    def test_resource_limits_can_narrow_without_changing_measurements(self):
        from validity import protocol_rules
        protocol = self.protocol()
        protocol['budget'].update(probe_guest_attempts=29, build_attempts=7, wall_seconds=60000)
        self.assertEqual(protocol_rules(protocol)['protocol_revision'], 8)
        for key, ceiling in (('probe_guest_attempts', 32), ('guest_attempts', 88),
                             ('build_attempts', 10), ('wall_seconds', 64800)):
            for value in (ceiling + 1, 0, -1, True, 1.5):
                with self.subTest(key=key, value=value):
                    changed = copy.deepcopy(protocol)
                    changed['budget'][key] = value
                    with self.assertRaises(ValueError):
                        protocol_rules(changed)

    def test_versioned_debug_contract_requires_its_own_exact_frozen_pin(self):
        import configurations
        from validity import protocol_rules
        original = self.protocol()
        replacement = copy.deepcopy(original)
        for case in replacement['correctness_matrix']['cases']:
            if case['config_id'] == 'c1-debug':
                case['config_id'] = 'c1-debug-v2'
        old_pin = replacement['configurations'].pop('c1-debug')
        replacement['configurations']['c1-debug-v2'] = {
            'input_config_sha256': configurations.get_config('c1-debug-v2', ROOT)['input_config_sha256']}
        self.assertEqual(protocol_rules(original)['protocol_revision'], 8)
        self.assertEqual(protocol_rules(replacement)['protocol_revision'], 8)
        replacement['configurations']['c1-debug-v2'] = old_pin
        with self.assertRaisesRegex(ValueError, 'configuration input hash mismatch'):
            protocol_rules(replacement)

    def test_socket_numa_variant_requires_a_separate_matching_matrix_row(self):
        import configurations
        from validity import protocol_rules
        legacy = self.protocol()
        replacement = copy.deepcopy(legacy)
        case = next(item for item in replacement['correctness_matrix']['cases'] if item['group'] == 'numa-lifecycle')
        case.update(config_id='c1-debug-v2', topology_id='numa2-sockets-v2')
        replacement['configurations']['c1-debug-v2'] = {
            'input_config_sha256': configurations.get_config('c1-debug-v2', ROOT)['input_config_sha256']}
        self.assertEqual(protocol_rules(legacy)['protocol_revision'], 8)
        self.assertEqual(protocol_rules(replacement)['protocol_revision'], 8)
        for group in ('debug-failures', 'compressed-roundtrip', 'regression'):
            changed = copy.deepcopy(replacement)
            wrong = next(item for item in changed['correctness_matrix']['cases'] if item['group'] == group)
            wrong['topology_id'] = 'numa2-sockets-v2'
            with self.subTest(group=group), self.assertRaises(ValueError):
                protocol_rules(changed)
        changed = copy.deepcopy(replacement)
        changed['cases']['swapin-compressed']['topology_id'] = 'numa2-sockets-v2'
        with self.assertRaises(ValueError):
            protocol_rules(changed)
        case['config_id'] = 'c1-debug'
        with self.assertRaises(ValueError):
            protocol_rules(replacement)

    def test_measurement_or_coverage_drift_is_rejected(self):
        from validity import protocol_rules
        changes = [lambda p: p['compression_workload'].update(target_bytes=1073741824),
                   lambda p: p['compression_observer'].update(per_target_decode=False),
                   lambda p: p['cases']['swapin-disk'].update(primary='swapin_seq.mean_ns'),
                   lambda p: p['cases']['swapin-zram-64k'].update(guard=['swapin_rand.mean_ns']),
                   lambda p: p['cases']['swapin-compressed'].update(config_id='standard'),
                   lambda p: p['cases']['swapin-compressed'].update(topology_id='numa2'),
                   lambda p: p['configurations']['c1-common'].update(input_config_sha256='0' * 64),
                   lambda p: p['correctness_matrix']['cases'].pop(),
                   lambda p: p['correctness_matrix']['build_only'].pop(),
                   lambda p: p['tiers']['fast'].update(calibration_pairs=11),
                   lambda p: p['budget'].update(guest_timeout=1800),
                   lambda p: p.update(metadata_rescore={'fresh_probe_calibration_required': False}),
                   lambda p: p['cases']['metadata-brd']['metadata_accounting'].update(on_missing='ignore')]
        for i, change in enumerate(changes):
            protocol = self.protocol()
            change(protocol)
            with self.subTest(mutation=i), self.assertRaises(ValueError):
                protocol_rules(protocol)


if __name__ == '__main__':
    unittest.main()
