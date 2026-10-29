# SPDX-License-Identifier: GPL-2.0-only
"""Guest-free validity and revision protocol tests."""
import json
from pathlib import Path
import tempfile
import unittest

from validity import (classify_attempt, clocksource_invalid, launch_blocked,
                      parse_loadavg, parse_psi, protocol_rules, read_host_load, wall_outlier)

ROOT = Path(__file__).resolve().parents[2]
NEXT_REPORT = ROOT / "campaigns/xswap-next-2026-10-24/report"


def tcg_revision3_protocol():
    """Falls back to the pre-migration path until campaigns/ holds the protocol."""
    new = ROOT / "campaigns/xswap-tcg-rev3-2026-10-25/protocol.json"
    return new if new.exists() else ROOT / "benchmark/swap-standard/protocol-tcg-revision3.json"


def tcg_revision6_protocol():
    return json.loads((ROOT / "campaigns/xswap-tcg-kbench-2026-10-29/protocol.json").read_text())


def parse_params(text):
    values = {}
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values
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

    def test_pre_launch_stall_blocks_from_revision_3(self):
        self.assertFalse(launch_blocked(3, 60))
        self.assertTrue(launch_blocked(3, 60.01))
        self.assertTrue(launch_blocked(6, 60.01))
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
        protocol = json.loads(tcg_revision3_protocol().read_text())
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
        self.assertTrue(protocol["preallocate_swap"])
        self.assertNotIn("slow", protocol["tiers"])

    def test_revision4_kvm_shape_and_probe_runs_are_not_latency_pairs(self):
        p = json.loads((Path(__file__).parent / "revision4-protocol-template.json").read_text())
        rules = protocol_rules(p)
        self.assertEqual(rules["protocol_revision"], 4)
        self.assertTrue(rules["enforce_validity"])
        self.assertEqual(rules["max_reruns"], 1)
        for key, value in (("vcpus", 4), ("mem_mib", 4096), ("swap_gib", 8)):
            wrong = json.loads(json.dumps(p))
            wrong["guest"][key] = value
            with self.assertRaises(ValueError):
                protocol_rules(wrong)
        p["accelerator"]["require"] = "tcg"
        with self.assertRaisesRegex(ValueError, "requires KVM"):
            protocol_rules(p)

    def test_revision6_tcg_kbench_shape_excludes_build_and_is_not_opened(self):
        protocol = tcg_revision6_protocol()
        campaign = ROOT / "campaigns/xswap-tcg-kbench-2026-10-29"
        self.assertFalse((campaign / "campaign.json").exists())
        self.assertFalse((campaign / "ledger").exists())
        policy = json.loads((campaign / "policy.json").read_text())
        base = json.loads((ROOT / "evolve/control/config/policy.json").read_text())
        self.assertEqual(protocol["campaign"], campaign.name)
        self.assertEqual(protocol["baseline_commit"], policy["seed_ref"])
        self.assertLessEqual(set(policy["allowed_modify"]), set(base["allowed_modify"]))
        self.assertNotIn("mm/memory.c", policy["allowed_modify"])
        self.assertEqual(len(policy["allowed_modify"]), 8)
        self.assertLessEqual(set(policy["allowed_add"]), set(base["allowed_add"]))
        budget = protocol["budget"]
        self.assertLessEqual(budget["probe_guest_attempts"] + budget["guest_attempts"], 120)
        self.assertLessEqual(budget["wall_seconds"], 64800)
        self.assertGreaterEqual(policy["budget"]["max_candidates"], protocol["max_probe_candidates"])
        rules = protocol_rules(protocol)
        self.assertEqual(rules["protocol_revision"], 6)
        self.assertEqual(rules["noise_ceiling"], 0.25)
        self.assertEqual(rules["envelope"], "p90")
        self.assertEqual(rules["decision"], "median")
        self.assertEqual(rules["advisory_suffixes"], (".p99_ns",))
        self.assertEqual(rules["max_reruns"], 2)
        self.assertEqual(protocol["guest"], {"vcpus": 4, "mem_mib": 4096, "swap_gib": 16})
        self.assertEqual(protocol["accelerator"]["require"], "tcg")
        self.assertEqual(protocol["tiers"]["probe"]["calibration_runs"], 3)
        self.assertEqual(protocol["tiers"]["probe"]["candidate_runs"], 1)
        self.assertEqual(protocol["tiers"]["fast"]["calibration_pairs"], 10)
        self.assertEqual(protocol["tiers"]["fast"]["comparison_pairs"], 4)
        self.assertNotIn("slow", protocol["tiers"])
        self.assertNotIn("template_only", protocol)
        self.assertEqual(protocol["build_oom"]["choice"], "exclude")
        self.assertTrue(protocol["build_oom"]["params_unchanged"])
        planned = protocol["planned_guest_counts"]
        self.assertEqual(planned["probe_calibration"] + planned["three_probe_candidates"]
                         + planned["fast_calibration"] + planned["three_fast_candidates"]
                         + planned["three_correctness"],
                         planned["performance_and_correctness"])
        self.assertEqual(planned["performance_and_correctness"] + planned["validity_spare"],
                         planned["total_ceiling"])
        self.assertEqual(planned["calibration_total"] + planned["three_rounds"],
                         planned["performance_and_correctness"])
        self.assertEqual(planned["remaining_after_calibration"], 71)
        self.assertEqual(planned["one_round"],
                         planned["probe_candidate"] + planned["fast_candidate"] + planned["correctness_per_round"])
        self.assertEqual(planned["total_ceiling"], 120)
        self.assertEqual(protocol["baseline_build"], "kb-xs-desc-v1")
        self.assertEqual(protocol["page_cluster"]["value"], 3)
        factor = protocol["wall_estimate"]["tcg_planning_seconds_per_guest"]
        wall = protocol["wall_estimate"]["first_pass_at_planning_factor_seconds"]
        self.assertEqual(planned["probe_calibration"], 9)
        self.assertEqual(planned["fast_calibration"], 40)
        self.assertEqual(wall["probe_calibration"], planned["probe_calibration"] * factor)
        self.assertEqual(wall["fast_calibration"], planned["fast_calibration"] * factor)
        self.assertEqual(wall["one_round"], planned["one_round"] * factor)
        self.assertEqual(wall["three_rounds"], planned["three_rounds"] * factor)
        self.assertEqual(wall["calibrations_plus_three_rounds"],
                         (planned["calibration_total"] + planned["three_rounds"]) * factor)
        cap = protocol["wall_estimate"]["timeout_cap_seconds"]
        self.assertEqual(cap["calibrations_plus_one_round"],
                         (planned["calibration_total"] + planned["one_round"]) * 900)
        import hashlib
        config = ROOT / "benchmark/config/swap-standard.config"
        text = config.read_text().splitlines()
        self.assertIn("CONFIG_TRANSPARENT_HUGEPAGE=y", text)
        self.assertIn("CONFIG_THP_SWAP=y", text)
        self.assertEqual(protocol["input_config_sha256"], hashlib.sha256(config.read_bytes()).hexdigest())
        self.assertEqual(protocol["kernel_config"]["input_config_sha256"], protocol["input_config_sha256"])
        self.assertEqual(protocol["cases"]["swapin-disk"]["mode"], "xswap")
        self.assertEqual(protocol["cases"]["swapin-zram-64k"]["mode"], "xswap")
        self.assertEqual(protocol["cases"]["swapin-zram-64k"]["primary"], "swapin_seq.mean_ns")
        self.assertEqual(protocol["cases"]["swapin-zram-64k"]["metrics"]["swapin_rand.mean_ns"], "lower")
        self.assertEqual(protocol["cases"]["metadata-brd"]["mode"], "plain")
        self.assertNotIn("swapin-zswap", protocol["cases"])
        self.assertEqual(protocol["tiers"]["probe"]["cases"],
                         ["swapin-disk", "swapin-zram-64k", "metadata-brd"])
        self.assertEqual(protocol["tiers"]["fast"]["cases"],
                         ["swapin-disk", "swapin-zram-64k"])
        bench = (ROOT / "benchmark/swap-standard/bench.sh").read_text()
        self.assertIn('page_cluster=$(cat /proc/sys/vm/page-cluster)', bench)
        self.assertIn('echo "PAGE_CLUSTER $page_cluster"', bench)
        self.assertIn('[ "$page_cluster" = 3 ] || fail page_cluster', bench)
        self.assertNotRegex(bench, r">\s*/proc/sys/vm/page-cluster")
        params = parse_params((ROOT / "benchmark/swap-standard/params.sh").read_text())
        for key, value in protocol["kbench_params"].items():
            self.assertEqual(params[key], value, key)
        self.assertEqual(params["BUILD_MEMCG"], "470M")
        self.assertEqual(params["BUILD_JOBS"], "32")
        rev5 = json.loads(json.dumps(protocol))
        rev5["protocol_revision"] = 5
        with self.assertRaisesRegex(ValueError, "unapproved protocol revision"):
            protocol_rules(rev5)
        wider = json.loads(json.dumps(protocol))
        wider["noise_ceiling"] = 0.30
        with self.assertRaisesRegex(ValueError, "25%"):
            protocol_rules(wider)
        kvm = json.loads(json.dumps(protocol))
        kvm["accelerator"]["require"] = "kvm"
        with self.assertRaisesRegex(ValueError, "requires TCG"):
            protocol_rules(kvm)
        built = json.loads(json.dumps(protocol))
        built["cases"]["build-zram"] = {"workload": "build", "backend": "zram", "mode": "xswap",
                                         "metrics": {"build_real_usec": "lower"}, "primary": None}
        built["tiers"]["fast"]["cases"].append("build-zram")
        with self.assertRaisesRegex(ValueError, "build"):
            protocol_rules(built)

    @unittest.skipUnless((NEXT_REPORT / "protocol-revision1.json").exists(), "before migration")
    def test_revision1_and_2_protocol_shape(self):
        rev1 = json.loads((NEXT_REPORT / "protocol-revision1.json").read_text())
        rev2 = json.loads((NEXT_REPORT / "protocol-revision2.json").read_text())
        self.assertNotIn("protocol_revision", rev1)
        self.assertEqual(rev2["protocol_revision"], 2)
        self.assertEqual(rev1["noise_ceiling"], 0.2)
        self.assertEqual(rev2["noise_ceiling"], 0.2)
        self.assertEqual(rev1["tiers"]["fast"]["calibration_pairs"], 2)
        self.assertEqual(rev2["tiers"]["fast"]["comparison_pairs"], 2)


if __name__ == "__main__":
    unittest.main()
