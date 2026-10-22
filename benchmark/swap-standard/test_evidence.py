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
