# SPDX-License-Identifier: GPL-2.0-only
"""Guest-free comparator fixtures; no kernel build or guest is launched."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from evolve import comparisons as c


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fixture():
    protocol = {"campaign": "comparison-fixture", "baseline_commit": "a" * 40,
                "baseline_build": "base-build", "protocol_revision": 7,
                "accelerator": {"require": "kvm"},
                "guest": {"vcpus": 8, "mem_mib": 8192, "swap_gib": 16},
                "cases": {"disk": {"workload": "swapin", "mode": "xswap", "backend": "disk",
                                  "metrics": {"latency": "lower"}, "primary": "latency"}},
                "tiers": {"fast": {"cases": ["disk"], "comparison_pairs": 4,
                                  "calibration_pairs": 10}},
                "validity": {"reruns_per_arm": 1},
                "required_correctness_gates": ["data_roundtrip"]}
    arms = {}
    for name, letter, build in (("baseline", "a", "base-build"),
                               ("upstream", "b", "upstream-build"),
                               ("candidate", "c", "candidate-build")):
        arms[name] = {"compatibility": "compatible", "commit": letter * 40,
                      "tree": letter * 40, "build": build,
                      "build_manifest_sha256": letter * 64, "patch_sha256": letter * 64,
                      "correctness": [], **({"candidate": name + "-record"} if name != "baseline" else {})}
    arms["upstream"]["source"] = {"url": "https://lore.kernel.org/example", "revision": "v3",
                                 "patch_sha256": "d" * 64, "dependencies": []}
    contract = {"schema_version": 1, "id": "compare-one", "campaign": protocol["campaign"],
                "protocol_sha256": sha(c.canonical_bytes(protocol)),
                "environment": {"machine": "hurricpc", "fingerprint": "f" * 64,
                                "accelerator": "kvm", "guest": copy.deepcopy(protocol["guest"]),
                                "input_config_sha256": "e" * 64, "guest_image_sha256": "d" * 64},
                "common_base": {"commit": "a" * 40, "tree": "a" * 40}, "tier": "fast",
                "pair_order": ["AB", "BA", "AB", "BA"],
                "correctness_routes": [{"mode": "xswap", "backend": "disk"}],
                "arms": arms,
                "contrasts": [{"id": "upstream-control", "control": "baseline", "treatment": "upstream"},
                              {"id": "candidate-control", "control": "baseline", "treatment": "candidate"}]}
    return contract, protocol


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.contract, self.protocol = fixture()

    def test_plan_is_deterministic_and_does_not_change_protocol(self):
        before = copy.deepcopy((self.contract, self.protocol))
        plan = c.execution_plan(self.contract, self.protocol, "candidate-control")
        self.assertEqual(plan, c.execution_plan(self.contract, self.protocol, "candidate-control"))
        self.assertEqual(before, (self.contract, self.protocol))
        self.assertEqual(plan["required_guests"], 8)
        self.assertEqual([(r["pair"], r["slot"], r["arm"]) for r in plan["schedule"][:4]],
                         [(0, "a", "baseline"), (0, "b", "candidate"),
                          (1, "b", "candidate"), (1, "a", "baseline")])
        self.assertEqual(plan["directions"], {"disk.latency": "lower"})
        self.assertEqual(plan["primary"], ["disk.latency"])

    def test_distinct_control_calibration_and_same_control_reuse_key(self):
        upstream = c.execution_plan(self.contract, self.protocol, "upstream-control", "calibrate")
        candidate = c.execution_plan(self.contract, self.protocol, "candidate-control", "calibrate")
        self.assertEqual(upstream["calibration_key"], candidate["calibration_key"])
        self.assertEqual({r["arm"] for r in upstream["schedule"]}, {"baseline"})
        self.contract["contrasts"].append(
            {"id": "candidate-upstream", "control": "upstream", "treatment": "candidate"})
        direct = c.execution_plan(self.contract, self.protocol, "candidate-upstream", "calibrate")
        self.assertNotEqual(direct["calibration_key"], candidate["calibration_key"])
        self.assertEqual({r["arm"] for r in direct["schedule"]}, {"upstream"})

    def test_cost_includes_control_repetition_correctness_and_reruns(self):
        cost = c.planned_cost(self.contract, self.protocol)
        self.assertEqual(cost["distinct_controls"], 1)
        self.assertEqual(cost["calibration_guests"], 20)
        self.assertEqual(cost["comparison_guests"], 16)
        self.assertEqual(cost["correctness_guests_minimum"], 3)
        self.assertEqual(cost["minimum_total_guests"], 39)
        self.assertEqual(cost["performance_guests_with_maximum_reruns"], 72)
        self.contract["contrasts"].append(
            {"id": "candidate-upstream", "control": "upstream", "treatment": "candidate"})
        self.assertEqual(c.planned_cost(self.contract, self.protocol)["minimum_total_guests"], 67)

    def test_incompatible_is_explicit_not_zero(self):
        self.contract["arms"]["upstream"] = {
            "compatibility": "incompatible", "reason": "series requires another base",
            "source": self.contract["arms"]["upstream"]["source"]}
        result = c.execution_plan(self.contract, self.protocol, "upstream-control")
        self.assertEqual(result["status"], "NOT_COMPARABLE")
        self.assertEqual(result["schedule"], [])
        report = c.reconcile(self.contract, self.protocol, [])
        self.assertIsNone(report["outcomes"][0]["analysis"])
        self.assertEqual(report["outcomes"][1]["status"], "PENDING")
        self.assertFalse(report["performance_accepted"])
        self.assertEqual(c.planned_cost(self.contract, self.protocol)["not_comparable"],
                         ["upstream-control"])

    def test_optional_composition_pins_both_inputs(self):
        self.contract["arms"]["combined"] = dict(
            self.contract["arms"]["candidate"], commit="d" * 40, tree="d" * 40,
            build="combined-build", candidate="combined-record",
            composition={"upstream_commit": "b" * 40, "candidate_commit": "c" * 40,
                         "rationale": "test incremental benefit"})
        self.contract["contrasts"].append(
            {"id": "combined-upstream", "control": "upstream", "treatment": "combined"})
        c.validate(self.contract, self.protocol)
        self.contract["arms"]["combined"]["composition"]["candidate_commit"] = "f" * 40
        with self.assertRaisesRegex(c.ComparisonError, "composition"):
            c.validate(self.contract, self.protocol)

    def test_same_tree_and_build_do_not_buy_new_arm(self):
        for key in ("tree", "build"):
            contract = copy.deepcopy(self.contract)
            contract["arms"]["candidate"][key] = contract["arms"]["upstream"][key]
            with self.subTest(key=key), self.assertRaises(c.ComparisonError):
                c.validate(contract, self.protocol)

    def test_unmatched_environment_protocol_and_order_rejected(self):
        for path, value in [(("environment", "accelerator"), "tcg"),
                            (("environment", "guest"), {"vcpus": 2}),
                            (("common_base", "commit"), "f" * 40),
                            (("pair_order",), ["BA", "AB", "BA", "AB"]),
                            (("schema_version",), True)]:
            contract = copy.deepcopy(self.contract)
            dest = contract
            for part in path[:-1]:
                dest = dest[part]
            dest[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(c.ComparisonError):
                c.validate(contract, self.protocol)
        with self.assertRaisesRegex(c.ComparisonError, "protocol hash"):
            c.validate(self.contract, self.protocol, "0" * 64)

    def test_unknown_and_duplicate_contrasts_rejected(self):
        for change in ("unknown", "duplicate", "missing"):
            contract = copy.deepcopy(self.contract)
            if change == "unknown":
                contract["contrasts"][0]["control"] = "other"
            elif change == "duplicate":
                contract["contrasts"].append(copy.deepcopy(contract["contrasts"][0]))
            else:
                contract["contrasts"].pop()
            with self.subTest(change=change), self.assertRaises(c.ComparisonError):
                c.validate(contract, self.protocol)

    def test_correctness_route_cannot_be_silently_narrowed(self):
        self.protocol["cases"]["compressed"] = dict(
            self.protocol["cases"]["disk"], backend="zswap")
        with self.assertRaisesRegex(c.ComparisonError, "route coverage"):
            c.validate(self.contract, self.protocol)
        self.protocol["comparison_correctness_routes"] = self.contract["correctness_routes"]
        c.validate(self.contract, self.protocol)

    def test_finite_data_and_safe_evidence_paths(self):
        for value in (float("nan"), float("inf")):
            contract = copy.deepcopy(self.contract)
            contract["untrusted_score"] = value
            with self.assertRaisesRegex(c.ComparisonError, "finite JSON"):
                c.validate(contract, self.protocol)
        self.contract["arms"]["candidate"]["correctness"] = [
            {"path": "../outside.json", "sha256": "a" * 64}]
        with self.assertRaisesRegex(c.ComparisonError, "path"):
            c.validate(self.contract, self.protocol)

    def test_missing_upstream_revision_is_not_a_named_comparator(self):
        self.contract["arms"]["upstream"]["source"].pop("revision")
        with self.assertRaisesRegex(c.ComparisonError, "series revision"):
            c.validate(self.contract, self.protocol)


class FileFixture(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.contract, self.protocol = fixture()
        self.protocol_path = self.root / "campaigns/comparison-fixture/protocol.json"
        self.protocol_path.parent.mkdir(parents=True)
        self.protocol_path.write_bytes(c.canonical_bytes(self.protocol))


class FilesTests(FileFixture):
    def test_freeze_and_load_are_idempotent_and_protocol_immutable(self):
        before = self.protocol_path.read_bytes()
        first = c.freeze(self.root, self.contract, self.protocol)
        path = self.root / first["path"]
        stamp = path.stat().st_mtime_ns
        self.assertEqual(first, c.freeze(self.root, self.contract, self.protocol))
        self.assertEqual(stamp, path.stat().st_mtime_ns)
        self.assertEqual(c.load(self.root, "comparison-fixture", "compare-one", self.protocol),
                         self.contract)
        self.assertEqual(before, self.protocol_path.read_bytes())
        self.contract["arms"]["upstream"]["source"]["revision"] = "v4"
        with self.assertRaisesRegex(c.ComparisonError, "cannot be replaced"):
            c.freeze(self.root, self.contract, self.protocol)

    def test_load_refuses_modified_protocol_or_noncanonical_contract(self):
        first = c.freeze(self.root, self.contract, self.protocol)
        (self.root / first["path"]).write_text(json.dumps(self.contract))
        with self.assertRaisesRegex(c.ComparisonError, "canonical"):
            c.load(self.root, "comparison-fixture", "compare-one", self.protocol)
        (self.root / first["path"]).write_bytes(c.canonical_bytes(self.contract))
        self.protocol_path.write_text(json.dumps(self.protocol))
        with self.assertRaisesRegex(c.ComparisonError, "protocol hash"):
            c.load(self.root, "comparison-fixture", "compare-one", self.protocol)

    def test_symlink_contract_directory_rejected(self):
        other = self.root / "elsewhere"
        other.mkdir()
        (self.protocol_path.parent / "comparisons").symlink_to(other, target_is_directory=True)
        with self.assertRaisesRegex(c.ComparisonError, "symlink"):
            c.freeze(self.root, self.contract, self.protocol)


class EvidenceTests(FileFixture):
    def setUp(self):
        super().setUp()
        self.source = self.root / "source"
        self.source.mkdir()
        self.git("init", "-q")
        self.git("config", "--local", "user.name", "Swap Next fixture")
        self.git("config", "--local", "user.email", "fixture@example.invalid")
        self.commit_file("base.txt", "common\n")
        base = self.git("rev-parse", "HEAD")
        tree = self.git("rev-parse", "HEAD^{tree}")
        self.protocol["baseline_commit"] = base
        self.contract["common_base"] = {"commit": base, "tree": tree}
        self.protocol_path.write_bytes(c.canonical_bytes(self.protocol))
        self.contract["protocol_sha256"] = sha(self.protocol_path.read_bytes())
        self.contract["environment"]["input_config_sha256"] = sha(b"CONFIG_SWAP=y\n")
        self.put("benchmark/config/swap-standard.config", b"CONFIG_SWAP=y\n")
        self.put("benchmark/swap-standard/image.json",
                 {"image_sha256": self.contract["environment"]["guest_image_sha256"]})
        self.put("campaigns/comparison-fixture/campaign.json", {"machine": "hurricpc"})
        upstream_source = self.contract["arms"]["upstream"]["source"]
        source_path = "campaigns/comparison-fixture/patches/upstream.mbox"
        upstream_source["patch_sha256"] = self.put(source_path, b"fixture upstream patch bytes\n")
        upstream_source["artifact"] = {"path": source_path, "sha256": upstream_source["patch_sha256"]}
        for name in ("baseline", "upstream", "candidate"):
            if name != "baseline":
                self.git("checkout", "-q", "--detach", base)
                self.commit_file(name + ".txt", name + "\n")
            arm = self.contract["arms"][name]
            arm["commit"] = self.git("rev-parse", "HEAD")
            arm["tree"] = self.git("rev-parse", "HEAD^{tree}")
            arm["patch_sha256"] = sha(self.git("diff", "--no-ext-diff", "--no-textconv",
                "--binary", "--full-index", base, arm["commit"], "--", binary=True))
            self.build(name)
        self.sources_before = self.git("status", "--porcelain")

    def git(self, *args, binary=False):
        output = subprocess.check_output(["git", "-C", str(self.source), *args],
                                         stderr=subprocess.DEVNULL)
        return output if binary else output.decode().strip()

    def commit_file(self, name, content):
        (self.source / name).write_text(content)
        self.git("add", name)
        self.git("commit", "-qm", "fixture")

    def put(self, path, content):
        path = self.root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else c.canonical_bytes(content))
        return sha(path.read_bytes())

    def build(self, name):
        arm = self.contract["arms"][name]
        prefix = "benchmark/kernel/builds/" + arm["build"]
        manifest = {"commit": arm["commit"], "passed": True, "exit_code": 0,
                    "instrument_sha256": None,
                    "input_config_sha256": self.contract["environment"]["input_config_sha256"],
                    "config_sha256": self.put(prefix + "/output/.config", b"fixture config\n"),
                    "image_sha256": self.put(prefix + "/output/arch/x86/boot/bzImage",
                                             (name + " fixture only\n").encode())}
        arm["build_manifest_sha256"] = self.put(prefix + "/result.json", manifest)
        proof = {"source_commit": arm["commit"], "candidate_commit": arm["commit"],
                 "build_manifest_sha256": arm["build_manifest_sha256"],
                 "protocol_sha256": self.contract["protocol_sha256"],
                 "passed": True, "integration_pass": True, "mode": "xswap", "backend": "disk"}
        path = "campaigns/comparison-fixture/runs/" + name + "-correctness.json"
        arm["correctness"] = [{"path": path, "sha256": self.put(path, proof)}]

    def validate(self, **kwargs):
        return c.validate_evidence(self.contract, self.protocol, self.root,
                                   "f" * 64, "hurricpc", source_repo=self.source,
                                   correctness_validator=lambda raw, p, root: raw, **kwargs)

    def test_exact_git_build_and_proof_identity(self):
        result = self.validate()
        self.assertEqual(set(result["arms"]), {"baseline", "upstream", "candidate"})
        self.assertEqual(result["contract_sha256"], c.digest(self.contract))
        self.assertEqual(self.sources_before, self.git("status", "--porcelain"))
        self.assertEqual(self.protocol_path.read_bytes(), c.canonical_bytes(self.protocol))

    def test_wrong_tree_patch_build_and_raw_file_rejected(self):
        for field in ("tree", "patch_sha256", "build_manifest_sha256"):
            original = self.contract["arms"]["candidate"][field]
            self.contract["arms"]["candidate"][field] = "e" * len(original)
            with self.subTest(field=field), self.assertRaises(c.ComparisonError):
                self.validate()
            self.contract["arms"]["candidate"][field] = original
        proof = self.contract["arms"]["candidate"]["correctness"][0]
        (self.root / proof["path"]).write_text("{}")
        with self.assertRaisesRegex(c.ComparisonError, "hash mismatch"):
            self.validate()

    def test_incompatible_git_ancestry_rejected(self):
        self.git("checkout", "--orphan", "unrelated")
        self.git("rm", "-q", "-rf", ".")
        self.commit_file("foreign.txt", "unrelated\n")
        arm = self.contract["arms"]["candidate"]
        arm.update(commit=self.git("rev-parse", "HEAD"), tree=self.git("rev-parse", "HEAD^{tree}"))
        with self.assertRaisesRegex(c.ComparisonError, "ancestry"):
            c.verify_sources(self.contract, self.source)

    def test_correctness_coverage_and_exact_source_cannot_be_forged(self):
        arm = self.contract["arms"]["candidate"]
        ref = arm["correctness"][0]
        proof = json.loads((self.root / ref["path"]).read_bytes())
        for field, value in (("source_commit", "f" * 40), ("backend", "zswap"),
                             ("passed", False), ("protocol_sha256", "e" * 64)):
            altered = dict(proof, **{field: value})
            ref["sha256"] = self.put(ref["path"], altered)
            with self.subTest(field=field), self.assertRaises(c.ComparisonError):
                self.validate()
        arm["correctness"] = []
        with self.assertRaisesRegex(c.ComparisonError, "missing correctness"):
            self.validate()

    def test_environment_mismatch_is_not_comparable_evidence(self):
        for field, value in (("machine", "other"), ("fingerprint", "e" * 64),
                             ("guest_image_sha256", "e" * 64),
                             ("input_config_sha256", "b" * 64)):
            original = self.contract["environment"][field]
            self.contract["environment"][field] = value
            with self.subTest(field=field), self.assertRaises(c.ComparisonError):
                self.validate()
            self.contract["environment"][field] = original

    def test_upstream_patch_bytes_must_exist_and_match_the_source_record(self):
        source = self.contract["arms"]["upstream"]["source"]
        (self.root / source["artifact"]["path"]).write_bytes(b"modified source")
        with self.assertRaisesRegex(c.ComparisonError, "hash mismatch"):
            self.validate()
        source.pop("artifact")
        with self.assertRaisesRegex(c.ComparisonError, "patch artifact"):
            self.validate()

    def test_native_validator_rejects_summary_without_raw_runner_evidence(self):
        module_source = Path(__file__).parent / "control/correctness_proof.py"
        self.put("evolve/control/correctness_proof.py", module_source.read_bytes())
        with self.assertRaisesRegex(ValueError, "raw runner proof schema"):
            c.validate_evidence(self.contract, self.protocol, self.root, "f" * 64,
                                "hurricpc", source_repo=self.source)

    def test_composition_is_descendant_of_upstream(self):
        upstream = self.contract["arms"]["upstream"]
        candidate = self.contract["arms"]["candidate"]
        self.git("checkout", "-q", "--detach", upstream["commit"])
        self.commit_file("candidate.txt", "candidate\n")
        combined = copy.deepcopy(candidate)
        combined.update(commit=self.git("rev-parse", "HEAD"), tree=self.git("rev-parse", "HEAD^{tree}"),
                        build="combined-build", candidate="combined-record",
                        composition={"upstream_commit": upstream["commit"],
                                     "candidate_commit": candidate["commit"], "rationale": "composition"})
        combined["patch_sha256"] = sha(self.git("diff", "--no-ext-diff", "--no-textconv",
            "--binary", "--full-index", self.contract["common_base"]["commit"], combined["commit"],
            "--", binary=True))
        self.contract["arms"]["combined"] = combined
        self.contract["contrasts"].append(
            {"id": "combined-upstream", "control": "upstream", "treatment": "combined"})
        self.build("combined")
        self.assertIn("combined", self.validate()["arms"])


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.contract, self.protocol = fixture()
        self.plan = c.execution_plan(self.contract, self.protocol, "candidate-control")
        self.row = {"id": "evaluation-one", "action": "evaluate", "tier": "fast", "status": "FAST_PASS",
                    "protocol_sha256": self.contract["protocol_sha256"],
                    "fingerprint": self.contract["environment"]["fingerprint"],
                    "comparison": self.plan["identity"],
                    "analysis": {"status": "FAST_PASS", "pair_count": 4, "combined_score": 1.1,
                                 "performance_accepted": False, "auto_promote": False,
                                 "metrics": {"disk.latency": {
                                     "median_ratio": 1.1, "noise_relative": .03, "guard_pass": True}}}}

    def outcome(self, rows):
        return c.reconcile(self.contract, self.protocol, rows)["outcomes"][1]

    def test_report_keeps_direct_measured_comparisons_only(self):
        report = c.reconcile(self.contract, self.protocol, [self.row])
        self.assertEqual([r["status"] for r in report["outcomes"]], ["PENDING", "FAST_PASS"])
        self.assertEqual(report["outcomes"][1]["analysis"]["combined_score"], 1.1)
        self.assertFalse(report["performance_accepted"])
        self.assertFalse(report["auto_promote"])

    def test_foreign_measurement_cannot_enter_report(self):
        for key, value in (("fingerprint", "e" * 64), ("protocol_sha256", "e" * 64),
                           ("tier", "slow")):
            row = dict(self.row, **{key: value})
            with self.subTest(key=key):
                self.assertEqual(self.outcome([row])["status"], "INCOMPLETE")
                self.assertIsNone(self.outcome([row])["analysis"])

    def test_failures_and_missing_values_remain_failures(self):
        row = dict(self.row, status="INCOMPLETE", reason="guest result missing", analysis=None)
        self.assertEqual(self.outcome([row])["reasons"], ["guest result missing"])
        for value in (float("nan"), float("inf"), True, 0, 10 ** 1000):
            row = copy.deepcopy(self.row)
            row["analysis"]["metrics"]["disk.latency"]["median_ratio"] = value
            with self.subTest(value=value):
                self.assertEqual(self.outcome([row])["status"], "INCOMPLETE")

    def test_duplicates_are_not_silently_selected_for_best_result(self):
        self.assertEqual(self.outcome([self.row, dict(self.row, id="evaluation-two")])["status"],
                         "INCOMPLETE")

    def test_calibration_reuse_checks_exact_control_and_age(self):
        calibration = dict(self.row, action="calibrate", finished=100,
                           analysis={"passed": True, "status": "CALIBRATED", "pair_count": 10,
                                     "directions": self.plan["directions"], "primary": self.plan["primary"]},
                           status="CALIBRATED")
        self.assertTrue(c.reusable_calibration(calibration, self.plan, self.contract, 110, 60))
        for field, value in (("finished", 200), ("finished", 1), ("fingerprint", "a" * 64),
                             ("protocol_sha256", "b" * 64), ("status", "INCOMPLETE")):
            row = dict(calibration, **{field: value})
            with self.subTest(field=field, value=value):
                self.assertFalse(c.reusable_calibration(row, self.plan, self.contract, 110, 60))
        changed = copy.deepcopy(calibration)
        changed["comparison"]["control_commit"] = "d" * 40
        self.assertFalse(c.reusable_calibration(changed, self.plan, self.contract, 110, 60))
        changed = dict(calibration, analysis={"passed": False})
        self.assertFalse(c.reusable_calibration(changed, self.plan, self.contract, 110, 60))


if __name__ == "__main__":
    unittest.main()
