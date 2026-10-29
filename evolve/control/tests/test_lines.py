# SPDX-License-Identifier: GPL-2.0-only
"""Campaign indexes retain outcomes and report only the recorded baseline."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("campaign_lines", Path(__file__).parents[1] / "lines.py")
lines = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lines)


class LineIndexTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.put("campaigns/hosts.json", {"hurricpc": {"hostnames": []}})
        self.campaign("first", "2026-10-22", "1" * 40)
        self.campaign("second", "2026-10-24", "2" * 40, origin={"campaign": "first", "candidate": "screened", "commit": "2" * 40, "evidence": {"kind": "fast_pass", "ledger_row": "row-7"}})
        self.put("campaigns/first/candidates/rejected.json", {"id": "rejected", "status": "closed", "reason": "Random tail regressed | retain result"})
        self.put("campaigns/second/candidates/screened.json", {"id": "screened", "status": "closed", "reason": "FAST_PASS; review pending", "commit": "9" * 40})
        self.put("campaigns/first/report/README.md", "Original findings\n")
        self.put("campaigns/second/report/REPORT.md", "Second findings\n")

    def put(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value, indent=2) + "\n")

    def campaign(self, name, opened, baseline, origin=None):
        self.put(f"campaigns/{name}/campaign.json", {"campaign": name, "status": "closed", "line": "xswap", "machine": "hurricpc", "opened": opened, "closed": opened, "baseline_from": origin, "budget": {"guest_attempts": 120, "wall_seconds": 64800, "probe_guest_attempts": 0, "approved_over_cap": None}})
        self.put(f"campaigns/{name}/protocol.json", {"campaign": name, "baseline_commit": baseline})

    def test_line_index(self):
        lines.generate(self.root)
        history = (self.root / "campaigns/lines/xswap.md").read_text()
        index = (self.root / "campaigns/README.md").read_text()
        self.assertLess(history.index("## first"), history.index("## second"))
        self.assertIn("Random tail regressed \\| retain result", history)
        self.assertIn("FAST_PASS; review pending", history)
        self.assertIn("row-7", history)
        self.assertIn("../first/report/README.md", history)
        self.assertIn("../second/report/REPORT.md", history)
        self.assertTrue(history.endswith("Current baseline: " + "2" * 40 + " (second)\n"))
        self.assertNotIn("Current baseline: " + "9" * 40, history)
        self.assertIn("| Campaign | Status | Line | Machine | Opened | Closed | Baseline |", index)
        for name in ("first", "second"):
            self.assertIn(f"[{name}]", index)
        paths = [self.root / name for name in lines.render(self.root)]
        before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in paths}
        lines.generate(self.root)
        self.assertEqual(before, {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in paths})

    def test_older_protocol_reference_and_controller_policy(self):
        path = self.root / "campaigns/first/campaign.json"
        record = json.loads(path.read_text())
        record["protocol_ref"] = "benchmark/legacy/protocol.json"
        self.put("campaigns/first/campaign.json", record)
        (self.root / "campaigns/first/protocol.json").unlink()
        self.put("benchmark/legacy/protocol.json", {"baseline_commit": "a" * 40})
        (self.root / "campaigns/second/protocol.json").unlink()
        self.put("campaigns/second/policy.json", {"seed_ref": "b" * 40})
        generated = lines.render(self.root)
        self.assertIn("a" * 40, generated["campaigns/lines/xswap.md"])
        self.assertTrue(generated["campaigns/lines/xswap.md"].endswith("Current baseline: " + "b" * 40 + " (second)\n"))
        self.assertFalse((self.root / "campaigns/README.md").exists())

    def test_invalid_candidate_preserves_existing_indexes(self):
        lines.generate(self.root)
        before = (self.root / "campaigns/README.md").read_bytes()
        self.put("campaigns/second/candidates/screened.json", {"id": "different"})
        with self.assertRaises(lines.store.CampaignError):
            lines.generate(self.root)
        self.assertEqual((self.root / "campaigns/README.md").read_bytes(), before)

    def test_line_index_lists_voided_calibration_attempts(self):
        attempt = "16fe9d24" + "ab" * 12
        receipt = "cd" * 16
        self.put(f"campaigns/first/ledger/ledger.json", [
            {"id": attempt, "action": "calibrate", "tier": "fast", "status": "INCOMPLETE"},
            {"schema_version": 1, "id": receipt, "action": "void-calibration", "tier": "fast",
             "status": "VOIDED", "attempt_id": attempt, "reason": "False watchdog STOP",
             "guests": [{"id": attempt + "-guest", "status": "PASS"}]},
        ])
        history = lines.render(self.root)["campaigns/lines/xswap.md"]
        self.assertLess(history.index("Voided calibration attempts:"), history.index("## second"))
        self.assertIn(attempt, history)
        self.assertIn(receipt, history)
        self.assertIn(attempt + "-guest PASS", history)
        self.assertIn("False watchdog STOP", history)
        self.assertEqual(history.count("Voided calibration attempts:"), 1)

    def test_broken_void_receipt_does_not_rewrite_indexes(self):
        lines.generate(self.root)
        before = (self.root / "campaigns/lines/xswap.md").read_bytes()
        self.put("campaigns/first/ledger/ledger.json", [
            {"id": "ab" * 16, "action": "void-calibration", "status": "VOIDED"},
        ])
        with self.assertRaises(lines.store.CampaignError):
            lines.generate(self.root)
        self.assertEqual((self.root / "campaigns/lines/xswap.md").read_bytes(), before)

    def test_unassigned_and_noncampaign_directories_are_ignored(self):
        self.put("campaigns/_unassigned/patches/one.patch", "patch\n")
        self.put("campaigns/lines/old.md", "kept until explicit cleanup\n")
        generated = lines.render(self.root)
        self.assertNotIn("_unassigned", generated["campaigns/README.md"])
        self.assertEqual(set(generated), {"campaigns/README.md", "campaigns/lines/xswap.md"})


if __name__ == "__main__":
    unittest.main()
