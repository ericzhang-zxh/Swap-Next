# SPDX-License-Identifier: GPL-2.0-only
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("workflow", Path(__file__).with_name("standard_workflow.py"))
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.bench = self.root / "bench"
        self.p = w.read(w.PROTOCOL)
        for name, value in [("STATE", self.state), ("BENCH", self.bench), ("ROOT", self.root)]:
            p = patch.object(w, name, value); p.start(); self.addCleanup(p.stop)

    def test_reservation_survives_failure_and_budget(self):
        flow = w.Workflow(self.p)
        flow.reserve("guest")
        self.assertEqual(w.read(flow.budget_path)["guests"], 1)
        flow.budget["guests"] = self.p["budget"]["guest_attempts"]
        with self.assertRaisesRegex(RuntimeError, "budget"):
            flow.reserve("guest")

    def test_interrupted_identity_is_recovered_from_report(self):
        row = {"id": "one", "status": "RUNNING", "action": "evaluate", "tier": "fast"}
        w.save(self.state / "ledger.json", [row])
        w.save(self.bench / "evaluations/one/report.json", dict(row, candidate_commit="deadbeef", runs=[{"id": "reserved"}]))
        flow = w.Workflow(self.p)
        self.assertEqual(flow.ledger[0]["status"], "INTERRUPTED")
        self.assertEqual(flow.ledger[0]["candidate_commit"], "deadbeef")
        self.assertEqual(w.read(self.bench / "evaluations/one/report.json")["status"], "INTERRUPTED")

    def test_blocked_historical_commit_uses_no_budget(self):
        flow = w.Workflow(self.p)
        with patch.object(w, "fingerprint", return_value="fingerprint"):
            row = flow.run("evaluate", "fast", next(iter(self.p["blocked_commits"])))
        self.assertEqual(row["status"], "BLOCKED")
        self.assertEqual(flow.budget["guests"], 0)
        self.assertFalse(row["performance_accepted"])

    def test_calibration_fingerprint_and_noise_fail_closed(self):
        flow = w.Workflow(self.p)
        w.save(self.state / "calibration-fast.json", {"tier":"fast", "fingerprint":"old"})
        with self.assertRaisesRegex(RuntimeError, "stale"):
            flow.calibration("fast", "new")
        w.save(self.state / "calibration-fast.json", {"tier":"fast", "fingerprint":"new", "finished":w.time.time(), "analysis":{"passed":False}})
        with self.assertRaisesRegex(RuntimeError, "noisy"):
            flow.calibration("fast", "new")

    def test_expired_passed_calibration_may_be_renewed_but_noisy_may_not(self):
        flow = w.Workflow(self.p)
        old = w.time.time() - self.p["calibration_max_age_seconds"] - 10
        flow.ledger = [{"action": "calibrate", "tier": "fast", "fingerprint": "fp", "execution_started": True,
                        "finished": old, "analysis": {"passed": True}}]
        with patch.object(w, "fingerprint", return_value="fp"), patch.object(flow, "reserve", side_effect=RuntimeError("reserved")):
            row = flow.run("calibrate", "fast")
        self.assertEqual(row["reason"], "reserved")
        flow.ledger = [{"action": "calibrate", "tier": "fast", "fingerprint": "fp", "execution_started": True,
                        "finished": old, "analysis": {"passed": False}}]
        with patch.object(w, "fingerprint", return_value="fp"):
            row = flow.run("calibrate", "fast")
        self.assertIn("already attempted", row["reason"])
        flow.ledger = [{"action": "calibrate", "tier": "fast", "fingerprint": "fp", "execution_started": True,
                        "finished": w.time.time(), "analysis": {"passed": True}}]
        with patch.object(w, "fingerprint", return_value="fp"):
            row = flow.run("calibrate", "fast")
        self.assertIn("already attempted", row["reason"])

    def test_new_protocol_must_score_swapin_and_metadata(self):
        self.assertIn("fast tier needs a metadata case scoring " + w.METADATA_METRIC, w.contract_errors(self.p))
        good = {"cases": {"swapin-disk": {"workload": "swapin", "metrics": {"swapin_rand.mean_ns": "lower"},
                                          "primary": "swapin_rand.mean_ns"},
                          "metadata-brd": {"workload": "metadata", "metrics": {w.METADATA_METRIC: "lower"},
                                           "primary": None}},
                "tiers": {"fast": {"cases": ["swapin-disk", "metadata-brd"]}}}
        self.assertEqual(w.contract_errors(good), [])
        good["cases"]["swapin-disk"]["primary"] = "throughput_kbps_sum"
        self.assertTrue(w.contract_errors(good))
        flow = w.Workflow(self.p)
        with patch.object(w, "PROTOCOL", self.root / "protocol-new-campaign.json"):
            row = flow.run("calibrate", "fast")
        self.assertEqual(row["status"], "BLOCKED")
        self.assertEqual(flow.budget["guests"], 0)

    def test_slow_gate_before_build_or_guest(self):
        flow = w.Workflow(self.p)
        with patch.object(w, "fingerprint", return_value="fp"), patch.object(flow, "candidate", return_value=("commit", {}, {})):
            row = flow.run("evaluate", "slow", "candidate")
        self.assertIn("slow requires", row["reason"])
        self.assertEqual(flow.budget["guests"], 0)
        self.assertEqual(flow.budget["builds"], 0)

    def test_exact_commit_proof_alias_still_requires_all_gates(self):
        campaign = self.p["campaign"]
        records = self.root / "evolve/control/state" / campaign / "candidates.json"
        w.save(records, {"candidate": {"worktree": str(self.root / "candidate")}})
        proof = self.root / "proof.json"
        flow = w.Workflow(self.p)
        with patch.object(w.subprocess, "check_output", return_value="exact\n"):
            w.save(proof, {"source_commit": "exact", "gates": {"swapin_data": True}})
            with self.assertRaisesRegex(RuntimeError, "correctness"):
                flow.candidate("candidate", proof)
            gates = {key: True for key in self.p["required_correctness_gates"]}
            w.save(proof, {"source_commit": "wrong", "gates": gates, "integration_pass": True})
            with self.assertRaisesRegex(RuntimeError, "correctness"):
                flow.candidate("candidate", proof)
            w.save(proof, {"source_commit": "exact", "gates": gates})
            with self.assertRaisesRegex(RuntimeError, "integration"):
                flow.candidate("candidate", proof)
            w.save(proof, {"source_commit": "exact", "gates": gates, "integration_pass": True})
            self.assertEqual(flow.candidate("candidate", proof)[0], "exact")

    def test_stop_prevents_reservation(self):
        flow = w.Workflow(self.p)
        flow.stop.parent.mkdir(parents=True)
        flow.stop.touch()
        with self.assertRaisesRegex(RuntimeError, "STOP"):
            flow.reserve("guest")
        self.assertEqual(flow.budget["guests"], 0)


