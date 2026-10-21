# SPDX-License-Identifier: GPL-2.0-only
import unittest
from evidence import parse, PHASES

def fixture():
    parts = ["XSWAP_BOOT", "11111111-1111-1111-1111-111111111111", "XSWAP_TYPE 1", "XSWAP_RUNTIME_PASS",
             "VMSTAT_BEFORE", "pswpin 0", "pswpout 0", "zswpin 0", "zswpout 0",
             "DISKSTAT_BEFORE", "0 0 0 0 0 0 0 0 0 0 0"]
    for phase in PHASES:
        parts += ["META_BEGIN "+phase, "clusters_max 4096", "clusters_mapped 16",
                  "usage_pages 1", "tail_free 1", "grows 0", "shrinks 0", "META_END"]
    parts += ["LATENCY_BEGIN samples=1000 skipped=15384 minor=1000 major=0"]
    parts += ["LATENCY_NS 1000 TYPE 1"] * 1000
    parts += ["LATENCY_END", "FORK_SHARED_PASS", "COW_PASS", "DESTROY_LIVE_PASS",
              "SWAPOFF_LIVE_PASS", "WORKLOAD_NS 12345", "DESTROY_LIVE_XSWAP_PTES 1000", "KERNEL_WORKLOAD_PASS", "VMSTAT_AFTER",
              "pswpin 10", "pswpout 10", "zswpin 0", "zswpout 0",
              "DISKSTAT_AFTER", "1 0 8 0 1 0 8 0 0 0 0", "EMPTY_SWAPS_PASS",
              "SWAPS_BEGIN", "Filename Type Size Used Priority", "SWAPS_END",
              "KERNEL_LOG_BEGIN", "kernel clean", "KERNEL_LOG_END", "XSWAP_PASS"]
    return "\n".join(parts)+"\n"

class EvidenceTests(unittest.TestCase):
    def test_complete(self):
        result=parse(fixture())
        self.assertTrue(all(result["gates"].values()), result)
        self.assertEqual(result["metrics"]["swapped_first_access_p99_us"], 1)
        self.assertEqual(result["metrics"]["sampled_mapped_clusters_max"], 16)
    def reject(self, text, gate):
        self.assertFalse(parse(text)["gates"][gate])
    def test_missing_vmstat_is_not_zero(self):
        self.reject(fixture().replace("zswpin 0\n","",1), "evidence_complete")
    def test_duplicate_snapshot(self):
        self.reject(fixture().replace("META_BEGIN after_settle", "META_BEGIN before"), "evidence_complete")
    def test_missing_snapshot_field(self):
        self.reject(fixture().replace("shrinks 0\n","",1), "evidence_complete")
    def test_wrong_type_single_sample(self):
        self.reject(fixture().replace("TYPE 1","TYPE 0",1), "every_sample_xswap")
    def test_missing_sample(self):
        self.reject(fixture().replace("LATENCY_NS 1000 TYPE 1\n","",1), "sample_count")
    def test_malformed_sample(self):
        self.reject(fixture().replace("LATENCY_NS 1000 TYPE 1","LATENCY_NS 1000 TYPE bad",1), "sample_count")
    def test_warning(self):
        self.reject(fixture().replace("kernel clean","WARNING: bad"), "no_kernel_warnings")
    def test_truncated_kernel_log(self):
        self.reject(fixture().replace("KERNEL_LOG_END",""), "kernel_log_complete")
    def test_failed_workload_even_with_pass(self):
        self.reject(fixture()+"XSWAP_FAIL workload\n", "completed")
    def test_live_swap(self):
        self.reject(fixture().replace("SWAPS_END","/dev/vda partition 1 1 -2\nSWAPS_END"), "empty_swaps")
    def test_counter_regression(self):
        self.reject(fixture().replace("pswpin 0","pswpin 100"), "evidence_complete")
    def test_duplicate_boot(self):
        self.reject(fixture()+"11111111-1111-1111-1111-111111111111\n", "boot_identity")
    def test_invalid_maximum(self):
        self.reject(fixture().replace("clusters_max 4096","clusters_max 1"), "evidence_complete")
    def test_outside_sample_cannot_replace_malformed_inside(self):
        text=fixture().replace("LATENCY_NS 1000 TYPE 1", "LATENCY_NS invalid", 1)
        self.reject(text+"LATENCY_NS 1000 TYPE 1\n", "sample_count")
    def test_missing_live_destroy_ptes(self):
        self.reject(fixture().replace("DESTROY_LIVE_XSWAP_PTES 1000", "DESTROY_LIVE_XSWAP_PTES 0"), "destroy_live_xswap_ptes")
    def test_missing_duration(self):
        self.reject(fixture().replace("WORKLOAD_NS 12345\n", ""), "workload_duration")
    def test_missing_type(self):
        self.reject(fixture().replace("XSWAP_TYPE 1\n",""), "evidence_complete")

if __name__ == "__main__":
    unittest.main()
