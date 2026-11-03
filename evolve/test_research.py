# SPDX-License-Identifier: GPL-2.0-only
"""Guest-free research contract tests; all mutations use temporary fixtures."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from evolve import research as r


def complexity(change="unchanged"):
    item = {key: {"change": "unchanged", "reason": "Existing obligation is preserved."}
            for key in r.COMPLEXITY_DIMENSIONS}
    item["state"] = {"change": change, "reason": "The reviewed change alters a state obligation."}
    return {"parent": copy.deepcopy(item), "baseline": copy.deepcopy(item)}


def idea(name="first", priority=1):
    return {"id": name, "status": "proposed", "priority": priority, "change_type": "optimize",
            "bottleneck": "Repeated path work", "mechanism": "Reduce repeated work",
            "mechanism_evidence_type": "counter_shift",
            "affected_paths": ["mm/swap_state.c"], "expected_benefit": "Lower fault latency",
            "simpler_alternative": "Keep the original path", "falsifier": "The work does not decrease",
            "upstream_refs": [], "no_upstream_reason": "Fixture has no relevant alternative.",
            "required_evidence": ["Correctness and paired latency"],
            "estimated_cost": {"guest_attempts": 20, "build_attempts": 1},
            "selection_reason": "Resolve the highest priority bottleneck.",
            "complexity": complexity()}


def line(name="research"):
    return {"schema_version": 1, "line": name, "contributor": "fixture-contributor", "question": "Can fault work be reduced?",
            "status": "active", "profile": "swap-core", "anchor_commit": "a" * 40,
            "baseline_commit": "b" * 40, "ideas": [idea()], "upstream_refs": [],
            "no_upstream_reason": "Fixture has no relevant alternative.",
            "value_policy": {"min_useful_effect": .05, "equivalence_margin": .02,
                             "requires_upstream_comparison": False,
                             "rationale": "Engineering threshold fixed before evaluation."},
            "resource_ceiling": {"guest_attempts": 200, "build_attempts": 20}}


def identity():
    return {"candidate_commit": "c" * 40, "candidate_tree": "d" * 40,
            "parent_commit": "b" * 40, "parent_tree": "e" * 40,
            "baseline_commit": "b" * 40, "protocol_sha256": "f" * 64,
            "evaluation_id": "eval-1", "evaluation_report": "campaigns/c/runs/eval-1/report.json"}


def decision(contract, change="unchanged"):
    return {"schema_version": 1, "identity": identity(),
            "scientific_sha256": contract["scientific_sha256"],
            "scientific_result": "screen", "review_status": "clear",
            "complexity": complexity(change), "evidence": ["campaigns/c/report/review.md"],
            "reason": "Candidate tradeoff was reviewed.", "learning_value": "Tests one mechanism.",
            "complexity_justification": "Potential gain must cover the added obligation.",
            "performance": {"normalized_gain": .10, "noise_relative": .03, "scored_guards_pass": True},
            "upstream_comparison": {"status": "not-applicable", "reason": "No relevant alternative.", "evidence": []},
            "frontier_eligible": True, "frontier_reason": "No simpler candidate dominates it."}


class ResearchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        shutil.copytree(r.ROOT / "evolve/profiles", self.root / "evolve/profiles")
        self.profile = r.load_profile("swap-core", self.root)
        self.line = line()
        self.contract = r.line_contract(self.line, self.profile)

    def tearDown(self):
        self.tmp.cleanup()

    def put(self, path, value):
        path = self.root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n")
        return path

    def campaign(self, name, *, status="closed", guests=0, probes=0, builds=0, missing=False):
        self.put(f"campaigns/{name}/campaign.json",
                 {"campaign": name, "line": "research", "status": status})
        if not missing:
            self.put(f"campaigns/{name}/ledger/budget.json",
                     {"guests": guests, "probe_guests": probes, "builds": builds})
        self.put(f"campaigns/{name}/protocol.json",
                 {"budget": {"guest_attempts": 96, "probe_guest_attempts": 24, "build_attempts": 10}})

    def test_profiles_are_trusted_and_policy_cannot_widen(self):
        policy = {"allowed_modify": ["mm/swap_state.c"], "allowed_add": []}
        self.assertEqual(r.validate_policy_scope(policy, self.profile), [])
        policy["allowed_modify"].append("mm/memory.c")
        self.assertIn("widens", r.validate_policy_scope(policy, self.profile)[0])
        policy["allowed_modify"].pop()
        policy["allowed_add"] = ["tools/testing/selftests/mm/*.c"]
        self.assertIn("widens", r.validate_policy_scope(policy, self.profile)[0])
        with self.assertRaises(r.ResearchError):
            r.load_profile("../untrusted", self.root)

    def test_current_protocol_checks_and_architecture_missing_capabilities(self):
        protocol = r.read_json(r.ROOT / "campaigns/xswap-tcg-kbench-2026-10-29/protocol.json")
        result = r.capability_readout(self.profile, protocol)
        self.assertTrue(result["ready"], result)
        self.assertFalse(result["execution_authorized"])
        for change in ("guest", "primary", "correctness", "revision"):
            bad = copy.deepcopy(protocol)
            if change == "guest":
                bad["guest"]["mem_mib"] = 9999
            elif change == "primary":
                bad["cases"]["swapin-disk"]["primary"] = "unregistered.cost"
            elif change == "correctness":
                bad["required_correctness_gates"] = []
            else:
                bad["protocol_revision"] = 7
            self.assertFalse(r.capability_readout(self.profile, bad)["ready"], change)
        architecture = r.load_profile("swap-architecture", self.root)
        result = r.capability_readout(architecture, protocol)
        self.assertFalse(result["ready"])
        self.assertTrue(any("KCSAN" in reason for reason in result["missing_capabilities"]))

    def test_plain_protocol_has_concrete_correctness_gap(self):
        protocol = r.read_json(r.ROOT / "benchmark/swap-standard/revision4-protocol-template.json")
        result = r.capability_readout(self.profile, protocol)
        self.assertFalse(result["ready"])
        self.assertTrue(any("plain correctness" in reason for reason in result["missing_capabilities"]))

    def test_contract_ignores_backlog_and_current_baseline(self):
        changed = copy.deepcopy(self.line)
        changed["baseline_commit"] = "1" * 40
        changed["ideas"][0]["priority"] = 9
        changed["ideas"].append(idea("next"))
        changed["status"] = "paused"
        self.assertEqual(r.line_contract(changed, self.profile), self.contract)
        changed["value_policy"]["min_useful_effect"] = .08
        self.assertNotEqual(r.line_contract(changed, self.profile), self.contract)
        bad = copy.deepcopy(self.contract)
        bad["value_policy"]["min_useful_effect"] = 0
        with self.assertRaisesRegex(r.ResearchError, "hash"):
            r.validate_contract(bad, self.root)

    def test_missing_upstream_and_nonfinite_threshold_are_rejected(self):
        bad = copy.deepcopy(self.line)
        del bad["no_upstream_reason"]
        with self.assertRaises(r.ResearchError):
            r.validate_line(bad)
        for invalid in (float("nan"), float("inf"), True, -.1):
            bad = copy.deepcopy(self.line)
            bad["value_policy"]["min_useful_effect"] = invalid
            with self.assertRaises(r.ResearchError):
                r.validate_line(bad)

    def test_added_complexity_with_small_gain_is_rejected(self):
        value = decision(self.contract, "increased")
        value["performance"]["normalized_gain"] = .01
        result = r.assess_value(value, self.contract)
        self.assertEqual(result["disposition"], "rejected")
        self.assertIn("added complexity", result["reasons"][0])

    def test_equivalent_simplification_requires_bounded_interval(self):
        value = decision(self.contract, "decreased")
        value["performance"]["normalized_gain"] = 0
        self.assertEqual(r.assess_value(value, self.contract)["disposition"], "exploratory")
        value["performance"].update(gain_interval=[-.01, .01], interval_method="trusted paired interval")
        result = r.assess_value(value, self.contract)
        self.assertEqual(result["disposition"], "simplification")
        self.assertFalse(result["performance_accepted"])
        value["performance"]["gain_interval"] = [-.03, .01]
        self.assertEqual(r.assess_value(value, self.contract)["disposition"], "exploratory")

    def test_useful_screen_needs_clear_review_upstream_and_frontier(self):
        value = decision(self.contract, "increased")
        self.assertEqual(r.assess_value(value, self.contract)["disposition"], "worthwhile-to-confirm")
        for key, setting, expected in (
                ("review_status", "blocked", "review-blocked"),
                ("frontier_eligible", False, "rejected"),
                ("advisory_flags", ["campaigns/c/report/tail.md"], "review-blocked")):
            changed = copy.deepcopy(value)
            changed[key] = setting
            self.assertEqual(r.assess_value(changed, self.contract)["disposition"], expected)
        changed = copy.deepcopy(value)
        changed["upstream_comparison"]["status"] = "missing"
        self.assertEqual(r.assess_value(changed, self.contract)["disposition"], "exploratory")

    def test_inherited_gain_cannot_justify_added_parent_complexity(self):
        value = decision(self.contract, "increased")
        value["identity"]["parent_commit"] = "1" * 40
        result = r.assess_value(value, self.contract)
        self.assertEqual(result["disposition"], "exploratory")
        self.assertIn("marginal value", result["reasons"][0])

    def test_running_report_cannot_be_finalized_as_incomplete(self):
        with self.assertRaises(r.ResearchError):
            r.performance_from_report({"status": "RUNNING"})

    def test_incomplete_needs_no_invented_numbers(self):
        value = decision(self.contract)
        value.update(scientific_result="incomplete", performance=None)
        self.assertEqual(r.assess_value(value, self.contract)["disposition"], "exploratory")
        value["scientific_result"] = "correctness-failure"
        self.assertEqual(r.assess_value(value, self.contract)["disposition"], "rejected")

    def test_value_identity_and_numeric_finiteness(self):
        value = decision(self.contract)
        expected = identity()
        expected["candidate_tree"] = "1" * 40
        with self.assertRaisesRegex(r.ResearchError, "identity mismatch"):
            r.assess_value(value, self.contract, expected)
        value["performance"]["normalized_gain"] = float("nan")
        with self.assertRaises(r.ResearchError):
            r.assess_value(value, self.contract)

    def test_line_counts_both_pools_closed_failures_and_open_commitments(self):
        self.campaign("old", guests=65, probes=15, builds=3)
        self.campaign("active", status="open", guests=9, probes=2, builds=1)
        spending = r.line_spending(self.root, "research")
        self.assertEqual(spending["spent"], {"guest_attempts": 91, "build_attempts": 4})
        self.assertEqual(spending["committed"], {"guest_attempts": 109, "build_attempts": 9})
        budget = r.line_budget(self.line, spending, {"guest_attempts": 1})
        self.assertFalse(budget["ready"])
        budget = r.line_budget(self.line, spending, {"guest_attempts": 20}, exclude_campaign="active")
        self.assertTrue(budget["ready"])
        self.campaign("unknown", missing=True)
        spending = r.line_spending(self.root, "research")
        self.assertFalse(spending["complete"])
        self.assertFalse(r.line_budget(self.line, spending)["ready"])

    def test_selection_uses_explicit_priority_and_excludes_unimplemented_ideas(self):
        self.line["ideas"] = [idea("first", 1), idea("second", 3), idea("third", 10)]
        self.line["ideas"][2]["mechanism_evidence_type"] = "per_operation_cost"
        self.put("campaigns/lines/research.json", self.line)
        selected = r.select_line(self.root, contributor="fixture-contributor")
        self.assertEqual(selected["selected"]["idea"], "second")
        self.assertEqual(selected["blocked"][0]["idea"], "third")
        self.assertFalse(selected["execution_authorized"])

    def test_value_record_is_bound_to_report_protocol_and_frozen_policy(self):
        self.campaign("c")
        contract = self.contract
        self.put("campaigns/c/research.json", {"line_contract": contract})
        value = decision(contract)
        protocol = self.root / "campaigns/c/protocol.json"
        value["identity"]["protocol_sha256"] = hashlib.sha256(protocol.read_bytes()).hexdigest()
        report = {"id": "eval-1", "candidate": "candidate", "candidate_commit": "c"*40,
                  "candidate_tree": "d"*40, "status": "FAST_PASS",
                  "analysis": {"combined_score": 1.1, "primary": ["latency"],
                               "metrics": {"latency": {"noise_relative": .03, "guard_pass": True}}}}
        self.put(value["identity"]["evaluation_report"], report)
        (self.root / "campaigns/c/report").mkdir()
        (self.root / "campaigns/c/report/review.md").write_text("review")
        value.update(r.performance_from_report(report))
        expected = copy.deepcopy(value["identity"])
        forged = copy.deepcopy(value)
        forged["performance"]["normalized_gain"] = 9
        with self.assertRaisesRegex(r.ResearchError, "authored performance"):
            r.record_value(self.root/"campaigns/c", "candidate", forged, contract, expected, self.root)
        record = r.record_value(self.root/"campaigns/c", "candidate", value, contract, expected, self.root)
        self.assertEqual(r.read_json(self.root/"campaigns/c/candidates/candidate/value.json"), record)
        self.assertEqual(r.record_value(self.root/"campaigns/c", "candidate", value, contract, expected, self.root), record)
        changed = copy.deepcopy(value)
        changed["reason"] = "Changed interpretation"
        with self.assertRaisesRegex(r.ResearchError, "record exists"):
            r.record_value(self.root/"campaigns/c", "candidate", changed, contract, expected, self.root)
        protocol.write_text(protocol.read_text()+" ")
        with self.assertRaisesRegex(r.ResearchError, "protocol bytes"):
            r.record_value(self.root/"campaigns/c", "candidate", value, contract, expected, self.root)


if __name__ == "__main__":
    unittest.main()
