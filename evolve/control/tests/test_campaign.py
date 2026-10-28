# SPDX-License-Identifier: GPL-2.0-only
"""Campaign selection, campaign directories and the stop flags are controller boundaries."""
import contextlib
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import campaign_store as cs
import controller as c
from analysis import Invalid, load_json

BASE_POLICY = load_json(pathlib.Path(c.__file__).resolve().parent / "config/policy.json")
HOSTS = {"hurricpc": {"hostnames": ["Hurricpc"]}, "grok-cloud": {"hostnames": []}}


def sh(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args],
                                   stderr=subprocess.DEVNULL).decode().strip()


class Fixture(unittest.TestCase):
    """A temp project: campaigns/, a fake linux repo at tag `seed`, isolated claim and machine."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="swap-next-campaign-")
        self.addCleanup(tmp.cleanup)
        self.project = pathlib.Path(tmp.name)
        self.campaigns = self.project / "campaigns"
        self.campaigns.mkdir()
        (self.campaigns / "hosts.json").write_text(json.dumps(HOSTS))
        self.linux = self.project / "linux"
        (self.linux / "mm").mkdir(parents=True)
        (self.linux / "scripts").mkdir()
        (self.linux / "mm/swapfile.c").write_text("int swap_fixture;\n")
        (self.linux / "scripts/checkpatch.pl").write_text("exit 0;\n")
        sh(self.linux, "init", "-q")
        sh(self.linux, "config", "user.name", "T")
        sh(self.linux, "config", "user.email", "t@example.com")
        sh(self.linux, "add", "-A")
        sh(self.linux, "commit", "-qm", "seed")
        sh(self.linux, "tag", "seed")
        env = patch.dict(os.environ, {"SWAP_NEXT_CLAIM": str(self.project / "claim"),
                                      "SWAP_NEXT_MACHINE": "hurricpc"})
        env.start()
        self.addCleanup(env.stop)
        for mod, name, value in ((cs, "CAMPAIGNS", self.campaigns),
                                 (cs, "HOSTS", self.campaigns / "hosts.json"),
                                 (cs, "GLOBAL_STOP", self.campaigns / "STOP"),
                                 (c, "PROJECT", self.project), (c, "ROOT", self.linux),
                                 (c, "POLICY", c.POLICY), (c, "STATE", c.STATE),
                                 (c, "WORKTREES", c.WORKTREES), (c, "CAMPAIGN", None)):
            p = patch.object(mod, name, value)
            p.start()
            self.addCleanup(p.stop)

    def policy(self, name, **changes):
        d = self.campaigns / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "policy.json").write_text(json.dumps(dict(BASE_POLICY, seed_ref="seed", **changes)))

    def record(self, name, **changes):
        r = {"campaign": name, "status": "open", "line": "swap", "baseline_from": None,
             "machine": "hurricpc", "opened": "2026-10-27", "closed": None,
             "budget": {"guest_attempts": 10, "wall_seconds": 1000,
                        "probe_guest_attempts": 0, "approved_over_cap": None}}
        r.update(changes)
        return r

    def open_dir(self, name, **changes):
        self.policy(name)
        cs.write(name, self.record(name, **changes))

    def prep(self, name, **budget):
        """policy.json + protocol.json, ready for open-campaign."""
        self.policy(name)
        b = {"guest_attempts": 10, "wall_seconds": 1000}
        b.update(budget)
        (self.campaigns / name / "protocol.json").write_text(json.dumps({"budget": b}))

    def run_cli(self, *argv):
        out = io.StringIO()
        with patch.object(sys, "argv", ["controller.py", *argv]), contextlib.redirect_stdout(out):
            rc = c.main()
        return rc, json.loads(out.getvalue())

    def commit_change(self, root):
        (root / "mm/swapfile.c").write_text("int swap_fixture_updated;\n")
        sh(root, "commit", "-qam", "change")


class CampaignTests(Fixture):
    def test_invalid_or_unknown_campaign_does_not_mutate_paths(self):
        old = c.POLICY, c.STATE, c.WORKTREES, c.CAMPAIGN
        for name in ("../escape", "/absolute", "a/b", "missing-campaign-xyz"):
            with self.assertRaises(Invalid):
                c.configure_campaign(name)
            self.assertEqual((c.POLICY, c.STATE, c.WORKTREES, c.CAMPAIGN), old)

    def test_global_and_campaign_stop(self):
        self.open_dir("campaign")
        c.configure_campaign("campaign")
        c.active()
        for flag in (cs.GLOBAL_STOP, self.campaigns / "campaign/STOP"):
            flag.touch()
            with self.assertRaises(Invalid):
                c.active()
            flag.unlink()
        c.active()

    def test_unscoped_mode_checks_global_stop_only(self):
        self.assertFalse(c.stopped())
        cs.GLOBAL_STOP.touch()
        self.assertTrue(c.stopped())

    def test_campaign_paths(self):
        self.open_dir("demo")
        rc, new = self.run_cli("--campaign", "demo", "new", "cand-a", "--hypothesis", "a long enough hypothesis")
        self.assertEqual(rc, 0, new)
        record = json.loads((self.campaigns / "demo/candidates/cand-a.json").read_text())
        self.assertEqual(record["worktree"], "worktrees/demo/cand-a")
        task = (self.campaigns / "demo/candidates/cand-a/task.json").read_text()
        self.assertNotIn(str(self.project), task)
        self.assertNotIn(str(c.CONTROL), task)
        self.assertTrue((self.campaigns / "demo/ledger/events.jsonl").is_file())
        self.assertTrue((self.campaigns / "demo/.lock").is_file())
        self.commit_change(self.project / "worktrees/demo/cand-a")
        rc, check = self.run_cli("--campaign", "demo", "check", "cand-a")
        self.assertEqual(rc, 0, check)
        self.assertTrue((self.campaigns / "demo/patches/cand-a.patch").stat().st_size)
        self.assertTrue((self.campaigns / "demo/candidates/cand-a/static.json").is_file())

    def test_closed_campaign_refuses_work(self):
        self.open_dir("demo", status="closed", closed="2026-10-27")
        rc, out = self.run_cli("--campaign", "demo", "new", "cand-a", "--hypothesis", "a long enough hypothesis")
        self.assertEqual((rc, out["status"]), (2, "BLOCKED_OR_REJECTED"))
        self.assertIn("closed", out["error"])
        rc, out = self.run_cli("--campaign", "demo", "check", "cand-a")
        self.assertEqual(out["status"], "BLOCKED_OR_REJECTED")
        self.assertIn("closed", out["error"])


class CandidateCloseTests(Fixture):
    def test_candidate_close_gated_on_open_not_stop(self):
        self.open_dir("demo")
        self.run_cli("--campaign", "demo", "new", "cand-a", "--hypothesis", "a long enough hypothesis")
        cs.GLOBAL_STOP.touch()
        rc, out = self.run_cli("--campaign", "demo", "close", "cand-a", "--reason", "r")
        self.assertEqual(rc, 0, out)
        self.assertEqual(cs.candidates("demo")["cand-a"]["status"], "closed")

    def test_closed_campaign_refuses_candidate_close(self):
        self.open_dir("demo", status="closed", closed="2026-10-27")
        (self.campaigns / "demo/candidates").mkdir()
        cs.write_candidate("demo", {"id": "cand-a", "status": "active"})
        rc, out = self.run_cli("--campaign", "demo", "close", "cand-a", "--reason", "r")
        self.assertEqual((rc, out["status"]), (2, "BLOCKED_OR_REJECTED"))
        self.assertIn("closed", out["error"])
        self.assertEqual(cs.candidates("demo")["cand-a"]["status"], "active")
        self.assertFalse((self.campaigns / "demo/ledger/events.jsonl").exists())


class OpenCloseTests(Fixture):
    def open(self, name, *extra, machine="hurricpc"):
        return self.run_cli("--campaign", name, "open-campaign", "--line", "swap",
                            "--machine", machine, *extra)

    def test_open_writes_record_and_takes_claim(self):
        self.prep("one")
        rc, out = self.open("one")
        self.assertEqual(rc, 0, out)
        r = cs.load("one")
        self.assertEqual((r["status"], r["machine"], r["closed"], r["baseline_from"]),
                         ("open", "hurricpc", None, None))
        self.assertEqual(r["budget"]["probe_guest_attempts"], 0)
        self.assertEqual(cs.read_claim(), "one")

    def test_open_requires_protocol_and_no_existing_record(self):
        self.policy("one")
        self.assertEqual(self.open("one")[0], 2)
        self.prep("two")
        self.assertEqual(self.open("two")[0], 0)
        cs.release_claim(None, "test")
        rc, out = self.open("two")
        self.assertEqual(rc, 2)
        self.assertIn("campaign.json", out["error"])

    def test_open_refuses_policy_that_widens_base(self):
        self.prep("one")
        self.policy("one", allowed_modify=BASE_POLICY["allowed_modify"] + ["mm/memory.c"])
        self.assertIn("base", self.open("one")[1]["error"])
        self.policy("one", allowed_add=["tools/testing/selftests/mm/other_*.c"])
        self.assertIn("base", self.open("one")[1]["error"])
        self.policy("one", allowed_modify=BASE_POLICY["allowed_modify"][:2])
        self.assertEqual(self.open("one")[0], 0)

    def test_open_campaign_checks(self):
        self.prep("one")
        self.assertEqual(self.open("one")[0], 0)
        # a second open campaign on the same machine
        self.prep("two")
        rc, out = self.open("two")
        self.assertEqual(rc, 2)
        self.assertIn("one", out["error"])
        self.assertFalse((self.campaigns / "two/campaign.json").exists())
        cs.release_claim(None, "test")
        cs.write("one", dict(cs.load("one"), status="closed", closed="2026-10-27"))
        # budget over the cap
        self.prep("three", guest_attempts=121)
        rc, out = self.open("three")
        self.assertEqual(rc, 2)
        self.assertIn("cap", out["error"])
        rc, out = self.open("three", "--over-cap-approval", "owner said so")
        self.assertEqual(rc, 0, out)
        self.assertEqual(cs.load("three")["budget"]["approved_over_cap"], "owner said so")
        cs.write("three", dict(cs.load("three"), status="closed", closed="2026-10-27"))
        cs.release_claim(None, "test")
        # wrong machine
        self.prep("four")
        rc, out = self.open("four", machine="grok-cloud")
        self.assertEqual(rc, 2)
        self.assertIn("grok-cloud", out["error"])

    def test_open_baseline_evidence(self):
        self.open_dir("old", status="closed", closed="2026-10-26")
        ledger = self.campaigns / "old/ledger"
        ledger.mkdir()
        (ledger / "ledger.json").write_text(json.dumps([
            {"id": "row-ok", "candidate": "cand-a", "status": "FAST_PASS", "candidate_commit": "a" * 40},
            {"id": "row-bad", "candidate": "cand-b", "status": "FAST_REJECT", "candidate_commit": "b" * 40}]))
        self.prep("new1")
        base = "old:cand-b"
        rc, out = self.open("new1", "--baseline-from", base, "--evidence-row", "row-bad")
        self.assertEqual(rc, 2)
        self.assertIn("FAST_PASS", out["error"])
        rc, out = self.open("new1", "--baseline-from", "old:cand-z", "--evidence-row", "row-ok")
        self.assertEqual(rc, 2)
        self.assertFalse((self.campaigns / "new1/campaign.json").exists())
        sh(self.linux, "branch", "agents/cand-b", "seed")
        report = self.campaigns / "old/report.md"
        rc, out = self.open("new1", "--baseline-from", base, "--evidence-report", str(report))
        self.assertEqual(rc, 2)
        report.write_text("fix and evidence\n")
        rc, out = self.open("new1", "--baseline-from", base, "--evidence-report", str(report))
        self.assertEqual(rc, 0, out)
        r = cs.load("new1")["baseline_from"]
        self.assertEqual((r["campaign"], r["candidate"], r["evidence"]["kind"]),
                         ("old", "cand-b", "correctness_fix"))

    def test_open_fast_pass_row_records_commit(self):
        self.open_dir("old", status="closed", closed="2026-10-26")
        (self.campaigns / "old/ledger").mkdir()
        (self.campaigns / "old/ledger/ledger.json").write_text(json.dumps([
            {"id": "row-ok", "candidate": "cand-a", "status": "FAST_PASS", "candidate_commit": "a" * 40}]))
        self.prep("new1")
        rc, out = self.open("new1", "--baseline-from", "old:cand-a", "--evidence-row", "row-ok")
        self.assertEqual(rc, 0, out)
        b = cs.load("new1")["baseline_from"]
        self.assertEqual((b["commit"], b["evidence"]), ("a" * 40, {"kind": "fast_pass", "ledger_row": "row-ok"}))

    def test_close_campaign_requires_exported_patches(self):
        self.open_dir("demo")
        cs.take_claim("demo")
        self.run_cli("--campaign", "demo", "new", "cand-a", "--hypothesis", "a long enough hypothesis")
        self.commit_change(self.project / "worktrees/demo/cand-a")
        rc, out = self.run_cli("--campaign", "demo", "close-campaign", "--reason", "done")
        self.assertEqual(rc, 2)
        self.assertIn("cand-a", out["error"])
        self.assertEqual(cs.load("demo")["status"], "open")
        self.assertEqual(cs.read_claim(), "demo")
        self.run_cli("--campaign", "demo", "check", "cand-a")
        rc, out = self.run_cli("--campaign", "demo", "close-campaign", "--reason", "done")
        self.assertEqual(rc, 0, out)
        r = cs.load("demo")
        self.assertEqual(r["status"], "closed")
        self.assertTrue(r["closed"])
        cand = cs.candidates("demo")["cand-a"]
        self.assertEqual((cand["status"], cand["reason"]), ("closed", "done"))
        self.assertIsNone(cs.read_claim())

    def test_close_campaign_tolerates_released_claim(self):
        self.open_dir("demo")
        rc, out = self.run_cli("--campaign", "demo", "close-campaign", "--reason", "done")
        self.assertEqual(rc, 0, out)
        self.assertEqual(cs.load("demo")["status"], "closed")

    def test_release_claim_works_without_campaign(self):
        cs.take_claim("demo")
        rc, out = self.run_cli("release-claim", "--reason", "crashed")
        self.assertEqual(rc, 0, out)
        self.assertIsNone(cs.read_claim())


if __name__ == "__main__":
    unittest.main()