class Revision3WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.bench = self.root / "bench"
        self.p = json.loads(json.dumps(w.read(w.PROTOCOL)))
        self.p.update(protocol_revision=3, noise_envelope="p90", noise_ceiling=0.25,
                      comparison_decision="median", advisory_metric_suffixes=[".p99_ns"],
                      preallocate_swap=True, guest={"vcpus": 4, "mem_mib": 4096, "swap_gib": 16},
                      accelerator={"require": "tcg"},
                      validity={"pre_qemu_seconds_max": 60, "wall_time_factor": 1.5,
                                "wall_median_min_samples": 3, "reruns_per_arm": 1},
                      tiers={"fast": {"cases": ["swapin-disk"], "calibration_pairs": 10, "comparison_pairs": 4}},
                      cases={"swapin-disk": {"workload": "swapin", "backend": "disk", "mode": "xswap",
                                             "metrics": {"swapin_seq.mean_ns": "lower"},
                                             "primary": "swapin_seq.mean_ns"}})
        for name, value in [("STATE", self.state), ("BENCH", self.bench), ("ROOT", self.root)]:
            p = patch.object(w, name, value)
            p.start()
            self.addCleanup(p.stop)

    def _analysis(self):
        spec = importlib.util.spec_from_file_location(
            "real_standard_analysis", Path(__file__).resolve().parents[1] / "benchmark/swap-standard/analysis.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _fake_guest(self, calls, invalid_until):
        def fake_command(command, logfile, timeout, accept_failure=False, env=None):
            calls["env"] = env
            calls["commands"].append(command)
            calls["n"] += 1
            run_id = command[command.index("--run-id") + 1]
            dest = self.bench / "runs" / run_id
            dest.mkdir(parents=True)
            invalid = calls["n"] <= invalid_until
            (dest / "result.json").write_text(json.dumps({
                "run_id": run_id, "source_commit": self.p["baseline_commit"], "integration_pass": True,
                "swap_image_allocation": "preallocated", "clocksource_invalid": invalid,
                "pre_qemu_seconds": 1.0, "wall_seconds": 100.0,
                "host_load": {"before_launch": {"loadavg_1m": 0.2, "loadavg_5m": 0.2, "loadavg_15m": 0.2}},
                "metrics": {"swapin_seq": {"mean_ns": 1000.0}}, "guest_mem_mib": 4096,
                "guest_vcpus": 4, "accelerator": "tcg"}))
            logfile.write_text("mocked\n")
            return 1 if invalid else 0
        return fake_command

    def test_invalid_clocksource_is_retained_and_rerun(self):
        flow = w.Workflow(self.p)
        calls = {"n": 0, "commands": []}
        with patch.dict("os.environ", {"SWAP_NEXT_ACCEL": "kvm"}, clear=False), \
             patch.object(w, "fingerprint", return_value="fp"), \
             patch.object(w, "analysis_module", return_value=self._analysis()), \
             patch.object(flow, "command", side_effect=self._fake_guest(calls, 1)):
            row = flow.run("calibrate", "fast")
        self.assertEqual(row["status"], "CALIBRATED")
        self.assertEqual(row["protocol_revision"], 3)
        self.assertEqual(row["runs"][0]["status"], "INVALID")
        self.assertEqual(row["runs"][0]["invalid_reason"], "clocksource_fallback")
        self.assertEqual(row["runs"][0]["host_load"]["before_launch"]["loadavg_1m"], 0.2)
        self.assertEqual(row["runs"][1]["status"], "PASS")
        self.assertTrue(row["runs"][1]["id"].endswith("-r1"))
        self.assertEqual(flow.budget["guests"], 21)
        command = calls["commands"][0]
        self.assertEqual(command[command.index("--mode") + 1], "xswap")
        self.assertIn("--preallocate-swap", command)
        self.assertEqual(command[command.index("--protocol-revision") + 1], "3")
        self.assertEqual(calls["env"]["SWAP_NEXT_TCG_MEM_MIB"], "4096")
        self.assertEqual(calls["env"]["SWAP_NEXT_TCG_SMP"], "4")
        self.assertEqual(calls["env"]["SWAP_NEXT_ACCEL"], "tcg")

    def test_exhausted_validity_reruns_fail_closed(self):
        flow = w.Workflow(self.p)
        calls = {"n": 0, "commands": []}
        with patch.object(w, "fingerprint", return_value="fp"), \
             patch.object(flow, "command", side_effect=self._fake_guest(calls, 99)):
            row = flow.run("calibrate", "fast")
        self.assertEqual(row["status"], "INCOMPLETE")
        self.assertIn("validity reruns exhausted", row["reason"])
        self.assertEqual([item["status"] for item in row["runs"]], ["INVALID", "INVALID"])
        self.assertEqual(flow.budget["guests"], 2)

    def test_protocol_campaign_selects_its_own_state_directory(self):
        real_root = Path(__file__).resolve().parents[1]
        saved = (w.STATE, w.PROTOCOL, w.ROOT, w.BENCH)
        path = real_root / "benchmark/swap-standard/protocol-tcg-revision3.json"
        try:
            w.ROOT = real_root
            w.BENCH = real_root / "benchmark/swap-standard"
            w.select_protocol(path)
            self.assertEqual(w.STATE, real_root / "evolve/swap-standard/state-xswap-tcg-rev3-2026-10-25")
            self.assertEqual(w.PROTOCOL, path.resolve())
        finally:
            w.STATE, w.PROTOCOL, w.ROOT, w.BENCH = saved


if __name__ == "__main__":
    unittest.main()
