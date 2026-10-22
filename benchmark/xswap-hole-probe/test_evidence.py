# SPDX-License-Identifier: GPL-2.0-only
import unittest
from evidence import FIELDS, expected_events, parse

IMAGE = 'a' * 64


def fixture(backend='disk'):
    lines = ['XSWAP_BOOT', '11111111-1111-1111-1111-111111111111',
             'CMDLINE_BEGIN', f'console=ttyS0 evolve.backend={backend} evolve.image_sha={IMAGE}',
             'CMDLINE_END', 'XSWAP_TYPE 1', 'XSWAP_RUNTIME_PASS',
             'VMSTAT_BEFORE', 'pswpin 0', 'pswpout 0', 'zswpin 0', 'zswpout 0',
             'DISKSTAT_BEFORE', '0 0 0 0 0 0 0 0 0 0 0']
    values = dict.fromkeys(FIELDS, 0)
    values.update(clusters_max=8192, clusters_mapped=2048, clusters_free=1500, tail_free=500,
                  clusters_nonempty=10, highest_nonempty_plus1=1088, highest_blocker_plus1=1088,
                  referenced_pages=1000, highest_referenced_plus1=1088)
    for event in expected_events():
        if event[0] == 'META_BEGIN':
            lines += ['META_BEGIN ' + event[1]]
            lines += [f'{key} {value}' for key, value in sorted(values.items())]
            lines += ['META_END']
        elif event[0] == 'PLACEMENT':
            label, cycle = event[1:]
            if label == 'filler_swapout':
                counts = 'swapped=200000 total=262144 min_cluster=0 max_cluster=1200'
            else:
                counts = 'swapped=1000 total=16384 min_cluster=1024 max_cluster=1087'
            lines += [f'PLACEMENT {label} cycle={cycle} {counts}']
        elif event[0] == 'DESTROY_LIVE_XSWAP_PTES':
            lines += ['DESTROY_LIVE_XSWAP_PTES 1000']
        else:
            lines += [' '.join(map(str, event))]
    z = 10 if backend == 'zswap' else 0
    lines += ['VMSTAT_AFTER', 'pswpin 10', 'pswpout 10', f'zswpin {z}', f'zswpout {z}',
              'DISKSTAT_AFTER', '1 0 8 0 1 0 8 0 0 0 0', 'EMPTY_SWAPS_PASS',
              'SWAPS_BEGIN', 'Filename Type Size Used Priority', 'SWAPS_END',
              'KERNEL_LOG_BEGIN', 'kernel clean', 'KERNEL_LOG_END', 'XSWAP_PASS']
    return '\n'.join(lines) + '\n'


class ParserTests(unittest.TestCase):
    def reject(self, text):
        result = parse(text, IMAGE, 'disk')
        self.assertFalse(all(result['gates'].values()), result)

    def test_both_backends(self):
        for backend in ('disk', 'zswap'):
            result = parse(fixture(backend), IMAGE, backend)
            self.assertTrue(all(result['gates'].values()), result)
            self.assertFalse(result['performance_accepted'])
            self.assertEqual(result['topology']['cycle2_after_settle']['interior_free_estimate'], 1000)

    def test_each_required_event_missing(self):
        for line in ('HOLE_CYCLE_BEGIN 1', 'FILLER_DATA_PASS 1', 'HOLE_CYCLE_PASS 2',
                     'ANCHOR_DATA_PASS', 'COW_PASS', 'DESTROY_LIVE_PASS', 'SWAPOFF_LIVE_PASS',
                     'KERNEL_WORKLOAD_PASS', 'KERNEL_LOG_END', 'CMDLINE_END', 'XSWAP_PASS'):
            with self.subTest(line=line):
                self.reject(fixture().replace(line + '\n', '', 1))

    def test_order_and_duplicate(self):
        self.reject(fixture().replace('HOLE_CYCLE_BEGIN 0', 'HOLE_CYCLE_BEGIN 1', 1))
        self.reject(fixture().replace('COW_PASS', 'COW_PASS\nCOW_PASS', 1))
        self.reject(fixture().replace('ANCHOR_DATA_PASS\nCOW_PASS', 'COW_PASS\nANCHOR_DATA_PASS'))

    def test_filler_threshold(self):
        self.reject(fixture().replace('swapped=200000', 'swapped=196607', 1))
        self.assertTrue(all(parse(fixture().replace('swapped=200000', 'swapped=196608'), IMAGE, 'disk')['gates'].values()))

    def test_anchor_prerequisites_at_every_cycle(self):
        for cycle in range(3):
            for label in ('anchor_after_unmap', 'anchor_after_settle'):
                prefix = f'PLACEMENT {label} cycle={cycle} '
                self.reject(fixture().replace(prefix+'swapped=1000', prefix+'swapped=999'))
                self.reject(fixture().replace(prefix+'swapped=1000 total=16384 min_cluster=1024',
                                             prefix+'swapped=1000 total=16384 min_cluster=511'))

    def test_placement_bounds_and_destroy_match(self):
        self.reject(fixture().replace('max_cluster=1087', 'max_cluster=8192', 1))
        self.reject(fixture().replace('total=16384', 'total=999', 1))
        self.reject(fixture().replace('DESTROY_LIVE_XSWAP_PTES 1000', 'DESTROY_LIVE_XSWAP_PTES 999'))
        self.reject(fixture().replace('PLACEMENT anchor_initial', 'PLACEMENT wrong_label'))

    def test_snapshot_fields_bounds_and_nonatomic_usage(self):
        self.reject(fixture().replace('cache_only_pages 0\n', '', 1))
        self.reject(fixture().replace('cache_only_pages 0', 'cache_only_pages -1', 1))
        self.reject(fixture().replace('clusters_free 1500', 'clusters_free 9000', 1))
        self.reject(fixture().replace('META_END', 'META_END\nMETA_END', 1))
        self.assertTrue(all(parse(fixture().replace('usage_pages 0', 'usage_pages 123456'), IMAGE, 'disk')['gates'].values()))

    def test_boot_and_image(self):
        self.reject(fixture().replace(IMAGE, 'b'*64))
        self.reject(fixture().replace('evolve.backend=disk', 'evolve.backend=zswap'))
        self.reject(fixture()+'11111111-1111-1111-1111-111111111111\n')
        self.reject(fixture().replace('XSWAP_TYPE 1', 'XSWAP_TYPE 32'))

    def test_kernel_warning_backend_failure_and_empty_swap(self):
        self.reject(fixture().replace('kernel clean', 'WARNING: bad'))
        self.reject(fixture().replace('pswpin 10', 'pswpin 0'))
        self.reject(fixture().replace('zswpin 0', 'zswpin 1', 1))
        self.reject(fixture().replace('SWAPS_END', '/dev/vda partition 1 1 -2\nSWAPS_END'))
        self.reject(fixture()+'XSWAP_FAIL hole_probe data_mismatch\n')
        self.reject(fixture().replace('VMSTAT_AFTER', 'VMSTAT_AFTER\nVMSTAT_AFTER'))
        text = fixture().replace('KERNEL_LOG_BEGIN\nkernel clean\nKERNEL_LOG_END\n', '')
        self.reject('KERNEL_LOG_BEGIN\nkernel clean\nKERNEL_LOG_END\n' + text)


if __name__ == '__main__':
    unittest.main()
