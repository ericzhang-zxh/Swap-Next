# SPDX-License-Identifier: GPL-2.0-only
"""Native revision-9 coverage/planner tests using synthetic files, never guests."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from evolve.test_compression_coverage import CoverageFixture, SOURCE, load_catalog
from evolve import standard_workflow as workflow
from evolve import reference_cache
from evolve.control import guest_budget

proofs = workflow.correctness_proof


class C2CoverageFixture(CoverageFixture):
    def __init__(self, root):
        super().__init__(root, populate=False)
        # Only this temporary fixture has fake source commits. Native validation
        # is reloaded from its copied catalog and still enforces exact identities.
        path = root / "benchmark/swap-standard/configurations.py"
        path.write_text(path.read_text().replace(self.catalog.C2_BASELINE, self.commits["baseline"]) + "\n# Fixture source binding.\n")
        for path in (SOURCE / "benchmark/config").glob("compression-c2-*.config"):
            self.put("benchmark/config/" + path.name, path.read_bytes())
        self.catalog = load_catalog(root)
        rows = [dict(id=ident, role=role, group=group, **copy.deepcopy(self.catalog.C2_GROUPS[group]))
                for ident, role, group in self.catalog.C2_CASES]
        disabled = [{"id": "c-noswap", "role": "candidate", "config_id": "c1-noswap"},
                    {"id": "c-no-frontends", "role": "candidate", "config_id": "c1-no-frontends"}]
        used = {row["config_id"] for row in rows + disabled}
        self.protocol.update(protocol_revision=9, contract_id=self.catalog.C2_CONTRACT,
            predecessor_commit=self.catalog.C2_PREDECESSOR,
            compression_observer=copy.deepcopy(self.catalog.C2_OBSERVER),
            compression_admission=copy.deepcopy(self.catalog.C2_ADMISSION),
            compression_workload={"target_bytes": 134217728},
            configurations={name: {"input_config_sha256": self.catalog.get_config(name, root)["input_config_sha256"]}
                            for name in used},
            correctness_matrix={"schema_version": 1, "cases": rows, "build_only": disabled,
                                "negative_builds": [self.catalog.C2_NEGATIVE]},
            required_correctness_gates=[*self.catalog.BASE_GATES, "source_role_identity",
                "compression_evidence", "compression_reset",
                *sorted({"compression_" + phase for row in rows if row["role"] == "candidate"
                          for phase in row["subcases"]}), "kasan", "lockdep", "kcsan"])
        self.protocol["accelerator"]["qemu"] = ["-accel", "tcg,thread=multi,tb-size=256",
                                                 "-machine", "pc", "-cpu", "max"]
        self.put("campaigns/fixture-c1/protocol.json", self.protocol)
        self.put("campaigns/fixture-c1/candidates/c2/static.json", {
            "status": "SCOPE_PASS", "candidate_commit": self.commits["candidate"],
            "parent": self.commits["baseline"]})
        matrix = self.catalog.validate_protocol(self.protocol, root)
        for row in matrix["cases"] + matrix["build_only"] + matrix["negative_builds"]:
            if (row["role"], row["config_id"]) not in self.builds:
                self.add_build(row)
        # Baseline common/legacy are natively retained controls from a separate
        # completed source campaign; current nine candidate + one negative cost ten.
        old_rows = [row for row in self.ledger if row["commit"] == self.commits["baseline"]
                    and row["config_id"] != "c2-independent"]
        self.put("campaigns/fixture-controls/protocol.json", {"budget": {"build_attempts": 10}})
        self.put("campaigns/fixture-controls/ledger/ledger.json", old_rows)
        self.put("campaigns/fixture-controls/ledger/budget.json", {"builds": 2})
        for row in old_rows:
            sidecar = str(Path(row["build_manifest"]).with_name("configured-build.json"))
            data = json.loads((root / sidecar).read_bytes())
            data.update(campaign="fixture-controls",
                        protocol_sha256=self.digest("campaigns/fixture-controls/protocol.json"))
            self.put(sidecar, data)
        self.ledger = [row for row in self.ledger if row not in old_rows]
        self.put("campaigns/fixture-c1/ledger/ledger.json", self.ledger)
        self.put("campaigns/fixture-c1/ledger/budget.json", {"guests": 0, "probe_guests": 12, "builds": 10})
        for row in matrix["cases"]:
            self.add_run(row)

    def add_build(self, row):
        super().add_build(row)
        if row["id"] != self.catalog.C2_NEGATIVE["id"]:
            return
        build, prefix, manifest = self.builds[("baseline", "c2-independent")]
        self.put(prefix + "/output/.config",
            b"CONFIG_SWAP=y\nCONFIG_MEMCG=y\n# CONFIG_ZSWAP is not set\n"
            b"# CONFIG_XSWAP is not set\n# CONFIG_PAGE_COMPRESS is not set\n# CONFIG_XSWAP_TEST is not set\n")
        manifest["config_sha256"] = self.digest(prefix + "/output/.config")
        self.put(prefix + "/result.json", manifest)
        sidecar = prefix + "/configured-build.json"
        data = json.loads((self.root / sidecar).read_bytes())
        data.update(outcome="EXPECTED_UNSUPPORTED_CONFIG", guest_eligible=False,
                    build_manifest_sha256=self.digest(prefix + "/result.json"),
                    build_log_sha256=self.digest(prefix + "/build.log"))
        self.put(sidecar, data)
        self.ledger[-1].update(status="EXPECTED_UNSUPPORTED_CONFIG", guest_eligible=False,
                              build_manifest_sha256=self.digest(prefix + "/result.json"))

    def add_run(self, row, suffix=""):
        raw = super().add_run(row, suffix)
        arm = self.catalog.runtime_source_binding(self.protocol, self.root, raw["build"],
                                                   row["config_id"], row["backend"], row)
        raw.update(arm, protocol_revision=9, correctness_group=row["group"])
        ticket = json.loads((self.root / raw["reservation"]).read_bytes())
        ticket["identity"].update(arm)
        self.put(raw["reservation"], ticket)
        raw["reservation_sha256"] = self.digest(raw["reservation"])
        if row["topology_id"] == self.catalog.C2_TOPOLOGY:
            accelerator = self.catalog.effective_accelerator(row["topology_id"], self.protocol["accelerator"]["qemu"])
            raw.update(qemu_accel=accelerator,
                       command=["synthetic-qemu", *accelerator, "-smp", "4,sockets=2,cores=2,threads=1",
                                "-m", "4096", *self.catalog.topology_args(row["topology_id"], self.protocol)])
        self.save_raw(raw)
        return raw

    def matrix(self):
        result = super().matrix()
        _, prefix, _ = self.builds[("baseline", "c2-independent")]
        result["negative_builds"] = [{"case_id": self.catalog.C2_NEGATIVE["id"],
            "build_manifest": prefix + "/result.json", "build_manifest_sha256": self.digest(prefix + "/result.json")}]
        return result


class C2CoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fx = C2CoverageFixture(Path(self.temp.name))

    def validate(self, matrix=None):
        return proofs.validate(matrix or self.fx.matrix(), self.fx.protocol, self.fx.root)

    def test_complete_twelve_rows_nine_candidate_configs_and_typed_negative(self):
        result = self.validate()
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["cases"]), 12)
        self.assertEqual(len({config for role, config in self.fx.builds if role == "candidate"}), 9)
        self.assertEqual(sum(row["build_reserved"] for row in self.fx.ledger), 10)
        self.assertEqual(result["negative_builds"][0]["status"], "EXPECTED_UNSUPPORTED_CONFIG")
        self.assertFalse(result["negative_builds"][0]["guest_eligible"])
        self.assertTrue(all(result["gates"][flag] for flag in ("kasan", "lockdep", "kcsan")))
        progress = proofs.matrix_progress(self.fx.protocol, self.fx.root, self.fx.commits["candidate"])
        self.assertTrue(progress["passed"], progress)
        self.assertEqual(progress["manifest_data"], self.fx.matrix())

    def test_missing_duplicate_or_wrong_negative_coverage_fails(self):
        for negative in ([], self.fx.matrix()["negative_builds"] * 2,
                         [dict(self.fx.matrix()["negative_builds"][0], case_id="b-legacy")]):
            matrix = self.fx.matrix()
            matrix["negative_builds"] = negative
            with self.subTest(), self.assertRaises(ValueError):
                self.validate(matrix)

    def test_negative_has_no_runtime_source_or_positive_build_eligibility(self):
        build, prefix, manifest = self.fx.builds[("baseline", "c2-independent")]
        with self.assertRaisesRegex(ValueError, "never guest eligible"):
            self.fx.catalog.runtime_source_binding(self.fx.protocol, self.fx.root, build,
                                                    "c2-independent", "compressed")
        with self.assertRaises(ValueError):
            self.fx.catalog.verify_build_binding(self.fx.root, prefix + "/result.json",
                self.fx.commits["baseline"], "c2-independent", self.fx.environment)

    def test_failed_interrupted_negative_remains_spent_and_stops_planner(self):
        row = next(row for row in self.fx.ledger if row["case_id"] == "b-independent-unsupported")
        for status in ("BUILD_FAILED", "RUNNING", "BLOCKED", "BUILD_VERIFIED"):
            row["status"] = status
            self.fx.put("campaigns/fixture-c1/ledger/ledger.json", self.fx.ledger)
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "failed or incomplete"):
                self.validate()
            progress = proofs.matrix_progress(self.fx.protocol, self.fx.root, self.fx.commits["candidate"])
            self.assertFalse(progress["pending"])
            self.assertFalse(progress["passed"])
            self.assertTrue(progress["attempted"])
            self.assertEqual(sum(item["build_reserved"] for item in self.fx.ledger), 10)

    def test_wrong_source_observer_and_reservation_rejected(self):
        raw = self.fx.raw["c-independent"]
        for key, value in (("observer_symbol", "zswap_load"), ("source_role", "baseline"),
                           ("source_tree", "e" * 40), ("frontend", "legacy")):
            original = raw[key]
            raw[key] = value
            self.fx.save_raw(raw)
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.validate()
            raw[key] = original
            self.fx.save_raw(raw)

    def test_absent_sanitizer_cannot_be_asserted_by_serial_gates(self):
        _, prefix, manifest = self.fx.builds[("candidate", "c2-debug-independent")]
        path = self.fx.root / prefix / "output/.config"
        path.write_text(path.read_text().replace("CONFIG_KASAN=y", "# CONFIG_KASAN is not set"))
        with self.assertRaisesRegex(ValueError, "CONFIG_KASAN"):
            self.fx.catalog.validate_final("c2-debug-independent", path, "correctness")

    def test_common_timing_input_cannot_enable_new_test_symbol(self):
        _, prefix, _ = self.fx.builds[("candidate", "c1-common")]
        path = self.fx.root / prefix / "output/.config"
        path.write_text(path.read_text() + "CONFIG_XSWAP_TEST=y\n")
        with self.assertRaisesRegex(ValueError, "CONFIG_XSWAP_TEST"):
            self.fx.catalog.validate_final("c1-common", path, "timing", protocol_revision=9)
        # The frozen revision-8 resolver keeps its original symbol contract.
        self.fx.catalog.validate_final("c1-common", path, "timing", protocol_revision=8)

    def test_correctness_source_needs_unique_native_scope_record(self):
        static = self.fx.root / "campaigns/fixture-c1/candidates/c2/static.json"
        static.unlink()
        with self.assertRaisesRegex(ValueError, "unique current native candidate"):
            self.validate()

    def test_frozen_contract_rejects_missing_phase_wrong_cap_or_observer(self):
        for mutation in ("phase", "cap", "observer", "topology", "negative"):
            protocol = copy.deepcopy(self.fx.protocol)
            if mutation == "phase":
                protocol["correctness_matrix"]["cases"][8]["subcases"].pop(0)
            elif mutation == "cap":
                protocol["compression_admission"]["percent"] = 30
            elif mutation == "observer":
                protocol["compression_observer"]["isolation_proof"] = "asserted"
            elif mutation == "topology":
                protocol["cases"]["compressed"]["topology_id"] = self.fx.catalog.C2_TOPOLOGY
            else:
                protocol["correctness_matrix"]["negative_builds"] = []
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.fx.catalog.validate_protocol(protocol, self.fx.root)

    def test_incomplete_guest_preserves_verified_prefix(self):
        raw = self.fx.raw["c-race-independent"]
        (self.fx.root / raw["reservation"]).unlink()
        progress = proofs.matrix_progress(self.fx.protocol, self.fx.root, self.fx.commits["candidate"])
        self.assertTrue(progress["pending"], progress)
        self.assertFalse(progress["passed"])
        self.assertEqual(progress["next_missing_case"]["id"], "c-race-independent")
        self.assertEqual(len(progress["verified_cases"]), 11)

    def test_missing_negative_is_next_durable_build_action(self):
        self.fx.ledger = [row for row in self.fx.ledger if row["case_id"] != "b-independent-unsupported"]
        self.fx.put("campaigns/fixture-c1/ledger/ledger.json", self.fx.ledger)
        progress = proofs.matrix_progress(self.fx.protocol, self.fx.root, self.fx.commits["candidate"])
        self.assertTrue(progress["pending"], progress)
        self.assertFalse(progress["passed"])
        self.assertEqual(progress["missing_builds"][0]["id"], "b-independent-unsupported")


    def test_counted_build_and_source_tree_are_checked_before_reservation(self):
        from unittest import mock
        case = self.fx.catalog.correctness_case(self.fx.protocol, "c-independent")
        build, prefix, manifest = self.fx.builds[("candidate", "c2-independent")]
        with mock.patch.object(guest_budget.store, "PROJECT", self.fx.root):
            identity = guest_budget.reservation_identity(self.fx.protocol, build, case["backend"],
                case["mode"], case["workload"], case["config_id"], case["id"], case["topology_id"])
            self.assertEqual(identity["source_role"], "candidate")
            self.assertEqual(identity["observer_symbol"], "xswap_load_folio")
            sidecar = prefix + "/configured-build.json"
            original = json.loads((self.fx.root / sidecar).read_bytes())
            for key, value in (("source_tree", "e" * 40), ("environment", {}),
                               ("evaluation_id", "f" * 32), ("guest_eligible", False)):
                changed = copy.deepcopy(original)
                changed[key] = value
                self.fx.put(sidecar, changed)
                with self.subTest(key=key), self.assertRaises(ValueError):
                    guest_budget.reservation_identity(self.fx.protocol, build, case["backend"],
                        case["mode"], case["workload"], case["config_id"], case["id"], case["topology_id"])
            self.fx.put(sidecar, original)

    def test_expected_negative_cannot_enter_positive_build_cache(self):
        _, prefix, _ = self.fx.builds[("baseline", "c2-independent")]
        verifier = reference_cache.Verifier(self.fx.root)
        with self.assertRaises(ValueError):
            verifier.build(prefix + "/result.json", self.fx.commits["baseline"],
                           self.fx.build_identity("baseline", "c2-independent"))
        _, prefix, _ = self.fx.builds[("candidate", "c2-independent")]
        verifier = reference_cache.Verifier(self.fx.root)
        self.assertTrue(verifier.build(prefix + "/result.json", self.fx.commits["candidate"],
                                       self.fx.build_identity("candidate", "c2-independent"))["passed"])

    def test_draft_profile_stays_explicitly_non_executable(self):
        from evolve import research
        profile = research.load_profile("xswap-independent-v1", SOURCE)
        self.assertFalse(profile["executable"])
        self.assertTrue(profile["missing_capabilities"])
        self.assertEqual(len(profile["allowed_modify"]) + len(profile["allowed_add"]), 20)
        self.assertEqual(profile["protocol_revisions"], [9])
        readiness = research.capability_readout(profile, root=SOURCE)
        self.assertFalse(readiness["ready"])
        self.assertIn("profile is not executable", readiness["missing_capabilities"])



if __name__ == "__main__":
    unittest.main()
