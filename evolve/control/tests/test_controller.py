# SPDX-License-Identifier: GPL-2.0-only
"""Synthetic controller tests only; these do not test a running Linux kernel."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
CONTROL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CONTROL))
from analysis import Invalid, analyze, artifact, digest, load_json, metrics
from controller import diff_guard
import controller as controller_module

BASE = "a" * 40
CANDIDATE = "b" * 40
PROTOCOL = "c" * 64


class ResultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="swap-next-analysis-")
        self.root = Path(self.tmp.name)
        self.policy = load_json(CONTROL / "config/policy.json")
        self.policy["measurement"].update(min_pairs=2, min_operations=4,
                                          bootstrap_resamples=2000,
                                          min_bootstrap_tail_samples=1)
        self.env = {k: "d" * 64 for k in ("compiler_sha256", "config_sha256",
                    "rootfs_sha256", "suite_sha256", "machine_profile_sha256")}
        log = self.root / "gate.log"
        log.write_text("SYNTHETIC fixture; not a real kernel run.\n")
        self.manifest = {
            "schema_version": 1, "experiment_id": "synthetic-unit-test",
            "execution_kind": "isolated_guest", "protocol_sha256": PROTOCOL,
            "baseline_commit": BASE, "candidate_commit": CANDIDATE,
            "environment": self.env,
            "gates": {g: {"status": "pass", "candidate_commit": CANDIDATE,
                         "evidence": {"path": "gate.log", "sha256": digest(log)}}
                      for g in self.policy["required_gates"]},
            "runs": [], "planned_run_ids": []
        }
        clock = 1000000
        for part_index, part in enumerate(self.policy["measurement"]["required_partitions"]):
            for work in self.policy["measurement"]["required_workloads"]:
                for pair_index in range(2):
                    order = "AB" if pair_index == 0 else "BA"
                    variants = ("baseline", "candidate") if order == "AB" else ("candidate", "baseline")
                    for variant in variants:
                        name = f"{part}-{work}-{pair_index}-{variant}"
                        raw = {
                            "schema_version": 1, "status": "completed",
                            "experiment_id": "synthetic-unit-test",
                            "run_id": name, "boot_id": name + "-boot",
                            "variant": variant,
                            "kernel_commit": BASE if variant == "baseline" else CANDIDATE,
                            "booted_commit": BASE if variant == "baseline" else CANDIDATE,
                            "environment": self.env, "partition": part, "workload": work,
                            "pair_id": "pair-" + str(pair_index), "order": order,
                            "seed": part_index * 100 + pair_index,
                            "started_unix": clock, "finished_unix": clock + 12,
                            "attempted_operations": 4, "completed_operations": 4,
                            "elapsed_s": 10 if variant == "baseline" else 9,
                            "cpu_core_seconds": 4, "latency_us": [100] * 4,
                            "backend_read_bytes": 8192, "backend_write_bytes": 8192,
                            "metadata_samples": [{"attributable_bytes": 8192, "occupied_slots": 1024}],
                            "swapout_pages": 8, "swapin_pages": 8,
                            "data_mismatches": 0, "timeouts": 0, "kernel_warnings": 0
                        }
                        path = self.root / (name + ".json")
                        path.write_text(json.dumps(raw))
                        self.manifest["runs"].append({"path": path.name, "sha256": digest(path)})
                        self.manifest["planned_run_ids"].append(name)
                        clock += 20
        self.save()

    def tearDown(self):
        self.tmp.cleanup()

    def save(self):
        self.path = self.root / "manifest.json"
        self.path.write_text(json.dumps(self.manifest))

    def change_run(self, index, **changes):
        desc = self.manifest["runs"][index]
        path = self.root / desc["path"]
        raw = load_json(path)
        raw.update(changes)
        path.write_text(json.dumps(raw))
        desc["sha256"] = digest(path)
        self.save()
        return raw

    def run_analysis(self):
        self.save()
        return analyze(self.path, self.policy, PROTOCOL, BASE, CANDIDATE)

    def test_complete_fixture_never_auto_accepts(self):
        result = self.run_analysis()
        self.assertEqual(result["verdict"], "NEEDS_CALIBRATION")
        self.assertFalse(result["auto_promote"])
        self.assertFalse(result["provenance_verified"])
        row = result["metrics"]["discovery/anon_disk"]["throughput_ops_s"]
        self.assertAlmostEqual(row["mean_paired_improvement"], 1 / 9)

    def test_calibrated_positive_result_still_requires_review(self):
        self.policy["thresholds_calibrated"] = True
        for spec in self.policy["metrics"].values():
            spec["min_gain"] = .02
            spec["max_regression"] = .01
        self.assertEqual(self.run_analysis()["verdict"], "REVIEW_REQUIRED")

    def test_regression_does_not_hide_in_average(self):
        self.policy["thresholds_calibrated"] = True
        for spec in self.policy["metrics"].values():
            spec["min_gain"] = .02
            spec["max_regression"] = .01
        self.change_run(1, latency_us=[1000] * 4)
        self.assertEqual(self.run_analysis()["verdict"], "REJECT_OR_NO_GAIN")

    def test_hash_mismatch(self):
        desc = self.manifest["runs"][0]
        (self.root / desc["path"]).write_text("{}")
        with self.assertRaisesRegex(Invalid, "hash mismatch"):
            self.run_analysis()

    def test_duplicate_run_id(self):
        first = self.manifest["planned_run_ids"][0]
        self.change_run(1, run_id=first)
        with self.assertRaisesRegex(Invalid, "run_id"):
            self.run_analysis()

    def test_incomplete_roster(self):
        self.manifest["runs"].pop()
        with self.assertRaisesRegex(Invalid, "roster"):
            self.run_analysis()

    def test_missing_workload(self):
        keep = [r for r in self.manifest["runs"] if "mixed_file_anon" not in r["path"]]
        self.manifest["runs"] = keep
        self.manifest["planned_run_ids"] = [load_json(self.root / r["path"])["run_id"] for r in keep]
        with self.assertRaisesRegex(Invalid, "coverage"):
            self.run_analysis()

    def test_skipped_gate_is_not_pass(self):
        self.manifest["gates"]["kcsan"]["status"] = "skip"
        with self.assertRaisesRegex(Invalid, "gate not passed"):
            self.run_analysis()

    def test_stale_gate(self):
        self.manifest["gates"]["kasan"]["candidate_commit"] = BASE
        with self.assertRaisesRegex(Invalid, "stale gate"):
            self.run_analysis()

    def test_wrong_boot_identity(self):
        self.change_run(1, booted_commit=BASE)
        with self.assertRaisesRegex(Invalid, "identity"):
            self.run_analysis()

    def test_mismatched_environment(self):
        self.change_run(1, environment=dict(self.env, rootfs_sha256="e" * 64))
        with self.assertRaisesRegex(Invalid, "environment"):
            self.run_analysis()

    def test_boolean_metric_rejected(self):
        self.change_run(1, elapsed_s=True)
        with self.assertRaisesRegex(Invalid, "boolean"):
            self.run_analysis()

    def test_nonfinite_metric_rejected(self):
        self.change_run(1, elapsed_s=float("nan"))
        with self.assertRaisesRegex(Invalid, "non-finite"):
            self.run_analysis()

    def test_no_actual_swap_activity(self):
        self.change_run(1, swapout_pages=0)
        with self.assertRaisesRegex(Invalid, "swap activity"):
            self.run_analysis()

    def test_data_corruption_rejected(self):
        self.change_run(1, data_mismatches=1)
        with self.assertRaisesRegex(Invalid, "correctness"):
            self.run_analysis()

    def test_incomplete_work_rejected(self):
        self.change_run(1, completed_operations=3)
        with self.assertRaisesRegex(Invalid, "incomplete work"):
            self.run_analysis()

    def test_timeout_rejected(self):
        self.change_run(1, status="timeout")
        with self.assertRaisesRegex(Invalid, "did not complete"):
            self.run_analysis()

    def test_confirmation_seeds_are_independent(self):
        indexes = [i for i, d in enumerate(self.manifest["runs"])
                   if d["path"].startswith("confirmation-anon_disk-0")]
        for i in indexes:
            self.change_run(i, seed=0)
        with self.assertRaisesRegex(Invalid, "reuses discovery"):
            self.run_analysis()

    def test_overlapping_runs_rejected(self):
        self.change_run(1, started_unix=1000001, finished_unix=1000013)
        with self.assertRaisesRegex(Invalid, "overlapping"):
            self.run_analysis()

    def test_wrong_protocol(self):
        self.manifest["protocol_sha256"] = "f" * 64
        with self.assertRaisesRegex(Invalid, "protocol"):
            self.run_analysis()

    def test_extra_pairs_must_remain_counterbalanced(self):
        originals = [load_json(self.root / self.manifest["runs"][i]["path"]) for i in (0, 1)]
        for extra in range(2):
            for variant_index, source in enumerate(originals):
                raw = copy.deepcopy(source)
                name = f"extra-{extra}-{variant_index}"
                raw.update(run_id=name, boot_id=name + "-boot", pair_id=f"extra-{extra}",
                           seed=1000 + extra, started_unix=2000000 + extra * 100 + variant_index * 20,
                           finished_unix=2000012 + extra * 100 + variant_index * 20)
                path = self.root / (name + ".json")
                path.write_text(json.dumps(raw))
                self.manifest["runs"].append({"path": path.name, "sha256": digest(path)})
                self.manifest["planned_run_ids"].append(name)
        with self.assertRaisesRegex(Invalid, "unbalanced"):
            self.run_analysis()

    def test_insufficient_bootstrap_precision(self):
        self.policy["measurement"]["bootstrap_resamples"] = 10
        with self.assertRaisesRegex(Invalid, "tail resolution"):
            self.run_analysis()

    def test_overflowing_derived_metric(self):
        self.change_run(1, elapsed_s=1e-309, cpu_core_seconds=1e-309)
        with self.assertRaisesRegex(Invalid, "non-finite"):
            self.run_analysis()

    def test_host_execution_rejected(self):
        self.manifest["execution_kind"] = "host"
        with self.assertRaisesRegex(Invalid, "host execution"):
            self.run_analysis()

    def test_duplicate_json_keys(self):
        p = self.root / "duplicate.json"
        p.write_text('{"a":1,"a":2}')
        with self.assertRaisesRegex(Invalid, "duplicate"):
            load_json(p)

    def test_path_traversal(self):
        with self.assertRaisesRegex(Invalid, "escapes"):
            artifact(self.root, {"path": "../escape.log", "sha256": "a" * 64})

    def test_symlink_evidence_rejected(self):
        (self.root / "link.log").symlink_to(self.root / "gate.log")
        with self.assertRaisesRegex(Invalid, "symlink"):
            artifact(self.root, {"path": "link.log", "sha256": digest(self.root / "gate.log")})


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="swap-next-guard-")
        self.root = Path(self.tmp.name)
        self.policy = load_json(CONTROL / "config/policy.json")
        self.git("init", "-q")
        self.git("config", "user.name", "Eric Zhang")
        self.git("config", "user.email", "zxh@xh-zhang.com")
        (self.root / "mm").mkdir()
        (self.root / "mm/swapfile.c").write_text("int swap_fixture;\n")
        (self.root / ".gitignore").write_text("*.secret\n")
        self.commit()
        self.base = self.git("rev-parse", "HEAD").strip()

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args],
                                       stderr=subprocess.DEVNULL).decode()

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-qm", "Synthetic guard test fixture")

    def guard(self):
        return diff_guard(self.root, self.base, self.policy)

    def test_allowed_small_commit(self):
        (self.root / "mm/swapfile.c").write_text("int swap_fixture_updated;\n")
        self.commit()
        self.assertEqual(self.guard()["status"], "SCOPE_PASS")

    def test_empty_candidate_rejected(self):
        with self.assertRaisesRegex(Invalid, "empty"):
            self.guard()

    def test_forbidden_controller_change(self):
        (self.root / "controller.py").write_text("pass\n")
        self.commit()
        with self.assertRaisesRegex(Invalid, "outside"):
            self.guard()

    def test_untracked_file_rejected(self):
        (self.root / "payload").write_text("anything")
        with self.assertRaisesRegex(Invalid, "dirty"):
            self.guard()

    def test_ignored_file_rejected(self):
        (self.root / "payload.secret").write_text("not a real secret")
        with self.assertRaisesRegex(Invalid, "dirty"):
            self.guard()

    def test_symlink_code_rejected(self):
        p = self.root / "mm/swapfile.c"
        p.unlink()
        p.symlink_to("/etc/passwd")
        self.commit()
        with self.assertRaisesRegex(Invalid, "type change|symlink"):
            self.guard()

    def test_executable_bit_rejected(self):
        (self.root / "mm/swapfile.c").chmod(0o755)
        self.commit()
        with self.assertRaisesRegex(Invalid, "mode change"):
            self.guard()

    def test_deletion_rejected(self):
        (self.root / "mm/swapfile.c").unlink()
        self.commit()
        with self.assertRaisesRegex(Invalid, "deletion"):
            self.guard()

    def test_rename_rejected_before_advisory_classification(self):
        self.git("mv", "mm/swapfile.c", "mm/swapfile_renamed.c")
        self.commit()
        with self.assertRaisesRegex(Invalid, "deletion/rename"):
            self.guard()

    def test_guard_records_only_added_paths(self):
        self.policy["allowed_add"] = ["mm/page_compress.c"]
        (self.root / "mm/page_compress.c").write_text("int added_fixture;\n")
        (self.root / "mm/swapfile.c").write_text("int modified_fixture;\n")
        self.commit()
        with patch.object(controller_module, "scope_profile", return_value=self.policy):
            self.assertEqual(self.guard()["added_paths"], ["mm/page_compress.c"])

    def test_campaign_cannot_widen_base_scope(self):
        (self.root / "mm/filemap.c").write_text("int memory_fixture;\n")
        self.commit()
        self.base = self.git("rev-parse", "HEAD").strip()
        (self.root / "mm/filemap.c").write_text("int memory_fixture_updated;\n")
        self.commit()
        self.policy["allowed_modify"].append("mm/filemap.c")
        with self.assertRaisesRegex(Invalid, "outside"):
            self.guard()

    def test_nested_added_path_rejected(self):
        p = self.root / "tools/testing/selftests/mm/swap_next_nested/arbitrary.c"
        p.parent.mkdir(parents=True)
        p.write_text("int nested;\n")
        self.commit()
        with self.assertRaisesRegex(Invalid, "outside"):
            self.guard()

    def test_patch_size_budget(self):
        (self.root / "mm/swapfile.c").write_text("\n".join("int x%d;" % i for i in range(400)) + "\n")
        self.commit()
        with self.assertRaisesRegex(Invalid, "line budget"):
            self.guard()


class LifecycleTests(unittest.TestCase):
    def test_closed_candidate_cannot_be_checked_again(self):
        with patch.object(controller_module, "registry", return_value={"old": {"status": "closed"}}):
            with self.assertRaisesRegex(Invalid, "closed"):
                controller_module.get_candidate("old")

    def test_static_checks_are_bound_to_guarded_commit(self):
        with tempfile.TemporaryDirectory(prefix="swap-next-static-") as directory:
            record = {"parent": BASE}
            snapshot = {"candidate_commit": CANDIDATE, "status": "SCOPE_PASS"}
            process = subprocess.CompletedProcess([], 0, b"", b"")
            with patch.object(controller_module, "trusted_control"), \
                 patch.object(controller_module, "active"), \
                 patch.object(controller_module, "get_candidate", return_value=(record, Path(directory))), \
                 patch.object(controller_module, "diff_guard", return_value=snapshot), \
                 patch.object(controller_module, "STATE", Path(directory)), \
                 patch.object(controller_module, "static_checker_identity", return_value={"controller_sha256": "c" * 64, "checkpatch_sha256": "d" * 64}), \
                 patch.object(controller_module, "git", return_value=b"synthetic patch") as git_mock, \
                 patch.object(controller_module.subprocess, "run", return_value=process) as run_mock, \
                 patch.object(controller_module, "event"):
                controller_module.check_candidate("trial", static=True)
                self.assertIn(CANDIDATE, git_mock.call_args.args)
                self.assertNotIn("HEAD", git_mock.call_args.args)
                diff_command = run_mock.call_args_list[0].args[0]
                self.assertEqual(diff_command[-1], CANDIDATE)


class StaticAdvisoryTests(unittest.TestCase):
    WARNING = (b"WARNING:FILE_PATH_CHANGES: added, moved or deleted file(s), "
               b"does MAINTAINERS need updating?\n")
    CHECKER = {"controller_sha256": "c" * 64, "checkpatch_sha256": "d" * 64}

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="swap-next-static-advisory-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.policy = {"allowed_add": ["mm/page_compress.c"]}
        self.snapshot = {"status": "SCOPE_PASS", "parent": BASE,
                         "candidate_commit": CANDIDATE,
                         "added_paths": ["mm/page_compress.c"]}

    @staticmethod
    def process(code=0, output=b""):
        return subprocess.CompletedProcess([], code, output, b"")

    def check(self, processes):
        with patch.object(controller_module, "trusted_control"), \
             patch.object(controller_module, "active"), \
             patch.object(controller_module, "policy", return_value=self.policy), \
             patch.object(controller_module, "get_candidate", return_value=({"parent": BASE}, self.root)), \
             patch.object(controller_module, "diff_guard", return_value=copy.deepcopy(self.snapshot)), \
             patch.object(controller_module, "STATE", self.root), \
             patch.object(controller_module, "CAMPAIGN", None), \
             patch.object(controller_module, "static_checker_identity", return_value=self.CHECKER), \
             patch.object(controller_module, "git", return_value=b"synthetic patch"), \
             patch.object(controller_module.subprocess, "run", side_effect=processes) as run, \
             patch.object(controller_module, "event"):
            result = controller_module.check_candidate("trial", static=True)
            self.commands = [call.args[0] for call in run.call_args_list]
            return result

    def test_allowed_add_advisory_preserves_raw_reject_and_history(self):
        out = self.root / "trial"
        out.mkdir()
        prior = b'{"status":"STATIC_REJECT","candidate_commit":"' + CANDIDATE.encode() + b'"}\n'
        (out / "static.json").write_bytes(prior)
        (out / "checkpatch.log").write_bytes(b"original untyped diagnostic\n")
        raw = self.WARNING + b"total: 0 errors, 1 warnings, 20 lines checked\n"
        clean = b"total: 0 errors, 0 warnings, 20 lines checked\n"
        result = self.check([self.process(), self.process(1, raw), self.process(0, clean)])
        self.assertEqual(result["status"], "SCOPE_PASS")
        self.assertEqual(result["checkpatch"]["exit_code"], 1)
        self.assertEqual(result["checkpatch-filtered"]["exit_code"], 0)
        self.assertEqual(result["checker_identity"], self.CHECKER)
        self.assertEqual(result["checkpatch_advisory"]["added_paths"], ["mm/page_compress.c"])
        log = Path(result["checkpatch"]["evidence"])
        self.assertEqual(log.read_bytes(), raw)
        self.assertEqual(digest(log), result["checkpatch"]["sha256"])
        self.assertEqual(Path(result["checkpatch-filtered"]["evidence"]).read_bytes(), clean)
        self.assertEqual((log.parent / "previous.json").read_bytes(), prior)
        self.assertEqual((out / "checkpatch.log").read_bytes(), b"original untyped diagnostic\n")
        self.assertEqual(load_json(log.parent / "result.json"), load_json(out / "static.json"))
        self.assertEqual(self.commands[-1][-3:], ["--ignore", "FILE_PATH_CHANGES", "-"])
        self.assertIn("--show-types", self.commands[-2])

    def test_other_original_diagnostics_and_process_errors_reject(self):
        for code, output in ((1, self.WARNING + b"WARNING:LONG_LINE: too long\n"),
                             (1, self.WARNING + b"ERROR:TRAILING_WHITESPACE: space\n"),
                             (1, self.WARNING + b"WARNING: untyped additional warning\n"),
                             (1, b"WARNING:FILE_PATH_CHANGES: unexpected wording\n"),
                             (2, self.WARNING)):
            with self.subTest(code=code, output=output):
                result = self.check([self.process(), self.process(code, output)])
                self.assertEqual(result["status"], "STATIC_REJECT")
                self.assertNotIn("checkpatch-filtered", result)
                self.assertNotIn("checkpatch_advisory", result)

    def test_no_additions_or_not_exactly_allowed_additions_reject(self):
        for added, allowed in (([], ["mm/page_compress.c"]),
                               (["mm/unlisted.c"], ["mm/page_compress.c"]),
                               (["mm/page_compress.c"], ["mm/*.c"])):
            with self.subTest(added=added, allowed=allowed):
                self.snapshot["added_paths"] = added
                self.policy["allowed_add"] = allowed
                result = self.check([self.process(), self.process(1, self.WARNING)])
                self.assertEqual(result["status"], "STATIC_REJECT")
                self.assertEqual(len(self.commands), 2)

    def test_filtered_failure_or_remaining_diagnostic_rejects(self):
        for code, output in ((1, b"WARNING:LONG_LINE: too long\n"),
                             (0, b"WARNING:LONG_LINE: too long\n"), (2, b"checker failed\n")):
            with self.subTest(code=code):
                result = self.check([self.process(), self.process(1, self.WARNING),
                                     self.process(code, output)])
                self.assertEqual(result["status"], "STATIC_REJECT")
                self.assertNotIn("checkpatch_advisory", result)

    def test_diff_check_failure_survives_advisory_classification(self):
        result = self.check([self.process(2, b"bad diff\n"), self.process(1, self.WARNING), self.process()])
        self.assertEqual(result["status"], "STATIC_REJECT")
        self.assertEqual(result["diff-check"]["exit_code"], 2)

    def test_checker_identity_binds_both_executed_sources(self):
        control, linux = self.root / "control", self.root / "linux"
        control.mkdir()
        (linux / "scripts").mkdir(parents=True)
        (control / "controller.py").write_text("controller version one\n")
        (linux / "scripts/checkpatch.pl").write_text("checker version one\n")
        with patch.object(controller_module, "CONTROL", control), patch.object(controller_module, "ROOT", linux):
            first = controller_module.static_checker_identity()
            (control / "controller.py").write_text("controller version two\n")
            second = controller_module.static_checker_identity()
            self.assertNotEqual(first["controller_sha256"], second["controller_sha256"])
            self.assertEqual(first["checkpatch_sha256"], second["checkpatch_sha256"])
            (linux / "scripts/checkpatch.pl").write_text("checker version two\n")
            third = controller_module.static_checker_identity()
            self.assertNotEqual(second["checkpatch_sha256"], third["checkpatch_sha256"])


if __name__ == "__main__":
    unittest.main()
