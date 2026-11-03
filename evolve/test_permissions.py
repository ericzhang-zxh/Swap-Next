# SPDX-License-Identifier: GPL-2.0-only
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from evolve import permissions as p

class ApprovalTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.campaign = self.root / "campaigns/test"
        (self.campaign / "approvals").mkdir(parents=True)
        (self.campaign / "protocol.json").write_text('{"campaign":"test"}')
        self.protocol = {"campaign": "test"}
        self.path = self.campaign / "approvals/slow-one.json"
        self.approval = {"schema_version": 1, "id": "slow-one", "campaign": "test",
            "action": "evaluate", "tier": "slow", "candidate_commit": "a" * 40,
            "candidate_tree": "b" * 40, "fingerprint": "fp", "max_executions": 1,
            "protocol_sha256": hashlib.sha256((self.campaign / "protocol.json").read_bytes()).hexdigest(),
            "owner_authorization": "Synthetic explicit owner request", "expires_unix": time.time() + 3600}
        self.path.write_text(json.dumps(self.approval))

    def permit(self, execution="one"):
        return p.validate(self.root, self.protocol, "slow-one", "evaluate", "a" * 40, "b" * 40, "fp", execution)

    def test_one_execution_consumes_once_before_any_retry(self):
        permit = self.permit()
        p.consume(self.root, permit)
        p.consume(self.root, permit)
        self.assertEqual(self.permit(), permit)
        with self.assertRaisesRegex(ValueError, "consumed"):
            self.permit("two")

    def test_expiry_drift_and_wrong_identity_fail(self):
        permit = self.permit()
        self.approval["expires_unix"] = 0
        self.path.write_text(json.dumps(self.approval))
        with self.assertRaisesRegex(ValueError, "expired"):
            self.permit()
        with self.assertRaisesRegex(ValueError, "changed or expired"):
            p.consume(self.root, permit)
        self.approval.update(expires_unix=time.time()+3600, candidate_tree="c" * 40)
        self.path.write_text(json.dumps(self.approval))
        with self.assertRaisesRegex(ValueError, "exact"):
            self.permit()
        self.assertFalse((self.campaign / "ledger/approval-uses/slow-one.json").exists())

    def test_missing_owner_reference_and_path_escape_fail(self):
        self.approval["owner_authorization"] = ""
        self.path.write_text(json.dumps(self.approval))
        with self.assertRaisesRegex(ValueError, "explicit"):
            self.permit()
        with self.assertRaisesRegex(ValueError, "approval ID"):
            p.validate(self.root, self.protocol, "../other", "evaluate", "a" * 40, "b" * 40, "fp", "one")

if __name__ == "__main__":
    unittest.main()
