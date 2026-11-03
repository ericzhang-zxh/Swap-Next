# SPDX-License-Identifier: GPL-2.0-only
"""Native raw A/A cache and Workflow fixtures; no QEMU guest or build is run."""
import contextlib
import copy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from evolve import standard_workflow as workflow
from evolve import test_reference_cache as fixtures
import calibration_cache as cc

ROOT = Path(__file__).resolve().parents[1]


class CalibrationCacheTests(unittest.TestCase):
    def setUp(self):
        self.seed = fixtures.ReferenceCacheTests("test_calibration_replays_raw_and_preserves_original_expiry")
        self.seed.setUp()
        self.addCleanup(self.seed.tearDown)
        self.root, self.protocol = self.seed.root, self.seed.protocol
        for relative in (
            "evolve/standard_workflow.py", "evolve/calibration_cache.py", "evolve/reference_cache.py",
            "evolve/control/controller.py", "evolve/control/campaign_store.py",
            "evolve/control/guest_budget.py", "evolve/control/correctness_proof.py",
            "benchmark/kernel/build.py", "benchmark/kernel/lifetime.py", "benchmark/kernel/build_namespace.sh",
            "benchmark/swap-standard/guest-init", "benchmark/swap-standard/tools.json",
        ):
            self.seed.put(relative, (ROOT / relative).read_bytes())
        self.clock = patch.object(cc.time, "time", return_value=105).start()
        self.addCleanup(patch.stopall)
        native_output = cc.subprocess.check_output
        def version_only(argv, **kwargs):
            if argv == ["qemu-system-x86_64", "--version"]:
                return "QEMU synthetic identity fixture 1"
            return native_output(argv, **kwargs)
        patch.object(cc.subprocess, "check_output", side_effect=version_only).start()
        self.fp = "9" * 64

    def original(self, tier="fast"):
        if tier == "probe":
            self.protocol["tiers"]["probe"] = {
                "kind": "probe", "cases": ["swapin-disk"], "calibration_runs": 3, "candidate_runs": 1}
            self.protocol["probe_band"] = {"relative_padding": .01, "integer_padding_floor": 1,
                                           "metadata_spread_fraction": .01}
            self.protocol["cases"]["swapin-disk"]["probe_signals"] = ["swapin_vmstat_delta.swap_ra"]
            self.seed.put("campaigns/source/protocol.json", self.protocol)
            runs, samples = [], {"swapin-disk": []}
            for index in range(3):
                attempt, raw = self.seed.raw_run("probe-" + str(index))
                attempt.update(index=index)
                attempt.pop("pair"); attempt.pop("arm")
                ticket = json.loads((self.root / raw["reservation"]).read_text())
                ticket["pool"] = "probe"
                self.seed.put(raw["reservation"], ticket)
                raw["reservation_sha256"] = self.seed.sha(raw["reservation"])
                self.seed.put(raw["result_path"], raw)
                attempt["result_sha256"] = self.seed.sha(raw["result_path"])
                self.seed.put(str(Path(raw["result_path"]).with_name("result.sha256")),
                              (attempt["result_sha256"] + "\n").encode())
                runs.append(attempt)
                samples["swapin-disk"].append(raw["metrics"])
            self.seed.put("campaigns/source/ledger/budget.json", {"guests": 0, "probe_guests": 3})
            analysis = cc.cache.Verifier(self.root).native("benchmark/swap-standard/probe.py").calibrate(self.protocol, samples)
            row = {"id": "aa-probe", "action": "calibrate", "tier": "probe", "runs": runs,
                   "probe_signals": samples, "analysis": analysis, "status": analysis["status"],
                   "finished": 100, "candidate_commit": self.seed.commit, "fingerprint": "f" * 64}
        else:
            row, _ = self.seed.measurement("calibration", "aa-fast")
        row.update(started=90, candidate_tree=self.seed.tree, execution_started=True,
                   protocol_sha256=self.seed.sha("campaigns/source/protocol.json"))
        self.seed.put("campaigns/source/runs/evaluations/" + row["id"] + "/report.json", row)
        self.seed.put("campaigns/source/ledger/ledger.json", [row])
        result = cc.register(self.root, self.protocol, row)
        self.assertEqual(result["status"], "registered", result)
        return row, result

    def target(self):
        self.protocol = copy.deepcopy(self.protocol)
        self.protocol["campaign"] = "target"
        self.protocol["budget"].update(guest_attempts=80, probe_guest_attempts=10)
        self.seed.put("campaigns/target/protocol.json", self.protocol)
        self.seed.put("campaigns/target/campaign.json", {"campaign": "target", "machine": "fixture", "status": "open"})
        self.seed.put("campaigns/target/ledger/budget.json", {"guests": 80, "probe_guests": 10, "builds": 0})
        return self.protocol

    def alias(self, tier="fast"):
        row = {"id": "alias", "action": "calibrate", "tier": tier, "status": "RUNNING", "started": 105,
               "runs": [], "pairs": [], "performance_accepted": False, "auto_promote": False}
        self.assertTrue(cc.reuse(self.root, self.protocol, row, self.fp))
        return row

    def flow(self, ledger=None):
        campaign = self.root / "campaigns/target"
        for name, value in {
            "ROOT": self.root, "CAMPAIGN": campaign, "PROTOCOL": campaign / "protocol.json",
            "STATE": campaign / "ledger", "EVALUATIONS": campaign / "runs/evaluations",
            "RUNS": campaign / "runs/guests", "ARCHIVE": campaign / "archive",
            "BENCH": self.root / "benchmark/swap-standard",
        }.items():
            patch.object(workflow, name, value).start()
        patch.object(workflow, "fingerprint", return_value=self.fp).start()
        patch.object(workflow, "contract_errors", return_value=[]).start()
        flow = workflow.Workflow.__new__(workflow.Workflow)
        flow.p = self.protocol
        flow.ledger = ledger or []
        flow.ledger_path = campaign / "ledger/ledger.json"
        flow.budget_path = campaign / "ledger/budget.json"
        flow.budget = json.loads(flow.budget_path.read_text())
        flow.stop = campaign / "STOP"
        flow.global_stop = self.root / "STOP"
        flow.check = lambda: None
        flow.campaign_errors = lambda: []
        flow.reserve = Mock(side_effect=AssertionError("cache path reserved a build"))
        flow._reserve_guest = Mock(side_effect=AssertionError("cache path reserved a guest"))
        flow.command = Mock(side_effect=AssertionError("cache path launched a process"))
        flow.archive = Mock(side_effect=AssertionError("cache path archived a candidate"))
        return flow

    def test_workflow_cross_campaign_native_fast_cache_has_zero_new_attempts(self):
        original, receipt = self.original()
        original_path = "campaigns/source/runs/evaluations/aa-fast/report.json"
        report_before = self.seed.sha(original_path)
        budget_before = self.seed.sha("campaigns/source/ledger/budget.json")
        self.target()
        flow = self.flow()
        target_budget = copy.deepcopy(flow.budget)
        with contextlib.redirect_stdout(io.StringIO()):
            row = flow.run("calibrate", "fast")
        self.assertEqual(row["status"], "CALIBRATED", row.get("reason"))
        self.assertTrue(row["measurement_reused"])
        self.assertFalse(row["independent_measurement"])
        self.assertEqual(row["source_campaign"], "source")
        self.assertEqual(row["source_evaluation_id"], "aa-fast")
        self.assertEqual(row["source_binding"]["record_sha256"], receipt["record_sha256"])
        self.assertEqual((row["started"], row["finished"]), (90, 100))
        self.assertEqual(row["reused_at"], 105)
        self.assertEqual(row["analysis"], original["analysis"])
        self.assertEqual(flow.budget, target_budget)
        self.assertEqual(report_before, self.seed.sha(original_path))
        self.assertEqual(budget_before, self.seed.sha("campaigns/source/ledger/budget.json"))
        for method in (flow.reserve, flow._reserve_guest, flow.command, flow.archive):
            method.assert_not_called()
        self.assertEqual(flow.calibration("fast", self.fp), row)
        self.assertEqual(json.loads((workflow.EVALUATIONS / row["id"] / "report.json").read_text()), row)

    def test_workflow_native_probe_cache_preserves_original_expiry(self):
        original, _ = self.original("probe")
        self.target()
        flow = self.flow()
        with contextlib.redirect_stdout(io.StringIO()):
            row = flow.run("calibrate", "probe")
        self.assertEqual(row["status"], "CALIBRATED", row.get("reason"))
        self.assertTrue(row["measurement_reused"])
        self.assertEqual(row["finished"], original["finished"])
        self.assertEqual(flow.calibration("probe", self.fp), row)
        for method in (flow.reserve, flow._reserve_guest, flow.command, flow.archive):
            method.assert_not_called()
        self.clock.return_value = 110
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            flow.calibration("probe", self.fp)

    def test_expired_original_cannot_be_refreshed_by_alias_time(self):
        self.original(); self.target()
        row = self.alias()
        self.clock.return_value = 110
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            cc.validate_alias(self.root, self.protocol, row)
        fresh_request = {"id": "later", "action": "calibrate", "tier": "fast"}
        self.assertFalse(cc.reuse(self.root, self.protocol, fresh_request, self.fp))
        self.assertEqual(fresh_request, {"id": "later", "action": "calibrate", "tier": "fast"})

    def test_tampered_original_serial_invalidates_reuse_and_existing_alias(self):
        original, _ = self.original(); self.target()
        alias = self.alias()
        raw = json.loads((self.root / original["runs"][0]["result"]).read_text())
        (self.root / raw["serial_log"]).write_text("tampered synthetic serial\n")
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            cc.validate_alias(self.root, self.protocol, alias)
        self.assertFalse(cc.reuse(self.root, self.protocol, {"tier": "fast"}, self.fp))

    def test_current_native_veto_invalidates_reuse_and_existing_alias(self):
        self.original(); self.target()
        alias = self.alias()
        evidence = "benchmark/config/swap-standard.config"
        self.seed.put("campaigns/target/candidates/baseline.json", {"id": "baseline",
                      "candidate_commit": self.seed.commit, "source_tree": self.seed.tree})
        cc.reviews.record(self.root, "target", {
            "schema_version": 1, "id": "baseline-veto", "campaign": "target", "candidate": "baseline",
            "candidate_commit": self.seed.commit, "source_tree": self.seed.tree, "reviewer": "fixture",
            "summary": "Synthetic current baseline veto", "disposition": "veto",
            "findings": [{"id": "unsafe", "summary": "Unresolved fixture finding"}], "resolves": [],
            "evidence": [{"path": evidence, "sha256": self.seed.sha(evidence)}]})
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            cc.validate_alias(self.root, self.protocol, alias)
        self.assertFalse(cc.reuse(self.root, self.protocol, {"tier": "fast"}, self.fp))

    def test_semantic_environment_or_harness_change_requires_new_measurement(self):
        self.original(); self.target()
        self.protocol["budget"]["guest_timeout"] += 1
        self.seed.put("campaigns/target/protocol.json", self.protocol)
        self.assertFalse(cc.reuse(self.root, self.protocol, {"tier": "fast"}, self.fp))
        self.protocol["budget"]["guest_timeout"] -= 1
        self.seed.put("campaigns/target/protocol.json", self.protocol)
        self.assertTrue(cc.reuse(self.root, self.protocol, {"tier": "fast"}, self.fp))
        path = self.root / "evolve/standard_workflow.py"
        path.write_text(path.read_text() + "\n# fixture evaluator drift\n")
        self.assertFalse(cc.reuse(self.root, self.protocol, {"tier": "fast"}, self.fp))

    def test_alias_measurement_and_provenance_edits_are_rejected(self):
        self.original(); self.target()
        alias = self.alias()
        edits = {
            "analysis": {"passed": True}, "runs": [], "pairs": [], "candidate_commit": "0" * 40,
            "candidate_tree": "0" * 40, "started": 95, "finished": 105, "independent_measurement": True,
            "source_binding": dict(alias["source_binding"], campaign="different"),
        }
        for field, value in edits.items():
            with self.subTest(field=field), self.assertRaises(ValueError):
                cc.validate_alias(self.root, self.protocol, dict(alias, **{field: value}))

    def test_alias_action_and_source_attribution_edits_are_rejected(self):
        self.original(); self.target()
        alias = self.alias()
        for field, value in (("action", "evaluate"), ("status", "FAST_PASS"),
                             ("source_evaluation_id", "another-source"), ("source_campaign", "another-campaign")):
            with self.subTest(field=field), self.assertRaises(ValueError):
                cc.validate_alias(self.root, self.protocol, dict(alias, **{field: value}))

    def prior_failure_blocks_cache_before_lookup(self, tier):
        self.original(tier); self.target()
        prior = {"id": "failed-target-aa", "action": "calibrate", "tier": tier, "fingerprint": self.fp,
                 "execution_started": True, "status": "CALIBRATION_NOISY", "finished": 104,
                 "analysis": {"passed": False}, "runs": []}
        flow = self.flow([prior])
        with patch.object(flow, "reuse_calibration", wraps=flow.reuse_calibration) as lookup:
            with contextlib.redirect_stdout(io.StringIO()):
                row = flow.run("calibrate", tier)
            lookup.assert_not_called()
        self.assertEqual(row["status"], "INCOMPLETE")
        self.assertIn("already attempted", row["reason"])
        self.assertFalse(row.get("measurement_reused", False))
        self.assertEqual(flow.ledger[0], prior)
        for method in (flow.reserve, flow._reserve_guest, flow.command, flow.archive):
            method.assert_not_called()

    def test_target_prior_fast_failure_blocks_cache_before_lookup(self):
        self.prior_failure_blocks_cache_before_lookup("fast")

    def test_target_prior_probe_failure_blocks_cache_before_lookup(self):
        self.prior_failure_blocks_cache_before_lookup("probe")


if __name__ == "__main__":
    unittest.main()
