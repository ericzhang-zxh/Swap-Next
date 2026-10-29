# SPDX-License-Identifier: GPL-2.0-only
"""A STOP-blocked calibration can be voided once. A noisy or invalid one cannot."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import campaign_store as store
import void_calibration as vc

REASON = "False campaign STOP from an external watchdog; no KVM or safety event."
ROOT = Path(__file__).resolve().parents[3]


def ident(prefix="16fe9d24"):
    return prefix + "ab" * 12


class VoidCalibrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.campaigns = self.root / "campaigns"
        self.name = "void-calibration-unit"
        self.campaign = self.campaigns / self.name
        (self.campaign / "ledger").mkdir(parents=True)
        (self.campaigns / "hosts.json").write_text(json.dumps({
            "grok-cloud": {"hostnames": []}, "hurricpc": {"hostnames": []}}))
        self.record = {"campaign": self.name, "status": "open", "line": "xswap", "baseline_from": None,
                       "machine": "grok-cloud", "opened": "2026-10-29", "closed": None,
                       "budget": {"guest_attempts": 96, "wall_seconds": 64800,
                                  "probe_guest_attempts": 24, "approved_over_cap": None}}
        self._write(self.campaign / "campaign.json", self.record)
        self.claim = self.root / "claim"
        self.claim.write_text(self.name + "\n")
        env = patch.dict(os.environ, {"SWAP_NEXT_CLAIM": str(self.claim), "SWAP_NEXT_MACHINE": "grok-cloud"})
        env.start()
        self.addCleanup(env.stop)
        paths = patch.multiple(store, PROJECT=self.root, CAMPAIGNS=self.campaigns,
                               HOSTS=self.campaigns / "hosts.json", GLOBAL_STOP=self.campaigns / "STOP")
        paths.start()
        self.addCleanup(paths.stop)
        self.assertIs(vc.store, store)

    def _write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value, indent=2) + "\n")

    def attempt(self, **extra):
        row = {"id": ident(), "action": "calibrate", "tier": "fast", "status": "INCOMPLETE",
               "reason": "STOP", "execution_started": True, "fingerprint": "fp",
               "runs": [{"id": ident() + "-0-a", "status": "PASS", "run_valid": True},
                        {"id": ident() + "-0-b", "status": "PASS", "run_valid": True}]}
        row.update(extra)
        return row

    def write_ledger(self, rows, budget=None):
        path = self.campaign / "ledger" / "ledger.json"
        self._write(path, rows)
        if budget is not None:
            self._write(self.campaign / "ledger" / "budget.json", budget)
        return path

    def test_stop_void_keeps_guests_budget_and_records_stop_files(self):
        probe = {"id": "86fc2f67" + "cd" * 12, "action": "calibrate", "tier": "probe",
                 "status": "CALIBRATED", "execution_started": True, "fingerprint": "fp",
                 "analysis": {"passed": True, "status": "CALIBRATED"}, "runs": [{"id": "probe-guest", "status": "PASS"}]}
        budget = {"guests": 7, "probe_guests": 9, "builds": 1}
        ledger_path = self.write_ledger([probe, self.attempt()], budget)
        report = self.campaign / "runs/evaluations" / ident() / "report.json"
        self._write(report, self.attempt())
        (self.campaign / "STOP").write_bytes(b"watchdog\n")
        (self.campaigns / "STOP").write_bytes(b"")
        budget_bytes, report_bytes, probe_runs = (self.campaign / "ledger" / "budget.json").read_bytes(), report.read_bytes(), probe["runs"]
        code = None
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = vc.main(["--campaign", self.name, "--attempt", "16fe9d24", "--reason", REASON])
        self.assertEqual(code, 0)
        printed = json.loads(stdout.getvalue())
        self.assertEqual(printed["status"], "VOIDED")
        self.assertEqual(printed["attempt_id"], ident())
        ledger = json.loads(ledger_path.read_text())
        self.assertEqual(ledger[0]["runs"], probe_runs)
        self.assertTrue(ledger[0]["execution_started"])
        self.assertEqual(ledger[0]["status"], "CALIBRATED")
        self.assertEqual(ledger[1]["runs"][0]["status"], "PASS")
        self.assertFalse(ledger[1]["execution_started"])
        self.assertEqual(ledger[1]["status"], "INCOMPLETE")
        self.assertEqual(ledger[1]["reason"], "STOP")
        receipt = ledger[2]
        self.assertEqual(receipt["action"], "void-calibration")
        self.assertEqual(receipt["status"], "VOIDED")
        self.assertEqual(receipt["attempt_id"], ident())
        self.assertEqual(receipt["reason"], REASON)
        self.assertEqual(receipt["attempt_reason"], "STOP")
        self.assertIsNone(receipt["preflight"])
        self.assertTrue(receipt["execution_started"])
        self.assertEqual([(g["id"], g["status"]) for g in receipt["guests"]],
                         [(ident() + "-0-a", "PASS"), (ident() + "-0-b", "PASS")])
        files = {item["role"]: item for item in receipt["stop_files"]}
        self.assertEqual(files["campaign"]["text"], "watchdog\n")
        self.assertEqual(files["campaign"]["sha256"], hashlib.sha256(b"watchdog\n").hexdigest())
        self.assertEqual(files["global"]["sha256"], hashlib.sha256(b"").hexdigest())
        self.assertTrue(files["campaign"]["path"].startswith("campaigns/"))
        self.assertNotIn(str(self.root), json.dumps(receipt))
        self.assertEqual((self.campaign / "ledger" / "budget.json").read_bytes(), budget_bytes)
        self.assertEqual(report.read_bytes(), report_bytes)
        self.assertTrue((self.campaign / "STOP").is_file())
        before = ledger_path.read_bytes()
        with self.assertRaisesRegex(vc.VoidError, "already voided"):
            vc.void_calibration(self.name, ident(), REASON)
        self.assertEqual(ledger_path.read_bytes(), before)

    def test_absent_stop_file_is_recorded_and_blocked_campaign_stop_is_eligible(self):
        self.write_ledger([self.attempt(status="BLOCKED", reason="BLOCKED: campaign: STOP", tier="probe")])
        receipt = vc.void_calibration(self.name, ident(), REASON)
        self.assertEqual(receipt["tier"], "probe")
        self.assertEqual(receipt["attempt_status"], "BLOCKED")
        self.assertTrue(all(item["exists"] is False for item in receipt["stop_files"]))

    def test_started_guest_and_missing_run_valid_can_be_voided(self):
        row = self.attempt(runs=[{"id": "still-starting", "status": "STARTED"},
                                 {"id": "passed-without-flag", "status": "PASS"}])
        self.write_ledger([row])
        receipt = vc.void_calibration(self.name, ident(), REASON)
        self.assertEqual([guest["status"] for guest in receipt["guests"]], ["STARTED", "PASS"])

    def refuse(self, row, pattern, token=None):
        path = self.write_ledger([row], {"guests": 7, "probe_guests": 9, "builds": 0})
        before, budget = path.read_bytes(), (self.campaign / "ledger" / "budget.json").read_bytes()
        with self.assertRaisesRegex(vc.VoidError, pattern):
            vc.void_calibration(self.name, token or row["id"], REASON)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual((self.campaign / "ledger" / "budget.json").read_bytes(), budget)
        self.assertTrue(json.loads(before)[0]["execution_started"])

    def test_noisy_scored_failed_and_invalid_calibrations_stay(self):
        noisy = self.attempt(status="CALIBRATION_NOISY", reason="spread",
                             analysis={"status": "CALIBRATION_NOISY", "passed": False})
        self.refuse(noisy, "noisy")
        forged = self.attempt(analysis={"status": "CALIBRATION_NOISY", "passed": False})
        self.refuse(forged, "noisy")
        scored = self.attempt(analysis={"passed": False})
        self.refuse(scored, "scored calibration cannot be voided")
        passed = self.attempt(status="CALIBRATED", reason="ok", analysis={"passed": True, "status": "CALIBRATED"})
        self.refuse(passed, "noisy|STOP-blocked")
        self.refuse(self.attempt(reason="calibration already attempted for this protocol; inspect retained evidence"),
                    "did not end because of STOP")
        self.refuse(self.attempt(reason="validity reruns exhausted: wall",
                                 runs=[{"id": "bad", "status": "INVALID", "run_valid": False}]),
                    "run_invalid")
        self.refuse(self.attempt(runs=[{"id": "bad", "status": "INVALID", "run_valid": False}]),
                    "run_invalid")
        self.refuse(self.attempt(runs=[{"id": "bad", "status": "FAIL", "run_valid": False}]),
                    "guest FAIL")
        self.refuse(self.attempt(runs=[{"id": "bad", "status": "PASS", "run_valid": False}]),
                    "run_invalid")
        self.refuse(self.attempt(action="evaluate", status="INCOMPLETE"), "not a calibration attempt")

    def test_cli_refusal_does_not_write(self):
        path = self.write_ledger([self.attempt(status="CALIBRATION_NOISY", reason="spread",
                                              analysis={"status": "CALIBRATION_NOISY", "passed": False})])
        before = path.read_bytes()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = vc.main(["--campaign", self.name, "--attempt", "16fe9d24", "--reason", REASON])
        self.assertEqual(code, 2)
        self.assertIn("noisy", err.getvalue())
        self.assertEqual(path.read_bytes(), before)

    def test_reason_claim_machine_and_ambiguous_prefix_fail_closed(self):
        self.write_ledger([self.attempt(), self.attempt(id="16fe9d24" + "cd" * 12)])
        with self.assertRaisesRegex(vc.VoidError, "ambiguous"):
            vc.void_calibration(self.name, "16fe9d24", REASON)
        self.write_ledger([self.attempt()])
        for bad in ("", "  ", "reason\n", "x" * 2001):
            with self.assertRaisesRegex(vc.VoidError, "reason"):
                vc.void_calibration(self.name, ident(), bad)
        self.record["status"] = "closed"
        self.record["closed"] = "2026-10-29"
        self._write(self.campaign / "campaign.json", self.record)
        with self.assertRaisesRegex(store.CampaignError, "closed"):
            vc.void_calibration(self.name, ident(), REASON)
        self.record.update(status="open", closed=None)
        self._write(self.campaign / "campaign.json", self.record)
        with patch.dict(os.environ, {"SWAP_NEXT_MACHINE": "hurricpc"}):
            with self.assertRaisesRegex(vc.VoidError, "belongs to"):
                vc.void_calibration(self.name, ident(), REASON)
        self.claim.unlink()
        with self.assertRaisesRegex(store.CampaignError, "claim"):
            vc.void_calibration(self.name, ident(), REASON)

    def ram_log(self, attempt_id, run_id, text="need 5120 MiB available host RAM\n"):
        path = self.campaign / "runs/evaluations" / attempt_id / (run_id + ".log")
        self._write(path, text)
        return path

    def test_prelaunch_host_ram_refusal_can_be_voided_once(self):
        attempt_id = ident("0c2cd749")
        run_id = attempt_id + "-0-swapin-disk-a"
        passed = attempt_id + "-0-swapin-disk-b"
        row = self.attempt(id=attempt_id, reason="missing run result", status="INCOMPLETE",
                           runs=[{"id": passed, "status": "PASS", "run_valid": True},
                                 {"id": run_id, "status": "STARTED"}])
        budget = {"guests": 1, "probe_guests": 9, "builds": 0}
        ledger_path = self.write_ledger([row], budget)
        log = self.ram_log(attempt_id, run_id)
        report = self.campaign / "runs/evaluations" / attempt_id / "report.json"
        self._write(report, row)
        budget_bytes, report_bytes = (self.campaign / "ledger" / "budget.json").read_bytes(), report.read_bytes()
        reason = ("Fast calibration 0c2cd749 reserved 0-swapin-disk-a then run.py refused before "
                  "QEMU: need 5120 MiB available host RAM. No guest booted.")
        receipt = vc.void_calibration(self.name, "0c2cd749", reason)
        self.assertEqual(receipt["attempt_id"], attempt_id)
        self.assertEqual(receipt["attempt_reason"], "missing run result")
        self.assertTrue(receipt["execution_started"])
        self.assertEqual(receipt["preflight"], [receipt["guests"][1]["preflight"]])
        proof = receipt["preflight"][0]
        self.assertEqual(proof["message"], "need 5120 MiB available host RAM")
        self.assertEqual(proof["sha256"], hashlib.sha256(log.read_bytes()).hexdigest())
        self.assertTrue(proof["log"].startswith("campaigns/"))
        self.assertFalse(proof["guest_directory"])
        self.assertNotIn(str(self.root), json.dumps(receipt))
        ledger = json.loads(ledger_path.read_text())
        self.assertFalse(ledger[0]["execution_started"])
        self.assertEqual(ledger[0]["status"], "INCOMPLETE")
        self.assertEqual(ledger[0]["runs"][1]["status"], "STARTED")
        self.assertEqual((self.campaign / "ledger" / "budget.json").read_bytes(), budget_bytes)
        self.assertEqual(report.read_bytes(), report_bytes)
        self.assertTrue(log.is_file())
        before = ledger_path.read_bytes()
        with self.assertRaisesRegex(vc.VoidError, "already voided"):
            vc.void_calibration(self.name, attempt_id, reason)
        self.assertEqual(ledger_path.read_bytes(), before)

    def test_disk_refusal_and_blocked_status_are_the_same_preflight_class(self):
        attempt_id = ident("0c2cd749")
        run_id = attempt_id + "-0-swapin-disk-a"
        self.write_ledger([self.attempt(id=attempt_id, status="BLOCKED", reason="missing run result",
                                        runs=[{"id": run_id, "status": "STARTED"}])])
        self.ram_log(attempt_id, run_id, "need 24 GiB free disk\n")
        receipt = vc.void_calibration(self.name, attempt_id, "Disk preflight refused before QEMU.")
        self.assertEqual(receipt["preflight"][0]["message"], "need 24 GiB free disk")
        self.assertEqual(receipt["attempt_status"], "BLOCKED")

    def test_prelaunch_proof_fails_closed(self):
        attempt_id = ident("0c2cd749")
        run_id = attempt_id + "-0-swapin-disk-a"
        reason = "missing run result"

        def plant(text=None, directory=False, **extra):
            row = self.attempt(id=attempt_id, reason=reason, runs=[{"id": run_id, "status": "STARTED", **extra}])
            path = self.write_ledger([row], {"guests": 1, "probe_guests": 0, "builds": 0})
            if text is not None:
                self.ram_log(attempt_id, run_id, text)
            if directory:
                (self.campaign / "runs/guests" / run_id).mkdir(parents=True)
            return path

        cases = (
            (dict(), "missing preflight log"),
            (dict(text="need 5120 MiB available host RAM\nqemu-system-x86_64\n"), "shows a boot"),
            (dict(text="need 5120 MiB available host RAM\nextra\n"), "not a single"),
            (dict(text="process failed\n"), "not a single"),
            (dict(text="need 5120 MiB available host RAM\n", directory=True), "launch setup began"),
            (dict(text="need 5120 MiB available host RAM\n", metrics={"swapin_seq.mean_ns": 1}), "measurement result"),
            (dict(text="need 5120 MiB available host RAM\n", result="runs/guests/x/result.json"), "measurement result"),
        )
        for kwargs, pattern in cases:
            path = plant(**kwargs)
            before = path.read_bytes()
            with self.assertRaisesRegex(vc.VoidError, pattern):
                vc.void_calibration(self.name, attempt_id, REASON)
            self.assertEqual(path.read_bytes(), before)
            guest = self.campaign / "runs/guests" / run_id
            if guest.exists():
                guest.rmdir()

        noisy = self.attempt(id=attempt_id, status="CALIBRATION_NOISY", reason="spread",
                             analysis={"status": "CALIBRATION_NOISY", "passed": False},
                             runs=[{"id": run_id, "status": "STARTED"}])
        path = self.write_ledger([noisy], {"guests": 1, "probe_guests": 0, "builds": 0})
        self.ram_log(attempt_id, run_id)
        before = path.read_bytes()
        with self.assertRaisesRegex(vc.VoidError, "noisy"):
            vc.void_calibration(self.name, attempt_id, REASON)
        self.assertEqual(path.read_bytes(), before)

        self.refuse(self.attempt(reason="missing run result"),
                    "did not end because of STOP")
        self.refuse(self.attempt(reason="missing run result",
                                 runs=[{"id": "booted", "status": "FAIL", "run_valid": False}]),
                    "guest FAIL")

    def test_void_command_stays_outside_the_calibration_fingerprint(self):
        workflow = (ROOT / "evolve/standard_workflow.py").read_text()
        self.assertNotIn("void_calibration", workflow)
        self.assertIn("Path(__file__)", workflow)
        fingerprint = workflow[workflow.index("def fingerprint"):workflow.index("def metric_spec")]
        self.assertIn("Path(__file__)", fingerprint)
        self.assertNotIn("host_preflight", fingerprint)
        self.assertIn("host_preflight", workflow)
        runner = (ROOT / "benchmark/swap-standard/run.py").read_text()
        self.assertIn("host_preflight.refusal_for", runner)
        self.assertNotIn("void_calibration", runner)
        for name in ("evidence.py", "validity.py"):
            self.assertNotIn("void_calibration", (ROOT / "benchmark/swap-standard" / name).read_text())
        for name in ("controller.py", "campaign_store.py", "guest_budget.py", "analysis.py"):
            self.assertNotIn("void_calibration", (ROOT / "evolve/control" / name).read_text())


if __name__ == "__main__":
    unittest.main()
