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


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.bench = self.root / "bench"
        self.p = w.read(w.PROTOCOL)
        for name, value in [("STATE", self.state), ("BENCH", self.bench), ("ROOT", self.root)]:
            p = patch.object(w, name, value); p.start(); self.addCleanup(p.stop)

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
        w.save(self.bench / "evaluations/one/report.json", dict(row, candidate_commit="deadbeef", runs=[{"id": "reserved"}]))
        flow = w.Workflow(self.p)
        self.assertEqual(flow.ledger[0]["status"], "INTERRUPTED")
        self.assertEqual(flow.ledger[0]["candidate_commit"], "deadbeef")
        self.assertEqual(w.read(self.bench / "evaluations/one/report.json")["status"], "INTERRUPTED")

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

    def test_slow_gate_before_build_or_guest(self):
        flow = w.Workflow(self.p)
        with patch.object(w, "fingerprint", return_value="fp"), patch.object(flow, "candidate", return_value=("commit", {}, {})):
            row = flow.run("evaluate", "slow", "candidate")
        self.assertIn("slow requires", row["reason"])
        self.assertEqual(flow.budget["guests"], 0)
        self.assertEqual(flow.budget["builds"], 0)

    def test_stop_prevents_reservation(self):
        flow = w.Workflow(self.p)
        flow.stop.parent.mkdir(parents=True)
        flow.stop.touch()
        with self.assertRaisesRegex(RuntimeError, "STOP"):
            flow.reserve("guest")
        self.assertEqual(flow.budget["guests"], 0)


if __name__ == "__main__":
    unittest.main()
