# SPDX-License-Identifier: GPL-2.0-only
"""The host-RAM threshold is the one run.py uses, and it does not launch a guest."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import host_preflight as hp
import void_calibration as vc

ROOT = Path(__file__).resolve().parents[3]
TCG = {"SWAP_NEXT_ACCEL": "tcg", "SWAP_NEXT_TCG_MEM_MIB": "4096", "SWAP_NEXT_TCG_SMP": "4"}


class HostPreflightTests(unittest.TestCase):
    def test_meminfo_parser_reads_kib(self):
        self.assertEqual(hp.mem_available_kib("MemTotal: 1 kB\nMemAvailable:    5242880 kB\n"), 5242880)
        with self.assertRaises(OSError):
            hp.mem_available_kib("MemFree: 1 kB\n")

    def test_tcg_needs_guest_plus_1024_mib_and_kvm_needs_10240(self):
        self.assertEqual(hp.need_kib(True, 4096), 5120 * 1024)
        self.assertEqual(hp.need_kib(False, 8192), 10 * 1024**2)
        self.assertEqual(hp.refusal_for(5120 * 1024 - 1, True, 4096), "need 5120 MiB available host RAM")
        self.assertIsNone(hp.refusal_for(5120 * 1024, True, 4096))
        self.assertEqual(hp.refusal_for(10240 * 1024 - 1, False, 8192), "need 10240 MiB available host RAM")
        self.assertIsNone(hp.refusal_for(10240 * 1024, False, 8192))
        self.assertRegex(hp.refusal_for(1, True, 4096), vc.PREFLIGHT_LINE)
        self.assertRegex(hp.DISK_MESSAGE, vc.PREFLIGHT_LINE)

    def test_refusal_uses_guest_shape_from_the_child_environment(self):
        with patch.object(hp, "mem_available_kib", return_value=5120 * 1024 - 1):
            self.assertEqual(hp.refusal(TCG), "need 5120 MiB available host RAM")
        with patch.object(hp, "mem_available_kib", return_value=5120 * 1024):
            self.assertIsNone(hp.refusal(TCG))
        with patch.object(hp, "mem_available_kib", return_value=10240 * 1024 - 1):
            self.assertEqual(hp.refusal({"SWAP_NEXT_ACCEL": "kvm"}), "need 10240 MiB available host RAM")

    def test_runner_calls_the_same_threshold(self):
        source = (ROOT / "benchmark/swap-standard/run.py").read_text()
        self.assertIn("host_preflight.mem_available_kib()", source)
        self.assertIn("host_preflight.refusal_for(available, tcg, guest_mib)", source)
        self.assertIn('raise SystemExit("need 24 GiB free disk")', source)
        self.assertNotIn("(guest_mib + 1024) * 1024", source)


if __name__ == "__main__":
    unittest.main()
