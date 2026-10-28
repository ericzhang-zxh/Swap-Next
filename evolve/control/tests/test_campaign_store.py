# SPDX-License-Identifier: GPL-2.0-only
"""The campaign directory store validates layout, cap, host and claim."""
import json
import multiprocessing
import os
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import campaign_store as cs

HOSTS = {"hurricpc": {"hostnames": ["Hurricpc"]}, "grok-cloud": {"hostnames": []}}

def record(**kw):
    r = {"campaign": "a", "status": "open", "line": "swap", "baseline_from": None,
         "machine": "hurricpc", "opened": "2026-10-27", "closed": None,
         "budget": {"guest_attempts": 10, "wall_seconds": 100,
                    "probe_guest_attempts": 0, "approved_over_cap": None}}
    r.update(kw)
    return r

def contend_claim(name, event, result):
    event.wait(5)
    try:
        cs.take_claim(name)
        result.put((name, True))
    except cs.CampaignError:
        result.put((name, False))


class StoreTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name) / "campaigns"
        self.root.mkdir()
        (self.root / "hosts.json").write_text(json.dumps(HOSTS))
        for p in (patch.object(cs, "CAMPAIGNS", self.root),
                  patch.object(cs, "HOSTS", self.root / "hosts.json"),
                  patch.object(cs, "GLOBAL_STOP", self.root / "STOP"),
                  patch.dict(os.environ, {"SWAP_NEXT_CLAIM": str(pathlib.Path(tmp.name) / "c/campaign.claim")})):
            p.start()
            self.addCleanup(p.stop)

    def test_name_validation(self):
        for bad in ("../x", "A", "a/b", "", "a" * 49):
            with self.assertRaises(cs.CampaignError):
                cs.campaign_dir(bad)
        self.assertEqual(cs.campaign_dir("a-1"), self.root / "a-1")

    def test_write_load_roundtrip(self):
        cs.write("a", record())
        text = (self.root / "a/campaign.json").read_text()
        self.assertTrue(text.endswith("}\n"))
        self.assertEqual(cs.load("a"), record())
        self.assertEqual(cs.require_open("a")["status"], "open")
        cs.write("a", record(status="closed", closed="2026-10-28"))
        with self.assertRaises(cs.CampaignError):
            cs.require_open("a")

    def test_load_rejects_bad_records(self):
        ev = {"campaign": "b", "candidate": "c1", "commit": "abc", "evidence": {"kind": "vibes"}}
        bad = [{k: v for k, v in record().items() if k != "line"},
               record(status="paused"), record(machine="elsewhere"),
               record(baseline_from=ev), record(line="Bad Line"),
               record(campaign="b")]
        for r in bad:
            d = self.root / "a"
            d.mkdir(exist_ok=True)
            (d / "campaign.json").write_text(json.dumps(r))
            with self.assertRaises(cs.CampaignError, msg=r):
                cs.load("a")
            with self.assertRaises(cs.CampaignError, msg=r):
                cs.write("a", r)
        ok = dict(ev, evidence={"kind": "fast_pass", "ledger_row": "r1"})
        cs.write("a", record(baseline_from=ok))
        ok["evidence"] = {"kind": "correctness_fix", "report": "r.md"}
        cs.write("a", record(baseline_from=ok))

    def test_budget_cap(self):
        b = lambda **kw: record(budget=dict(record()["budget"], **kw))
        self.assertEqual(cs.budget_errors(b(guest_attempts=120, wall_seconds=64800)), [])
        self.assertIn("guest_attempts", " ".join(cs.budget_errors(b(guest_attempts=121))))
        self.assertIn("wall_seconds", " ".join(cs.budget_errors(b(wall_seconds=64801))))
        self.assertEqual(cs.budget_errors(b(guest_attempts=121, wall_seconds=64801,
                                            approved_over_cap="2026-10-27 owner in session")), [])
        self.assertTrue(cs.budget_errors(b(guest_attempts=80, probe_guest_attempts=45)))
        self.assertEqual(cs.budget_errors(dict(b(guest_attempts=999), status="closed")), [])

    def test_current_machine(self):
        with patch.dict(os.environ, {"SWAP_NEXT_MACHINE": "hurricpc"}):
            self.assertEqual(cs.current_machine(), "hurricpc")
        with patch.dict(os.environ, {"SWAP_NEXT_MACHINE": "nope"}):
            with self.assertRaises(cs.CampaignError):
                cs.current_machine()
        env = {k: v for k, v in os.environ.items() if k != "SWAP_NEXT_MACHINE"}
        with patch.dict(os.environ, env, clear=True):
            with patch.object(cs.platform, "node", return_value="Hurricpc"):
                self.assertEqual(cs.current_machine(), "hurricpc")
            with patch.object(cs.platform, "node", return_value="stranger"):
                with self.assertRaisesRegex(cs.CampaignError, "SWAP_NEXT_MACHINE"):
                    cs.current_machine()

    def test_claim_lifecycle(self):
        self.assertIsNone(cs.read_claim())
        cs.take_claim("a")
        self.assertEqual(cs.read_claim(), "a")
        cs.take_claim("a")
        with self.assertRaises(cs.CampaignError):
            cs.take_claim("b")
        cs.write("a", record())
        with self.assertRaises(cs.CampaignError):
            cs.take_claim("b")
        cs.write("a", record(status="closed", closed="2026-10-28"))
        with self.assertLogs(level="WARNING"):
            cs.take_claim("b")
        self.assertEqual(cs.read_claim(), "b")
        with self.assertRaises(cs.CampaignError):
            cs.require_claim("c")
        cs.require_claim("b")
        with self.assertRaises(cs.CampaignError):
            cs.release_claim("c", "wrong")
        cs.release_claim("b", "done")
        self.assertIsNone(cs.read_claim())
        cs.take_claim("b")
        cs.release_claim(None, "crash")
        self.assertIsNone(cs.read_claim())
        self.assertIn("crash", cs.claim_path().with_suffix(".log").read_text())

    def test_concurrent_claims_have_one_owner(self):
        ctx = multiprocessing.get_context("fork")
        event, result = ctx.Event(), ctx.Queue()
        processes = [ctx.Process(target=contend_claim, args=(name, event, result)) for name in ("a", "b")]
        for proc in processes:
            proc.start()
        event.set()
        rows = [result.get(timeout=10) for _ in processes]
        for proc in processes:
            proc.join(10)
            self.assertEqual(proc.exitcode, 0)
        winners = [name for name, ok in rows if ok]
        self.assertEqual(len(winners), 1, rows)
        self.assertEqual(cs.read_claim(), winners[0])

    def test_execution_requires_machine_claim_and_both_stops(self):
        cs.write("a", record())
        cs.take_claim("a")
        with patch.dict(os.environ, {"SWAP_NEXT_MACHINE": "hurricpc"}):
            self.assertEqual(cs.require_execution("a")["campaign"], "a")
            for stop in (self.root / "STOP", self.root / "a/STOP"):
                stop.touch()
                with self.assertRaisesRegex(cs.CampaignError, "STOP"):
                    cs.require_execution("a")
                stop.unlink()
        with patch.dict(os.environ, {"SWAP_NEXT_MACHINE": "grok-cloud"}):
            with self.assertRaisesRegex(cs.CampaignError, "belongs to"):
                cs.require_execution("a")
        cs.release_claim("a", "test")
        with patch.dict(os.environ, {"SWAP_NEXT_MACHINE": "hurricpc"}):
            with self.assertRaisesRegex(cs.CampaignError, "claim"):
                cs.require_execution("a")
        cs.write("a", record(status="closed", closed="2026-10-27"))
        with self.assertRaisesRegex(cs.CampaignError, "closed"):
            cs.require_execution("a")

    def test_claim_transition_holds_machine_lock(self):
        # Fork before acquiring the lock, so the child inherits no lock descriptor.
        ctx = multiprocessing.get_context("fork")
        event, result = ctx.Event(), ctx.Queue()
        proc = ctx.Process(target=contend_claim, args=("a", event, result))
        proc.start()
        with cs.claim_lock():
            event.set()
            import queue
            with self.assertRaises(queue.Empty):
                result.get(timeout=0.1)
        self.assertEqual(result.get(timeout=10), ("a", True))
        proc.join(10)
        self.assertEqual(proc.exitcode, 0)

    def test_candidates_roundtrip(self):
        cs.write_candidate("a", {"id": "c1", "x": 1})
        self.assertEqual(cs.candidates("a"), {"c1": {"id": "c1", "x": 1}})
        (self.root / "a/candidates/c2.json").write_text(json.dumps({"id": "c3"}))
        with self.assertRaises(cs.CampaignError):
            cs.candidates("a")
        self.assertEqual(cs.candidates("missing"), {})

if __name__ == "__main__":
    unittest.main()
