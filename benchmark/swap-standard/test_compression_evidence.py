# SPDX-License-Identifier: GPL-2.0-only
"""Synthetic raw-evidence tests; these never claim executed kernel coverage."""
import copy
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
    nodes = [0, 1] if topology == 'numa2' else [0]
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


def group_log(group):
    spec = row(group)
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
    device = 'xswap1' if mode == 'xswap' else '/dev/zram1'
    vm0 = 'pswpin 0\npswpout 0\nzswpin 0\nzswpout 0\nzswpwb 0\nswpin_zero 0\nswpout_zero 0\nswap_ra 0\nswap_ra_hit 0'
    vm1 = vm0.replace('zswpin 0', 'zswpin 32768').replace('zswpout 0', 'zswpout 32768')
    return ('BENCH_BOOT\nCMDLINE_BEGIN\n' + command + '\nCMDLINE_END\n'
            f'GUEST_TOPOLOGY {topology}\nONLINE_NODES ' + ('0-1' if topology == 'numa2' else '0') + '\n'
            'ZSWAP_ENABLED Y\n' + ('XSWAP_TYPE 1\n' if mode == 'xswap' else '')
            + 'BACKEND_DEVICE ' + ('none' if backend == 'compressed' else '/dev/zram1') + '\n'
            + f'SWAPS_BEGIN\nFilename Type Size Used Priority\n{device} partition 16384 0 32767\nSWAPS_END\n'
            + f'SWAP_PEAK_BEGIN\n{device} 131072\nSWAP_PEAK_END\n'
            + block('VMSTAT', 'before', vm0) + block('VMSTAT', 'end', vm1)
            + block('VMSTAT', 'swapin_start', vm0) + block('VMSTAT', 'swapin_end', vm1)
            + block('XSWAP', 'swapin_start', 'clusters_mapped 10\nusage_pages 0\ngrows 0\nshrinks 0')
            + block('XSWAP', 'swapin_end', 'clusters_mapped 10\nusage_pages 0\ngrows 1\nshrinks 0')
            + thp() + 'KERNEL_LOG_BEGIN\nLinux version fixture\nKERNEL_LOG_END\nBENCH_WORKLOAD_PASS\nBENCH_PASS\n')


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

    def test_numa_topology_is_bound(self):
        text, expected = group_log('numa-lifecycle')
        spec = row('numa-lifecycle')
        text = basic_log('compressed', 'xswap', 'compression', 'c1-debug', 'numa2', spec) + text
        text = text.replace('ONLINE_NODES 0-1', 'ONLINE_NODES 0')
        result = evidence.parse(text, 'abc', 'compressed', 'xswap', 'compression', 8,
                                config_id='c1-debug', correctness_case=spec['id'], topology_id='numa2', expected_case=spec)
        self.assertFalse(result['gates']['configuration_identity'])


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
