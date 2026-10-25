# SPDX-License-Identifier: GPL-2.0-only
"""Statistical invariants and fail-closed analysis tests."""
import copy
import importlib.util
import math
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("standard_analysis", Path(__file__).with_name("analysis.py"))
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


def pairs(ratios, directions=None):
    directions = directions or {"usemem.throughput": "higher"}
    return [{"a": {k: 100.0 for k in directions},
             "b": {k: 100.0 * ratio if d == "higher" else 100.0 / ratio
                   for k, d in directions.items()}} for ratio in ratios]


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.directions = {"usemem.throughput": "higher", "build.elapsed": "lower"}
        self.calibration = analysis.calibrate(pairs([1, 1], self.directions), self.directions)

    def test_direction_and_pairwise_not_pooled_ratio(self):
        data = [{"a": {"x": 1}, "b": {"x": 2}},
                {"a": {"x": 100}, "b": {"x": 50}}]
        result = analysis.compare(data, {"x": "higher"},
                                  analysis.calibrate(pairs([1, 1], {"x": "higher"}), {"x": "higher"}), "fast")
        self.assertAlmostEqual(result["overall_geomean_ratio"], 1)
        gain = analysis.compare(pairs([1.1, 1.1], self.directions),
                                self.directions, self.calibration, "fast")
        for metric in gain["metrics"].values():
            self.assertAlmostEqual(metric["geomean_ratio"], 1.1)

    def test_calibration_floor_and_outlier_rejection(self):
        self.assertAlmostEqual(self.calibration["noise_relative"]["build.elapsed"], .03)
        bad = analysis.calibrate(pairs([1, 1, 1.21], self.directions), self.directions)
        self.assertFalse(bad["passed"])
        self.assertEqual(bad["status"], "CALIBRATION_NOISY")
        with self.assertRaises(ValueError):
            analysis.compare(pairs([1, 1], self.directions), self.directions, bad, "fast")

    def test_fast_guard_detects_one_bad_metric(self):
        data = pairs([1.2, 1.2], self.directions)
        for row in data:
            row["b"]["build.elapsed"] = 110
        result = analysis.compare(data, self.directions, self.calibration, "fast")
        self.assertEqual(result["status"], "REGRESSION")
        self.assertFalse(result["eligible_for_slow"])

    def test_fast_tolerates_calibrated_noise(self):
        data = pairs([.98, .98], self.directions)
        result = analysis.compare(data, self.directions, self.calibration, "fast")
        self.assertTrue(result["eligible_for_slow"])

    def test_slow_gain_and_determinism(self):
        data = pairs([1.08, 1.10, 1.12, 1.09] * 3, self.directions)
        first = analysis.compare(data, self.directions, self.calibration, "slow")
        second = analysis.compare(data, self.directions, self.calibration, "slow")
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "NEEDS_REVIEW")
        self.assertTrue(first["needs_review"])
        self.assertFalse(first["performance_accepted"])
        self.assertGreater(first["overall_ci95"][0], 1.03)

    def test_joint_bootstrap_preserves_anticorrelation(self):
        data = [{"a": {"x": 100, "y": 100}, "b": {"x": 200, "y": 50}},
                {"a": {"x": 100, "y": 100}, "b": {"x": 50, "y": 200}}]
        directions = {"x": "higher", "y": "higher"}
        calibration = analysis.calibrate(pairs([1, 1], directions), directions)
        result = analysis.compare(data * 5, directions, calibration, "slow")
        for bound in result["overall_ci95"]:
            self.assertAlmostEqual(bound, 1)
        self.assertEqual(result["status"], "INCONCLUSIVE")

    def test_slow_no_gain_and_guard_regression_are_inconclusive(self):
        equal = analysis.compare(pairs([1] * 10, self.directions),
                                 self.directions, self.calibration, "slow")
        self.assertEqual(equal["status"], "INCONCLUSIVE")
        data = pairs([1.5] * 10, self.directions)
        for row in data:
            row["b"]["build.elapsed"] = 110
        result = analysis.compare(data, self.directions, self.calibration, "slow")
        self.assertGreater(result["overall_ci95"][0], 1.03)
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertFalse(result["metrics"]["build.elapsed"]["guard_pass"])

    def test_reference_is_never_admitted(self):
        for tier in ("fast",):
            result = analysis.compare(pairs([1.2, 1.2], self.directions),
                                      self.directions, self.calibration, tier, reference=True)
            self.assertEqual(result["status"], "REFERENCE_COMPLETE")
            self.assertFalse(result["eligible_for_slow"])
            self.assertFalse(result["needs_review"])

    def test_invalid_metrics_fail_closed(self):
        for value in (None, True, 0, -1, math.nan, math.inf, "3"):
            data = pairs([1, 1], self.directions)
            data[0]["a"]["build.elapsed"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                analysis.calibrate(data, self.directions)
        for mutate in (
            lambda p: p[0]["a"].pop("build.elapsed"),
            lambda p: p[0]["b"].update(extra=1),
            lambda p: p.pop(),
        ):
            data = pairs([1, 1], self.directions)
            mutate(data)
            with self.assertRaises(ValueError):
                analysis.calibrate(data, self.directions)

    def test_primary_weights_cases_and_keeps_guards(self):
        directions = {"x.main": "higher", "x.guard": "higher", "y.main": "higher"}
        primary = ["x.main", "y.main"]
        calibration = analysis.calibrate(pairs([1, 1], directions), directions, primary)
        data = pairs([1.1] * 10, directions)
        for row in data:
            row["b"]["x.guard"] = 105
        result = analysis.compare(data, directions, calibration, "slow", primary=primary)
        self.assertAlmostEqual(result["combined_score"], 1.1)
        with self.assertRaises(ValueError):
            analysis.compare(data, directions, calibration, "fast")

    def test_tier_minimum_and_reference_boundaries(self):
        with self.assertRaises(ValueError):
            analysis.compare(pairs([1] * 9, self.directions),
                             self.directions, self.calibration, "slow")
        with self.assertRaises(ValueError):
            analysis.compare(pairs([1] * 10, self.directions),
                             self.directions, self.calibration, "slow", reference=True)

    def test_mismatched_calibration_fails_closed(self):
        for field, value in (("directions", {"other": "higher"}),
                             ("noise_log", {"usemem.throughput": .03}),
                             ("passed", False)):
            calibration = copy.deepcopy(self.calibration)
            calibration[field] = value
        with self.assertRaises(ValueError):
            analysis.compare(pairs([1, 1], self.directions), self.directions, calibration, "fast")


class Revision3Tests(unittest.TestCase):
    def test_p90_drops_one_outlier_and_keeps_the_ceiling(self):
        directions = {"x": "higher"}
        passed = analysis.calibrate(pairs([1.10] * 9 + [1.50], directions), directions,
                                    envelope="p90", min_pairs=10, noise_ceiling=0.25)
        self.assertTrue(passed["passed"])
        self.assertEqual(passed["status"], "CALIBRATED")
        self.assertAlmostEqual(passed["noise_relative"]["x"], 0.10)
        rejected = analysis.calibrate(pairs([1.26] * 10, directions), directions,
                                      envelope="p90", min_pairs=10, noise_ceiling=0.25)
        self.assertFalse(rejected["passed"])
        self.assertEqual(rejected["rejected_metrics"], ["x"])
        with self.assertRaises(ValueError):
            analysis.calibrate(pairs([1.0] * 9, directions), directions, envelope="p90", min_pairs=9)

    def test_p99_is_advisory_and_comparison_uses_the_median(self):
        directions = {"case.mean_ns": "lower", "case.p99_ns": "lower"}
        rows = [{"a": {"case.mean_ns": 100.0, "case.p99_ns": 100.0},
                 "b": {"case.mean_ns": 105.0, "case.p99_ns": 140.0}} for _ in range(10)]
        calibration = analysis.calibrate(rows, directions, primary=["case.mean_ns"], envelope="p90",
                                         min_pairs=10, noise_ceiling=0.25, advisory_suffixes=(".p99_ns",))
        self.assertTrue(calibration["passed"])
        self.assertEqual(calibration["advisory_metrics"], ["case.p99_ns"])
        self.assertGreater(calibration["noise_relative"]["case.p99_ns"], 0.25)
        with self.assertRaises(ValueError):
            analysis.calibrate(rows, directions, primary=["case.p99_ns"], envelope="p90",
                               min_pairs=10, advisory_suffixes=(".p99_ns",))
        data = [{"a": {"case.mean_ns": 100.0, "case.p99_ns": 100.0},
                 "b": {"case.mean_ns": 100.0, "case.p99_ns": 200.0}} for _ in range(4)]
        screen = analysis.compare(data, directions, calibration, "fast", primary=["case.mean_ns"],
                                  decision="median", min_pairs=4)
        self.assertEqual(screen["status"], "FAST_PASS")
        self.assertTrue(screen["metrics"]["case.p99_ns"]["advisory"])
        self.assertFalse(screen["metrics"]["case.p99_ns"]["guard_pass"])
        self.assertFalse(screen["eligible_for_slow"])

    def test_median_decision_ignores_a_single_bad_pair(self):
        directions = {"x": "higher"}
        calibration = analysis.calibrate(pairs([1, 1], directions), directions)
        result = analysis.compare(pairs([0.5, 1.2, 1.2, 1.2], directions), directions, calibration,
                                  "fast", decision="median", min_pairs=4)
        self.assertAlmostEqual(result["combined_score"], 1.2)
        self.assertAlmostEqual(result["overall_median_ratio"], 1.2)
        self.assertLess(result["overall_geomean_ratio"], 1)
        self.assertEqual(result["status"], "FAST_PASS")
        with self.assertRaises(ValueError):
            analysis.compare(pairs([1, 1, 1], directions), directions, calibration, "fast",
                             decision="median", min_pairs=3)


if __name__ == "__main__":
    unittest.main()
