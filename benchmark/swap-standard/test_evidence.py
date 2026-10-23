# SPDX-License-Identifier: GPL-2.0-only
import unittest
from evidence import parse


def block(kind, tag, body):
    return f"{kind}_BEGIN {tag}\n{body}\n{kind}_END {tag}\n"


def fixture(workload="usemem", backend="disk"):
    return (f"BENCH_BOOT\nCMDLINE_BEGIN\nbench.image_sha=abc bench.backend={backend} bench.mode=plain bench.workload={workload}\nCMDLINE_END\n"
            "ZSWAP_ENABLED N\nKERNEL_LOG_BEGIN\nLinux version test\nKERNEL_LOG_END\nBENCH_WORKLOAD_PASS\nBENCH_PASS\n"
            + block("VMSTAT", "before", "pswpout 0\npswpin 0")
            + block("VMSTAT", "end", "pswpout 100\npswpin 100")
            + "SWAP_PEAK_BEGIN\n/dev/vda 1024\nSWAP_PEAK_END\n")


def usemem(n=8):
    return ("USEMEM_EXPECT nproc=8 bytes_per_worker=1073741824\nUSEMEM_BEGIN\n"
            + "1207959552 bytes / 1000 usecs = 1048576 KB/s\n100 usecs to free memory\n" * n
            + "USEMEM_END\n")


class EvidenceTests(unittest.TestCase):
    def test_complete_usemem(self):
        r = parse(fixture() + usemem(), "abc", "disk", "plain", "usemem")
        self.assertTrue(all(r["gates"].values()), r)

    def test_partial_workers_fail(self):
        r = parse(fixture() + usemem(1), "abc", "disk", "plain", "usemem")
        self.assertFalse(r["gates"]["usemem_output"])

    def test_wrong_bytes_fail(self):
        r = parse(fixture() + usemem().replace("1207959552 bytes", "100 bytes"), "abc", "disk", "plain", "usemem")
        self.assertFalse(r["gates"]["usemem_output"])

    def test_missing_completion_fail(self):
        r = parse((fixture() + usemem()).replace("BENCH_PASS", ""), "abc", "disk", "plain", "usemem")
        self.assertFalse(r["gates"]["workload_complete"])

    def test_warning_fails(self):
        r = parse((fixture() + usemem()).replace("Linux version test", "WARNING: bad lock"), "abc", "disk", "plain", "usemem")
        self.assertFalse(r["gates"]["no_kernel_warnings"])

    def test_early_oom_outside_dmesg_fails(self):
        log = fixture() + usemem() + "Memory cgroup out of memory: Killed process 123 (usemem)\n"
        r = parse(log, "abc", "disk", "plain", "usemem")
        self.assertFalse(r["gates"]["no_kernel_warnings"])
        self.assertTrue(r["metrics"]["kernel_diagnostics"])

    def test_bad_identity_fails(self):
        r = parse(fixture() + usemem(), "different", "disk", "plain", "usemem")
        self.assertFalse(r["gates"]["cmdline_identity"])

    def test_no_swap_fails(self):
        r = parse((fixture() + usemem()).replace("pswpout 100", "pswpout 0"), "abc", "disk", "plain", "usemem")
        self.assertFalse(r["gates"]["swap_activity"])

    def test_metadata_missing_fields_fails(self):
        log = fixture("metadata", "brd") + block("MEMINFO", "metadata_before", "Bogus 1") + block("MEMINFO", "metadata_after", "Bogus 2")
        r = parse(log, "abc", "brd", "plain", "metadata")
        self.assertFalse(r["gates"]["meminfo_present"])
        self.assertFalse(r["gates"]["swap_capacity"])

    def test_metadata_requires_full_capacity(self):
        log = fixture("metadata", "brd") + "SWAPS_BEGIN\n/dev/ram0 partition 1073741820 0 0\nSWAPS_END\n"
        log += block("MEMINFO", "metadata_before", "MemAvailable: 8000000 kB\nMemFree: 8000000 kB\nSwapTotal: 0 kB")
        log += block("MEMINFO", "metadata_after", "MemAvailable: 7900000 kB\nMemFree: 7900000 kB\nSwapTotal: 1073741820 kB")
        self.assertTrue(all(parse(log, "abc", "brd", "plain", "metadata")["gates"].values()))
        log = log.replace("SwapTotal: 1073741820", "SwapTotal: 4092")
        self.assertFalse(parse(log, "abc", "brd", "plain", "metadata")["gates"]["swap_capacity"])

    def test_redis_default_ok_fails(self):
        log = fixture("redis") + "REDIS_GET GET: 42.0 requests per second\nREDIS_GET_BGSAVE GET: 40.0 requests per second\nREDIS_BGSAVE_STATUS ok\n"
        r = parse(log, "abc", "disk", "plain", "redis")
        self.assertFalse(r["gates"]["redis_bgsave_ok"])
        self.assertFalse(r["gates"]["redis_fill"])
        self.assertFalse(r["gates"]["redis_get_swap_activity"])

    def test_setup_swap_does_not_qualify_build(self):
        log = fixture("build") + "BUILD_REAL_USEC 1000\n" + block("CGSTAT", "build_start", "system_usec 1\nuser_usec 1") + block("CGSTAT", "end", "system_usec 2\nuser_usec 2")
        for tag in ("build_start", "build_end"):
            log += block("VMSTAT", tag, "pswpout 100\npswpin 100")
        r = parse(log, "abc", "disk", "plain", "build")
        self.assertFalse(r["gates"]["build_swap_activity"])

    def test_empty_swapin_samples_fail(self):
        log = fixture("swapin") + "SWAPIN_SEQ samples=0\nSWAPIN_RAND samples=0\nSWAPIN_DATA_PASS\n"
        r = parse(log, "abc", "disk", "plain", "swapin")
        self.assertFalse(r["gates"]["swapin_output"])

    def test_serial_crlf(self):
        r = parse((fixture() + usemem()).replace("\n", "\r\n"), "abc", "disk", "plain", "usemem")
        self.assertTrue(all(r["gates"].values()))


