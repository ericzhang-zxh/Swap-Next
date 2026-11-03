# SPDX-License-Identifier: GPL-2.0-only
"""Guest-free correctness-review veto and retained rev7 regression fixtures."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT / "evolve"))
sys.path.insert(0, str(PROJECT / "evolve/control"))
import reviews
import population
import controller

BASE, COMMIT, TREE = "a" * 40, "1" * 40, "b" * 40
METRIC = "swapin-disk.swapin_seq.mean_ns"


class ReviewTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="swap-next-reviews-")
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name)
        self.directory = self.project / "campaigns/demo"
        self.directory.mkdir(parents=True)
        self.write(self.directory / "campaign.json", {"status": "open", "baseline_from": None})
        self.subject = self.candidate("one", COMMIT, TREE)
        evidence = self.directory / "report/review.md"
        evidence.parent.mkdir()
        evidence.write_text("Synthetic correctness finding; not a kernel execution.\n")
        self.evidence = {"path": str(evidence.relative_to(self.project)),
                         "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()}

    @staticmethod
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def candidate(self, name, commit, tree, **extra):
        record = dict(id=name, candidate_commit=commit, source_tree=tree,
                      parent_commit=BASE, parent_candidate=None, **extra)
        self.write(self.directory / "candidates" / (name + ".json"), record)
        return record

    def payload(self, ident="review-one", subject=None, disposition="veto", resolves=None):
        subject = subject or self.subject
        return {"schema_version": 1, "id": ident, "campaign": "demo", "candidate": subject["id"],
                "candidate_commit": subject["candidate_commit"], "source_tree": subject["source_tree"],
                "reviewer": "fixture-reviewer", "disposition": disposition,
                "summary": "Review of the exact synthetic source tree.",
                "findings": [{"id": "sigbus-toctou", "summary": "Unresolved SIGBUS TOCTOU."}] if disposition == "veto" else [],
                "resolves": resolves or [], "evidence": [self.evidence]}

    def veto(self):
        return reviews.record(self.project, "demo", self.payload())

    def blocked(self, subject=None, campaign="demo"):
        return reviews.blockers(self.project, campaign, subject or self.subject)

    def test_immutable_idempotent_review_preserves_candidate_history(self):
        before = (self.directory / "candidates/one.json").read_bytes()
        saved = self.veto()
        self.assertEqual(self.veto(), saved)
        self.assertEqual((self.directory / "candidates/one.json").read_bytes(), before)
        self.assertEqual(self.blocked()[0]["finding"], "demo/review-one/sigbus-toctou")
        self.assertEqual(reviews.list_reviews(self.project, "demo"), [saved])
        changed = self.payload()
        changed["summary"] = "Rewritten finding"
        with self.assertRaisesRegex(reviews.ReviewError, "immutable"):
            reviews.record(self.project, "demo", changed)

    def test_plain_pass_and_prose_close_cannot_clear_veto(self):
        self.veto()
        reviews.record(self.project, "demo", self.payload("passed", disposition="pass"))
        closed = dict(self.subject, status="closed", reason="safe now, pass")
        self.write(self.directory / "candidates/one.json", closed)
        self.assertEqual(len(self.blocked()), 1)
        bad = self.payload("pass-resolve", disposition="pass", resolves=["demo/review-one/sigbus-toctou"])
        with self.assertRaisesRegex(reviews.ReviewError, "pass cannot"):
            reviews.record(self.project, "demo", bad)

    def test_resolve_names_existing_applicable_findings(self):
        self.veto()
        bad = self.payload("resolved", disposition="resolve", resolves=["demo/absent/sigbus-toctou"])
        with self.assertRaisesRegex(reviews.ReviewError, "existing applicable"):
            reviews.record(self.project, "demo", bad)
        other = self.candidate("other", "2" * 40, "c" * 40)
        bad = self.payload("unrelated", other, "resolve", ["demo/review-one/sigbus-toctou"])
        with self.assertRaisesRegex(reviews.ReviewError, "existing applicable"):
            reviews.record(self.project, "demo", bad)
        good = self.payload("resolved", disposition="resolve", resolves=["demo/review-one/sigbus-toctou"])
        reviews.record(self.project, "demo", good)
        self.assertEqual(self.blocked(), [])

    def test_resolution_is_exact_commit_and_tree(self):
        self.veto()
        reviews.record(self.project, "demo", self.payload("resolved", disposition="resolve",
                       resolves=["demo/review-one/sigbus-toctou"]))
        self.assertEqual(self.blocked(), [])
        self.assertTrue(self.blocked(dict(self.subject, candidate_commit="9" * 40)))
        self.assertTrue(self.blocked(dict(self.subject, source_tree="e" * 40)))

    def test_descendant_quarantine_requires_its_own_exact_review(self):
        child = dict(self.candidate("child", "2" * 40, "c" * 40),
                     parent_candidate="one", parent_commit=COMMIT)
        self.write(self.directory / "candidates/child.json", child)
        grandchild = dict(self.candidate("grandchild", "3" * 40, "d" * 40),
                          parent_candidate="child", parent_commit=child["candidate_commit"])
        self.write(self.directory / "candidates/grandchild.json", grandchild)
        self.veto()
        self.assertTrue(self.blocked(child)[0]["inherited"])
        self.assertTrue(self.blocked(grandchild))
        reviews.record(self.project, "demo", self.payload("child-fixed", child, "resolve",
                       ["demo/review-one/sigbus-toctou"]))
        self.assertEqual(self.blocked(child), [])
        self.assertTrue(self.blocked(self.subject))
        self.assertTrue(self.blocked(grandchild))
        self.assertEqual(self.blocked(self.candidate("unrelated", "4" * 40, "f" * 40)), [])

    def test_equivalent_tree_cannot_evade_veto_under_new_candidate_id(self):
        self.veto()
        equivalent = self.candidate("same-tree", "2" * 40, TREE)
        self.assertTrue(self.blocked(equivalent))

    def test_partial_resolution_retains_other_findings(self):
        review = self.payload()
        review["findings"].append({"id": "lifetime", "summary": "Unproven lifetime."})
        reviews.record(self.project, "demo", review)
        reviews.record(self.project, "demo", self.payload("resolved", disposition="resolve",
                       resolves=["demo/review-one/sigbus-toctou"]))
        self.assertEqual([item["finding"] for item in self.blocked()], ["demo/review-one/lifetime"])

    def test_baseline_inherits_review_across_campaigns(self):
        self.veto()
        successor = self.project / "campaigns/successor"
        self.write(successor / "campaign.json", {"status": "open",
            "baseline_from": {"campaign": "demo", "candidate": "one", "commit": COMMIT}})
        subject = {"id": "new", "candidate_commit": "2" * 40, "source_tree": "c" * 40}
        self.assertTrue(self.blocked(subject, "successor"))
        protocol = {"campaign": "successor", "baseline_commit": COMMIT}
        model = population.Population(successor, protocol, "fp")
        with self.assertRaisesRegex(ValueError, "baseline has unresolved"):
            model.next_brief([], "", {}, persist=False)

    def test_direct_baseline_commit_cannot_escape_a_recorded_veto(self):
        self.veto()
        self.assertTrue(reviews.blockers(self.project, "demo", {"id": None, "candidate_commit": COMMIT}))
        reviews.record(self.project, "demo", self.payload("fixed", disposition="resolve",
                       resolves=["demo/review-one/sigbus-toctou"]))
        self.assertFalse(reviews.blockers(self.project, "demo", {"id": None, "candidate_commit": COMMIT}))

    def test_exact_inherited_baseline_can_use_source_resolution(self):
        self.veto()
        successor = self.project / "campaigns/successor"
        self.write(successor / "campaign.json", {"status": "open",
            "baseline_from": {"campaign": "demo", "candidate": "one", "commit": COMMIT}})
        model = population.Population(successor, {"campaign": "successor", "baseline_commit": COMMIT}, "fp")
        self.assertFalse(model._baseline_parent()["parent_eligible"])
        reviews.record(self.project, "demo", self.payload("source-resolved", disposition="resolve",
                       resolves=["demo/review-one/sigbus-toctou"]))
        self.assertTrue(model._baseline_parent()["parent_eligible"])
        self.assertTrue(self.blocked({"id": "changed", "candidate_commit": "2" * 40,
                                    "source_tree": "c" * 40}, "successor"))

    def test_unhashed_missing_modified_and_escaping_evidence_are_refused(self):
        bad = self.payload()
        bad["evidence"][0] = dict(self.evidence, sha256="0" * 64)
        with self.assertRaisesRegex(reviews.ReviewError, "hash mismatch"):
            reviews.record(self.project, "demo", bad)
        self.assertFalse((self.directory / "reviews").exists())
        bad = self.payload()
        bad["evidence"] = [{"path": "../outside", "sha256": "0" * 64}]
        with self.assertRaisesRegex(reviews.ReviewError, "project-relative"):
            reviews.record(self.project, "demo", bad)
        self.veto()
        (self.project / self.evidence["path"]).write_text("Changed evidence\n")
        self.assertEqual(self.blocked()[0]["kind"], "review_integrity")

    def test_review_tampering_and_broken_lineage_fail_closed(self):
        self.veto()
        cyclic = dict(self.subject, parent_candidate="one", parent_commit=COMMIT)
        self.assertEqual(self.blocked(cyclic)[0]["kind"], "review_integrity")
        path = self.directory / "reviews/review-one.json"
        value = json.loads(path.read_text())
        value["findings"] = []
        self.write(path, value)
        self.assertEqual(self.blocked()[0]["kind"], "review_integrity")

    def test_closed_campaign_can_append_review_without_reopening(self):
        self.write(self.directory / "campaign.json", {"status": "closed", "closed": "2026-11-02"})
        before = (self.directory / "campaign.json").read_bytes()
        self.veto()
        self.assertEqual((self.directory / "campaign.json").read_bytes(), before)
        self.assertTrue(self.blocked())

    def test_missing_review_identity_cannot_be_recorded(self):
        bad = self.payload()
        bad["source_tree"] = "c" * 40
        with self.assertRaisesRegex(reviews.ReviewError, "differs from archived"):
            reviews.record(self.project, "demo", bad)

    def test_controller_record_checks_git_tree_before_recording(self):
        payload = self.payload()
        path = self.project / "input.json"
        self.write(path, payload)
        with patch.object(controller, "CAMPAIGN", "demo"), patch.object(controller, "PROJECT", self.project), \
             patch.object(controller, "STATE", self.directory), patch.object(controller, "registry", return_value={"one": self.subject}), \
             patch.object(controller, "git", side_effect=[COMMIT, "e" * 40]):
            with self.assertRaisesRegex(ValueError, "tree does not match"):
                controller.record_review("one", path)
        self.assertFalse((self.directory / "reviews").exists())

    def test_population_sampling_advancement_and_stale_brief_recheck(self):
        protocol = {"campaign": "demo", "baseline_commit": BASE}
        model = population.Population(self.directory, protocol, "fp")
        row = {"id": "one-fast", "action": "evaluate", "tier": "fast", "status": "FAST_PASS",
               "candidate": "one", "candidate_commit": COMMIT, "fingerprint": "fp",
               "analysis": {"status": "FAST_PASS", "combined_score": 1.5, "primary": [METRIC],
                            "metrics": {METRIC: {"guard_pass": True, "noise_relative": 0.1}}}}
        entry = model.record(row, self.subject, "+++ b/mm/swap_state.c\n+fixture\n", TREE)
        brief = model.next_brief([], "", {})
        before = model.path.read_bytes()
        self.assertTrue(entry["advancement"]["eligible"])
        self.veto()
        self.assertEqual(model.eligible_parents(), {})
        self.assertFalse(model._view(model._state()["entries"]["one"])["advancement"]["eligible"])
        self.assertFalse(population.advancement_evidence(row, project=self.project, campaign="demo",
                         candidate_record=self.subject)["eligible"])
        with self.assertRaisesRegex(ValueError, "no longer eligible"):
            model.validate_parent(brief["id"], COMMIT)
        self.assertEqual(model.next_brief([], "", {}, persist=False)["allowed_parents"], [BASE])
        self.assertEqual(model.path.read_bytes(), before)

    def test_retained_rev7_review_discrepancy_is_reconciled_without_rewriting_archive(self):
        name = "xswap-tcg-kbench-rev7-2026-10-29"
        source = PROJECT / "campaigns" / name
        if not source.is_dir():
            self.skipTest("retained rev7 fixture unavailable")
        target = self.project / "campaigns" / name
        for relative in ("campaign.json", "protocol.json", "archive/population.json",
                         "candidates/v2-c1-xs-sync-ra.json"):
            dest = target / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / relative, dest)
        shutil.copytree(source / "archive/briefs", target / "archive/briefs")
        origin = "xswap-p123-2026-10-23"
        for relative in ("campaign.json", "candidates/xs-desc-lifetime-v1.json"):
            dest = self.project / "campaigns" / origin / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PROJECT / "campaigns" / origin / relative, dest)
        data = json.loads((target / "archive/population.json").read_text())
        entry = data["entries"]["v2-c1-xs-sync-ra"]
        protocol = json.loads((target / "protocol.json").read_text())
        model = population.Population(target, protocol, entry["fingerprint"])
        self.assertIn(entry["id"], model.eligible_parents())
        before = {str(p.relative_to(target)): p.read_bytes() for p in target.rglob("*") if p.is_file()}
        payload = self.payload("rev7-review", entry)
        payload["campaign"] = name
        reviews.record(self.project, name, payload)
        self.assertNotIn(entry["id"], model.eligible_parents())
        sampled = [key for key, value in data["briefs"].items()
                   if entry["candidate_commit"] in value["allowed_parents"]]
        self.assertTrue(sampled)
        with self.assertRaisesRegex(ValueError, "no longer eligible"):
            model.validate_parent(sampled[0], entry["candidate_commit"])
        self.assertEqual(before, {key: (target / key).read_bytes() for key in before})


if __name__ == "__main__":
    unittest.main()
