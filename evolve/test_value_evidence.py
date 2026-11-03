# SPDX-License-Identifier: GPL-2.0-only
"""Guest-free retained-value fixtures created by the native record_value API."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from evolve import research
from evolve import value_evidence
from evolve.test_research import decision, line


class ValueEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        shutil.copytree(research.ROOT / "evolve/profiles", self.root / "evolve/profiles")
        self.contract = research.line_contract(line(), root=self.root)
        self.put("campaigns/c/research.json", {"line_contract": self.contract})
        self.protocol = self.put("campaigns/c/protocol.json", {"baseline_commit": "b" * 40})
        self.review = self.put("campaigns/c/report/review.md", {"review": "synthetic fixture"})
        self.decision = decision(self.contract)
        self.decision["identity"]["protocol_sha256"] = self.sha(self.protocol)
        self.report = {"id": "eval-1", "candidate": "candidate", "candidate_commit": "c" * 40,
                       "candidate_tree": "d" * 40, "status": "FAST_PASS",
                       "analysis": {"combined_score": 1.1, "primary": ["latency"],
                                    "metrics": {"latency": {"noise_relative": .03, "guard_pass": True}}}}
        self.report_path = self.put(self.decision["identity"]["evaluation_report"], self.report)
        self.decision.update(research.performance_from_report(self.report))
        self.record_path = self.root / "campaigns/c/candidates/candidate/value.json"
        self.expected = {key: self.decision["identity"][key] for key in
                         ("candidate_commit", "candidate_tree", "parent_commit", "baseline_commit", "evaluation_id")}

    def tearDown(self):
        self.temporary.cleanup()

    def put(self, path, value):
        path = self.root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + "\n")
        return path

    @staticmethod
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def save(self):
        return research.record_value(self.root / "campaigns/c", "candidate", self.decision,
                                     self.contract, self.decision["identity"], self.root)

    def validate(self, expected=None):
        return value_evidence.validate(self.root, "c", "candidate", self.expected if expected is None else expected)

    def test_native_record_revalidates_exact_identity_and_changes_no_files(self):
        saved = self.save()
        before = {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        validated = self.validate()
        self.assertEqual(validated, {key: saved[key] for key in ("assessment", "decision", "provenance")})
        self.assertEqual(validated["assessment"]["disposition"], "worthwhile-to-confirm")
        after = {str(path.relative_to(self.root)): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)
        self.assertFalse(validated["assessment"]["auto_promote"])
        self.assertEqual(self.validate({"candidate_tree": "d" * 40}), validated)

    def test_pending_review_is_retained_for_the_callers_policy(self):
        self.decision["review_status"] = "pending"
        self.save()
        self.assertEqual(self.validate()["assessment"]["disposition"], "review-blocked")

    def test_expected_identity_mismatch_and_unknown_field_fail(self):
        self.save()
        for key in self.expected:
            with self.subTest(key=key):
                expected = dict(self.expected, **{key: "different"})
                with self.assertRaisesRegex(ValueError, "identity mismatch"):
                    self.validate(expected)
        with self.assertRaisesRegex(ValueError, "known identity"):
            self.validate({"untrusted": "value"})

    def test_missing_or_corrupt_value_record_fails(self):
        with self.assertRaises(ValueError):
            self.validate()
        self.save()
        self.record_path.write_text("{broken")
        with self.assertRaises(ValueError):
            self.validate()

    def test_protocol_report_and_declared_evidence_hashes_are_rechecked(self):
        self.save()
        for path, message in ((self.protocol, "protocol bytes"), (self.report_path, "evaluation hash"),
                              (self.review, "evidence hash")):
            with self.subTest(path=path.name):
                original = path.read_bytes()
                path.write_bytes(original + b" ")
                with self.assertRaisesRegex(ValueError, message):
                    self.validate()
                path.write_bytes(original)

    def test_original_report_identity_cannot_change_even_with_updated_hash(self):
        saved = self.save()
        for key in ("id", "candidate", "candidate_commit", "candidate_tree"):
            with self.subTest(key=key):
                self.put(self.report_path, dict(self.report, **{key: "different"}))
                changed = copy.deepcopy(saved)
                changed["provenance"]["evaluation_sha256"] = self.sha(self.report_path)
                self.put(self.record_path, changed)
                with self.assertRaisesRegex(ValueError, "evaluation (source|identity) mismatch"):
                    self.validate()

    def test_authored_numbers_cannot_override_native_report(self):
        saved = self.save()
        changed = copy.deepcopy(saved)
        changed["decision"]["performance"]["normalized_gain"] = 9
        changed["assessment"] = research.assess_value(changed["decision"], self.contract)
        self.put(self.record_path, changed)
        with self.assertRaisesRegex(ValueError, "authored performance"):
            self.validate()

    def test_unknown_or_modified_assessment_is_rejected(self):
        saved = self.save()
        for change in ({"disposition": "automatically-accepted"}, {"disposition": "exploratory"},
                       {"reasons": ["unbound judgment"]}, {"auto_promote": True}):
            with self.subTest(change=change):
                changed = copy.deepcopy(saved)
                changed["assessment"].update(change)
                self.put(self.record_path, changed)
                with self.assertRaisesRegex(ValueError, "fresh assessment"):
                    self.validate()

    def test_unknown_decision_status_is_rejected(self):
        saved = self.save()
        changed = copy.deepcopy(saved)
        changed["decision"]["review_status"] = "auto-clear"
        self.put(self.record_path, changed)
        with self.assertRaisesRegex(ValueError, "unknown review status"):
            self.validate()

    def test_frozen_contract_and_profile_are_revalidated(self):
        self.save()
        changed = copy.deepcopy(self.contract)
        changed["value_policy"]["min_useful_effect"] = 0
        self.put("campaigns/c/research.json", {"line_contract": changed})
        with self.assertRaisesRegex(ValueError, "contract hash"):
            self.validate()
        self.put("campaigns/c/research.json", {"line_contract": self.contract})
        profile = self.root / "evolve/profiles/swap-core.json"
        changed_profile = research.read_json(profile)
        changed_profile["description"] += " changed"
        self.put(profile, changed_profile)
        with self.assertRaisesRegex(ValueError, "profile identity changed"):
            self.validate()

    def test_declared_hash_coverage_must_be_exact(self):
        saved = self.save()
        for hashes in ({}, {**saved["provenance"]["evidence_sha256"], "campaigns/c/protocol.json": self.sha(self.protocol)}):
            changed = copy.deepcopy(saved)
            changed["provenance"]["evidence_sha256"] = hashes
            self.put(self.record_path, changed)
            with self.assertRaisesRegex(ValueError, "exactly the declared"):
                self.validate()

    def test_evidence_symlink_and_cross_campaign_report_are_rejected(self):
        saved = self.save()
        copied = self.root / "copied-review.md"
        copied.write_bytes(self.review.read_bytes())
        self.review.unlink()
        self.review.symlink_to(copied)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.validate()
        self.review.unlink()
        self.review.write_bytes(copied.read_bytes())
        changed = copy.deepcopy(saved)
        changed["decision"]["identity"]["evaluation_report"] = "campaigns/other/report.json"
        self.put("campaigns/other/report.json", self.report)
        changed["assessment"] = research.assess_value(changed["decision"], self.contract)
        self.put(self.record_path, changed)
        with self.assertRaisesRegex(ValueError, "outside campaign"):
            self.validate()


if __name__ == "__main__":
    unittest.main()
