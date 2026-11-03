# SPDX-License-Identifier: GPL-2.0-only
"""No guests/builds: exercise runtime binding with retained fixture runner files."""
import copy
import contextlib
import io
import shutil
import sys
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from evolve import comparison_runtime as r
from evolve import comparisons as c
from evolve import test_comparisons as fixtures

ROOT = Path(__file__).resolve().parents[1]
NATIVE_GIT_IDENTITY = r._git_identity


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.seed = fixtures.EvidenceTests("test_exact_git_build_and_proof_identity")
        self.seed.setUp()
        self.addCleanup(self.seed.doCleanups)
        self.root = self.seed.root
        self.protocol = self.seed.protocol
        self.contract = self.seed.contract
        self.protocol.update(protocol_revision=3, calibration_max_age_seconds=1000,
                             noise_floor=.03, noise_ceiling=.25, noise_envelope="p90",
                             comparison_decision="median", preallocate_swap=True,
                             budget={"guest_attempts": 120, "probe_guest_attempts": 0, "guest_timeout": 10})
        self.protocol["guest"] = {"vcpus": 4, "mem_mib": 4096, "swap_gib": 16}
        self.protocol["accelerator"] = {"require": "tcg"}
        self.contract["environment"].update(guest=copy.deepcopy(self.protocol["guest"]), accelerator="tcg")
        self.protocol_path = self.seed.protocol_path
        self.seed.put(self.protocol_path.relative_to(self.root), self.protocol)
        self.contract["protocol_sha256"] = fixtures.sha(self.protocol_path.read_bytes())
        c.freeze(self.root, self.contract, self.protocol)
        self.output = self.root / "campaigns/comparison-fixture/runs/evaluations/current"
        self.output.mkdir(parents=True)
        self.flow = SimpleNamespace(p=self.protocol, ledger=[], budget={"guests": 0},
                                    command=self.command, check=lambda: None)
        self.commands = []
        self.recorded_reviews = []
        for name in ("upstream", "candidate"):
            arm = self.contract["arms"][name]
            record = {"id": arm["candidate"], "status": "closed" if name == "upstream" else "active",
                      "worktree": "worktrees/" + arm["candidate"], "candidate_commit": arm["commit"],
                      "source_tree": arm["tree"]}
            self.seed.put("campaigns/comparison-fixture/candidates/" + arm["candidate"] + ".json", record)
            self.recorded_reviews.append({"candidate": arm["candidate"], "candidate_commit": arm["commit"],
                "source_tree": arm["tree"], "disposition": "pass", "id": name + "-review", "record_sha256": "a" * 64})
        for filename in ("run.py", "evidence.py", "analysis.py", "validity.py"):
            self.seed.put("benchmark/swap-standard/" + filename,
                          (ROOT / "benchmark/swap-standard" / filename).read_bytes())
        self.native_module = r._module
        patches = [
            patch.object(c, "validate_evidence", return_value={"verified": True}),
            patch.object(r, "_machine", return_value="hurricpc"),
            patch.object(r, "_git_identity", side_effect=lambda project, record, expected=None:
                         (record["candidate_commit"], record["source_tree"])),
            patch.object(r.reviews, "list_reviews", side_effect=lambda project, campaign: self.recorded_reviews),
            patch.object(r.reviews, "blockers", return_value=[]),
            patch.object(r, "_module", side_effect=self.module),
            patch.object(r.time, "time", return_value=300),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.seed.put("campaigns/comparison-fixture/ledger/budget.json", {"guests": 0})

    def test_retired_upstream_identity_uses_retained_git_object(self):
        shutil.copytree(self.seed.source, self.root / "linux")
        arm = self.contract["arms"]["upstream"]
        record = json.loads((self.root / "campaigns/comparison-fixture/candidates" /
                             (arm["candidate"] + ".json")).read_bytes())
        self.assertFalse((self.root / record["worktree"]).exists())
        before = self.seed.git("status", "--porcelain")
        self.assertEqual(NATIVE_GIT_IDENTITY(self.root, record, arm),
                         (arm["commit"], arm["tree"]))
        self.assertEqual(before, self.seed.git("status", "--porcelain"))
        with self.assertRaises(c.ComparisonError):
            NATIVE_GIT_IDENTITY(self.root, dict(record, status="active"), arm)
        with self.assertRaises(c.ComparisonError):
            NATIVE_GIT_IDENTITY(self.root, record, dict(arm, commit="e" * 40))

    def module(self, project, path):
        if path.endswith("/evidence.py"):
            return SimpleNamespace(parse=lambda serial, image, backend, mode, workload: json.loads(serial))
        return self.native_module(project, path)

    def command(self, argv, log, timeout):
        self.commands.append(argv)
        candidate = argv[-1]
        arm = next(a for a in self.contract["arms"].values() if a.get("candidate") == candidate)
        Path(log).write_bytes(c.canonical_bytes(
            {"status": "SCOPE_PASS", "candidate_commit": arm["commit"],
             "parent": self.contract["common_base"]["commit"]}))

    def write_report(self, row):
        self.seed.put("campaigns/comparison-fixture/runs/evaluations/" + row["id"] + "/report.json", row)

    def current(self, action="evaluate", contrast="upstream-control"):
        row = {"id": "current", "action": action, "tier": "fast", "started": 300,
               "status": "RUNNING", "runs": [], "pairs": []}
        context = r.prepare(self.flow, self.root, self.protocol_path, self.contract["id"],
                            contrast, action, row, self.output, "f" * 64)
        return context, row

    def add_measurement(self, action="calibrate", contrast="upstream-control", ident="cal-one",
                        comparison=False, started=100, finished=150, invalid_first=False):
        plan = c.execution_plan(self.contract, self.protocol, contrast, action)
        target = plan["control"] if action == "calibrate" else plan["treatment"]
        row = {"id": ident, "action": action, "tier": "fast", "started": started, "finished": finished,
               "protocol_sha256": self.contract["protocol_sha256"], "fingerprint": "f" * 64,
               "candidate_commit": target["commit"], "candidate_tree": target["tree"],
               "execution_started": True, "runs": [],
               "pairs": [{"a": {}, "b": {}, "order": "AB" if i % 2 == 0 else "BA"}
                         for i in range(plan["pair_count"])]}
        if comparison:
            row["comparison"] = copy.deepcopy(plan["identity"])
        for step in plan["schedule"]:
            arm = self.contract["arms"][step["arm"]]
            manifest = self.seed.root / "benchmark/kernel/builds" / arm["build"] / "result.json"
            manifest_data = json.loads(manifest.read_bytes())
            repetitions = 2 if invalid_first and step["ordinal"] == 0 else 1
            for number in range(repetitions):
                invalid = repetitions == 2 and number == 0
                run_id = ident + "-" + str(step["ordinal"]) + "-" + str(number)
                run = "campaigns/comparison-fixture/runs/guests/" + run_id
                ticket = "campaigns/comparison-fixture/ledger/guest-reservations/" + run_id + ".json"
                identity = {"build": arm["build"], "backend": "disk", "mode": "xswap", "workload": "swapin"}
                ticket_sha = self.seed.put(ticket, {
                    "id": run_id, "campaign": "comparison-fixture", "status": "STARTED", "pool": "fast",
                    "protocol_sha256": self.contract["protocol_sha256"], "identity": identity})
                value = 100 if step["arm"] == "baseline" else 90 if step["arm"] == "upstream" else 80
                metrics = {"latency": value}
                parsed = {"gates": {"data": True, "identity": True}, "metrics": metrics}
                serial_sha = self.seed.put(run + "/serial.log", parsed)
                raw = dict(identity, run_id=run_id, result_path=run + "/result.json",
                           campaign="comparison-fixture", source_commit=arm["commit"],
                           protocol_sha256=self.contract["protocol_sha256"], protocol_revision=3,
                           build_manifest_sha256=arm["build_manifest_sha256"],
                           input_config_sha256=self.contract["environment"]["input_config_sha256"],
                           config_sha256=manifest_data["config_sha256"], image_sha256=manifest_data["image_sha256"],
                           accelerator="tcg", guest_vcpus=4, guest_mem_mib=4096, swap_bytes=16 * 1024 ** 3,
                           guest_provenance={"image_sha256": self.contract["environment"]["guest_image_sha256"]},
                           swap_image_allocation="preallocated", reservation=ticket, reservation_sha256=ticket_sha,
                           pre_qemu_seconds=61 if invalid else 0, clocksource_invalid=False, wall_seconds=1,
                           host_load={"before_launch": {"loadavg_1m": 0}}, integration_pass=True,
                           exit_code=0, stop_reason=None, serial_log=run + "/serial.log", serial_sha256=serial_sha,
                           harness_sha256={filename: r._sha(self.root / "benchmark/swap-standard" / filename)
                                           for filename in ("run.py", "evidence.py")},
                           gates=dict(parsed["gates"], qemu_exit=True), metrics=metrics)
                raw_sha = self.seed.put(run + "/result.json", raw)
                self.seed.put(run + "/result.sha256", (raw_sha + "\n").encode())
                attempt = dict(id=run_id, pair=step["pair"], case=step["case"], arm=step["slot"],
                               attempt=number, result=run + "/result.json", result_sha256=raw_sha,
                               reservation=ticket, status="INVALID" if invalid else "PASS",
                               run_valid=not invalid, invalid_reason="pre_qemu_delay" if invalid else None,
                               metrics=metrics)
                row["runs"].append(attempt)
                if not invalid:
                    row["pairs"][step["pair"]][step["slot"]]["disk.latency"] = value
        paired = [{key: pair[key] for key in ("a", "b")} for pair in row["pairs"]]
        analyzer = self.module(self.root, "benchmark/swap-standard/analysis.py")
        if action == "calibrate":
            analysis = analyzer.calibrate(paired, plan["directions"], primary=plan["primary"],
                envelope="p90", min_pairs=10, noise_floor=.03, noise_ceiling=.25, advisory_suffixes=[])
        else:
            calibration = next(x for x in self.flow.ledger if x.get("action") == "calibrate"
                               and not x.get("measurement_reused"))
            row["calibration_id"] = calibration["id"]
            analysis = analyzer.compare(paired, plan["directions"], calibration["analysis"], "fast",
                primary=plan["primary"], decision="median", min_pairs=4)
        row.update(analysis=analysis, status=analysis["status"])
        self.flow.ledger.append(row)
        self.flow.budget["guests"] += len(row["runs"])
        self.seed.put("campaigns/comparison-fixture/ledger/budget.json", self.flow.budget)
        self.write_report(row)
        return row


    def workflow(self):
        # Use the real Workflow.run adapter, while scope/guest processes remain
        # fixture producers. Any unexpected build/archive/reservation is fatal.
        from evolve import standard_workflow as w
        campaign = self.root / "campaigns" / self.protocol["campaign"]
        values = {"ROOT": self.root, "BENCH": self.root / "benchmark/swap-standard",
                  "PROTOCOL": self.protocol_path, "CAMPAIGN": campaign,
                  "STATE": campaign / "ledger", "EVALUATIONS": campaign / "runs/evaluations",
                  "RUNS": campaign / "runs/guests", "ARCHIVE": campaign / "archive"}
        for name, value in values.items():
            item = patch.object(w, name, value); item.start(); self.addCleanup(item.stop)
        for item in (patch.object(w, "fingerprint", return_value=self.contract["environment"]["fingerprint"]),
                     patch.object(w, "contract_errors", return_value=[]),
                     patch.dict(sys.modules, {"comparison_runtime": r})):
            item.start(); self.addCleanup(item.stop)
        flow = w.Workflow.__new__(w.Workflow)
        flow.p, flow.ledger, flow.budget = self.protocol, self.flow.ledger, self.flow.budget
        flow.ledger_path, flow.budget_path = campaign / "ledger/ledger.json", campaign / "ledger/budget.json"
        flow.stop, flow.global_stop = campaign / "STOP", self.root / "STOP"
        flow.check = lambda: None
        flow.campaign_errors = lambda: []
        flow.reserve = lambda *a, **k: self.fail("comparison unexpectedly reserved a build")
        flow.archive = lambda *a, **k: self.fail("comparison unexpectedly archived a population entry")
        flow._reserve_guest = lambda *a, **k: self.fail("comparison unexpectedly reserved a guest")
        flow.command = self.command
        self.flow = flow
        return w, flow

    def enable_shared_cache(self):
        shutil.copytree(self.seed.source, self.root / "linux")
        for filename in ("comparison_runtime.py", "comparisons.py", "reference_cache.py"):
            self.seed.put("evolve/" + filename, (ROOT / "evolve" / filename).read_bytes())
        image = {"image_sha256": self.seed.put("benchmark/swap-standard/bench.img", b"fixture guest image"),
                 "initrd_sha256": self.seed.put("benchmark/swap-standard/initramfs.cpio.gz", b"fixture initrd"),
                 "sources": {"guest-init": self.seed.put("benchmark/swap-standard/guest-init", b"fixture init")}}
        self.seed.put("benchmark/swap-standard/image.json", image)
        self.contract["environment"]["guest_image_sha256"] = image["image_sha256"]
        self.contract["id"] = "cache-plan"
        c.freeze(self.root, self.contract, self.protocol)
        native = r.reference_cache.Verifier.native
        item = patch.object(r.reference_cache.Verifier, "native", side_effect=lambda verifier, path:
            r if path == "evolve/comparison_runtime.py" else native(verifier, path), autospec=True)
        item.start(); self.addCleanup(item.stop)

    def register_upstream(self):
        self.seed.put("campaigns/comparison-fixture/ledger/ledger.json", self.flow.ledger)
        original = next(row for row in self.flow.ledger if row.get("action") == "evaluate")
        record = r.register_reference(self.flow, self.root, self.protocol_path, original)
        self.assertTrue(record["verification"]["passed"], record["verification"])
        return record, original

    def switch_campaign(self):
        self.protocol = copy.deepcopy(self.protocol)
        self.protocol["campaign"] = "target-fixture"
        self.protocol_path = self.root / "campaigns/target-fixture/protocol.json"
        self.seed.put(self.protocol_path.relative_to(self.root), self.protocol)
        self.contract = copy.deepcopy(self.contract)
        self.contract.update(campaign="target-fixture", id="target-plan",
                             protocol_sha256=r._sha(self.protocol_path))
        self.contract["environment"]["fingerprint"] = "9" * 64
        c.freeze(self.root, self.contract, self.protocol)
        for name in ("upstream", "candidate"):
            candidate = self.contract["arms"][name]["candidate"]
            record = json.loads((self.root / "campaigns/comparison-fixture/candidates" / (candidate + ".json")).read_bytes())
            self.seed.put("campaigns/target-fixture/candidates/" + candidate + ".json", record)
        self.seed.put("campaigns/target-fixture/ledger/budget.json", {"guests": 0})
        self.flow = SimpleNamespace(p=self.protocol, ledger=[], budget={"guests": 0},
                                    command=self.command, check=lambda: None)
        self.output = self.root / "campaigns/target-fixture/runs/evaluations/current"
        self.output.mkdir(parents=True)

    def test_workflow_uses_supplied_nonbaseline_control_and_treatment(self):
        self.add_measurement()
        self.add_measurement("evaluate", comparison=True, ident="upstream", started=180, finished=200)
        self.add_measurement("evaluate", "candidate-control", comparison=True,
                             ident="candidate", started=210, finished=230)
        self.contract["id"] = "direct-plan"
        self.contract["contrasts"].append({"id": "candidate-upstream", "control": "upstream", "treatment": "candidate"})
        c.freeze(self.root, self.contract, self.protocol)
        self.add_measurement("calibrate", "candidate-upstream", comparison=True,
                             ident="upstream-aa", started=240, finished=260)
        w, flow = self.workflow()
        reservations, launches = [], []
        def reserve(run_id, build, case):
            reservations.append(build)
            return {"reservation": "fixture-ticket"}
        def command(argv, logfile, timeout, **kwargs):
            if "evolve/control/controller.py" in argv:
                return self.command(argv, logfile, timeout)
            self.assertEqual(Path(argv[1]).name, "run.py")
            build, run_id = argv[argv.index("--build") + 1], argv[argv.index("--run-id") + 1]
            arm = next(arm for arm in self.contract["arms"].values() if arm.get("build") == build)
            launches.append((build, arm["commit"]))
            self.seed.put((w.RUNS / run_id / "result.json").relative_to(self.root), {
                "source_commit": arm["commit"], "run_id": run_id, "wall_seconds": 1,
                "pre_qemu_seconds": 0, "host_load": {"before_launch": {"loadavg_1m": 0}},
                "clocksource_invalid": False, "guest_mem_mib": 4096, "guest_vcpus": 4,
                "accelerator": "tcg", "swap_image_allocation": "preallocated", "integration_pass": True,
                "metrics": {"latency": 90 if build == "upstream-build" else 80}})
        flow._reserve_guest, flow.command = reserve, command
        with contextlib.redirect_stdout(io.StringIO()):
            row = flow.run("evaluate", "fast", comparison=self.contract["id"], contrast="candidate-upstream")
        self.assertEqual(row["status"], "FAST_PASS", row.get("reason"))
        self.assertEqual(len(reservations), 8)
        self.assertEqual(set(launches), {("upstream-build", self.contract["arms"]["upstream"]["commit"]),
                                       ("candidate-build", self.contract["arms"]["candidate"]["commit"])})
        self.assertEqual(reservations[:4], ["upstream-build", "candidate-build", "candidate-build", "upstream-build"])
        self.assertEqual(row["calibration_id"], "upstream-aa")
        self.assertEqual(json.loads((w.EVALUATIONS / row["id"] / "report.json").read_bytes()), row)

    def test_workflow_existing_upstream_reuse_spends_nothing(self):
        self.add_measurement()
        original = self.add_measurement("evaluate", comparison=True, ident="upstream", started=180, finished=200)
        w, flow = self.workflow()
        before = copy.deepcopy(flow.budget)
        with contextlib.redirect_stdout(io.StringIO()):
            row = flow.run("evaluate", "fast", comparison=self.contract["id"], contrast="upstream-control")
        self.assertEqual(row["status"], original["status"], row.get("reason"))
        self.assertTrue(row["measurement_reused"])
        self.assertEqual(flow.budget, before)
        self.assertEqual(row["new_guest_attempts"], 0)
        self.assertEqual(json.loads((w.EVALUATIONS / row["id"] / "report.json").read_bytes()), row)

    def test_shared_cache_replays_original_and_workflow_skips_new_guests(self):
        self.enable_shared_cache()
        self.add_measurement()
        self.add_measurement("evaluate", comparison=True, ident="upstream", started=180, finished=200)
        record, original = self.register_upstream()
        original_bytes = (self.root / record["provenance"]["artifact"]).read_bytes()
        self.switch_campaign()
        w, flow = self.workflow()
        with contextlib.redirect_stdout(io.StringIO()):
            row = flow.run("evaluate", "fast", comparison=self.contract["id"], contrast="upstream-control")
        self.assertEqual(row["status"], original["status"], row.get("reason"))
        self.assertTrue(row["measurement_reused"])
        self.assertEqual(row["source_binding"]["reference_cache_record"], record["record_sha256"])
        self.assertTrue(row["source_binding"]["cross_campaign_reused"])
        self.assertEqual(row["reused_from"]["campaign"], "comparison-fixture")
        self.assertEqual(row["measurement_finished"], 200)
        self.assertEqual(row["new_guest_attempts"], 0)
        self.assertFalse(row["may_pair_with_new_arm"])
        self.assertEqual(flow.budget, {"guests": 0})
        self.assertEqual(original_bytes, (self.root / record["provenance"]["artifact"]).read_bytes())
        self.assertEqual(json.loads((w.EVALUATIONS / row["id"] / "report.json").read_bytes()), row)
        candidate_plan = c.execution_plan(self.contract, self.protocol, "candidate-control")
        self.assertIsNone(r._evaluation(flow, self.root, self.contract, candidate_plan, 300, {}))
        self.assertIsNone(r.available_calibration(flow, self.root, self.protocol_path, self.contract,
                                               "candidate-control", "9" * 64))

    def test_expired_shared_reference_is_not_a_current_measurement(self):
        self.enable_shared_cache()
        self.add_measurement()
        self.add_measurement("evaluate", comparison=True, ident="upstream", started=180, finished=200)
        self.register_upstream()
        self.switch_campaign()
        plan = c.execution_plan(self.contract, self.protocol, "upstream-control")
        self.assertIsNone(r._evaluation(self.flow, self.root, self.contract, plan, 1200, {}))

    def test_changed_shared_source_raw_or_science_is_not_reused(self):
        self.enable_shared_cache()
        self.add_measurement()
        self.add_measurement("evaluate", comparison=True, ident="upstream", started=180, finished=200)
        record, original = self.register_upstream()
        self.switch_campaign()
        plan = c.execution_plan(self.contract, self.protocol, "upstream-control")
        self.protocol["guest"]["vcpus"] = 8
        self.assertIsNone(r._shared_evaluation(self.flow, self.root, self.contract, plan, 300))
        self.protocol["guest"]["vcpus"] = 4
        raw = self.root / original["runs"][0]["result"]
        raw.write_text("{}")
        self.assertIsNone(r._evaluation(self.flow, self.root, self.contract, plan, 300, {}))

    def test_new_calibration_prepares_existing_loop_without_spending(self):
        before = copy.deepcopy(self.flow.budget)
        context, row = self.current("calibrate")
        self.assertEqual(context["status"], "PLANNED")
        self.assertEqual(context["control_build"], "base-build")
        self.assertEqual(context["treatment_build"], "base-build")
        self.assertEqual(context["count"], 10)
        self.assertEqual(context["remaining_cost"]["minimum_remaining_guests"], 36)
        self.assertEqual(self.flow.budget, before)
        self.assertCountEqual([cmd[-2] for cmd in self.commands], ["check-reference", "check"])

    def test_reuses_verified_ordinary_baseline_calibration(self):
        original = self.add_measurement()
        before = copy.deepcopy(original), copy.deepcopy(self.flow.budget)
        context, row = self.current("calibrate")
        self.assertEqual(context["status"], "REUSED")
        self.assertEqual(row["source_evaluation_id"], "cal-one")
        self.assertEqual(row["analysis"], original["analysis"])
        self.assertTrue(row["measurement_reused"])
        self.assertFalse(row["independent_measurement"])
        self.assertEqual(before, (original, self.flow.budget))

    def test_reuses_prior_upstream_across_plan_ids(self):
        self.add_measurement()
        original = self.add_measurement("evaluate", comparison=True, ident="prior-upstream",
                                        started=180, finished=200)
        self.contract["id"] = "next-candidate-plan"
        c.freeze(self.root, self.contract, self.protocol)
        self.flow.ledger.append(dict(original, id="old-alias", source_evaluation_id=original["id"],
                                     measurement_reused=True))
        spent = self.flow.budget["guests"]
        context, row = self.current()
        self.assertEqual(context["status"], "REUSED")
        self.assertEqual(row["reused_from"]["evaluation_id"], "prior-upstream")
        self.assertEqual(row["reused_from"]["measurement_time"], 200)
        self.assertEqual(row["comparison"]["contract_id"], "next-candidate-plan")
        self.assertEqual(self.flow.budget["guests"], spent)
        self.assertEqual(original["comparison"]["contract_id"], "compare-one")

    def test_ordinary_candidate_result_reused_after_preceding_upstream(self):
        self.add_measurement()
        self.add_measurement("evaluate", ident="upstream", started=180, finished=200)
        original = self.add_measurement("evaluate", "candidate-control", ident="candidate",
                                        started=210, finished=240)
        context, row = self.current(contrast="candidate-control")
        self.assertEqual(context["status"], "REUSED")
        self.assertEqual(row["source_evaluation_id"], original["id"])
        self.assertEqual(row["analysis"], original["analysis"])

    def test_remaining_budget_excludes_existing_calibration_and_candidate(self):
        self.add_measurement()
        self.add_measurement("evaluate", "candidate-control", ident="candidate",
                             started=180, finished=200)
        self.flow.budget["guests"] = 112
        self.seed.put("campaigns/comparison-fixture/ledger/budget.json", self.flow.budget)
        context, row = self.current()
        self.assertEqual(context["status"], "PLANNED")
        self.assertEqual(context["remaining_cost"]["minimum_remaining_guests"], 8)
        self.assertEqual(context["calibration"]["id"], "cal-one")
        self.assertEqual(row["calibration_binding"]["source_evaluation_id"], "cal-one")

    def test_budget_must_cover_remaining_work_not_just_current_calibration(self):
        self.flow.budget["guests"] = 90
        with self.assertRaisesRegex(c.ComparisonError, "remaining comparison work"):
            self.current("calibrate")

    def test_contrast_order_enforced(self):
        self.add_measurement()
        with self.assertRaisesRegex(c.ComparisonError, "requires upstream-control first"):
            self.current(contrast="candidate-control")

    def test_invalid_retry_is_retained_and_revalidated(self):
        original = self.add_measurement(invalid_first=True)
        context, row = self.current("calibrate")
        self.assertEqual(context["status"], "REUSED")
        self.assertEqual(len(row["runs"]), 21)
        self.assertEqual(row["runs"][0]["status"], "INVALID")
        self.assertEqual(original["runs"][0]["status"], "INVALID")

    def test_source_raw_hash_mismatch_blocks_reuse_and_retry(self):
        original = self.add_measurement()
        path = self.root / original["runs"][0]["result"]
        path.write_text("{}")
        with self.assertRaisesRegex(c.ComparisonError, "hash mismatch"):
            self.current("calibrate")
        self.assertEqual(len(self.flow.ledger), 1)

    def test_source_pair_values_and_order_are_checked_against_raw(self):
        original = self.add_measurement()
        original["pairs"][0]["a"]["disk.latency"] = 12345
        self.write_report(original)
        with self.assertRaisesRegex(c.ComparisonError, "pair values/order"):
            self.current("calibrate")

    def test_missing_new_identity_never_reuses_older_result(self):
        original = self.add_measurement()
        del original["protocol_sha256"]
        self.write_report(original)
        with self.assertRaisesRegex(c.ComparisonError, "exact protocol"):
            self.current("calibrate")

    def test_failed_calibration_cannot_be_retried_by_new_plan(self):
        original = self.add_measurement()
        original.update(status="CALIBRATION_NOISY")
        original["analysis"]["passed"] = False
        self.write_report(original)
        self.contract["id"] = "another-plan"
        c.freeze(self.root, self.contract, self.protocol)
        with self.assertRaisesRegex(c.ComparisonError, "already failed/noisy/incomplete"):
            self.current("calibrate")

    def test_incomplete_source_contrast_cannot_be_retried(self):
        self.add_measurement()
        original = self.add_measurement("evaluate", ident="interrupted", started=180, finished=200)
        original.update(status="INTERRUPTED", analysis=None)
        self.write_report(original)
        with self.assertRaisesRegex(c.ComparisonError, "terminal"):
            self.current()

    def test_equivalent_tree_changed_commit_cannot_buy_trial(self):
        self.add_measurement()
        original = self.add_measurement("evaluate", comparison=True, ident="upstream",
                                        started=180, finished=200)
        original["candidate_commit"] = "f" * 40
        self.write_report(original)
        with self.assertRaisesRegex(c.ComparisonError, "equivalent code"):
            self.current()

    def test_failed_raw_environment_cannot_be_reused(self):
        original = self.add_measurement()
        attempt = original["runs"][0]
        raw = self.seed.root / attempt["result"]
        data = json.loads(raw.read_bytes())
        data["accelerator"] = "kvm"
        attempt["result_sha256"] = self.seed.put(attempt["result"], data)
        self.seed.put(str(Path(attempt["result"]).with_suffix(".sha256")),
                      (attempt["result_sha256"] + "\n").encode())
        self.write_report(original)
        with self.assertRaisesRegex(c.ComparisonError, "raw environment"):
            self.current("calibrate")

    def test_exact_clear_review_and_veto_each_gate_preparation(self):
        self.recorded_reviews.pop()
        with self.assertRaisesRegex(c.ComparisonError, "clear review"):
            self.current("calibrate")
        with patch.object(r.reviews, "blockers", return_value=[{"summary": "unresolved"}]):
            with self.assertRaisesRegex(c.ComparisonError, "baseline has unresolved"):
                self.current("calibrate")

    def test_actual_worktree_head_is_checked(self):
        with patch.object(r, "_git_identity", return_value=("f" * 40, "e" * 40)):
            with self.assertRaisesRegex(c.ComparisonError, "worktree HEAD"):
                self.current("calibrate")

    def test_passed_expired_calibration_can_renew(self):
        self.add_measurement()
        with patch.object(r.time, "time", return_value=1200):
            context, row = self.current("calibrate")
        self.assertEqual(context["status"], "PLANNED")
        self.assertEqual(context["remaining_cost"]["calibration_guests"], 20)

    def test_noisy_earlier_calibration_cannot_be_hidden_by_later_pass(self):
        first = self.add_measurement()
        first.update(status="CALIBRATION_NOISY")
        first["analysis"]["passed"] = False
        self.write_report(first)
        self.add_measurement(ident="cal-two", started=180, finished=200)
        with self.assertRaisesRegex(c.ComparisonError, "already failed/noisy/incomplete"):
            self.current("calibrate")

    def test_incompatible_upstream_has_no_measurement_or_metric(self):
        self.contract["id"] = "not-compatible"
        self.contract["arms"]["upstream"] = {
            "compatibility": "incompatible", "reason": "different application base",
            "source": self.contract["arms"]["upstream"]["source"]}
        c.freeze(self.root, self.contract, self.protocol)
        context, row = self.current()
        self.assertEqual(context["status"], "NOT_COMPARABLE")
        self.assertIsNone(row["analysis"])
        self.assertEqual(self.commands, [])

    def test_duplicate_independent_comparisons_are_not_cherry_picked(self):
        self.add_measurement()
        self.add_measurement("evaluate", ident="first", started=180, finished=200)
        self.add_measurement("evaluate", ident="second", started=210, finished=220)
        with self.assertRaisesRegex(c.ComparisonError, "duplicate independent"):
            self.current()


if __name__ == "__main__":
    unittest.main()
