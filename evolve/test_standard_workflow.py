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
REPO = Path(__file__).resolve().parents[1]


def fixture_protocol():
    """The standard protocol; falls back to its pre-migration path until campaigns/ holds it."""
    new = REPO / "campaigns/swap-standard-2026-10-22/protocol.json"
    return w.read(new if new.exists() else REPO / "benchmark/swap-standard/protocol.json")


def write_campaign(campaigns, name, status="open", **budget):
    record = {"campaign": name, "status": status, "line": "plain", "baseline_from": None,
              "machine": "hurricpc", "opened": "2026-10-27",
              "closed": "2026-10-27" if status == "closed" else None,
              "budget": dict({"guest_attempts": 120, "wall_seconds": 64800,
                              "probe_guest_attempts": 0, "approved_over_cap": None}, **budget)}
    w.save(campaigns / name / "campaign.json", record)


def campaign_tree(test, p):
    """Temp repository with an open campaign.json and a machine claim for p's campaign."""
    test.tmp = tempfile.TemporaryDirectory()
    test.addCleanup(test.tmp.cleanup)
    test.root = Path(test.tmp.name)
    test.campaigns = test.root / "campaigns"
    test.campaign = test.campaigns / p["campaign"]
    test.state = test.campaign / "ledger"
    test.state.mkdir(parents=True)
    test.bench = test.root / "bench"
    test.claim = test.root / "claim"
    test.claim.write_text(p["campaign"] + "\n")
    w.save(test.campaigns / "hosts.json", {"hurricpc": {"hostnames": []}})
    write_campaign(test.campaigns, p["campaign"])
    values = [("ROOT", test.root), ("BENCH", test.bench), ("CAMPAIGN", test.campaign),
              ("PROTOCOL", test.campaign / "protocol.json"), ("STATE", test.state),
              ("EVALUATIONS", test.campaign / "runs/evaluations"), ("RUNS", test.campaign / "runs/guests"),
              ("ARCHIVE", test.campaign / "archive"), ("TASKS", test.campaign / "runs/tasks")]
    patches = [patch.object(w, name, value) for name, value in values]
    patches += [patch.object(w.campaign_store, "CAMPAIGNS", test.campaigns),
                patch.object(w.campaign_store, "HOSTS", test.campaigns / "hosts.json"),
                patch.object(w.campaign_store, "GLOBAL_STOP", test.campaigns / "STOP"),
                patch.dict("os.environ", {"SWAP_NEXT_CLAIM": str(test.claim),
                                          "SWAP_NEXT_MACHINE": "hurricpc"})]
    for item in patches:
        item.start()
        test.addCleanup(item.stop)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.p = fixture_protocol()
        campaign_tree(self, self.p)

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
        report = self.campaign / "runs/evaluations/one/report.json"
        w.save(report, dict(row, candidate_commit="deadbeef", runs=[{"id": "reserved"}]))
        flow = w.Workflow(self.p)
        self.assertEqual(flow.ledger[0]["status"], "INTERRUPTED")
        self.assertEqual(flow.ledger[0]["candidate_commit"], "deadbeef")
        self.assertEqual(w.read(report)["status"], "INTERRUPTED")
        self.assertEqual(w.read(self.state / "ledger.json")[0]["status"], "INTERRUPTED")

    def test_unchanged_ledger_is_not_rewritten(self):
        write_campaign(self.campaigns, self.p["campaign"], status="closed")
        ledger = self.state / "ledger.json"
        ledger.write_text(json.dumps([{"id": "one", "status": "FAST_PASS", "action": "evaluate", "tier": "fast"}]))
        before = ledger.read_bytes()
        w.Workflow(self.p)
        self.assertEqual(ledger.read_bytes(), before)

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

    def test_contract_exemption_is_by_campaign(self):
        for name, blocked in (("new-campaign-2026-10-27", True), ("xswap-next-2026-10-24", False)):
            with self.subTest(campaign=name):
                p = dict(self.p, campaign=name)
                write_campaign(self.campaigns, name)
                self.claim.write_text(name + "\n")
                flow = w.Workflow(p)
                with patch.object(w, "fingerprint", return_value="fp"), \
                     patch.object(flow, "reserve", side_effect=RuntimeError("reserved")):
                    row = flow.run("calibrate", "fast")
                if blocked:
                    self.assertEqual(row["status"], "BLOCKED")
                    self.assertIn("protocol contract", row["reason"])
                else:
                    self.assertEqual(row["reason"], "reserved")
                self.assertEqual(flow.budget["guests"], 0)

    def test_closed_campaign_blocks_before_budget(self):
        write_campaign(self.campaigns, self.p["campaign"], status="closed")
        flow = w.Workflow(self.p)
        with patch.object(w, "fingerprint", return_value="fp"):
            row = flow.run("calibrate", "fast")
        self.assertEqual(row["status"], "BLOCKED")
        self.assertIn("closed", row["reason"])
        self.assertEqual(flow.budget["guests"], 0)
        ledger = w.read(self.state / "ledger.json") if (self.state / "ledger.json").exists() else []
        self.assertFalse(any(r.get("execution_started") for r in ledger))

    def test_over_cap_open_campaign_blocks(self):
        write_campaign(self.campaigns, self.p["campaign"], guest_attempts=200)
        flow = w.Workflow(self.p)
        with patch.object(w, "fingerprint", return_value="fp"), \
             patch.object(flow, "reserve", side_effect=RuntimeError("reserved")):
            row = flow.run("calibrate", "fast")
            self.assertEqual(row["status"], "BLOCKED")
            self.assertIn("cap", row["reason"])
            write_campaign(self.campaigns, self.p["campaign"], guest_attempts=200,
                           approved_over_cap="owner approved 2026-10-27")
            row = flow.run("calibrate", "fast")
            self.assertEqual(row["reason"], "reserved")
        self.assertEqual(flow.budget["guests"], 0)

    def test_claimless_evaluate_blocks_before_build(self):
        self.claim.unlink()
        flow = w.Workflow(self.p)
        with patch.object(w, "fingerprint", return_value="fp"), \
             patch.object(flow, "candidate", return_value=("commit", {}, {})), \
             patch.object(flow, "command") as command:
            row = flow.run("evaluate", "fast", "candidate")
        self.assertEqual(row["status"], "BLOCKED")
        self.assertIn("claim", row["reason"])
        self.assertEqual((flow.budget["builds"], flow.budget["guests"]), (0, 0))
        command.assert_not_called()
        self.assertFalse((self.state / "ledger.json").exists())

    def test_guest_needs_machine_claim(self):
        flow = w.Workflow(self.p)
        for held in ("other-campaign\n", None):
            with self.subTest(held=held):
                if held:
                    self.claim.write_text(held)
                else:
                    self.claim.unlink()
                with self.assertRaisesRegex(RuntimeError, "^BLOCKED: .*claim"):
                    flow.reserve("guest")
                self.assertEqual(flow.budget["guests"], 0)
                self.assertFalse(flow.budget_path.exists())

    def test_slow_gate_before_build_or_guest(self):
        flow = w.Workflow(self.p)
        with patch.object(w, "fingerprint", return_value="fp"), patch.object(flow, "candidate", return_value=("commit", {}, {})):
            row = flow.run("evaluate", "slow", "candidate")
        self.assertIn("slow requires", row["reason"])
        self.assertEqual(flow.budget["guests"], 0)
        self.assertEqual(flow.budget["builds"], 0)

    def test_exact_commit_proof_alias_still_requires_all_gates(self):
        campaign = self.p["campaign"]
        w.save(self.campaign / "candidates/candidate.json",
               {"id": "candidate", "worktree": "worktrees/" + campaign + "/candidate"})
        w.save(self.campaigns / "xswap-structure-2026-10-22/candidates/held.json",
               {"id": "held", "worktree": "worktrees/xswap-structure-2026-10-22/held"})
        proof = self.root / "proof.json"
        flow = w.Workflow(self.p)
        with self.assertRaisesRegex(RuntimeError, "BLOCKED: historical"):
            flow.candidate("held", None)
        with patch.object(w.subprocess, "check_output", return_value="exact\n") as git:
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
        self.assertEqual(git.call_args[0][0][:3], ["git", "-C", str(self.root / "worktrees" / campaign / "candidate")])

    def test_stop_prevents_reservation(self):
        for stop in (self.campaign / "STOP", self.campaigns / "STOP"):
            with self.subTest(stop=stop.name):
                flow = w.Workflow(self.p)
                stop.touch()
                with self.assertRaisesRegex(RuntimeError, "STOP"):
                    flow.reserve("guest")
                self.assertEqual(flow.budget["guests"], 0)
                stop.unlink()


