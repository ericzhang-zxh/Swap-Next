# SPDX-License-Identifier: GPL-2.0-only
"""Guest-free validity and revision 3 protocol tests."""
import json
from pathlib import Path
import tempfile
import unittest

from validity import (classify_attempt, clocksource_invalid, launch_blocked,
                      parse_loadavg, parse_psi, protocol_rules, read_host_load, wall_outlier)

ROOT = Path(__file__).resolve().parents[2]
RULES = {"pre_qemu_seconds_max": 60, "wall_factor": 1.5, "wall_min_samples": 3}


def result(clocksource=False, pre=1.0, wall=100.0):
    return {"clocksource_invalid": clocksource, "pre_qemu_seconds": pre, "wall_seconds": wall,
            "host_load": {"before_launch": {"loadavg_1m": 0.1, "loadavg_5m": 0.1, "loadavg_15m": 0.1}}}


class ValidityTests(unittest.TestCase):
    def test_clocksource_fallback_markers(self):
        self.assertTrue(clocksource_invalid("tsc: Marking TSC unstable due to check_tsc_sync_source failed"))
        self.assertTrue(clocksource_invalid("clocksource: Marking clocksource 'tsc' as unstable because the skew is too large"))
        self.assertTrue(clocksource_invalid("clocksource: Switched to clocksource hpet"))
        self.assertFalse(clocksource_invalid("clocksource: Switched to clocksource tsc"))
        self.assertFalse(clocksource_invalid("Linux version test"))

    def test_pre_launch_stall_blocks_only_revision_3(self):
        self.assertFalse(launch_blocked(3, 60))
        self.assertTrue(launch_blocked(3, 60.01))
        self.assertFalse(launch_blocked(2, 120))

    def test_wall_gate_waits_for_three_samples_and_uses_a_strict_factor(self):
        self.assertFalse(wall_outlier(1000, [10, 10], 1.5, 3))
        self.assertFalse(wall_outlier(90, [60, 60, 60], 1.5, 3))
        self.assertTrue(wall_outlier(90.01, [60, 60, 60], 1.5, 3))
        valid, reason = classify_attempt(result(wall=100), [100, 100, 100], RULES)
        self.assertTrue(valid)
        self.assertIsNone(reason)
        valid, reason = classify_attempt(result(clocksource=True, pre=61, wall=200), [100, 100, 100], RULES)
        self.assertFalse(valid)
        self.assertEqual(reason, "clocksource_fallback+pre_qemu_delay+wall_time_outlier")
        with self.assertRaises(ValueError):
            classify_attempt({"wall_seconds": 1}, [], RULES)

    def test_host_load_records_loadavg_and_psi_when_present(self):
        self.assertEqual(parse_loadavg("0.10 0.20 0.30 1/100 9"),
                         {"loadavg_1m": 0.10, "loadavg_5m": 0.20, "loadavg_15m": 0.30})
        psi = parse_psi("some avg10=1.50 avg60=0.25 avg300=0.00 total=10\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0\n")
        self.assertEqual(psi["some"]["avg10"], 1.50)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "load").write_text("1.00 2.00 3.00 1/2 3\n")
            pressure = root / "pressure"
            pressure.mkdir()
            (pressure / "cpu").write_text("some avg10=0.50 avg60=0.00 avg300=0.00 total=1\n")
            snap = read_host_load(root / "load", pressure)
        self.assertEqual(snap["loadavg_1m"], 1.0)
        self.assertEqual(snap["psi"]["cpu"]["some"]["avg10"], 0.50)
        self.assertNotIn("memory", snap["psi"])

    def test_revision3_protocol_shape(self):
        protocol = json.loads((ROOT / "benchmark/swap-standard/protocol-tcg-revision3.json").read_text())
        rules = protocol_rules(protocol)
        self.assertEqual(rules["protocol_revision"], 3)
        self.assertEqual(rules["noise_ceiling"], 0.25)
        self.assertEqual(rules["envelope"], "p90")
        self.assertEqual(rules["decision"], "median")
        self.assertEqual(rules["advisory_suffixes"], (".p99_ns",))
        self.assertEqual(rules["max_reruns"], 2)
        self.assertEqual(protocol["guest"], {"vcpus": 4, "mem_mib": 4096, "swap_gib": 16})
        self.assertEqual(protocol["tiers"]["fast"]["calibration_pairs"], 10)
        self.assertEqual(protocol["tiers"]["fast"]["comparison_pairs"], 4)
        self.assertEqual(protocol["accelerator"]["require"], "tcg")
        self.assertEqual(protocol["campaign"], "xswap-tcg-rev3-2026-10-25")
        self.assertEqual(protocol["state_directory"], "evolve/swap-standard/state-xswap-tcg-rev3-2026-10-25")
        self.assertTrue(protocol["preallocate_swap"])
        self.assertNotIn("slow", protocol["tiers"])
        rev1 = json.loads((ROOT / "results/xswap-next-2026-10-24/protocol-revision1.json").read_text())
        rev2 = json.loads((ROOT / "results/xswap-next-2026-10-24/protocol-revision2.json").read_text())
        self.assertNotIn("protocol_revision", rev1)
        self.assertEqual(rev2["protocol_revision"], 2)
        self.assertEqual(rev1["noise_ceiling"], 0.2)
        self.assertEqual(rev2["noise_ceiling"], 0.2)
        self.assertEqual(rev1["tiers"]["fast"]["calibration_pairs"], 2)
        self.assertEqual(rev2["tiers"]["fast"]["comparison_pairs"], 2)


if __name__ == "__main__":
    unittest.main()
