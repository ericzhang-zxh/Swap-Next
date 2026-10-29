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
    p = w.read(new if new.exists() else REPO / "benchmark/swap-standard/protocol.json")
    # Fresh fixture campaigns have matching records within the approved cap.
    p["budget"].update(guest_attempts=120, wall_seconds=64800)
    return p


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
    patches += [patch.object(w.campaign_store, "PROJECT", test.root),
                patch.object(w.campaign_store, "CAMPAIGNS", test.campaigns),
                patch.object(w.campaign_store, "HOSTS", test.campaigns / "hosts.json"),
                patch.object(w.campaign_store, "GLOBAL_STOP", test.campaigns / "STOP"),
                patch.dict("os.environ", {"SWAP_NEXT_CLAIM": str(test.claim),
                                          "SWAP_NEXT_MACHINE": "hurricpc"})]
    for item in patches:
        item.start()
        test.addCleanup(item.stop)
    w.save(w.PROTOCOL, p)


def probe_protocol():
    p = w.read(REPO / "benchmark/swap-standard/revision4-protocol-template.json")
    p.update(campaign="plain-unit-test", template_only=False)
    return p


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.p = fixture_protocol()
        campaign_tree(self, self.p)

    def test_retained_failure_reason_omits_machine_project_prefix(self):
        flow = w.Workflow(self.p)
        with patch.object(w, "fingerprint", side_effect=OSError("missing " + str(self.root / "private/control.json"))):
            row = flow.run("calibrate", "fast")
        self.assertEqual(row["status"], "INCOMPLETE")
        self.assertNotIn(str(self.root), row["reason"])
        self.assertIn("private/control.json", row["reason"])

    def test_reservation_survives_failure_and_budget(self):
        flow = w.Workflow(self.p)
        flow.reserve("guest")
        self.assertEqual(w.read(flow.budget_path)["guests"], 1)
        flow.budget["guests"] = self.p["budget"]["guest_attempts"]
        w.save(flow.budget_path, flow.budget)
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

    def test_closed_orphan_reads_never_write_reports_locks_or_tasks(self):
        write_campaign(self.campaigns, self.p["campaign"], status="closed")
        w.save(w.PROTOCOL, self.p)
        row = {"id": "orphan", "status": "RUNNING", "action": "evaluate", "tier": "fast"}
        ledger = self.state / "ledger.json"
        w.save(ledger, [row])
        before = {path: path.read_bytes() for path in self.campaign.rglob("*") if path.is_file()}
        for action in ("status", "plan", "next"):
            with patch.object(w, "fingerprint", return_value="fp"), \
                 patch.object(w.validity_module(), "protocol_rules"), patch("sys.stdout"):
                w.main([action, "--campaign", self.p["campaign"]])
        after = {path: path.read_bytes() for path in self.campaign.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(w.read(ledger)[0]["status"], "RUNNING")
        self.assertFalse((self.state / ".lock").exists())
        self.assertFalse((self.campaign / "runs").exists())

    def test_budget_and_machine_drift_block_every_reservation(self):
        flow = w.Workflow(self.p)
        self.p["budget"]["guest_attempts"] = 121
        with self.assertRaisesRegex(RuntimeError, "budget.guest_attempts"):
            flow.reserve("guest")
        self.p["budget"]["guest_attempts"] = 120
        self.p["budget"]["wall_seconds"] = 64801
        with self.assertRaisesRegex(RuntimeError, "budget.wall_seconds"):
            flow.reserve("build")
        self.p["budget"]["wall_seconds"] = 64800
        with patch.dict("os.environ", {"SWAP_NEXT_MACHINE": "unknown"}):
            with self.assertRaisesRegex(RuntimeError, "SWAP_NEXT_MACHINE"):
                flow.reserve("guest")
        self.assertEqual((flow.budget["guests"], flow.budget["builds"]), (0, 0))
        self.assertFalse(flow.budget_path.exists())

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
        with patch.object(w, "fingerprint", return_value="fp"), patch.object(flow, "_reserve_guest", side_effect=RuntimeError("reserved")):
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

    def test_new_protocol_scores_swapin_and_probes_metadata(self):
        good = probe_protocol()
        self.assertEqual(w.contract_errors(good), [])
        good["tiers"]["probe"]["cases"].remove("metadata-brd")
        self.assertIn("plain probe tier needs a metadata case scoring " + w.METADATA_METRIC, w.contract_errors(good))
        good = probe_protocol()
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
                     patch.object(flow, "_reserve_guest", side_effect=RuntimeError("reserved")):
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
             patch.object(flow, "_reserve_guest", side_effect=RuntimeError("reserved")):
            row = flow.run("calibrate", "fast")
            self.assertEqual(row["status"], "BLOCKED")
            self.assertIn("cap", row["reason"])
            write_campaign(self.campaigns, self.p["campaign"], guest_attempts=200,
                           approved_over_cap="owner approved 2026-10-27")
            self.p["budget"]["guest_attempts"] = 200
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


class ProbeWorkflowTests(unittest.TestCase):
    """Synthetic guest messages exercise sequencing; they prove no kernel capability."""
    def setUp(self):
        self.p = probe_protocol()
        campaign_tree(self, self.p)
        write_campaign(self.campaigns, self.p["campaign"], guest_attempts=84, probe_guest_attempts=36)
        self.commit, self.tree = "b" * 40, "c" * 40
        self.mechanism = "swapin-disk:swapin_vmstat_delta.swap_ra_hit:up"
        self.record = {"id": "candidate", "worktree": "worktrees/plain-unit-test/candidate", "mechanism": self.mechanism}
        config = self.root / "benchmark/config/swap-standard.config"
        config.parent.mkdir(parents=True)
        config.write_text("synthetic config; never used for a build")
        build = self.root / "benchmark/kernel/builds" / ("std-" + self.commit[:12]) / "result.json"
        w.save(build, {"commit": self.commit, "passed": True, "input_config_sha256": w.sha(config), "instrument_sha256": None})
        self.calls, self.invalid_candidate, self.bad_candidate, self.noisy_metadata = [], False, None, False
        self.counter = 20
        analysis_spec = importlib.util.spec_from_file_location("probe_fixture_analysis", REPO / "benchmark/swap-standard/analysis.py")
        analysis = importlib.util.module_from_spec(analysis_spec)
        analysis_spec.loader.exec_module(analysis)
        for item in (patch.object(w, "analysis_module", return_value=analysis),
                     patch.object(w, "fingerprint", return_value="fp"),
                     patch.object(w.Workflow, "candidate", return_value=(self.commit, self.record, {"synthetic_proof": True})),
                     patch.object(w.Workflow, "candidate_tree", return_value=self.tree),
                     patch.object(w.Workflow, "probe_build", return_value="candidate-build"),
                     patch.object(w.Workflow, "command", side_effect=self.fake_command)):
            item.start()
            self.addCleanup(item.stop)

    def fake_command(self, command, logfile, timeout, accept_failure=False, env=None):
        if "evolve/control/controller.py" in command:
            w.save(logfile, {"status": "SCOPE_PASS", "candidate_commit": self.commit, "parent": self.p["baseline_commit"]})
            return 0
        self.assertIn("--run-id", command, "no real build command is permitted in this fixture")
        self.calls.append(command)
        self.assertEqual(env["SWAP_NEXT_ACCEL"], "kvm")
        run_id = command[command.index("--run-id") + 1]
        build = command[command.index("--build") + 1]
        backend, workload = command[command.index("--backend") + 1], command[command.index("--workload") + 1]
        reservation = command[command.index("--reservation") + 1]
        w.guest_budget.consume_guest(self.p["campaign"], run_id, reservation,
                                     {"build": build, "backend": backend, "mode": "plain", "workload": workload})
        is_candidate = build != self.p["baseline_build"]
        count = self.counter if is_candidate else 10
        metadata = .210 if self.noisy_metadata and backend == "brd" and len(self.calls) % 3 == 0 else .206
        metrics = {"swapin_vmstat_delta": {k: count for k in w.probe_module().VMSTAT},
                   w.METADATA_METRIC: metadata, "swapin_seq": {"mean_ns": 1000., "p99_ns": 2000.},
                   "swapin_rand": {"mean_ns": 1000., "p99_ns": 2000.}}
        if is_candidate and self.bad_candidate == "missing":
            del metrics["swapin_vmstat_delta"]["swap_ra_hit"]
        if is_candidate and self.bad_candidate == "nonfinite":
            metrics["swapin_vmstat_delta"]["swap_ra_hit"] = float("nan")
        result = {"run_id": run_id, "source_commit": self.commit if is_candidate else self.p["baseline_commit"],
                  "integration_pass": True, "metrics": metrics, "clocksource_invalid": False,
                  "pre_qemu_seconds": 1., "wall_seconds": 200. if self.invalid_candidate and is_candidate else 100.,
                  "host_load": {"before_launch": {"loadavg_1m": .1}}, "guest_mem_mib": 8192,
                  "guest_vcpus": 8, "accelerator": "kvm", "swap_image_allocation": "preallocated"}
        dest = self.campaign / "runs/guests" / run_id
        dest.mkdir(parents=True)
        (dest / "result.json").write_text(json.dumps(result))
        logfile.write_text("synthetic guest output")
        return 0

    def probe_pair(self, flow):
        calibration = flow.run("calibrate", "probe")
        self.assertEqual(calibration["status"], "CALIBRATED", calibration)
        candidate = flow.run("evaluate", "probe", "candidate", self.root / "synthetic-proof.json")
        return calibration, candidate

    def test_probe_then_agent_admitted_fast_is_ticketed_and_never_auto_advances(self):
        flow = w.Workflow(self.p)
        calibration, candidate = self.probe_pair(flow)
        self.assertEqual(candidate["status"], "PROBE_PASS", candidate)
        self.assertEqual(len(self.calls), 12)
        self.assertEqual((flow.budget["probe_guests"], flow.budget["guests"]), (12, 0))
        self.assertEqual(candidate["candidate_tree"], self.tree)
        self.assertEqual({r["pool"] for r in candidate["runs"]}, {"probe"})
        row = flow.run("evaluate", "fast", "candidate", self.root / "synthetic-proof.json")
        self.assertEqual(row["status"], "BLOCKED")
        self.assertIn("selection-reason", row["reason"])
        self.assertEqual(len(self.calls), 12)
        fast_cal = flow.run("calibrate", "fast")
        self.assertEqual(fast_cal["status"], "CALIBRATED", fast_cal.get("reason"))
        fast = flow.run("evaluate", "fast", "candidate", self.root / "synthetic-proof.json", "Agent selects the engaged counter without a metadata regression")
        self.assertEqual(fast["status"], "FAST_PASS", fast.get("reason"))
        self.assertEqual(fast["probe_id"], candidate["id"])
        self.assertEqual(fast["candidate_tree"], self.tree)
        self.assertFalse(fast["performance_accepted"])
        self.assertEqual((flow.budget["probe_guests"], flow.budget["guests"]), (12, 56))
        self.assertEqual(flow.budget_pools()["total"]["spent"], 68)
        tickets = list((self.state / "guest-reservations").glob("*.json"))
        self.assertEqual(len(tickets), 68)
        self.assertTrue(all(w.read(p)["status"] == "STARTED" for p in tickets))

    def test_fast_needs_exact_commit_tree_fingerprint_and_mechanism(self):
        flow = w.Workflow(self.p)
        row = flow.run("evaluate", "fast", "candidate", selection_reason="Agent chooses this mechanism")
        self.assertEqual(row["status"], "BLOCKED")
        self.assertIn("PROBE_PASS", row["reason"])
        self.assertEqual(self.calls, [])
        good = {"id": "probe", "action": "evaluate", "tier": "probe", "candidate_commit": self.commit,
                "candidate_tree": self.tree, "fingerprint": "fp", "status": "PROBE_PASS",
                "execution_started": True, "mechanism": self.mechanism,
                "analysis": {"status": "PROBE_PASS", "passed": True},
                "probe_signals": {name: {key: [20] for key in w.probe_module().signals(self.p, name)}
                                  for name in self.p["tiers"]["probe"]["cases"]}}
        for field in ("candidate_commit", "candidate_tree", "fingerprint", "mechanism"):
            flow.ledger = [dict(good, **{field: "wrong"})]
            with self.assertRaisesRegex(RuntimeError, "PROBE_PASS"):
                flow.probe_prerequisite(self.commit, self.tree, "fp", self.record, "agent chooses")

    def test_content_reject_is_final_and_same_code_new_sha_does_not_get_a_retry(self):
        flow = w.Workflow(self.p)
        self.counter = 10
        _, row = self.probe_pair(flow)
        self.assertEqual(row["status"], "PROBE_REJECT")
        spent = flow.budget["probe_guests"]
        with patch.object(flow, "candidate", return_value=("d" * 40, self.record, {})), patch.object(w, "fingerprint", return_value="new-fp"):
            retried = flow.run("evaluate", "probe", "renamed-candidate")
        self.assertEqual(retried["status"], "BLOCKED", retried)
        self.assertIn("final PROBE_REJECT", retried["reason"])
        self.assertEqual(flow.budget["probe_guests"], spent)

    def test_pass_may_refresh_once_per_fingerprint_but_not_rename_under_same_fingerprint(self):
        flow = w.Workflow(self.p)
        _, row = self.probe_pair(flow)
        self.assertEqual(row["status"], "PROBE_PASS")
        with patch.object(flow, "candidate", return_value=("d" * 40, self.record, {})):
            renamed = flow.run("evaluate", "probe", "renamed")
        self.assertEqual(renamed["status"], "BLOCKED", renamed)
        self.assertIn("duplicate probe content", renamed["reason"])
        flow.ledger.append({"action": "evaluate", "tier": "probe", "candidate_commit": self.commit, "candidate_tree": self.tree, "fingerprint": "new-fp", "status": "RUNNING"})
        flow.probe_attempt_guard(self.commit, self.tree, "new-fp")

    def test_probe_validity_uses_baseline_calibration_walls_and_retains_invalid_attempts(self):
        flow = w.Workflow(self.p)
        self.assertEqual(flow.run("calibrate", "probe")["status"], "CALIBRATED")
        self.invalid_candidate = True
        row = flow.run("evaluate", "probe", "candidate")
        self.assertEqual(row["status"], "INCOMPLETE", row)
        self.assertIn("validity reruns exhausted", row["reason"])
        self.assertEqual([r["status"] for r in row["runs"]], ["INVALID", "INVALID"])
        self.assertEqual(flow.budget["probe_guests"], 11)

    def test_noisy_metadata_and_missing_or_nonfinite_signals_never_pass(self):
        flow = w.Workflow(self.p)
        self.noisy_metadata = True
        calibration = flow.run("calibrate", "probe")
        self.assertEqual(calibration["status"], "CALIBRATION_NOISY", calibration)
        row = flow.run("evaluate", "probe", "candidate")
        self.assertEqual(row["status"], "INCOMPLETE", row)
        self.assertEqual(len(self.calls), 9)
        self.assertEqual(flow.budget["probe_guests"], 9)

    def test_missing_signal_becomes_incomplete_without_a_silent_retry(self):
        flow = w.Workflow(self.p)
        self.assertEqual(flow.run("calibrate", "probe")["status"], "CALIBRATED")
        self.bad_candidate = "missing"
        row = flow.run("evaluate", "probe", "candidate")
        self.assertEqual(row["status"], "INCOMPLETE", row)
        retry = flow.run("evaluate", "probe", "candidate")
        self.assertEqual(retry["status"], "BLOCKED", retry)
        self.assertEqual(flow.budget["probe_guests"], 10)

    def test_probe_pool_never_borrows_fast_capacity_and_builds_preserve_other_reservations(self):
        flow = w.Workflow(self.p)
        w.guest_budget.reserve_guest(self.p["campaign"], "external-auxiliary", "fixture", "disk", "plain", "swapin")
        flow.reserve("build")
        self.assertEqual((flow.budget["guests"], flow.budget["builds"]), (1, 1))
        flow.budget["probe_guests"] = 36
        w.save(flow.budget_path, flow.budget)
        with self.assertRaisesRegex(RuntimeError, "probe guest budget"):
            flow._reserve_guest("no-probe-capacity", "fixture", self.p["cases"]["swapin-disk"], "probe")
        retained = w.read(flow.budget_path)
        self.assertEqual((retained["guests"], retained["probe_guests"], retained["builds"]), (1, 36, 1))
        self.assertEqual(flow.budget_pools()["fast"]["remaining"], 83)

    def test_probe_candidate_cap_counts_distinct_executed_contents(self):
        flow = w.Workflow(self.p)
        flow.ledger = [{"action": "evaluate", "tier": "probe", "candidate_commit": f"{i:040x}",
                        "candidate_tree": f"{i:040x}", "fingerprint": "fp", "status": "PROBE_PASS", "execution_started": True}
                       for i in range(1, 9)] + [{"status": "RUNNING"}]
        with self.assertRaisesRegex(RuntimeError, "probe candidate budget"):
            flow.probe_attempt_guard("e" * 40, "f" * 40, "fp")

    def test_unexecutable_template_and_missing_plain_correctness_do_not_launch(self):
        flow = w.Workflow(self.p)
        self.p["template_only"] = True
        row = flow.run("calibrate", "probe")
        self.assertEqual(row["status"], "BLOCKED")
        self.assertIn("template", row["reason"])
        self.assertEqual(self.calls, [])
        self.p["template_only"] = False
        with patch.object(flow, "candidate", side_effect=RuntimeError("missing exact-commit correctness evidence")):
            row = flow.run("evaluate", "probe", "candidate")
        self.assertEqual(row["status"], "INCOMPLETE")
        self.assertIn("correctness", row["reason"])
        self.assertEqual(self.calls, [])
        self.assertEqual(flow.budget["guests"], 0)
        self.assertEqual(flow.budget.get("probe_guests", 0), 0)

    def test_nonfinite_signal_has_a_serializable_incomplete_report(self):
        flow = w.Workflow(self.p)
        self.assertEqual(flow.run("calibrate", "probe")["status"], "CALIBRATED")
        self.bad_candidate = "nonfinite"
        row = flow.run("evaluate", "probe", "candidate")
        self.assertEqual(row["status"], "INCOMPLETE", row)
        self.assertEqual(w.read(w.EVALUATIONS / row["id"] / "report.json")["status"], "INCOMPLETE")


class Revision6WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.real = w.read(REPO / "campaigns/xswap-tcg-kbench-2026-10-29/protocol.json")
        self.p = json.loads(json.dumps(self.real))
        self.p["campaign"] = "tcg-kbench-unit"
        campaign_tree(self, self.p)
        record = json.loads((self.campaign / "campaign.json").read_text())
        record["budget"] = {"guest_attempts": self.p["budget"]["guest_attempts"],
                            "wall_seconds": self.p["budget"]["wall_seconds"],
                            "probe_guest_attempts": self.p["budget"]["probe_guest_attempts"],
                            "approved_over_cap": None}
        w.save(self.campaign / "campaign.json", record)

    def test_contract_and_child_env_force_tcg(self):
        self.assertEqual(w.contract_errors(self.real), [])
        self.assertNotIn(self.real["campaign"], w.CONTRACT_EXEMPT)
        self.assertFalse((REPO / "campaigns/xswap-tcg-kbench-2026-10-29/campaign.json").exists())
        with patch.dict("os.environ", {"SWAP_NEXT_ACCEL": "kvm"}, clear=False):
            env = w.child_env(self.real)
        self.assertEqual(env["SWAP_NEXT_ACCEL"], "tcg")
        self.assertEqual(env["SWAP_NEXT_TCG_SMP"], "4")
        self.assertEqual(env["SWAP_NEXT_TCG_MEM_MIB"], "4096")
        self.assertIn("--preallocate-swap", w.runner_extra(self.real))
        self.assertEqual(w.runner_extra(self.real)[w.runner_extra(self.real).index("--protocol-revision") + 1], "6")

    def test_kvm_accelerator_result_is_rejected(self):
        flow = w.Workflow(self.p)

        def fake_command(command, logfile, timeout, accept_failure=False, env=None):
            self.assertEqual(env["SWAP_NEXT_ACCEL"], "tcg")
            run_id = command[command.index("--run-id") + 1]
            dest = self.campaign / "runs/guests" / run_id
            dest.mkdir(parents=True)
            (dest / "result.json").write_text(json.dumps({
                "run_id": run_id, "source_commit": self.p["baseline_commit"], "integration_pass": True,
                "swap_image_allocation": "preallocated", "clocksource_invalid": False,
                "pre_qemu_seconds": 1.0, "wall_seconds": 100.0,
                "host_load": {"before_launch": {"loadavg_1m": 0.2, "loadavg_5m": 0.2, "loadavg_15m": 0.2}},
                "metrics": {}, "guest_mem_mib": 4096, "guest_vcpus": 4, "accelerator": "kvm"}))
            logfile.write_text("mocked\n")
            return 0

        with patch.dict("os.environ", {"SWAP_NEXT_ACCEL": "kvm"}, clear=False), \
             patch.object(w, "fingerprint", return_value="fp"), \
             patch.object(flow, "command", side_effect=fake_command):
            row = flow.run("calibrate", "fast")
        self.assertEqual(row["status"], "INCOMPLETE")
        self.assertIn("accelerator does not match protocol", row["reason"])
        self.assertEqual(row["protocol_revision"], 6)


if __name__ == "__main__":
    unittest.main()
