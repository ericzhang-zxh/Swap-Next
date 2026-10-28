# SPDX-License-Identifier: GPL-2.0-only
"""Guest-free reservation, crash and concurrent capacity checks."""
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import campaign_store as cs
import guest_budget as gb


class GuestBudgetTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.campaigns = self.root / "campaigns"
        self.directory = self.campaigns / "demo"
        self.directory.mkdir(parents=True)
        (self.campaigns / "hosts.json").write_text(json.dumps({"hurricpc": {"hostnames": []}}))
        self.p = {"campaign": "demo", "budget": {"guest_attempts": 2, "probe_guest_attempts": 2, "wall_seconds": 3600}}
        (self.directory / "protocol.json").write_text(json.dumps(self.p))
        self.record = {"campaign": "demo", "line": "plain", "baseline_from": None,
                       "status": "open", "opened": "2026-10-27", "closed": None,
                       "machine": "hurricpc", "budget": dict(self.p["budget"], approved_over_cap=None)}
        self.claim = self.root / "claim"
        self.claim.write_text("demo\n")
        for key, value in (("PROJECT", self.root), ("CAMPAIGNS", self.campaigns),
                           ("HOSTS", self.campaigns / "hosts.json"), ("GLOBAL_STOP", self.campaigns / "STOP")):
            item = patch.object(cs, key, value); item.start(); self.addCleanup(item.stop)
        item = patch.dict(os.environ, SWAP_NEXT_MACHINE="hurricpc", SWAP_NEXT_CLAIM=str(self.claim))
        item.start(); self.addCleanup(item.stop)
        cs.write("demo", self.record)
        self.identity = {"build": "build-a", "backend": "disk", "mode": "plain", "workload": "swapin"}

    def reserve(self, name="run-a", **kw):
        return gb.reserve_guest("demo", name, **self.identity, **kw)

    def test_pools_count_before_launch_and_fail_without_overspending(self):
        self.reserve("a"); self.reserve("b")
        with self.assertRaisesRegex(cs.CampaignError, "budget"):
            self.reserve("c")
        self.reserve("p", pool="probe")
        budget = gb.read_budget("demo")
        self.assertEqual((budget["guests"], budget["probe_guests"]), (2, 1))
        self.assertEqual(gb.load(gb.ticket_path("demo", "a"))["status"], "RESERVED")

    def test_matching_ticket_consumes_once_and_duplicate_reservation_stays_spent(self):
        ticket = self.reserve()
        with self.assertRaisesRegex(cs.CampaignError, "already exists"):
            self.reserve()
        result = gb.consume_guest("demo", "run-a", ticket["reservation"], self.identity)
        self.assertEqual(result["status"], "STARTED")
        with self.assertRaisesRegex(cs.CampaignError, "consumed"):
            gb.consume_guest("demo", "run-a", ticket["reservation"], self.identity)
        self.assertEqual(gb.read_budget("demo")["guests"], 1)

    def test_ticket_identity_path_and_protocol_must_match(self):
        ticket = self.reserve()
        for identity, path in ((dict(self.identity, build="wrong"), ticket["reservation"]),
                               (self.identity, self.root / "outside.json")):
            with self.assertRaises(cs.CampaignError):
                gb.consume_guest("demo", "run-a", path, identity)
        self.p["measurement_note"] = "revised"
        (self.directory / "protocol.json").write_text(json.dumps(self.p))
        with self.assertRaisesRegex(cs.CampaignError, "protocol changed"):
            gb.consume_guest("demo", "run-a", ticket["reservation"], self.identity)
        self.assertEqual(gb.load(gb.ticket_path("demo", "run-a"))["status"], "RESERVED")

    def test_closed_or_unclaimed_refuses_before_runtime_files(self):
        cs.write("demo", dict(self.record, status="closed", closed="2026-10-27"))
        with self.assertRaisesRegex(cs.CampaignError, "closed"):
            self.reserve()
        self.assertFalse((self.directory / "ledger").exists())
        cs.write("demo", self.record); self.claim.unlink()
        with self.assertRaisesRegex(cs.CampaignError, "claim"):
            self.reserve()
        self.assertFalse((self.directory / "ledger").exists())

    def test_missing_or_reset_budget_cannot_reuse_retained_reservations(self):
        ticket = self.reserve()
        path = self.directory / "ledger/budget.json"
        original = path.read_bytes()
        path.unlink()
        with self.assertRaisesRegex(cs.CampaignError, "budget missing"):
            self.reserve("second")
        with self.assertRaisesRegex(cs.CampaignError, "budget missing"):
            gb.consume_guest("demo", "run-a", ticket["reservation"], self.identity)
        path.write_bytes(original)
        data = gb.load(path); data["guests"] = 0; gb.save(path, data)
        with self.assertRaisesRegex(cs.CampaignError, "below retained"):
            self.reserve("second")

    def test_deadline_and_stop_preserve_budget(self):
        gb.save(self.directory / "ledger/budget.json", {"created": time.time()-4000, "guests": 0, "builds": 0})
        with self.assertRaisesRegex(cs.CampaignError, "deadline"):
            self.reserve()
        self.assertEqual(gb.read_budget("demo")["guests"], 0)
        (self.directory / "STOP").touch()
        with self.assertRaisesRegex(cs.CampaignError, "STOP"):
            self.reserve()

    def test_crash_after_budget_write_does_not_reuse_capacity(self):
        original = gb.save
        def fail_ticket(path, value):
            if path.parent.name == "guest-reservations":
                raise OSError("simulated interrupted ticket")
            original(path, value)
        with patch.object(gb, "save", side_effect=fail_ticket):
            with self.assertRaises(OSError):
                self.reserve()
        self.assertEqual(gb.read_budget("demo")["guests"], 1)
        self.assertFalse(gb.ticket_path("demo", "run-a").exists())

    def test_concurrent_reservations_cannot_exceed_cap(self):
        ctx = multiprocessing.get_context("fork")
        queue = ctx.Queue()
        def attempt(number):
            try:
                self.reserve("parallel-" + str(number)); queue.put("reserved")
            except cs.CampaignError:
                queue.put("blocked")
        jobs = [ctx.Process(target=attempt, args=(i,)) for i in range(4)]
        for job in jobs: job.start()
        outcomes = [queue.get(timeout=5) for _ in jobs]
        for job in jobs:
            job.join(5)
            self.assertEqual(job.exitcode, 0)
        self.assertEqual(outcomes.count("reserved"), 2)
        self.assertEqual(gb.read_budget("demo")["guests"], 2)


if __name__ == "__main__":
    unittest.main()
