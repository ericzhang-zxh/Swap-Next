# SPDX-License-Identifier: GPL-2.0-only
"""Synthetic revision-8 coverage fixtures; no kernel build or guest execution."""
import copy
from contextlib import ExitStack, redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from evolve import reference_cache as cache
from evolve import standard_workflow as workflow

proofs = workflow.correctness_proof
SOURCE = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_catalog(root):
    spec = importlib.util.spec_from_file_location("coverage_fixture_configurations",
        root / "benchmark/swap-standard/configurations.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture_protocol(catalog, root, baseline):
    groups = [
        ("b-common", "baseline", "regression"), ("b-legacy", "baseline", "legacy-roundtrip"),
        ("c-common", "candidate", "regression"), ("c-legacy", "candidate", "legacy-lifecycle"),
        ("c-compressed", "candidate", "compressed-roundtrip"), ("c-debug", "candidate", "debug-failures"),
        ("c-race", "candidate", "race-lifecycle"), ("c-numa", "candidate", "numa-lifecycle"),
    ]
    rows = [dict(id=name, role=role, group=group, **copy.deepcopy(catalog.GROUPS[group]))
            for name, role, group in groups]
    configs = {name: {"input_config_sha256": catalog.get_config(name, root)["input_config_sha256"]}
               for name in catalog.CONFIGS if name.startswith("c1-")}
    return {
        "campaign": "fixture-c1", "protocol_revision": 8, "baseline_commit": baseline,
        "baseline_build": "c1-baseline-common", "configurations": configs,
        "guest": {"vcpus": 4, "mem_mib": 4096, "swap_gib": 16}, "accelerator": {"require": "tcg"},
        "cases": {"compressed": {"config_id": "c1-common", "topology_id": "single",
            "workload": "swapin", "backend": "compressed", "mode": "xswap",
            "primary": "swapin_seq.mean_ns", "metrics": {"swapin_seq.mean_ns": "lower"}}},
        "required_correctness_gates": [*catalog.BASE_GATES, "compression_roundtrip",
            "compression_library_unit", "compression_guest_hotplug", "compression_memcg_limits",
            "compression_large_folio", "kasan", "lockdep", "kcsan"],
        "correctness_matrix": {"schema_version": 1, "cases": rows, "build_only": [
            {"id": "c-noswap", "role": "candidate", "config_id": "c1-noswap"},
            {"id": "c-no-frontends", "role": "candidate", "config_id": "c1-no-frontends"}]},
        "budget": {"build_attempts": 10, "guest_attempts": 88, "probe_guest_attempts": 32,
                   "wall_seconds": 64800, "guest_timeout": 900},
        "tiers": {"fast": {"cases": ["compressed"]}},
    }


class CoverageFixture:
    def __init__(self, root, populate=True):
        self.root = root
        for relative in ["benchmark/swap-standard/configurations.py", *(
                "benchmark/config/" + name for name in (
                    "swap-standard.config", "compression-common.config", "compression-legacy.config",
                    "compression-debug.config", "compression-kcsan.config", "compression-noswap.config",
                    "compression-no-frontends.config")), "benchmark/kernel/build.py",
                "benchmark/kernel/build_namespace.sh", "benchmark/kernel/lifetime.py",
                "evolve/control/correctness_proof.py", "benchmark/swap-standard/validity.py"]:
            self.put(relative, (SOURCE / relative).read_bytes())
        self.catalog = load_catalog(root)
        linux = root / "linux"
        linux.mkdir()
        subprocess.run(["git", "init", "-q", str(linux)], check=True)
        self.commits, self.trees = {}, {}
        for role in ("baseline", "candidate"):
            (linux / "fixture.txt").write_text(role + "\n")
            subprocess.run(["git", "-C", str(linux), "add", "fixture.txt"], check=True)
            subprocess.run(["git", "-C", str(linux), "-c", "user.name=Fixture",
                            "-c", "user.email=fixture@example.invalid", "commit", "-qm", role], check=True)
            self.commits[role] = subprocess.check_output(
                ["git", "-C", str(linux), "rev-parse", "HEAD"], text=True).strip()
            self.trees[role] = subprocess.check_output(
                ["git", "-C", str(linux), "rev-parse", "HEAD^{tree}"], text=True).strip()
        self.protocol = fixture_protocol(self.catalog, root, self.commits["baseline"])
        self.put("campaigns/fixture-c1/protocol.json", self.protocol)
        self.put("campaigns/fixture-c1/campaign.json", {"machine": "fixture"})
        self.put("benchmark/swap-standard/run.py", b"# Synthetic runner identity only.\n")
        # Matrix attestation is tested independently from H1's serial parser.
        self.put("benchmark/swap-standard/evidence.py",
                 b"import json\nATTRIBUTABLE_FIELDS = frozenset()\n\ndef parse(serial, *args, **kwargs):\n    return json.loads(serial)\n")
        self.put("benchmark/swap-standard/compression.c", b"/* Synthetic observer identity only. */\n")
        self.put("benchmark/swap-standard/bench.img", b"Synthetic guest image; never booted.")
        self.put("benchmark/swap-standard/initramfs.cpio.gz", b"Synthetic initrd; never booted.")
        self.image = {"image_sha256": self.digest("benchmark/swap-standard/bench.img"),
                      "initrd_sha256": self.digest("benchmark/swap-standard/initramfs.cpio.gz"),
                      "sources": {"compression.c": self.digest("benchmark/swap-standard/compression.c")}}
        self.put("benchmark/swap-standard/image.json", self.image)
        self.environment = self.catalog.build_environment(root)
        self.ledger, self.builds, self.raw = [], {}, {}
        self.put("campaigns/fixture-c1/ledger/budget.json",
                 {"guests": 0, "probe_guests": 0, "builds": 0})
        self.put("campaigns/fixture-c1/ledger/ledger.json", [])
        if populate:
            matrix = self.catalog.validate_protocol(self.protocol, root)
            for case in matrix["cases"] + matrix["build_only"]:
                key = (case["role"], case["config_id"])
                if key not in self.builds:
                    self.add_build(case)
            for case in matrix["cases"]:
                self.add_run(case)
            self.put("campaigns/fixture-c1/ledger/budget.json",
                     {"guests": 0, "probe_guests": len(self.raw), "builds": len(self.builds)})
            self.put("campaigns/fixture-c1/ledger/ledger.json", self.ledger)

    def put(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes)
                         else (json.dumps(value, indent=2) + "\n").encode())
        return path

    def digest(self, relative):
        return sha(self.root / relative)

    def artifact(self, build, commit, config_id):
        spec = self.catalog.CONFIGS[config_id]
        config = "\n".join("CONFIG_" + key + "=" + value for key, value in spec["required"].items())
        config += "\n" + "\n".join("# CONFIG_" + key + " is not set" for key in spec["forbidden"]) + "\n"
        prefix = "benchmark/kernel/builds/" + build
        self.put(prefix + "/output/.config", config.encode())
        self.put(prefix + "/output/arch/x86/boot/bzImage", (commit + config_id).encode())
        self.put(prefix + "/build.log", b"Synthetic fixture; compiler never launched.\n")
        manifest = {"commit": commit, "passed": True, "exit_code": 0, "instrument_sha256": None,
                    "input_config_sha256": self.catalog.get_config(config_id, self.root)["input_config_sha256"],
                    "config_sha256": self.digest(prefix + "/output/.config"),
                    "image_sha256": self.digest(prefix + "/output/arch/x86/boot/bzImage")}
        self.put(prefix + "/result.json", manifest)
        return prefix, manifest

    def add_build(self, case):
        config_id, role = case["config_id"], case["role"]
        build = ("c1-baseline-common" if role == "baseline" and config_id == "c1-common"
                 else "fixture-" + role + "-" + config_id)
        prefix, manifest = self.artifact(build, self.commits[role], config_id)
        evaluation = format(len(self.builds) + 1, "032x")
        binding = {"schema_version": 1, "source_commit": self.commits[role],
                   "source_tree": self.trees[role], "config_id": config_id,
                   "input_config_sha256": manifest["input_config_sha256"],
                   "build_manifest_sha256": self.digest(prefix + "/result.json"),
                   "environment": self.environment, "campaign": "fixture-c1", "evaluation_id": evaluation,
                   "protocol_sha256": self.digest("campaigns/fixture-c1/protocol.json")}
        self.put(prefix + "/configured-build.json", binding)
        self.ledger.append({"id": evaluation, "action": "build-coverage", "case_id": case["id"],
            "commit": self.commits[role], "config_id": config_id, "status": "BUILD_VERIFIED",
            "build_reserved": True, "build_manifest": prefix + "/result.json",
            "build_manifest_sha256": self.digest(prefix + "/result.json")})
        self.builds[(role, config_id)] = (build, prefix, manifest)

    def add_run(self, case, suffix=""):
        build, prefix, manifest = self.builds[(case["role"], case["config_id"])]
        run_id = case["id"] + suffix
        dest = "campaigns/fixture-c1/runs/guests/" + run_id
        parsed = {"metrics": {"fixture": 1},
                  "gates": {name: True for name in case["required_gates"]
                            + ["cmdline_identity", "configuration_identity"]}}
        if case["workload"] == "compression":
            parsed["correctness_subcases"] = {
                name: {"status": "PASS", "reset": True} for name in case["subcases"]}
        self.put(dest + "/serial.log", parsed)
        reservation = "campaigns/fixture-c1/ledger/guest-reservations/" + run_id + ".json"
        identity = {key: case[key] for key in ("config_id", "backend", "mode", "workload", "topology_id")}
        identity.update(build=build, correctness_case=case["id"])
        topology = self.catalog.topology_args(case["topology_id"], self.protocol)
        self.put(reservation, {"id": run_id, "campaign": "fixture-c1", "pool": "probe",
            "status": "STARTED", "reserved_unix": 1, "started_unix": 2, "identity": identity,
            "protocol_sha256": self.digest("campaigns/fixture-c1/protocol.json")})
        raw = {"proof_schema_version": 1, "campaign": "fixture-c1", "run_id": run_id,
               "result_path": dest + "/result.json", **identity, "source_commit": self.commits[case["role"]],
               **{key: manifest[key] for key in ("image_sha256", "input_config_sha256", "config_sha256")},
               "build_manifest": prefix + "/result.json", "build_manifest_sha256": self.digest(prefix + "/result.json"),
               "reservation": reservation, "reservation_sha256": self.digest(reservation),
               "serial_log": dest + "/serial.log", "serial_sha256": self.digest(dest + "/serial.log"),
               "protocol_sha256": self.digest("campaigns/fixture-c1/protocol.json"), "protocol_revision": 8,
               "harness_sha256": {name: self.digest("benchmark/swap-standard/" + name)
                   for name in ("run.py", "evidence.py", "configurations.py")},
               "guest_provenance": self.image, "accelerator": "tcg", "guest_vcpus": 4, "guest_mem_mib": 4096,
               "integration_pass": True, "run_valid": True, "invalid_reasons": [], "exit_code": 0,
               "stop_reason": None, "metrics": parsed["metrics"], "gates": dict(parsed["gates"], qemu_exit=True),
               "topology_arguments": topology, "command": ["synthetic-qemu", *topology]}
        if "correctness_subcases" in parsed:
            raw["correctness_subcases"] = parsed["correctness_subcases"]
        self.raw[run_id] = raw
        self.save_raw(raw)
        return raw

    def save_raw(self, raw):
        path = self.put(raw["result_path"], raw)
        path.with_name("result.sha256").write_text(sha(path) + "\n")

    def matrix(self):
        entries = [{"case_id": row["id"], "result_path": self.raw[row["id"]]["result_path"],
                    "result_sha256": self.digest(self.raw[row["id"]]["result_path"])}
                   for row in self.protocol["correctness_matrix"]["cases"]]
        builds = []
        for case in self.protocol["correctness_matrix"]["build_only"]:
            _, prefix, _ = self.builds[(case["role"], case["config_id"])]
            builds.append({"case_id": case["id"], "build_manifest": prefix + "/result.json",
                           "build_manifest_sha256": self.digest(prefix + "/result.json")})
        return {"proof_schema_version": 2, "workload": "correctness", "campaign": "fixture-c1",
                "source_commit": self.commits["candidate"], "candidate_commit": self.commits["candidate"],
                "baseline_commit": self.commits["baseline"],
                "protocol_sha256": self.digest("campaigns/fixture-c1/protocol.json"),
                "runs": entries, "builds": builds}

    def build_identity(self, role="baseline", config_id="c1-common"):
        _, prefix, manifest = self.builds[(role, config_id)]
        return {"source_commit": self.commits[role], "source_tree": self.trees[role],
                "config_id": config_id, "config_path": self.catalog.CONFIGS[config_id]["path"],
                "configured_build_sha256": self.digest(prefix + "/configured-build.json"),
                "build_manifest_sha256": self.digest(prefix + "/result.json"),
                **{key: manifest[key] for key in ("image_sha256", "config_sha256", "input_config_sha256")}}


class CompressionCoverageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.fx = CoverageFixture(Path(self.temporary.name))

    def validate(self, matrix=None):
        return proofs.validate(matrix or self.fx.matrix(), self.fx.protocol, self.fx.root)

    def test_complete_counted_matrix_carries_runtime_and_disabled_config_coverage(self):
        result = self.validate()
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["cases"]), 8)
        self.assertEqual(len(result["builds"]), 2)
        self.assertEqual(set(result["coverage"]["configurations"]), set(self.fx.protocol["configurations"]))
        self.assertTrue(all(result["gates"][flag] for flag in ("kasan", "lockdep", "kcsan")))
        progress = proofs.matrix_progress(self.fx.protocol, self.fx.root, self.fx.commits["candidate"])
        self.assertTrue(progress["passed"], progress)
        self.assertEqual(progress["manifest_data"], self.fx.matrix())

    def test_partial_duplicate_or_wrong_source_matrix_is_rejected(self):
        matrix = self.fx.matrix()
        for mutation in ("missing", "duplicate", "wrong-source"):
            changed = copy.deepcopy(matrix)
            if mutation == "missing":
                changed["runs"].pop()
            elif mutation == "duplicate":
                changed["runs"][-1] = copy.deepcopy(changed["runs"][0])
            else:
                changed["source_commit"] = self.fx.commits["baseline"]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.validate(changed)

    def test_no_baseline_or_debug_row_can_be_removed_from_frozen_contract(self):
        protocol = copy.deepcopy(self.fx.protocol)
        protocol["correctness_matrix"]["cases"].pop()
        with self.assertRaisesRegex(ValueError, "complete eight-case"):
            self.fx.catalog.validate_protocol(protocol, self.fx.root)
        protocol = copy.deepcopy(self.fx.protocol)
        protocol["correctness_matrix"]["build_only"].pop()
        with self.assertRaisesRegex(ValueError, "both candidate disabled"):
            self.fx.catalog.validate_protocol(protocol, self.fx.root)

    def test_pending_progress_preserves_successes_without_claiming_pass(self):
        last = self.fx.raw["c-numa"]
        (self.fx.root / last["reservation"]).unlink()
        progress = proofs.matrix_progress(self.fx.protocol, self.fx.root, self.fx.commits["candidate"])
        self.assertFalse(progress["passed"])
        self.assertTrue(progress["pending"])
        self.assertEqual(progress["next_missing_case"]["id"], "c-numa")
        self.assertEqual(len(progress["verified_cases"]), 7)

    def test_extra_counted_attempt_cannot_be_hidden_by_successful_matrix(self):
        case = self.fx.catalog.correctness_case(self.fx.protocol, "c-compressed")
        self.fx.add_run(case, "-extra")
        self.fx.put("campaigns/fixture-c1/ledger/budget.json", {"guests": 0, "probe_guests": 9, "builds": 8})
        with self.assertRaisesRegex(ValueError, "selectively omits"):
            self.validate()
        progress = proofs.matrix_progress(self.fx.protocol, self.fx.root, self.fx.commits["candidate"])
        self.assertTrue(progress["attempted"])
        self.assertFalse(progress["passed"])
        self.assertIn("multiple counted attempts", progress["reason"])

    def test_started_attempt_without_raw_result_stops_progress(self):
        (self.fx.root / self.fx.raw["c-race"]["result_path"]).unlink()
        progress = proofs.matrix_progress(self.fx.protocol, self.fx.root, self.fx.commits["candidate"])
        self.assertFalse(progress["pending"])
        self.assertIn("no completed raw result", progress["reason"])

    def test_subcase_reset_failure_remains_typed_correctness_failure(self):
        raw = self.fx.raw["c-debug"]
        parsed = json.loads((self.fx.root / raw["serial_log"]).read_text())
        parsed["correctness_subcases"]["library_unit"]["reset"] = False
        parsed["gates"]["compression_reset"] = False
        self.fx.put(raw["serial_log"], parsed)
        raw.update(serial_sha256=self.fx.digest(raw["serial_log"]), integration_pass=False,
                   gates=dict(parsed["gates"], qemu_exit=True),
                   correctness_subcases=parsed["correctness_subcases"])
        self.fx.save_raw(raw)
        with self.assertRaises(proofs.CorrectnessFailure):
            self.validate()
        progress = proofs.matrix_progress(self.fx.protocol, self.fx.root, self.fx.commits["candidate"])
        self.assertTrue(progress["failed"])
        self.assertFalse(progress["pending"])

    def test_unbound_subcase_failure_cannot_invalidate_candidate_history(self):
        raw = self.fx.raw["c-debug"]
        parsed = json.loads((self.fx.root / raw["serial_log"]).read_text())
        parsed["correctness_subcases"]["library_unit"]["reset"] = False
        parsed["gates"].update(compression_reset=False, cmdline_identity=False)
        self.fx.put(raw["serial_log"], parsed)
        raw.update(serial_sha256=self.fx.digest(raw["serial_log"]), integration_pass=False,
                   gates=dict(parsed["gates"], qemu_exit=True),
                   correctness_subcases=parsed["correctness_subcases"])
        self.fx.save_raw(raw)
        with self.assertRaises(ValueError) as caught:
            self.validate()
        self.assertNotIsInstance(caught.exception, proofs.CorrectnessFailure)
        self.assertIn("cannot bind", str(caught.exception))

    def test_unbound_configuration_is_not_a_candidate_correctness_veto(self):
        raw = self.fx.raw["c-debug"]
        parsed = json.loads((self.fx.root / raw["serial_log"]).read_text())
        parsed["gates"]["configuration_identity"] = False
        self.fx.put(raw["serial_log"], parsed)
        raw.update(serial_sha256=self.fx.digest(raw["serial_log"]), integration_pass=False,
                   gates=dict(parsed["gates"], qemu_exit=True))
        self.fx.save_raw(raw)
        with self.assertRaises(ValueError) as caught:
            self.validate()
        self.assertNotIsInstance(caught.exception, proofs.CorrectnessFailure)
        self.assertIn("configuration/case/topology", str(caught.exception))
        progress = proofs.matrix_progress(self.fx.protocol, self.fx.root, self.fx.commits["candidate"])
        self.assertFalse(progress["failed"])
        self.assertTrue(progress["attempted"])

    def test_config_topology_and_subcase_identity_are_not_interchangeable(self):
        raw = self.fx.raw["c-numa"]
        for key, value in (("config_id", "c1-common"), ("topology_id", "single"),
                           ("correctness_case", "c-debug")):
            changed = copy.deepcopy(raw)
            changed[key] = value
            self.fx.save_raw(changed)
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate()
            self.fx.save_raw(raw)

    def test_builder_drift_invalidates_counted_builds(self):
        _, prefix, _ = self.fx.builds[("candidate", "c1-debug")]
        binding_path = self.fx.root / prefix / "configured-build.json"
        binding = json.loads(binding_path.read_text())
        binding["environment"]["toolchain"]["gcc"]["sha256"] = "0" * 64
        self.fx.put(str(binding_path.relative_to(self.fx.root)), binding)
        with self.assertRaisesRegex(ValueError, "environment changed"):
            self.validate()

    def test_requested_debug_fragment_cannot_replace_missing_final_kasan(self):
        build, prefix, manifest = self.fx.builds[("candidate", "c1-debug")]
        path = self.fx.root / prefix / "output/.config"
        path.write_text(path.read_text().replace("CONFIG_KASAN=y", "# CONFIG_KASAN is not set"))
        manifest["config_sha256"] = sha(path)
        self.fx.put(prefix + "/result.json", manifest)
        digest = self.fx.digest(prefix + "/result.json")
        binding_path = self.fx.root / prefix / "configured-build.json"
        binding = json.loads(binding_path.read_text())
        binding["build_manifest_sha256"] = digest
        self.fx.put(prefix + "/configured-build.json", binding)
        for item in self.fx.ledger:
            if item["id"] == binding["evaluation_id"]:
                item["build_manifest_sha256"] = digest
        self.fx.put("campaigns/fixture-c1/ledger/ledger.json", self.fx.ledger)
        for raw in self.fx.raw.values():
            if raw["build"] == build:
                raw.update(config_sha256=manifest["config_sha256"], build_manifest_sha256=digest)
                self.fx.save_raw(raw)
        with self.assertRaisesRegex(ValueError, "required final CONFIG_KASAN"):
            self.validate()

    def test_consumed_ticket_must_match_configuration_fields(self):
        raw = self.fx.raw["c-numa"]
        ticket = json.loads((self.fx.root / raw["reservation"]).read_text())
        ticket["identity"]["topology_id"] = "single"
        self.fx.put(raw["reservation"], ticket)
        raw["reservation_sha256"] = self.fx.digest(raw["reservation"])
        self.fx.save_raw(raw)
        with self.assertRaisesRegex(ValueError, "consumed reservation identity"):
            self.validate()

    def test_canonical_matrix_requires_each_disabled_build_artifact(self):
        matrix = self.fx.matrix()
        matrix["builds"].pop()
        with self.assertRaisesRegex(ValueError, "build-only coverage mismatch"):
            self.validate(matrix)

    def test_uncounted_builds_cannot_supply_disabled_or_runtime_coverage(self):
        self.fx.put("campaigns/fixture-c1/ledger/budget.json", {"guests": 0, "probe_guests": 8, "builds": 0})
        with self.assertRaisesRegex(ValueError, "not counted"):
            self.validate()

    def test_counted_build_origin_cannot_use_a_symlinked_ledger(self):
        path = self.fx.root / "campaigns/fixture-c1/ledger/ledger.json"
        retained = path.with_name("retained-ledger.json")
        path.rename(retained)
        path.symlink_to(retained.name)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.validate()

    def test_sidecar_free_existing_artifact_is_not_native_build_reuse(self):
        _, prefix, _ = self.fx.builds[("baseline", "c1-common")]
        (self.fx.root / prefix / "configured-build.json").unlink()
        with self.assertRaisesRegex(ValueError, "missing configured build provenance"):
            self.validate()

    def test_named_build_cache_revalidates_config_builder_and_counted_origin(self):
        key = self.fx.build_identity()
        _, prefix, _ = self.fx.builds[("baseline", "c1-common")]
        provenance = {"artifact": prefix + "/result.json",
                      "artifact_sha256": key["build_manifest_sha256"], "observed_unix": 100}
        record = cache.register(self.fx.root, "build", key, provenance)
        self.assertTrue(record["verification"]["passed"], record["verification"])
        self.assertEqual(cache.lookup(self.fx.root, "build", key)["status"], "reusable")
        self.fx.put("campaigns/fixture-c1/ledger/budget.json", {"guests": 0, "probe_guests": 8, "builds": 0})
        self.assertNotEqual(cache.lookup(self.fx.root, "build", key)["status"], "reusable")

    def test_matrix_cache_identity_contains_every_source_configuration(self):
        harness = {name: "1" * 64 for name in cache.RUNTIME_HARNESS |
                   {"evolve/control/correctness_proof.py", "benchmark/swap-standard/configurations.py",
                    "benchmark/swap-standard/compression.c"}}
        builds = {}
        for (role, config_id) in self.fx.builds:
            variant = self.fx.build_identity(role, config_id)
            variant.pop("source_commit")
            variant.pop("source_tree")
            builds.setdefault(self.fx.commits[role],
                {"tree": self.fx.trees[role], "configurations": {}})["configurations"][config_id] = variant
        key = {"source_commit": self.fx.commits["candidate"], "source_tree": self.fx.trees["candidate"],
               "protocol": self.fx.protocol, "machine": "fixture", "accelerator": "tcg",
               "guest": self.fx.protocol["guest"], "builds": builds,
               "guest_image": self.fx.image, "harness": harness}
        cache.semantic_identity("correctness", key)
        changed = copy.deepcopy(key)
        changed["builds"][self.fx.commits["candidate"]]["configurations"].pop("c1-debug")
        with self.assertRaisesRegex(ValueError, "configuration set"):
            cache.semantic_identity("correctness", changed)
        changed = copy.deepcopy(key)
        changed["protocol"]["correctness_matrix"]["cases"][-1]["topology_id"] = "single"
        self.assertNotEqual(cache.cache_key("correctness", key), cache.cache_key("correctness", changed))

    def test_recorded_numa_command_and_current_guest_image_are_bound(self):
        raw = self.fx.raw["c-numa"]
        raw["command"] = ["synthetic-qemu"]
        self.fx.save_raw(raw)
        with self.assertRaisesRegex(ValueError, "command topology"):
            self.validate()
        raw["command"] = ["synthetic-qemu", *raw["topology_arguments"]]
        self.fx.save_raw(raw)
        self.fx.put("benchmark/swap-standard/bench.img", b"Changed image")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.validate()

    def test_existing_manifest_cannot_satisfy_another_candidate_progress(self):
        progress = proofs.matrix_progress(self.fx.protocol, self.fx.root, self.fx.commits["baseline"],
                                          manifest=self.fx.matrix())
        self.assertFalse(progress["passed"])
        self.assertIn("another candidate", progress["reason"])

    def test_native_timing_cache_replays_extended_counted_reservation(self):
        case = dict(self.fx.protocol["cases"]["compressed"], id="timing-fixture",
                    role="baseline", required_gates=["cmdline_identity"], subcases=[])
        raw = self.fx.add_run(case)
        raw["correctness_case"] = None
        ticket = json.loads((self.fx.root / raw["reservation"]).read_text())
        ticket["identity"]["correctness_case"] = None
        self.fx.put(raw["reservation"], ticket)
        raw["reservation_sha256"] = self.fx.digest(raw["reservation"])
        self.fx.save_raw(raw)
        self.fx.put("campaigns/fixture-c1/ledger/budget.json", {"guests": 0, "probe_guests": 9, "builds": 8})
        variant = self.fx.build_identity()
        identity = {"accelerator": "tcg", "guest": self.fx.protocol["guest"],
                    "guest_image": self.fx.image,
                    "builds": {self.fx.commits["baseline"]: dict(variant, tree=self.fx.trees["baseline"])}}
        attempt = {"result": raw["result_path"], "result_sha256": self.fx.digest(raw["result_path"]),
                   "id": raw["run_id"], "case": "compressed", "status": "PASS", "metrics": raw["metrics"]}
        parsed, valid = cache.Verifier(self.fx.root).run(attempt, self.fx.protocol, identity,
                                                        {"enforce_validity": False}, [])
        self.assertTrue(valid)
        self.assertEqual(parsed["config_id"], "c1-common")
        for revision in (7, None):
            changed = copy.deepcopy(raw)
            if revision is None:
                changed.pop("protocol_revision")
            else:
                changed["protocol_revision"] = revision
            self.fx.save_raw(changed)
            attempt["result_sha256"] = self.fx.digest(changed["result_path"])
            with self.subTest(revision=revision), self.assertRaisesRegex(ValueError, "protocol revision mismatch"):
                cache.Verifier(self.fx.root).run(attempt, self.fx.protocol, identity,
                                                 {"enforce_validity": False}, [])
        self.fx.save_raw(raw)
        ticket["identity"].pop("config_id")
        self.fx.put(raw["reservation"], ticket)
        raw["reservation_sha256"] = self.fx.digest(raw["reservation"])
        self.fx.save_raw(raw)
        attempt["result_sha256"] = self.fx.digest(raw["result_path"])
        with self.assertRaisesRegex(ValueError, "raw counted reservation mismatch"):
            cache.Verifier(self.fx.root).run(attempt, self.fx.protocol, identity,
                                             {"enforce_validity": False}, [])

    def test_reservations_bind_case_configuration_and_topology(self):
        budget = workflow.guest_budget
        with mock.patch.object(budget.store, "PROJECT", self.fx.root):
            identity = budget.reservation_identity(self.fx.protocol, "fixture", "compressed", "xswap",
                                                  "swapin", "c1-common", None, "single")
            self.assertEqual(identity["config_id"], "c1-common")
            with self.assertRaises(budget.store.CampaignError):
                budget.reservation_identity(self.fx.protocol, "fixture", "compressed", "xswap",
                                            "swapin", "c1-debug", None, "numa2")
            with self.assertRaises(budget.store.CampaignError):
                budget.reservation_identity(self.fx.protocol, "fixture", "compressed", "xswap",
                                            "compression", "c1-debug", "c-numa", "single")

    def test_workflow_adapter_passes_identity_for_both_guest_pools(self):
        flow = workflow.Workflow.__new__(workflow.Workflow)
        flow.p = self.fx.protocol
        flow.check = lambda: None
        with mock.patch.object(workflow.guest_budget, "reserve_guest", return_value={"reservation": "fixture"}) as reserve, \
                mock.patch.object(workflow.guest_budget, "read_budget", return_value={}):
            for pool in ("probe", "fast"):
                flow._reserve_guest("fixture", "fixture", self.fx.protocol["cases"]["compressed"], pool)
                self.assertEqual(reserve.call_args.kwargs, {"config_id": "c1-common",
                    "correctness_case": None, "topology_id": "single"})
            case = self.fx.catalog.correctness_case(self.fx.protocol, "c-numa")
            flow._reserve_guest("fixture", "fixture", case, "probe")
            self.assertEqual(reserve.call_args.kwargs, {"config_id": "c1-debug",
                "correctness_case": "c-numa", "topology_id": "numa2"})

    def test_timing_arguments_and_result_require_common_single_identity(self):
        case = self.fx.protocol["cases"]["compressed"]
        extra = workflow.runner_extra(self.fx.protocol, case)
        self.assertEqual(extra[extra.index("--config-id") + 1], "c1-common")
        with mock.patch.object(workflow, "ROOT", self.fx.root):
            result = {"config_id": "c1-common", "topology_id": "single", "correctness_case": None,
                      "topology_arguments": [], "command": ["synthetic-qemu"],
                      "input_config_sha256": self.fx.catalog.get_config("c1-common", self.fx.root)["input_config_sha256"]}
            workflow.validate_result_configuration(self.fx.protocol, result, case)
            result["config_id"] = "standard"
            with self.assertRaises(RuntimeError):
                workflow.validate_result_configuration(self.fx.protocol, result, case)


class ConfiguredBuildWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.fx = CoverageFixture(Path(self.temporary.name), populate=False)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        campaign = self.fx.root / "campaigns/fixture-c1"
        for key, value in {"ROOT": self.fx.root, "CAMPAIGN": campaign, "PROTOCOL": campaign / "protocol.json",
                           "STATE": campaign / "ledger", "EVALUATIONS": campaign / "runs/evaluations"}.items():
            self.stack.enter_context(mock.patch.object(workflow, key, value))
        self.flow = workflow.Workflow.__new__(workflow.Workflow)
        self.flow.p = self.fx.protocol
        self.flow.ledger = []
        self.flow.ledger_path = campaign / "ledger/ledger.json"
        self.flow.budget_path = campaign / "ledger/budget.json"
        self.flow.budget = {"builds": 0, "guests": 0, "probe_guests": 0}
        self.flow.check = lambda: None
        self.commands = []
        self.fail = False
        self.flow.reserve = self.reserve
        self.flow.command = self.command

    def reserve(self, kind):
        self.assertEqual(kind, "build")
        self.flow.budget["builds"] += 1
        workflow.save(self.flow.budget_path, self.flow.budget)

    def command(self, command, logfile, timeout, **kwargs):
        self.commands.append(command)
        self.assertEqual(self.flow.budget["builds"], 1)
        row = workflow.read(self.flow.ledger_path)[-1]
        self.assertTrue(row["build_reserved"])
        if self.fail:
            raise RuntimeError("synthetic compiler failure")
        build = command[command.index("--name") + 1]
        config_path = command[command.index("--config") + 1]
        config_id = next(name for name, spec in self.fx.catalog.CONFIGS.items() if spec["path"] == config_path)
        commit = command[command.index("--commit") + 1]
        self.fx.artifact(build, commit, config_id)

    def test_build_is_counted_before_command_and_same_case_is_idempotent(self):
        row = self.flow.build_coverage(None, "b-common")
        self.assertEqual(row["status"], "BUILD_VERIFIED", row)
        self.assertEqual(row["config_id"], "c1-common")
        self.assertEqual(self.flow.budget["builds"], 1)
        again = self.flow.build_coverage(None, "b-common")
        self.assertEqual(again["id"], row["id"])
        self.assertEqual(len(self.commands), 1)
        self.assertEqual(len(self.flow.ledger), 1)

    def test_revision8_calibration_cannot_launch_or_reuse_before_full_matrix(self):
        self.flow.campaign_errors = lambda: []
        self.flow.reuse_calibration = mock.Mock(return_value=True)
        self.flow.register_reference = lambda *args: None
        with mock.patch.object(workflow, "contract_errors", return_value=[]), redirect_stdout(io.StringIO()):
            probe = self.flow.run_probe("calibrate")
            fast = self.flow.run("calibrate", "fast")
        self.assertEqual(probe["status"], "BLOCKED", probe)
        self.assertEqual(fast["status"], "BLOCKED", fast)
        self.assertIn("complete --correctness matrix", probe["reason"])
        self.assertIn("complete --correctness matrix", fast["reason"])
        self.flow.reuse_calibration.assert_not_called()
        self.assertEqual(self.flow.budget["builds"], 0)
        self.assertEqual(self.commands, [])

    def test_failed_build_keeps_attempt_and_refuses_silent_retry(self):
        self.fail = True
        row = self.flow.build_coverage(None, "b-common")
        self.assertEqual(row["status"], "BUILD_FAILED")
        self.assertEqual(self.flow.budget["builds"], 1)
        with self.assertRaisesRegex(RuntimeError, "remains spent"):
            self.flow.build_coverage(None, "b-common")
        self.assertEqual(len(self.commands), 1)


if __name__ == "__main__":
    unittest.main()
