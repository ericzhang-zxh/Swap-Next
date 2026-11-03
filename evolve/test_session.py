# SPDX-License-Identifier: GPL-2.0-only
"""Guest-free public Session API fixtures; all runtime effects are synthetic."""
import copy
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from evolve import session as s
from evolve.test_research import line, decision
from evolve.test_delivery import explain, visual

REPO = Path(__file__).resolve().parents[1]
CAMPAIGN = "test-line"


class SessionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="swap-next-session-fixture-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.directory = self.root / "campaigns" / CAMPAIGN
        shutil.copytree(REPO / "evolve/profiles", self.root / "evolve/profiles")
        for rel in ("evolve/control/campaign_store.py", "benchmark/swap-standard/validity.py",
                    ".agents/skills/explaining-campaign-results/scripts/build_page.py"):
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / rel, target)
        self.linux = self.root / "linux"
        self.linux.mkdir()
        self.git(self.linux, "init", "-q")
        self.git(self.linux, "config", "user.name", "Session Fixture")
        self.git(self.linux, "config", "user.email", "fixture@example.invalid")
        (self.linux / "fixture.txt").write_text("parent fixture\n")
        self.git(self.linux, "add", "fixture.txt")
        self.git(self.linux, "commit", "-qm", "Synthetic parent")
        self.base = self.git(self.linux, "rev-parse", "HEAD")
        self.worktree = self.root / "worktrees/one"
        self.git(self.linux, "worktree", "add", "-qb", "one", str(self.worktree))
        (self.worktree / "fixture.txt").write_text("candidate fixture\n")
        self.git(self.worktree, "commit", "-qam", "Synthetic candidate")
        self.commit = self.git(self.worktree, "rev-parse", "HEAD")
        self.tree = self.git(self.worktree, "rev-parse", "HEAD^{tree}")
        self.protocol = s.read(REPO / "campaigns/xswap-tcg-kbench-2026-10-29/protocol.json")
        self.protocol.update(campaign=CAMPAIGN, template_only=False)
        self.protocol["budget"].update(guest_attempts=90, probe_guest_attempts=30, build_attempts=10)
        self.agenda = line()
        self.agenda.update(baseline_commit=self.protocol["baseline_commit"], anchor_commit=self.protocol["baseline_commit"])
        s.write(self.root / "campaigns/lines/research.json", self.agenda)
        self.policy = {"seed_ref": self.base, "allowed_modify": ["mm/swap_state.c"], "allowed_add": []}
        s.write(self.directory / "protocol.json", self.protocol)
        s.write(self.directory / "policy.json", self.policy)
        s.write(self.root / "campaigns/hosts.json", {"fixture": {"hostnames": []}})
        self.claim = self.root / "claim"
        env = patch.dict(os.environ, {"SWAP_NEXT_CONTRIBUTOR": "fixture-contributor", "SWAP_NEXT_MACHINE": "fixture", "SWAP_NEXT_CLAIM": str(self.claim)})
        env.start()
        self.addCleanup(env.stop)
        self.driver = s.Session(CAMPAIGN, self.root, executor=self.execute, clock=lambda: 1000)
        self.brief, self.correctness, self.calls, self.counter = None, {"passed": False}, [], 0
        for patcher in (
            patch.object(self.driver, "_runtime", return_value=([], "fixture-fingerprint")),
            patch.object(self.driver, "_brief", side_effect=lambda *_: self.brief),
            patch.object(self.driver, "_correctness", side_effect=lambda *_: copy.deepcopy(self.correctness)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    def git(root, *args):
        return subprocess.check_output(["git", "-C", str(root), *args], text=True,
                                       stderr=subprocess.STDOUT).strip()

    def campaign_record(self, status="open"):
        s.write(self.directory / "campaign.json", {"campaign": CAMPAIGN, "status": status,
            "line": "research", "machine": "fixture", "baseline_from": None,
            "opened": "fixture", "closed": "fixture" if status == "closed" else None,
            "budget": dict(self.protocol["budget"], approved_over_cap=None)})

    def write_row(self, row):
        path = self.directory / "ledger/ledger.json"
        rows = s.read(path) if path.exists() else []
        rows.append(row)
        s.write(path, rows)
        s.write(self.directory / "runs/evaluations" / row["id"] / "report.json", row)

    def execute(self, argv, log, token, on_spawn):
        # Model framework effects; never launch the generated argv.
        item = self.driver.state()["current_action"]
        command, params = item["command"], item["parameters"]
        self.calls.append(command)
        if command == "open":
            self.campaign_record()
            self.claim.write_text(CAMPAIGN + "\n")
            s.write(self.directory / "ledger/budget.json",
                    {"created": 1000, "guests": 0, "probe_guests": 0, "builds": 0})
        elif command == "brief":
            self.brief = {"id": "brief-one", "sha256": "a" * 64, "allowed_parents": [self.base]}
        elif command == "new":
            s.write(self.directory / "candidates/one.json", {"id": "one", "status": "active",
                "worktree": "worktrees/one", "hypothesis": "Avoid repeated synthetic work.",
                "parent_commit": self.base, "parent_candidate": None,
                "candidate_commit": self.commit, "source_tree": self.tree,
                "mechanism": {"case": "meta-disk", "counter": "metadata", "direction": "down"}})
        elif command == "check":
            s.write(self.directory / "candidates/one/static.json",
                    {"status": "SCOPE_PASS", "candidate_commit": self.commit})
        elif command in {"calibrate", "evaluate"}:
            self.counter += 1
            tier = params["tier"]
            ident = command + "-" + tier + "-" + str(self.counter)
            row = {"id": ident, "action": command, "tier": tier, "fingerprint": "fixture-fingerprint",
                   "finished": 1000, "status": "CALIBRATED" if command == "calibrate" else
                   ("PROBE_PASS" if tier == "probe" else "FAST_PASS"), "analysis": {"passed": True}}
            if command == "evaluate":
                row.update(candidate="one", candidate_commit=self.commit, candidate_tree=self.tree)
                if tier == "fast":
                    row["analysis"] = {"primary": ["disk.swapin_seq.mean_ns"], "combined_score": 1.1,
                        "metrics": {"disk.swapin_seq.mean_ns": {"guard_pass": True, "noise_relative": .03}}}
            self.write_row(row)
            if command == "calibrate":
                s.write(self.directory / ("ledger/calibration-" + tier + ".json"), row)
            budget = s.read(self.directory / "ledger/budget.json")
            budget["probe_guests" if tier == "probe" else "guests"] += 1
            s.write(self.directory / "ledger/budget.json", budget)
            s.write(self.directory / "ledger/guest-reservations" / (ident + ".json"),
                    {"campaign": CAMPAIGN, "pool": tier, "identity": {"synthetic": True}})
        elif command == "export":
            target = self.directory / "patches" / "one.patch"
            target.parent.mkdir(exist_ok=True)
            target.write_text("Synthetic retained patch fixture.\n")
        elif command == "close-candidate":
            record = s.read(self.directory / "candidates/one.json")
            record.update(status="closed", reason=params["close_reason"])
            s.write(self.directory / "candidates/one.json", record)
        elif command == "close-campaign":
            self.campaign_record("closed")
            self.claim.unlink()
        elif command == "render":
            s.delivery.render(self.root, CAMPAIGN)
        elif command == "verify-live":
            body = (self.directory / "report/explainer.html").read_bytes()
            run = {"head_sha": params["commit"], "status": "completed", "conclusion": "success",
                   "path": ".github/workflows/pages.yml"}
            with patch.object(s.delivery, "_git", return_value=body):
                s.delivery.verify_live(self.root, CAMPAIGN, params["commit"], params["run_id"],
                    fetch=lambda url: body if url.endswith("/test-line/") else b'<a href="test-line/">fixture</a>',
                    github=lambda _: run)
        else:
            self.fail("Unmodeled runtime command: " + command)
        return 0

    def step(self, stage):
        item = self.driver.next()
        self.assertEqual(item["stage"], stage, item)
        result = self.driver.execute(item["id"])
        self.assertTrue(result["executed"])
        self.assertEqual(result["receipt"]["status"], "completed", result)
        return result["next"]

    def prepare_candidate(self):
        self.assertEqual(self.driver.start(line="research", idea="first", machine="fixture")["stage"], "open")
        self.step("open")
        self.step("brief")
        item = self.driver.next()
        self.assertEqual(item["stage"], "propose")
        self.driver.decide(item["id"], {"kind": "propose", "reason": "Test the first bounded hypothesis.",
            "candidate": "one", "parent": self.base, "hypothesis": "Avoid repeated synthetic work.",
            "mechanism": "meta-disk:metadata:down"})
        self.step("create_candidate")
        self.step("check")

    def review(self, ident, disposition="pass", resolves=None):
        evidence = self.directory / "report/review.md"
        evidence.parent.mkdir(exist_ok=True)
        evidence.write_text("Synthetic independent review; no kernel efficacy claim.\n")
        return s.reviews.record(self.root, CAMPAIGN, {"schema_version": 1, "id": ident, "campaign": CAMPAIGN,
            "candidate": "one", "candidate_commit": self.commit, "source_tree": self.tree,
            "reviewer": "fixture-reviewer", "disposition": disposition, "summary": "Review the exact fixture tree.",
            "findings": [{"id": "lifetime", "summary": "Fixture lifetime remains unresolved."}] if disposition == "veto" else [],
            "resolves": resolves or [], "evidence": [{"path": str(evidence.relative_to(self.root)), "sha256": s.sha(evidence)}]})

    def to_probe(self):
        self.prepare_candidate()
        self.review("pass-one")
        self.assertEqual(self.driver.next()["stage"], "correctness")
        s.write(self.root / "proof.json", {"synthetic": True})
        self.correctness = {"passed": True, "path": "proof.json"}
        self.step("calibrate_probe")

    def fast_result(self):
        self.to_probe()
        self.step("evaluate_probe")
        item = self.driver.next()
        payload = {"kind": "fast_selection", "disposition": "screen", "reason": "Synthetic mechanism passed."}
        payload.update({key: item["identity"][key] for key in ("candidate_commit", "source_tree", "probe_id")})
        self.driver.decide(item["id"], payload)
        self.step("calibrate_fast")
        self.step("evaluate_fast")

    def value_decision(self):
        snap = self.driver.snapshot()
        contract = s.read(self.directory / "research.json")["line_contract"]
        value = decision(contract)
        value["identity"] = snap["candidate"]["value_identity"]
        value.update(s.research.performance_from_report(snap["candidate"]["fast"]))
        value["evidence"] = [str((self.directory / "report/review.md").relative_to(self.root))]
        return value

    def complete_delivery(self):
        self.assertEqual(self.driver.next()["stage"], "explain")
        story = explain(self.root)
        for section in story["sections"]:
            section["evidence"] = ["campaigns/test-line/campaign.json"]
        s.write(self.directory / "report/story.json", story)
        self.step("render")
        item = self.driver.next()
        self.assertEqual(item["stage"], "visual_check")
        self.driver.decide(item["id"], {"kind": "visual", "evidence": visual(self.root, item["identity"]["artifact_sha256"])})
        item = self.driver.next()
        self.assertEqual(item["stage"], "publish")
        self.driver.decide(item["id"], {"kind": "publication", "reason": "Synthetic network adapter only.",
                                      "commit": "f" * 40, "run_id": "123"})
        self.step("verify_live")
        self.assertEqual(self.driver.resume()["stage"], "complete")

    def receipt(self, item, **extra):
        value = {"action_id": item["id"], "operation_key": item["operation_key"],
                 "command": item["command"], "parameters": item["parameters"], "identity": item["identity"],
                 "token": "fixture-token", "status": "running", "process": None, "launcher": None, "log": "fixture.log"}
        value.update(extra)
        current = self.driver.state()
        current["executions"].append(value)
        s.write(self.driver.path, current)
        return value

    def test_delivery_resume_retries_only_failed_verification(self):
        self.prepare_candidate()
        item = self.driver.next()
        self.driver.decide(item["id"], {"kind": "stop", "reason": "Close fixture before delivery."})
        self.step("export")
        self.step("close_candidate")
        self.step("close_campaign")
        original = self.driver.executor
        failed = []
        def transient(argv, log, token, on_spawn):
            if "verify-live" in argv and not failed:
                failed.append(True)
                log.write_text("Synthetic transient service failure")
                return 1
            return original(argv, log, token, on_spawn)
        self.driver.executor = transient
        story = explain(self.root)
        for section in story["sections"]:
            section["evidence"] = ["campaigns/test-line/campaign.json"]
        s.write(self.directory / "report/story.json", story)
        self.step("render")
        item = self.driver.next()
        self.driver.decide(item["id"], {"kind": "visual", "evidence": visual(self.root, item["identity"]["artifact_sha256"])})
        item = self.driver.next()
        self.driver.decide(item["id"], {"kind": "publication", "reason": "Synthetic deployment.", "commit": "f" * 40, "run_id": "123"})
        before = (self.directory / "ledger/budget.json").read_bytes()
        first = self.driver.next()
        self.assertEqual(self.driver.execute(first["id"])["next"]["stage"], "delivery_blocked")
        self.assertFalse(self.driver.execute(first["id"])["executed"])
        retry = self.driver.resume()
        self.assertEqual(retry["stage"], "verify_live")
        self.assertNotEqual(first["id"], retry["id"])
        self.assertEqual(self.driver.execute(retry["id"])["next"]["stage"], "complete")
        self.assertEqual(before, (self.directory / "ledger/budget.json").read_bytes())
        self.assertEqual([x["status"] for x in self.driver.state()["executions"] if x["command"] == "verify-live"], ["failed", "completed"])

    def test_comparison_commands_route_to_supported_runtime_actions(self):
        for command, runtime_action in (("compare", "evaluate"), ("compare-calibrate", "calibrate")):
            item = s.action(command, "command", command=command, tier="fast", comparison="plan", contrast="upstream-control")
            argv = self.driver._argv(item)
            self.assertEqual(argv[3], runtime_action)
            self.assertIn("--comparison", argv)

    def test_complete_path_uses_actual_session_and_delivery_artifacts(self):
        self.fast_result()
        self.assertEqual(self.driver.next()["stage"], "value")
        value = self.value_decision()
        stored = self.driver.value("one", value)
        self.assertEqual(stored["assessment"]["disposition"], "worthwhile-to-confirm")
        self.assertEqual(stored, self.driver.value("one", value))
        self.step("export")
        self.step("close_candidate")
        item = self.driver.next()
        self.assertEqual(item["stage"], "next_idea")
        self.driver.decide(item["id"], {"kind": "stop", "reason": "Synthetic objective complete."})
        self.step("close_campaign")
        self.assertFalse(self.claim.exists())
        self.complete_delivery()
        self.assertEqual(self.calls.count("evaluate"), 2)
        self.assertEqual(s.read(self.directory / "ledger/budget.json")["guests"], 2)
        self.assertFalse(s.read(self.directory / "ledger/session-closeout.json")["auto_promote"])

    def test_stop_deadline_budget_export_close_release_and_deliver(self):
        for guard in ("stop", "deadline", "budget"):
            with self.subTest(guard=guard):
                case = SessionTests("runTest")
                case.setUp()
                try:
                    case.prepare_candidate()
                    budget = s.read(case.directory / "ledger/budget.json")
                    if guard == "stop":
                        (case.directory / "STOP").write_text("Preserve STOP\n")
                    elif guard == "deadline":
                        budget["created"] = -case.protocol["budget"]["wall_seconds"]
                    else:
                        budget.update(guests=case.protocol["budget"]["guest_attempts"],
                                      probe_guests=case.protocol["budget"]["probe_guest_attempts"])
                    s.write(case.directory / "ledger/budget.json", budget)
                    before = (case.directory / "ledger/budget.json").read_bytes()
                    case.step("export")
                    case.step("close_candidate")
                    case.step("close_campaign")
                    case.complete_delivery()
                    self.assertEqual((case.directory / "ledger/budget.json").read_bytes(), before)
                    self.assertFalse(case.claim.exists())
                    self.assertNotIn("evaluate", case.calls)
                    if guard == "stop":
                        self.assertEqual((case.directory / "STOP").read_text(), "Preserve STOP\n")
                finally:
                    case.doCleanups()

    def test_action_stability_and_stale_source_rejection(self):
        self.to_probe()
        item = self.driver.next()
        self.assertEqual(item, self.driver.resume())
        (self.worktree / "fixture.txt").write_text("changed source\n")
        self.git(self.worktree, "commit", "-qam", "Synthetic revision")
        with self.assertRaisesRegex(s.SessionError, "stale action"):
            self.driver.execute(item["id"])
        self.assertNotIn("evaluate", self.calls)

    def test_repeated_execute_does_not_duplicate_arm_or_guest_reservation(self):
        self.to_probe()
        item = self.driver.next()
        self.driver.execute(item["id"])
        before = (self.directory / "ledger/budget.json").read_bytes()
        tickets = sorted((self.directory / "ledger/guest-reservations").glob("*.json"))
        self.assertFalse(self.driver.execute(item["id"])["executed"])
        self.driver.resume()
        self.assertEqual((self.directory / "ledger/budget.json").read_bytes(), before)
        self.assertEqual(sorted((self.directory / "ledger/guest-reservations").glob("*.json")), tickets)
        self.assertEqual(self.calls.count("evaluate"), 1)

    def test_interruption_without_report_never_retries_reserved_arm(self):
        self.to_probe()
        item = self.driver.next()
        self.receipt(item)
        self.assertEqual(self.driver.resume()["stage"], "export")
        self.assertEqual(self.driver.state()["executions"][-1]["status"], "interrupted")
        self.assertFalse(self.driver.execute(item["id"])["executed"])
        self.assertNotIn("evaluate", self.calls)

    def test_live_owned_process_is_not_recovered_or_relaunched(self):
        self.to_probe()
        item = self.driver.next()
        self.receipt(item, process=s._process(os.getpid()))
        self.assertEqual(self.driver.resume()["stage"], "running")
        self.assertEqual(self.driver.state()["executions"][-1]["status"], "running")
        self.assertFalse(self.driver.execute(item["id"])["executed"])
        self.assertNotIn("evaluate", self.calls)

    def test_recovered_report_advances_without_new_launch(self):
        self.to_probe()
        item = self.driver.next()
        self.receipt(item)
        self.write_row({"id": "retained-probe", "action": "evaluate", "tier": "probe",
                        "candidate": "one", "candidate_commit": self.commit, "candidate_tree": self.tree,
                        "fingerprint": "fixture-fingerprint", "status": "PROBE_PASS"})
        self.assertEqual(self.driver.resume()["stage"], "fast_selection")
        self.assertEqual(self.driver.state()["executions"][-1]["status"], "artifact_reconciled")
        self.assertNotIn("evaluate", self.calls)

    def test_unrelated_input_change_cannot_buy_duplicate_measurement(self):
        self.to_probe()
        item = self.driver.next()
        self.receipt(item, status="completed")
        s.write(self.directory / "archive/population.json", {"entries": {}})
        self.assertEqual(self.driver.next()["stage"], "export")
        self.assertNotIn("evaluate", self.calls)

    def test_exact_review_and_veto_control_runtime_admission(self):
        self.prepare_candidate()
        self.assertEqual(self.driver.next()["stage"], "review")
        self.review("veto-one", "veto")
        self.review("plain-pass")
        self.assertEqual(self.driver.next()["stage"], "review")
        self.review("resolved", "resolve", [CAMPAIGN + "/veto-one/lifetime"])
        self.assertEqual(self.driver.next()["stage"], "correctness")
        (self.worktree / "fixture.txt").write_text("revised fixture\n")
        self.git(self.worktree, "commit", "-qam", "Synthetic revised source")
        self.commit = self.git(self.worktree, "rev-parse", "HEAD")
        self.step("check")
        self.assertEqual(self.driver.next()["stage"], "review")
        self.assertNotIn("evaluate", self.calls)

    def test_value_reconciles_measurements_and_late_review_veto(self):
        self.fast_result()
        value = self.value_decision()
        bad = copy.deepcopy(value)
        bad["performance"]["normalized_gain"] = 999
        with self.assertRaisesRegex(s.SessionError, "trusted evaluation"):
            self.driver.value("one", bad)
        self.review("late-veto", "veto")
        with self.assertRaisesRegex(s.SessionError, "review status"):
            self.driver.value("one", value)
        value["review_status"] = "blocked"
        self.assertEqual(self.driver.value("one", value)["assessment"]["disposition"], "review-blocked")

    def test_frozen_research_capability_and_budget_integrity(self):
        first = self.driver.start(line="research", idea="first", machine="fixture")
        self.assertEqual(first["stage"], "open")
        frozen = (self.directory / "research.json").read_bytes()
        self.agenda["ideas"][0]["priority"] += 1
        s.write(self.root / "campaigns/lines/research.json", self.agenda)
        self.assertEqual(self.driver.resume()["stage"], "open")
        self.assertEqual((self.directory / "research.json").read_bytes(), frozen)
        profile = self.root / "evolve/profiles/swap-core.json"
        changed = s.read(profile)
        changed["version"] += 1
        s.write(profile, changed)
        self.assertEqual(self.driver.next()["stage"], "capability_blocked")
        shutil.copy2(REPO / "evolve/profiles/swap-core.json", profile)
        self.step("open")
        s.write(self.directory / "ledger/guest-reservations/retained.json", {"campaign": CAMPAIGN, "pool": "fast"})
        self.assertEqual(self.driver.next()["stage"], "integrity_blocked")
        self.assertEqual(s.read(self.directory / "ledger/budget.json")["guests"], 0)

    def test_foreign_contributor_cannot_continue_any_session_action(self):
        item = self.driver.start(line="research", idea="first", machine="fixture")
        before = {str(p): p.read_bytes() for p in self.directory.rglob("*") if p.is_file()}
        other = s.Session(CAMPAIGN, self.root, contributor="another-contributor")
        calls = [lambda: other.start(), lambda: other.resume(), lambda: other.next(),
                 lambda: other.execute(item["id"]),
                 lambda: other.decide(item["id"], {"kind": "stop", "reason": "foreign"}),
                 lambda: other.value("one", {})]
        for call in calls:
            with self.assertRaisesRegex(ValueError, "belongs to contributor"):
                call()
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.directory.rglob("*") if p.is_file()})
        same = s.Session(CAMPAIGN, self.root, contributor="fixture-contributor")
        self.assertEqual(same.resume()["stage"], "open")

    def test_auto_selection_ignores_foreign_priority_and_unowned_history(self):
        foreign = copy.deepcopy(self.agenda)
        foreign.update(line="foreign", contributor="another-contributor")
        foreign["ideas"][0]["priority"] = 9999
        s.write(self.root / "campaigns/lines/foreign.json", foreign)
        s.write(self.root / "campaigns/lines/foreign-draft.json", {"contributor": "another-contributor"})
        legacy = copy.deepcopy(foreign)
        legacy["line"] = "unowned"
        legacy.pop("contributor")
        s.write(self.root / "campaigns/lines/unowned.json", legacy)
        self.assertEqual(self.driver.start(machine="fixture")["stage"], "open")
        self.assertEqual(self.driver.state()["line"], "research")
        frozen = s.read(self.directory / "research.json")
        self.assertEqual(frozen["line_contract"]["contributor"], "fixture-contributor")

    def test_explicit_foreign_line_is_not_frozen(self):
        self.agenda["contributor"] = "another-contributor"
        s.write(self.root / "campaigns/lines/research.json", self.agenda)
        result = self.driver.start(line="research", machine="fixture")
        self.assertEqual(result["stage"], "prepare")
        self.assertIn("another contributor", result["reason"])
        self.assertFalse((self.directory / "research.json").exists())

    def test_unowned_existing_campaign_is_not_automatically_adopted(self):
        self.campaign_record()
        before = (self.directory / "campaign.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "automatic adoption is forbidden"):
            self.driver.resume()
        self.assertFalse((self.directory / "owner.json").exists())
        self.assertFalse(self.driver.path.exists())
        self.assertEqual(before, (self.directory / "campaign.json").read_bytes())

    def test_nested_execution_remnants_are_not_automatically_adopted(self):
        retained = self.directory / "ledger/guest-reservations/orphan-attempt.json"
        s.write(retained, {"status": "STARTED", "campaign": CAMPAIGN})
        before = retained.read_bytes()
        with self.assertRaisesRegex(ValueError, "automatic adoption is forbidden"):
            self.driver.start(line="research", machine="fixture")
        self.assertFalse((self.directory / "owner.json").exists())
        self.assertFalse((self.directory / "research.json").exists())
        self.assertFalse(self.driver.path.exists())
        self.assertEqual(before, retained.read_bytes())

    def test_missing_caller_identity_never_infers_target_owner(self):
        self.driver.start(line="research", machine="fixture")
        with patch.dict(os.environ, {"SWAP_NEXT_CONTRIBUTOR": ""}):
            with self.assertRaisesRegex(ValueError, "stable contributor ID"):
                s.Session(CAMPAIGN, self.root)

    def test_same_contributor_new_campaign_has_independent_session(self):
        self.driver.start(line="research", machine="fixture")
        before = self.driver.path.read_bytes()
        other = s.Session("second-campaign", self.root, contributor="fixture-contributor")
        self.assertEqual(other.start(line="research", machine="fixture")["stage"], "prepare")
        self.assertNotEqual(other.path, self.driver.path)
        self.assertEqual(before, self.driver.path.read_bytes())
        self.assertEqual(other.state()["rounds"], [])

    def test_protocol_mutation_cannot_refreeze(self):
        self.driver.start(line="research", idea="first", machine="fixture")
        changed = copy.deepcopy(self.protocol)
        changed["budget"]["guest_attempts"] -= 1
        s.write(self.directory / "protocol.json", changed)
        self.assertEqual(self.driver.start()["stage"], "integrity_blocked")
        self.assertEqual(self.calls, [])

    def test_cached_calibration_revalidates_source_and_preserves_original_age(self):
        self.to_probe()
        path = self.directory / "ledger/ledger.json"
        rows = s.read(path)
        alias = rows[-1]
        alias.update(measurement_reused=True, independent_measurement=False,
                     source_campaign="older", source_evaluation_id="source-cal",
                     source_binding={"record_sha256": "a" * 64}, reused_at=1000)
        s.write(path, rows)
        s.write(self.directory / "runs/evaluations" / alias["id"] / "report.json", alias)
        with patch.object(s.calibration_cache, "validate_alias", return_value=True) as verified:
            self.assertEqual(self.driver.next()["stage"], "evaluate_probe")
            self.assertGreater(verified.call_count, 0)
        with patch.object(s.calibration_cache, "validate_alias", side_effect=ValueError("raw source changed")):
            item = self.driver.next()
            self.assertEqual(item["stage"], "export")
            self.assertIn("incomplete or noisy", item["reason"])
        alias["finished"] = -self.protocol["calibration_max_age_seconds"]
        s.write(path, rows)
        s.write(self.directory / "runs/evaluations" / alias["id"] / "report.json", alias)
        with patch.object(s.calibration_cache, "validate_alias", return_value=True):
            self.assertFalse(self.driver.snapshot()["calibration"]["probe"]["ready"])
        self.assertEqual(self.calls.count("calibrate"), 1)

    def test_comparison_alias_requires_independent_source_revalidation(self):
        self.driver.start(line="research", idea="first", machine="fixture")
        alias = {"id": "retained-comparison", "action": "evaluate", "tier": "fast",
                 "comparison": {"contract_id": "comparison-one", "contrast_id": "candidate-upstream"},
                 "status": "FAST_PASS", "measurement_reused": True, "independent_measurement": False,
                 "source_evaluation_id": "original-evaluation", "source_campaign": "older"}
        self.write_row(alias)
        with patch.object(s.comparison_runtime, "validate_alias", return_value=True) as verified:
            self.assertTrue(self.driver.snapshot()["rows"][-1]["attested"])
            verified.assert_called_once_with(self.root, self.protocol, alias)
        with patch.object(s.comparison_runtime, "validate_alias", side_effect=ValueError("source evidence expired")):
            row = self.driver.snapshot()["rows"][-1]
            self.assertFalse(row["attested"])
            self.assertIn("source evidence expired", row["evidence_error"])
        self.assertEqual(self.calls, [])

    def test_no_done_boolean_or_slow_dispatch(self):
        self.prepare_candidate()
        item = self.driver.next()
        with self.assertRaisesRegex(s.SessionError, "unsupported decision"):
            self.driver.decide(item["id"], {"kind": "done", "reason": "Done", "passed": True})
        with self.assertRaisesRegex(s.SessionError, "probe/fast"):
            self.driver._argv(s.action("bad", "command", command="calibrate", tier="slow"))
        with self.assertRaisesRegex(s.SessionError, "unregistered"):
            self.driver._argv(s.action("bad", "command", command="shell", argv=["echo", "bad"]))


if __name__ == "__main__":
    unittest.main()