if __name__ == "__main__":
    unittest.main()


def lifetime(rounds=5, shrinks=3, zswpwb=500):
    log = (fixture("lifetime", "zswap")
           .replace("bench.mode=plain", "bench.mode=xswap")
           .replace("ZSWAP_ENABLED N", "ZSWAP_ENABLED Y")
           .replace("pswpout 100", "pswpout 100\nzswpout 900")
           .replace("/dev/vda 1024", "/dev/vda 1024\n/dev/xswap0 4096"))
    return (log + "WB_DELAY_MS none\n"
            + block("XSWAP", "lifetime_start", "grows 1\nshrinks 0")
            + block("XSWAP", "lifetime_end", f"grows 9\nshrinks {shrinks}")
            + block("VMSTAT", "lifetime_start", "zswpwb 0\npswpout 0\nzswpout 0")
            + block("VMSTAT", "lifetime_end", f"zswpwb {zswpwb}\npswpout 10\nzswpout 900")
            + f"CHURN_PASS rounds={rounds} workers=4 bytes=536870912 verified_workers={2 * rounds}\n")


class LifetimeTests(unittest.TestCase):
    def test_complete_lifetime(self):
        r = parse(lifetime(), "abc", "zswap", "xswap", "lifetime")
        self.assertTrue(all(r["gates"].values()), r)
        self.assertEqual(r["metrics"]["lifetime_xswap_delta"], {"grows": 8, "shrinks": 3})

    def test_no_shrink_fails(self):
        r = parse(lifetime(shrinks=0), "abc", "zswap", "xswap", "lifetime")
        self.assertFalse(r["gates"]["lifetime_shrink"])

    def test_no_writeback_fails(self):
        r = parse(lifetime(zswpwb=0), "abc", "zswap", "xswap", "lifetime")
        self.assertFalse(r["gates"]["lifetime_writeback"])

    def test_mismatch_fails(self):
        r = parse(lifetime() + "CHURN_MISMATCH salt=1 page=2 word=3\n", "abc", "zswap", "xswap", "lifetime")
        self.assertFalse(r["gates"]["lifetime_data"])

    def test_too_few_rounds_fail(self):
        r = parse(lifetime(rounds=2), "abc", "zswap", "xswap", "lifetime")
        self.assertFalse(r["gates"]["lifetime_data"])


def correctness(backend='disk'):
    log = fixture('correctness', backend).replace('bench.mode=plain', 'bench.mode=xswap')
    log = log.replace('/dev/vda 1024', '/dev/vda 1024\n/dev/xswap0 4096')
    if backend == 'zswap':
        log = log.replace('ZSWAP_ENABLED N', 'ZSWAP_ENABLED Y').replace('pswpout 100', 'pswpout 100\nzswpout 1000')
    log += 'XSWAP_TYPE 1\nFORK_TARGET_XSWAP_PTES 16 TOTAL 16384\n'
    log += 'FORK_SHARED_PASS\nCONCURRENT_FAULT_PASS workers=48 targets=16\nCOW_PASS\n'
    log += 'PHYSICAL_SWAPOFF_LIVE_XSWAP_PTES 16384 BACKEND_USED_KIB 65536\nPHYSICAL_SWAPOFF_LIVE_PASS\n'
    log += 'DESTROY_LIVE_XSWAP_PTES 16384\nDESTROY_LIVE_PASS\nSWAPOFF_LIVE_PASS\nEMPTY_SWAPS_PASS\nKERNEL_WORKLOAD_PASS\n'
    log += 'LATENCY_BEGIN samples=1000 skipped=15384 minor=1 major=1\n' + 'LATENCY_NS 500 TYPE 1\n' * 1000 + 'LATENCY_END\n'
    for phase in ('before', 'after_pressure', 'fork_shared', 'after_children', 'after_reads', 'after_settle'):
        log += f'META_BEGIN {phase}\nclusters_max 100\nclusters_mapped 20\nusage_pages 1000\ntail_free 0\ngrows 2\nshrinks 1\nMETA_END\n'
    log += block('VMSTAT', 'correctness_start', 'pswpin 0\npswpout 0\nzswpin 0\nzswpout 0')
    log += block('VMSTAT', 'correctness_end', 'pswpin 1000\npswpout 1000\nzswpin 1000\nzswpout 1000' if backend == 'zswap' else 'pswpin 1000\npswpout 1000\nzswpin 0\nzswpout 0')
    return log


