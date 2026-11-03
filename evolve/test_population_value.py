# SPDX-License-Identifier: GPL-2.0-only
"""Guest-free integration of retained value with real population/controller gates."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "control"))
import campaign_store
import controller
import population
import research
import value_evidence
from evolve.test_research import decision, line

METRIC = "swapin-disk.swapin_seq.mean_ns"
PATCH = "diff --git a/mm/swap_state.c b/mm/swap_state.c\n--- a/mm/swap_state.c\n+++ b/mm/swap_state.c\n@@ -1 +1 @@\n-old\n+new\n"


class PopulationValueTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="swap-population-value-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.linux = self.root / "linux"
        self.linux.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Synthetic fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        source = self.linux / "fixture.txt"
        source.write_text("synthetic baseline\n")
        self.git("add", "fixture.txt")
        self.git("commit", "-qm", "synthetic baseline")
        self.base, self.base_tree = self.git("rev-parse", "HEAD"), self.git("rev-parse", "HEAD^{tree}")
        source.write_text("synthetic candidate\n")
        self.git("commit", "-qam", "synthetic candidate")
        self.commit, self.tree = self.git("rev-parse", "HEAD"), self.git("rev-parse", "HEAD^{tree}")
        self.directory = self.root / "campaigns/demo"
        self.protocol = {"campaign": "demo", "baseline_commit": self.base,
                         "line_anchor_commit": self.base, "max_candidates": 3,
                         "required_correctness_gates": ["data_roundtrip"]}
        self.put("campaigns/demo/protocol.json", self.protocol)
        self.put("campaigns/hosts.json", {"fixture": {"hostnames": []}})
        self.put("campaigns/demo/campaign.json", {
            "campaign": "demo", "line": "research", "status": "open", "baseline_from": None,
            "machine": "fixture", "opened": "fixture", "closed": None,
            "budget": {"guest_attempts": 0, "probe_guest_attempts": 0,
                       "wall_seconds": 1000, "approved_over_cap": None}})
        self.subject = {"id": "one", "parent": self.base, "parent_commit": self.base,
                        "candidate_commit": self.commit, "source_tree": self.tree,
                        "hypothesis": "Synthetic value-gate integration", "mechanism": "reviewed_structure"}
        self.put("campaigns/demo/candidates/one.json", self.subject)
        self.put("campaigns/destination/policy.json", {"seed_ref": self.commit})
        self.put("campaigns/demo/report/review.md", {"review": "synthetic fixture"})
        shutil.copytree(HERE / "profiles", self.root / "evolve/profiles")
        self.fp = "f" * 64
        self.population = population.Population(self.directory, self.protocol, self.fp)
        self.value_path = self.directory / "candidates/one/value.json"
        # Only path/fingerprint plumbing changes. Controller Git, review,
        # archived Population, value validation and advancement all execute.
        bindings = ((campaign_store, "PROJECT", self.root),
                    (campaign_store, "CAMPAIGNS", self.root / "campaigns"),
                    (campaign_store, "HOSTS", self.root / "campaigns/hosts.json"),
                    (controller, "PROJECT", self.root), (controller, "ROOT", self.linux),
                    (controller, "POLICY", self.root / "campaigns/destination/policy.json"))
        for module, name, value in bindings:
            binding = patch.object(module, name, value)
            binding.start()
            self.addCleanup(binding.stop)
        fingerprint = patch.object(controller, "campaign_fingerprint", return_value=self.fp)
        fingerprint.start()
        self.addCleanup(fingerprint.stop)
        network = patch.object(socket.socket, "connect", side_effect=AssertionError("no network in fixture"))
        network.start()
        self.addCleanup(network.stop)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.linux), *args],
                                       stderr=subprocess.PIPE, text=True).strip()

    def put(self, reference, value):
        path = self.root / reference
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n")
        return path

    def freeze_research(self):
        agenda = line()
        agenda.update(anchor_commit=self.base, baseline_commit=self.base)
        self.contract = research.line_contract(agenda, root=self.root)
        self.put("campaigns/demo/research.json", {"line_contract": self.contract})

    def admit(self, score=1.1, noise=.03, interval=None):
        analysis = {"status": "FAST_PASS", "combined_score": score, "primary": [METRIC],
                    "metrics": {METRIC: {"noise_relative": noise, "guard_pass": True}}}
        if interval is not None:
            analysis["overall_ci95"] = interval
        self.row = {"id": "one-fast", "action": "evaluate", "tier": "fast", "status": "FAST_PASS",
                    "candidate": "one", "candidate_commit": self.commit, "candidate_tree": self.tree,
                    "baseline_commit": self.base, "fingerprint": self.fp, "finished": 10,
                    "correctness": {"candidate_commit": self.commit, "gates": {"data_roundtrip": True}},
                    "analysis": analysis}
        self.report_ref = "campaigns/demo/runs/evaluations/one-fast/report.json"
        self.report_path = self.put(self.report_ref, self.row)
        self.put("campaigns/demo/ledger/ledger.json", [self.row])
        return self.population.record(self.row, self.subject, PATCH, self.tree)

    def retain_value(self, change="unchanged"):
        value = decision(self.contract, change)
        value["identity"] = {"candidate_commit": self.commit, "candidate_tree": self.tree,
            "parent_commit": self.base, "parent_tree": self.base_tree, "baseline_commit": self.base,
            "protocol_sha256": hashlib.sha256((self.directory / "protocol.json").read_bytes()).hexdigest(),
            "evaluation_id": self.row["id"], "evaluation_report": self.report_ref}
        value["evidence"] = ["campaigns/demo/report/review.md"]
        value["learning_value"] = "Retain this bounded mechanism result for a distinct next hypothesis."
        value.update(research.performance_from_report(self.row))
        record = research.record_value(self.directory, "one", value, self.contract, value["identity"], self.root)
        verified = value_evidence.validate(self.root, "demo", "one", value["identity"])
        self.assertEqual(record["assessment"], verified["assessment"])
        return record

    def view(self):
        return self.population._view(self.population._state()["entries"]["one"])

    def advance(self):
        args = SimpleNamespace(baseline_from="demo:one", evidence_row=self.row["id"],
                               evidence_report=None, line="research")
        return controller.baseline_from(args, {"baseline_commit": self.commit})

    def test_research_fast_pass_waits_for_verified_value(self):
        self.freeze_research()
        entry = self.admit()
        self.assertFalse(entry["parent_eligible"])
        self.assertIn("research_value_missing_or_invalid", entry["invalidation_reasons"])
        self.assertEqual(self.population.eligible_parents(), {})
        brief = self.population.next_brief([], "", {}, persist=False)
        self.assertEqual(brief["allowed_parents"], [self.base])
        with self.assertRaisesRegex(ValueError, "current eligible archived"):
            self.advance()
        self.retain_value()
        self.assertIn("one", self.population.eligible_parents())

    def test_expensive_tiny_gain_removes_parent_old_brief_and_advancement(self):
        # An existing durable receipt may predate mandatory value reconciliation.
        # Adding its frozen research record must not let that old receipt bypass it.
        self.admit(score=1.01, noise=.001)
        self.assertTrue(population.advancement_evidence(self.row)["eligible"])
        brief = self.population.next_brief([], "", {})
        self.assertIn(self.commit, brief["allowed_parents"])
        self.freeze_research()
        retained = self.retain_value("increased")
        self.assertEqual(retained["assessment"]["disposition"], "rejected")
        self.assertEqual(self.population.eligible_parents(), {})
        self.assertFalse(self.view()["advancement"]["eligible"])
        with self.assertRaisesRegex(ValueError, "no longer eligible"):
            self.population.validate_parent(brief["id"], self.commit)
        self.population.validate_parent(brief["id"], self.base)
        with self.assertRaisesRegex(ValueError, "current eligible archived"):
            self.advance()

    def test_exploratory_learning_can_parent_but_cannot_advance(self):
        self.freeze_research()
        self.admit(score=1.04, noise=.01)
        self.assertTrue(population.advancement_evidence(self.row)["eligible"])
        retained = self.retain_value()
        self.assertEqual(retained["assessment"]["disposition"], "exploratory")
        self.assertTrue(retained["decision"]["learning_value"])
        self.assertTrue(self.population.eligible_parents()["one"]["parent_eligible"])
        self.assertFalse(self.view()["advancement"]["eligible"])
        brief = self.population.next_brief([], "", {})
        self.population.validate_parent(brief["id"], self.commit)
        with self.assertRaisesRegex(ValueError, "practical-value"):
            self.advance()

    def test_worthwhile_value_preserves_numeric_advancement(self):
        self.freeze_research()
        self.admit()
        retained = self.retain_value("increased")
        self.assertEqual(retained["assessment"]["disposition"], "worthwhile-to-confirm")
        view = self.population.eligible_parents()["one"]
        self.assertTrue(view["advancement"]["eligible"])
        self.assertEqual(view["advancement"]["threshold"], 1.03)
        self.assertEqual(self.advance()["commit"], self.commit)
        self.assertFalse(view["performance_accepted"])

    def test_simplification_value_does_not_override_numeric_advancement_gate(self):
        self.freeze_research()
        self.admit(score=1, noise=.03, interval=[.99, 1.01])
        retained = self.retain_value("decreased")
        self.assertEqual(retained["assessment"]["disposition"], "simplification")
        self.assertIn("one", self.population.eligible_parents())
        self.assertFalse(self.view()["advancement"]["eligible"])
        with self.assertRaisesRegex(ValueError, "above calibrated noise"):
            self.advance()

    def test_legacy_campaign_keeps_existing_parent_and_advancement_behavior(self):
        self.admit()
        self.assertFalse((self.directory / "research.json").exists())
        self.assertFalse(self.value_path.exists())
        self.assertIn("one", self.population.eligible_parents())
        self.assertTrue(self.view()["advancement"]["eligible"])
        self.assertEqual(self.advance()["commit"], self.commit)

    def test_changed_decision_or_report_invalidates_parent_and_durable_brief(self):
        self.freeze_research()
        self.admit()
        retained = self.retain_value()
        brief = self.population.next_brief([], "", {})
        original_value, original_report = self.value_path.read_bytes(), self.report_path.read_bytes()
        for target in ("decision", "report", "source-tree"):
            with self.subTest(target=target):
                changed = copy.deepcopy(retained)
                if target == "decision":
                    changed["decision"]["review_status"] = "pending"
                    self.put(self.value_path, changed)
                elif target == "report":
                    self.report_path.write_bytes(original_report + b" ")
                else:
                    changed["decision"]["identity"]["candidate_tree"] = "9" * 40
                    changed["assessment"] = research.assess_value(changed["decision"], self.contract)
                    self.put(self.value_path, changed)
                self.assertEqual(self.population.eligible_parents(), {})
                self.assertIn("research_value_missing_or_invalid", self.view()["invalidation_reasons"])
                self.assertFalse(self.view()["advancement"]["eligible"])
                with self.assertRaisesRegex(ValueError, "no longer eligible"):
                    self.population.validate_parent(brief["id"], self.commit)
                with self.assertRaisesRegex(ValueError, "current eligible archived"):
                    self.advance()
                self.value_path.write_bytes(original_value)
                self.report_path.write_bytes(original_report)
        self.assertIn("one", self.population.eligible_parents())


if __name__ == "__main__":
    unittest.main()
