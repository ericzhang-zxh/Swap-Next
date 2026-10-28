# SPDX-License-Identifier: GPL-2.0-only
"""Cross-module lifecycle acceptance with synthetic measurement fixtures.

Run with evolve/.venv/bin/python -m unittest evolve.test_evolution_loop -v.
The tiny Git repository is not a Linux kernel, checkpatch is the existing fixture
stub, and measurement rows are fabricated unit-test inputs to pure analysis.
These tests establish control flow and evidence binding, never correctness or
performance of a kernel. No build, QEMU guest, model, or network may run.
"""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

from evolve.control.tests.test_campaign import Fixture, c, cs, sh

REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("lifecycle_workflow", REPO / "evolve/standard_workflow.py")
w = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(w)
FP = "synthetic-fixture-image-fingerprint"
MECHANISM = "swapin-disk:swapin_vmstat_delta.swap_ra_hit:up"
FIXTURE = "Synthetic measurement transport fixture; no kernel was built or booted."


class EvolutionLoopTests(Fixture):
    def setUp(self):
        super().setUp()
        # Assert that the real database/sampler comes from the repository's pin.
        import openevolve.config
        library = Path(openevolve.config.__file__).resolve().parents[1]
        expected = sh(REPO, "ls-tree", "HEAD", "evolve/openevolve").split()[2]
        self.assertEqual(sh(library, "rev-parse", "HEAD"), expected)
        self.name = "evolution-fixture"
        self.directory = self.campaigns / self.name
        self.baseline = sh(self.linux, "rev-parse", "seed")
        self.p = json.loads((REPO / "benchmark/swap-standard/revision4-protocol-template.json").read_text())
        self.p.update(campaign=self.name, template_only=False, baseline_commit=self.baseline,
                      baseline_tree=sh(self.linux, "rev-parse", "seed^{tree}"), baseline_build="fixture-no-image")
        self.policy(self.name, mechanism_required=True)
        self.write_json(self.directory / "protocol.json", self.p)
        changes = [(w, "ROOT", self.project), (w, "BENCH", REPO / "benchmark/swap-standard"),
                   (w, "CAMPAIGN", self.directory), (w, "PROTOCOL", self.directory / "protocol.json"),
                   (w, "STATE", self.directory / "ledger"), (w, "ARCHIVE", self.directory / "archive"),
                   (w, "EVALUATIONS", self.directory / "runs/evaluations"),
                   (w, "RUNS", self.directory / "runs/guests"), (w, "TASKS", self.directory / "runs/tasks"),
                   (w, "campaign_store", cs), (w.guest_budget, "store", cs), (cs, "PROJECT", self.project)]
        for module, name, value in changes:
            item = patch.object(module, name, value)
            item.start()
            self.addCleanup(item.stop)
        for item in (patch.object(w, "fingerprint", return_value=FP),
                     patch.object(c, "campaign_fingerprint", return_value=FP),
                     patch.object(w.Workflow, "command", side_effect=AssertionError("physical measurement transport is forbidden")),
                     patch.object(socket.socket, "connect", side_effect=AssertionError("network is forbidden"))):
            item.start()
            self.addCleanup(item.stop)
        rc, record = self.run_cli("--campaign", self.name, "open-campaign", "--line", "fixture-line", "--machine", "hurricpc")
        self.assertEqual(rc, 0, record)
        self.assertEqual(record["line_anchor_commit"], self.baseline)
        self.flow = w.Workflow(self.p)
        self.sequence = 0

    @staticmethod
    def write_json(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")

    def state_tree(self):
        return {str(path.relative_to(self.campaigns)):
                    ("file" if path.is_file() else "directory",
                     path.read_bytes() if path.is_file() else None, path.stat().st_mtime_ns)
                for path in self.campaigns.rglob("*")}

    def next_cli(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            w.main(["next", "--campaign", self.name])
        return json.loads(output.getvalue())

    def new_candidate(self, name, *, chosen="baseline"):
        brief = self.next_cli()["brief"]
        self.assertTrue(brief["persisted"])
        self.assertIn(chosen if chosen != "baseline" else self.baseline, brief["allowed_parents"])
        rc, record = self.run_cli("--campaign", self.name, "new", name, "--hypothesis", FIXTURE,
                                  "--mechanism", MECHANISM, "--parent", chosen, "--brief", brief["id"])
        self.assertEqual(rc, 0, record)
        durable = json.loads((self.directory / "archive/briefs" / (brief["id"] + ".json")).read_text())
        self.assertEqual(durable["parent_bindings"], brief["parent_bindings"])
        return record, brief

    def edit_candidate(self, name, declaration):
        record = cs.candidates(self.name)[name]
        root = self.project / record["worktree"]
        path = root / "mm/swapfile.c"
        path.write_text(path.read_text() + declaration + "\n")
        sh(root, "commit", "-qam", "synthetic source fixture: " + name)
        rc, checked = self.run_cli("--campaign", self.name, "check", name)
        self.assertEqual(rc, 0, checked)
        self.assertEqual(checked["status"], "SCOPE_PASS")
        self.assertEqual(checked["parent"], self.baseline)
        expected = sh(root, "diff", "--no-ext-diff", "--no-textconv", self.baseline, "HEAD")
        patch_file = self.directory / "patches" / (name + ".patch")
        self.assertEqual(patch_file.read_text().rstrip(), expected)
        return record, checked, sh(root, "rev-parse", "HEAD^{tree}")

    def append_row(self, row):
        self.flow.ledger.append(row)
        self.write_json(self.directory / "ledger/ledger.json", self.flow.ledger)

    def fixture_row(self, name, commit, tree, tier):
        self.sequence += 1
        return {"id": f"fixture-{name}-{tier}-{self.sequence}", "fixture": FIXTURE,
                "action": "evaluate", "tier": tier, "candidate": name,
                "candidate_commit": commit, "candidate_tree": tree, "baseline_commit": self.baseline,
                "fingerprint": FP, "mechanism": MECHANISM, "execution_started": True,
                "started": self.sequence, "finished": self.sequence + .5,
                "performance_accepted": False, "auto_promote": False,
                "correctness": {"fixture": FIXTURE, "candidate_commit": commit, "integration_pass": True,
                                "gates": {key: True for key in self.p["required_correctness_gates"]}}}

    def probe_row(self, name, checked, tree, counter):
        module = w.probe_module()
        def observations(count, value):
            return {case: [{"swapin_vmstat_delta": {key: value for key in module.VMSTAT},
                            module.METADATA: .206} for _ in range(count)]
                    for case in self.p["tiers"]["probe"]["cases"]}
        calibration = module.calibrate(self.p, observations(3, 10))
        outcome = module.compare(self.p, calibration, observations(1, counter), MECHANISM)
        self.assertEqual(outcome["status"], "PROBE_PASS")
        row = self.fixture_row(name, checked["candidate_commit"], tree, "probe")
        row.update(status="PROBE_PASS", analysis=outcome, probe_signals=outcome["probe_signals"], controller_check=checked)
        self.append_row(row)
        return row

    def fast_row(self, name, checked, tree, probe, ratio=1.):
        directions, primary = w.metric_spec(self.p, "fast")
        pairs = [{"a": {key: 1000. for key in directions}, "b": {key: 1000. for key in directions}} for _ in range(10)]
        analysis = w.analysis_module()
        calibration = analysis.calibrate(pairs, directions, primary, envelope="p90", min_pairs=10,
                                         noise_ceiling=.25, noise_floor=.03, advisory_suffixes=(".p99_ns",))
        samples = [{"a": {key: 1000. for key in directions}, "b": {key: 1000. * ratio for key in directions}} for _ in range(4)]
        result = analysis.compare(samples, directions, calibration, "fast", primary=primary, decision="median", min_pairs=4)
        row = self.fixture_row(name, checked["candidate_commit"], tree, "fast")
        row.update(status=result["status"], analysis=result, probe_id=probe["id"], probe_signals=probe["probe_signals"],
                   selection_reason="Synthetic fixture selects an engaged mechanism with an intact metadata guard.", controller_check=checked)
        self.append_row(row)
        return row

    def screen(self, name="parent", *, declaration="int fixture_parent = 1;", ratio=1., counter=20, chosen="baseline"):
        record, brief = self.new_candidate(name, chosen=chosen)
        record, checked, tree = self.edit_candidate(name, declaration)
        probe = self.probe_row(name, checked, tree, counter)
        self.flow.probe_prerequisite(checked["candidate_commit"], tree, FP, record, "Fixture agent selection")
        fast = self.fast_row(name, checked, tree, probe, ratio)
        self.assertEqual(fast["status"], "FAST_PASS")
        entry = self.flow.archive(fast, record)
        return record, checked, tree, probe, fast, entry, brief

    def close_candidate(self, name):
        rc, record = self.run_cli("--campaign", self.name, "close", name, "--reason", "synthetic fixture stage complete")
        self.assertEqual(rc, 0, record)

    def close_campaign(self):
        rc, record = self.run_cli("--campaign", self.name, "close-campaign", "--reason", "synthetic fixture lifecycle complete")
        self.assertEqual(rc, 0, record)
        self.assertEqual(record["status"], "closed")
        self.assertIsNone(cs.read_claim())

    def test_replaying_an_earlier_probe_preserves_latest_fast_status(self):
        self.screen()
        self.next_cli()
        path = self.directory / "archive/population.json"
        entry = json.loads(path.read_text())["entries"]["parent"]
        self.assertEqual(entry["latest_status"], "FAST_PASS")
        self.next_cli()
        self.assertEqual(json.loads(path.read_text())["entries"]["parent"]["latest_status"], "FAST_PASS")

    def test_parent_child_lifecycle_scope_invalidation_and_closed_restart(self):
        parent, brief = self.new_candidate("parent")
        parent, parent_scope, parent_tree = self.edit_candidate("parent", "int fixture_parent = 1;")
        commit = parent_scope["candidate_commit"]
        with self.assertRaisesRegex(RuntimeError, "PROBE_PASS"):
            self.flow.probe_prerequisite(commit, parent_tree, FP, parent, "Fixture selection")
        probe = self.probe_row("parent", parent_scope, parent_tree, 20)
        with self.assertRaisesRegex(RuntimeError, "selection-reason"):
            self.flow.probe_prerequisite(commit, parent_tree, FP, parent, None)
        self.flow.probe_prerequisite(commit, parent_tree, FP, parent, "Fixture selects this counter")
        fast = self.fast_row("parent", parent_scope, parent_tree, probe)
        entry = self.flow.archive(fast, parent)
        self.assertTrue(entry["parent_eligible"])
        self.assertFalse(entry["advancement"]["eligible"])
        self.assertEqual(entry["patch"], (self.directory / "patches/parent.patch").read_text())
        from openevolve.config import DatabaseConfig
        from openevolve.database import ProgramDatabase
        database = ProgramDatabase(DatabaseConfig(in_memory=True, num_islands=1))
        database.load(str(self.directory / "archive/database"))
        self.assertEqual(database.programs["parent"].metadata["candidate_commit"], commit)
        self.close_candidate("parent")
        child, child_brief = self.new_candidate("child", chosen=commit)
        self.assertEqual(child_brief["parent"]["candidate_commit"], commit)
        self.assertEqual((child["parent_candidate"], child["parent_commit"], child["generation"]), ("parent", commit, 2))
        root = self.project / child["worktree"]
        for empty_commit in (False, True):
            if empty_commit:
                sh(root, "commit", "--allow-empty", "-qm", "synthetic same-tree new SHA")
                self.assertNotEqual(sh(root, "rev-parse", "HEAD"), commit)
            rc, blocked = self.run_cli("--campaign", self.name, "check", "child")
            self.assertEqual(rc, 2, blocked)
            self.assertIn("unchanged", blocked["error"])
        child, child_scope, child_tree = self.edit_candidate("child", "int fixture_child = 2;")
        patch_text = (self.directory / "patches/child.patch").read_text()
        self.assertIn("+int fixture_parent = 1;", patch_text)
        self.assertIn("+int fixture_child = 2;", patch_text)
        self.assertNotEqual(patch_text.rstrip(), sh(root, "diff", commit, "HEAD"))
        child_probe = self.probe_row("child", child_scope, child_tree, 30)
        child_fast = self.fast_row("child", child_scope, child_tree, child_probe, .9)
        child_entry = self.flow.archive(child_fast, child)
        delta = child_entry["parent_delta"]
        self.assertTrue(delta["comparable"])
        self.assertEqual(delta["probe_signals"]["swapin-disk.swapin_vmstat_delta.swap_ra_hit"], 10)
        self.assertIn("not a paired parent control", delta["interpretation"])
        database.load(str(self.directory / "archive/database"))
        self.assertEqual(database.programs["child"].parent_id, "parent")
        self.assertEqual(database.programs["child"].generation, 2)
        self.assertEqual(database.programs["child"].code, patch_text)
        regression = self.fast_row("child", child_scope, child_tree, child_probe, 1.5)
        self.assertEqual(regression["status"], "REGRESSION")
        invalid = self.flow.archive(regression, child)
        self.assertFalse(invalid["parent_eligible"])
        next_brief = self.next_cli()["brief"]
        self.assertEqual(next_brief["parent"]["id"], "parent")
        self.assertNotIn("child", self.flow.population(FP).eligible_parents())
        self.close_campaign()
        state = self.state_tree()
        restarted = w.Workflow(self.p)
        self.assertTrue(restarted.read_only)
        self.assertEqual(restarted.ledger, self.flow.ledger)
        preview = self.next_cli()["brief"]
        self.assertFalse(preview["persisted"])
        self.assertEqual(preview["parent"]["id"], "parent")
        self.assertEqual(state, self.state_tree())

    def test_neutral_parent_cannot_advance_but_strong_parent_keeps_line_anchor(self):
        neutral = self.screen()
        self.close_candidate("parent")
        strong = self.screen("strong", declaration="int fixture_strong = 3;", ratio=.7, counter=40)
        self.assertTrue(strong[5]["advancement"]["eligible"])
        self.close_campaign()
        bypass = "omitted-origin"
        bypass_protocol = copy.deepcopy(self.p)
        bypass_protocol.update(campaign=bypass, baseline_commit=strong[1]["candidate_commit"],
                               baseline_tree=strong[2])
        self.policy(bypass, checkout_ref="seed", mechanism_required=True)
        bypass_policy_path = self.campaigns / bypass / "policy.json"
        bypass_policy = json.loads(bypass_policy_path.read_text())
        bypass_policy["seed_ref"] = strong[1]["candidate_commit"]
        self.write_json(bypass_policy_path, bypass_policy)
        self.write_json(self.campaigns / bypass / "protocol.json", bypass_protocol)
        rc, refused = self.run_cli("--campaign", bypass, "open-campaign", "--line", "fixture-line", "--machine", "hurricpc")
        self.assertEqual(rc, 2, refused)
        self.assertIn("baseline", refused["error"])
        self.assertFalse((self.campaigns / bypass / "campaign.json").exists())
        self.assertIsNone(cs.read_claim())
        for destination, screened, expected in (("neutral-destination", neutral, 2), ("strong-destination", strong, 0)):
            record, checked, _, _, row, _, _ = screened
            protocol = copy.deepcopy(self.p)
            protocol.update(campaign=destination, baseline_commit=checked["candidate_commit"], baseline_tree=screened[2])
            self.policy(destination, checkout_ref="seed", mechanism_required=True)
            policy_path = self.campaigns / destination / "policy.json"
            policy = json.loads(policy_path.read_text())
            policy["seed_ref"] = checked["candidate_commit"]
            self.write_json(policy_path, policy)
            self.write_json(self.campaigns / destination / "protocol.json", protocol)
            rc, result = self.run_cli("--campaign", destination, "open-campaign", "--line", "fixture-line", "--machine", "hurricpc",
                                      "--baseline-from", self.name + ":" + record["id"], "--evidence-row", row["id"])
            self.assertEqual(rc, expected, result)
            if expected:
                self.assertIn("above calibrated noise", result["error"])
                self.assertFalse((self.campaigns / destination / "campaign.json").exists())
            else:
                self.assertEqual(result["baseline_from"]["commit"], checked["candidate_commit"])
                self.assertEqual(result["line_anchor_commit"], self.baseline)
                self.assertNotEqual(result["baseline_from"]["commit"], self.baseline)
                from population import Population
                new = Population(self.campaigns / destination, protocol, FP)
                self.assertEqual(new.anchor, self.baseline)
                preview = new.next_brief([], "Synthetic line fixture", {}, persist=False)
                self.assertIn("no root-relative measurement is claimed", preview["anchor_comparison"])

    def test_bound_correctness_failure_invalidates_but_malformed_proof_does_not(self):
        record, checked, _, _, _, entry, _ = self.screen()
        proof = self.project / "synthetic-proof-boundary.json"
        self.write_json(proof, {"fixture": FIXTURE})
        original = (self.directory / "archive/population.json").read_bytes()
        with patch.object(w.correctness_proof, "validate", side_effect=ValueError("synthetic malformed proof boundary")), contextlib.redirect_stdout(io.StringIO()):
            malformed = self.flow.run("evaluate", "fast", "parent", proof, "Fixture selection")
        self.assertEqual(malformed["status"], "INCOMPLETE")
        self.assertIn("malformed proof boundary", malformed["reason"])
        self.assertEqual(original, (self.directory / "archive/population.json").read_bytes())
        self.assertIn("parent", self.flow.population(FP).eligible_parents())
        evidence = {"fixture": FIXTURE, "candidate_commit": checked["candidate_commit"], "integration_pass": False,
                    "gates": {key: key != "data_roundtrip" for key in self.p["required_correctness_gates"]}}
        failure = w.correctness_proof.CorrectnessFailure("synthetic counted/bound correctness failure", evidence)
        with patch.object(w.correctness_proof, "validate", side_effect=failure), contextlib.redirect_stdout(io.StringIO()):
            failed = self.flow.run("evaluate", "fast", "parent", proof, "Fixture selection")
        self.assertEqual(failed["status"], "CORRECTNESS_FAIL")
        self.assertEqual(failed["candidate_commit"], checked["candidate_commit"])
        self.assertNotIn("parent", self.flow.population(FP).eligible_parents())
        state = json.loads((self.directory / "archive/population.json").read_text())
        self.assertIn("correctness_failure", [item["reason"] for item in state["entries"]["parent"]["invalidations"]])
        self.assertEqual(self.next_cli()["brief"]["parent"]["kind"], "baseline")


if __name__ == "__main__":
    unittest.main()