class CorrectnessTests(unittest.TestCase):
    def check(self, text, backend='disk'):
        return parse(text, 'abc', backend, 'xswap', 'correctness')

    def test_complete_both_routes(self):
        for backend in ('disk', 'zswap'):
            r = self.check(correctness(backend), backend)
            self.assertTrue(all(r['gates'].values()), r)

    def test_missing_markers_and_proofs_fail(self):
        for marker in ('COW_PASS', 'FORK_SHARED_PASS', 'CONCURRENT_FAULT_PASS workers=48 targets=16', 'DESTROY_LIVE_PASS', 'SWAPOFF_LIVE_PASS', 'EMPTY_SWAPS_PASS', 'KERNEL_WORKLOAD_PASS', 'FORK_TARGET_XSWAP_PTES 16 TOTAL 16384', 'DESTROY_LIVE_XSWAP_PTES 16384', 'META_END'):
            self.assertFalse(all(self.check(correctness().replace(marker, ''))['gates'].values()), marker)

    def test_no_compressed_load_fails(self):
        self.assertFalse(self.check(correctness('zswap').replace('zswpin 1000', 'zswpin 0'), 'zswap')['gates']['correctness_evidence'])

    def test_wrong_swap_type_fails(self):
        self.assertFalse(self.check(correctness().replace('TYPE 1', 'TYPE 2', 1))['gates']['correctness_evidence'])

    def test_insufficient_live_ptes_fail(self):
        self.assertFalse(self.check(correctness().replace('DESTROY_LIVE_XSWAP_PTES 16384', 'DESTROY_LIVE_XSWAP_PTES 1'))['gates']['swapoff_live_pages'])

    def test_duplicate_marker_fails(self):
        self.assertFalse(self.check(correctness() + 'COW_PASS\n')['gates']['fork_cow'])

    def test_warning_alias_fails(self):
        self.assertFalse(self.check(correctness() + 'WARNING: bad lock\n')['gates']['no_new_kernel_warnings'])

    def test_physical_swapoff_requires_live_backend(self):
        log = correctness().replace('BACKEND_USED_KIB 65536', 'BACKEND_USED_KIB 0')
        self.assertFalse(self.check(log)['gates']['swapoff_live_pages'])
        log = correctness().replace('PHYSICAL_SWAPOFF_LIVE_PASS', '')
        self.assertFalse(self.check(log)['gates']['swapoff_live_pages'])

    def test_compressed_swapoff_allows_empty_physical_backend(self):
        log = correctness('zswap').replace('BACKEND_USED_KIB 65536', 'BACKEND_USED_KIB 0')
        self.assertTrue(self.check(log, 'zswap')['gates']['swapoff_live_pages'])

    def test_missing_start_counter_fails(self):
        log = correctness().replace('pswpin 0\npswpout 0\nzswpin 0\nzswpout 0', 'pswpout 0\nzswpin 0\nzswpout 0')
        self.assertFalse(self.check(log)['gates']['correctness_evidence'])

    def test_duplicate_phase_fails(self):
        log = correctness() + block('VMSTAT', 'correctness_start', 'pswpin 0\npswpout 0\nzswpin 0\nzswpout 0')
        self.assertFalse(self.check(log)['gates']['correctness_evidence'])

    def test_bad_snapshot_fails(self):
        self.assertFalse(self.check(correctness().replace('clusters_mapped 20', 'clusters_mapped 101'))['gates']['correctness_evidence'])


class MechanismTests(unittest.TestCase):
    def test_swapin_requires_phase_counters(self):
        log = fixture('swapin') + 'SWAPIN_SEQ samples=1000 mean_ns=100\nSWAPIN_RAND samples=1000 mean_ns=100\nSWAPIN_DATA_PASS\n'
        self.assertFalse(parse(log, 'abc', 'disk', 'plain', 'swapin')['gates']['swapin_phase_counters'])
        log += block('VMSTAT', 'swapin_start', 'swap_ra 0\nswap_ra_hit 0')
        log += block('VMSTAT', 'swapin_end', 'swap_ra 10\nswap_ra_hit 5')
        r = parse(log, 'abc', 'disk', 'plain', 'swapin')
        self.assertTrue(all(r['gates'].values()), r)
        self.assertEqual(r['metrics']['swapin_vmstat_delta']['swap_ra_hit'], 5)
