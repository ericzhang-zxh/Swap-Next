# SPDX-License-Identifier: GPL-2.0-only
"""Structural review evidence tests; fixtures are not kernel runtime evidence."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from evolve import reviews
# The production workflow uses script-local imports.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from evolve import mechanisms

C, T = "b" * 40, "c" * 40


class MechanismTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.campaign = self.root / "campaigns/campaign"
        self.campaign.mkdir(parents=True)
        self.protocol = {"campaign": "campaign", "mechanism_evidence_types": ["counter_shift", "reviewed_structure"]}
        (self.campaign / "protocol.json").write_text(json.dumps(self.protocol))
        self.declaration = {"kind": "reviewed_structure", "claim": "Remove duplicated state ownership.",
                            "falsifier": "The removed state represents an independent condition."}
        self.record = {"id": "candidate", "candidate_commit": C, "source_tree": T, "mechanism": self.declaration}
        (self.campaign / "candidates/candidate").mkdir(parents=True)
        (self.campaign / "candidates/candidate.json").write_text(json.dumps(self.record))
        report = self.campaign / "report.md"
        report.write_text("Synthetic exact-tree structural review.")
        payload = {"schema_version": 1, "id": "review-pass", "campaign": "campaign", "candidate": "candidate",
                   "candidate_commit": C, "source_tree": T, "reviewer": "fixture", "disposition": "pass",
                   "summary": "State is redundant in the fixture.", "findings": [], "resolves": [],
                   "evidence": [{"path": "campaigns/campaign/report.md",
                                 "sha256": hashlib.sha256(report.read_bytes()).hexdigest()}]}
        self.payload = payload
        self.review = reviews.record(self.root, "campaign", payload)
        self.proof = {"schema_version": 1, **self.declaration, "candidate_commit": C, "source_tree": T,
                      "protocol_sha256": hashlib.sha256((self.campaign / "protocol.json").read_bytes()).hexdigest(),
                      "review_id": self.review["id"], "review_record_sha256": self.review["record_sha256"]}
        self.save()

    def save(self):
        (self.campaign / "candidates/candidate/mechanism.json").write_text(json.dumps(self.proof))

    def test_clear_exact_tree_structural_review_is_bound(self):
        result = mechanisms.validate(self.root, self.protocol, self.record, C, T)
        self.assertEqual(result["kind"], "reviewed_structure")
        self.assertFalse(result["performance_accepted"])

    def test_old_protocol_cannot_bypass_directional_probe(self):
        with self.assertRaisesRegex(ValueError, "does not admit"):
            mechanisms.validate(self.root, {"campaign": "campaign"}, self.record, C, T)

    def test_changed_tree_or_proof_or_review_refuses(self):
        with self.assertRaisesRegex(ValueError, "identity"):
            mechanisms.validate(self.root, self.protocol, self.record, C, "d" * 40)
        self.proof["review_record_sha256"] = "0" * 64
        self.save()
        with self.assertRaisesRegex(ValueError, "exact-tree"):
            mechanisms.validate(self.root, self.protocol, self.record, C, T)

    def test_review_veto_dominates_structural_claim(self):
        payload = dict(self.payload, id="later-veto", disposition="veto",
                       findings=[{"id": "ownership", "summary": "Ownership is not equivalent."}])
        reviews.record(self.root, "campaign", payload)
        with self.assertRaisesRegex(ValueError, "unresolved"):
            mechanisms.validate(self.root, self.protocol, self.record, C, T)

    def test_counter_route_does_not_invent_structural_proof(self):
        self.assertIsNone(mechanisms.validate(self.root, self.protocol,
                          {"mechanism": "disk:swapin_vmstat_delta.swap_ra:up"}, C, T))


if __name__ == "__main__":
    unittest.main()