class Revision3WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.p = json.loads(json.dumps(fixture_protocol()))
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
        campaign_tree(self, self.p)

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
            self.assertEqual(command[command.index("--run-root") + 1], str(self.campaign / "runs/guests"))
            self.assertEqual(command[command.index("--stop-file") + 1], str(self.campaign / "STOP"))
            dest = Path(command[command.index("--run-root") + 1]) / run_id
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

    def test_select_campaign_paths(self):
        name = "xswap-tcg-rev3-2026-10-25"
        write_campaign(self.campaigns, name)
        w.select_campaign(name)
        c = self.campaigns / name
        self.assertEqual(w.CAMPAIGN, c)
        self.assertEqual(w.PROTOCOL, c / "protocol.json")
        self.assertEqual(w.STATE, c / "ledger")
        self.assertEqual(w.EVALUATIONS, c / "runs/evaluations")
        self.assertEqual(w.RUNS, c / "runs/guests")
        self.assertEqual(w.ARCHIVE, c / "archive")
        self.assertEqual(w.TASKS, c / "runs/tasks")
        for bad in ("unknown-campaign", "../escape", "Bad"):
            with self.subTest(bad=bad):
                with self.assertRaises(w.campaign_store.CampaignError):
                    w.select_campaign(bad)
                with self.assertRaises(w.campaign_store.CampaignError):
                    w.main(["status", "--campaign", bad])
                self.assertEqual(w.CAMPAIGN, c)
        self.assertFalse((self.campaigns / "unknown-campaign").exists())

    def test_module_defaults_name_the_standard_campaign(self):
        fresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fresh)
        c = REPO / "campaigns/swap-standard-2026-10-22"
        self.assertEqual((fresh.CAMPAIGN, fresh.PROTOCOL, fresh.STATE), (c, c / "protocol.json", c / "ledger"))


if __name__ == "__main__":
    unittest.main()
