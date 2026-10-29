# SPDX-License-Identifier: GPL-2.0-only
"""Synthetic probe bands and categorical outcomes, never kernel runtime evidence."""
import copy
import json
from pathlib import Path
import unittest

import probe

BASE = Path(__file__).resolve().parent


def protocol():
    return json.loads((BASE / "revision4-protocol-template.json").read_text())


def metrics(counter=10, metadata=.206):
    return {"swapin_vmstat_delta": {name: counter for name in probe.VMSTAT},
            probe.METADATA: metadata}


def samples(p, count, counter=10, metadata=.206):
    return {name: [metrics(counter, metadata) for _ in range(count)] for name in p["tiers"]["probe"]["cases"]}


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.p = protocol()
        self.baseline = samples(self.p, 3)
        self.cal = probe.calibrate(self.p, self.baseline)
        self.mechanism = "swapin-disk:swapin_vmstat_delta.swap_ra_hit:up"

    def test_integer_floor_and_fractional_metadata_band(self):
        counter = self.cal["bands"]["swapin-disk"]["swapin_vmstat_delta.swap_ra_hit"]
        self.assertEqual((counter["low"], counter["high"], counter["n"]), (9, 11, 3))
        metadata = self.cal["bands"]["metadata-brd"][probe.METADATA]
        self.assertAlmostEqual(metadata["low"], .20394)
        self.assertAlmostEqual(metadata["high"], .20806)
        zero = probe.band([0, 0, 0], integer=True, settings=probe.DEFAULT_CONSTANTS)
        self.assertEqual((zero["low"], zero["high"]), (-1, 1))

    def test_engaged_not_engaged_reversed_and_metadata_guard(self):
        for value, expected, reason in ((12, "PROBE_PASS", None), (11, "PROBE_REJECT", "MECHANISM_NOT_ENGAGED"),
                                        (8, "PROBE_REJECT", "MECHANISM_REVERSED")):
            result = probe.compare(self.p, self.cal, samples(self.p, 1, value), self.mechanism)
            self.assertEqual(result["status"], expected)
            if reason:
                self.assertIn(reason, result["reasons"])
            self.assertFalse(result["performance_accepted"])
        result = probe.compare(self.p, self.cal, samples(self.p, 1, 12, .209), self.mechanism)
        self.assertEqual(result["status"], "PROBE_REJECT")
        self.assertIn("metadata-brd: METADATA_REGRESSION", result["reasons"])

    def test_metadata_noise_blocks_probe_calibration(self):
        self.baseline["metadata-brd"][1][probe.METADATA] = .209
        cal = probe.calibrate(self.p, self.baseline)
        self.assertEqual(cal["status"], "CALIBRATION_NOISY")
        self.assertFalse(cal["passed"])
        with self.assertRaisesRegex(ValueError, "not passed"):
            probe.compare(self.p, cal, samples(self.p, 1, 12), self.mechanism)

    def test_missing_nonfinite_and_impossible_evidence_fail_closed(self):
        for bad in (float("nan"), float("inf"), None, True, -.1):
            with self.subTest(bad=bad):
                candidate = samples(self.p, 1, 12, bad)
                with self.assertRaises(ValueError):
                    probe.compare(self.p, self.cal, candidate, self.mechanism)
        candidate = samples(self.p, 1, 12)
        del candidate["swapin-disk"][0]["swapin_vmstat_delta"]["swap_ra_hit"]
        with self.assertRaises(KeyError):
            probe.compare(self.p, self.cal, candidate, self.mechanism)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            probe.compare(self.p, self.cal, samples(self.p, 0), self.mechanism)

    def test_mechanism_must_name_a_declared_case_and_signal(self):
        for mechanism in ("swapin-disk:swapin_vmstat_delta.swap_ra_hit:sideways", "unknown:swapin_vmstat_delta.swap_ra_hit:up",
                          "swapin-disk:swapin_vmstat_delta.no_such_counter:up", "swapin-disk:xswap.usage_pages:down"):
            with self.subTest(mechanism=mechanism), self.assertRaises(ValueError):
                probe.validate_mechanism(self.p, mechanism)

    def test_xswap_snapshot_delta_can_be_a_decreasing_gauge(self):
        case = self.p["cases"]["swapin-disk"]
        case.update(mode="xswap", probe_signals=["xswap.usage_pages"])
        for row in self.baseline["swapin-disk"]:
            row["swapin_xswap_snapshots"] = {"swapin_start": {"usage_pages": 10}, "swapin_end": {"usage_pages": 10}}
        cal = probe.calibrate(self.p, self.baseline)
        candidate = samples(self.p, 1)
        candidate["swapin-disk"][0]["swapin_xswap_snapshots"] = {"swapin_start": {"usage_pages": 10}, "swapin_end": {"usage_pages": 7}}
        result = probe.compare(self.p, cal, candidate, "swapin-disk:xswap.usage_pages:down")
        self.assertEqual(result["status"], "PROBE_PASS")
        self.assertEqual(result["probe_signals"]["swapin-disk"]["xswap.usage_pages"], [-3])

    def test_revision6_zram64k_counters_are_integer_count_signals(self):
        p = json.loads((BASE.parents[1] / "campaigns/xswap-tcg-kbench-2026-10-29/protocol.json").read_text())
        for key in ("swap_ra", "swap_ra_hit", "pgmajfault"):
            case, signal, direction = probe.validate_mechanism(
                p, "swapin-zram-64k:swapin_vmstat_delta." + key + ":up")
            self.assertEqual((case, signal, direction), ("swapin-zram-64k", "swapin_vmstat_delta." + key, "up"))
        rows = {name: [{"swapin_vmstat_delta": {n: 10 for n in probe.VMSTAT},
                        "swapin_xswap_snapshots": {"swapin_start": {n: 4 for n in ("grows", "shrinks", "usage_pages", "clusters_mapped")},
                                                   "swapin_end": {n: 4 for n in ("grows", "shrinks", "usage_pages", "clusters_mapped")}},
                        probe.METADATA: 0.2} for _ in range(3)]
                for name in p["tiers"]["probe"]["cases"]}
        cal = probe.calibrate(p, rows)
        band = cal["bands"]["swapin-zram-64k"]["swapin_vmstat_delta.swap_ra"]
        self.assertEqual((band["low"], band["high"]), (9, 11))
        self.assertIsInstance(probe.signal({"swapin_vmstat_delta": {"swap_ra": 12}}, "swapin_vmstat_delta.swap_ra"), int)
        with self.assertRaises(ValueError):
            probe.signal({"swapin_vmstat_delta": {"swap_ra": 12.5}}, "swapin_vmstat_delta.swap_ra")

    def test_template_budget_is_planned_and_within_default_cap(self):
        self.assertTrue(self.p["template_only"])
        planned = self.p["planned_guest_counts"]
        self.assertEqual(self.p["budget"]["probe_guest_attempts"] + self.p["budget"]["guest_attempts"], 120)
        self.assertEqual(planned["minimum_total"], 3 * 3 + 8 * 3 + 10 * 2 * 2 + 2 * 4 * 2 * 2)
        self.assertEqual(planned["minimum_total"] + planned["reserved_for_correctness_and_validity"], 120)
        self.assertIn("BLOCKED", self.p["correctness_capability"])


if __name__ == "__main__":
    unittest.main()
