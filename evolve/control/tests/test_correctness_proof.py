# SPDX-License-Identifier: GPL-2.0-only
"""Guest-free proof provenance fixtures, including a counted raw runner result."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "benchmark/swap-standard"))
from test_evidence import correctness
from evidence import parse
SPEC = importlib.util.spec_from_file_location("correctness_proof", Path(__file__).parents[1] / "correctness_proof.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def sha(data):
    return hashlib.sha256(data).hexdigest()


class CorrectnessProofTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.campaign, self.run, self.build = "proof-fixture", "counted-correctness", "candidate-build"
        self.prefix = f"campaigns/{self.campaign}"
        self.result_dir = f"{self.prefix}/runs/guests/{self.run}"
        self.manifest_dir = f"benchmark/kernel/builds/{self.build}"
        self.ticket = f"{self.prefix}/ledger/guest-reservations/{self.run}.json"
        self.protocol = {"campaign": self.campaign, "protocol_revision": 4, "cases": {"swapin-disk": {"workload": "swapin", "mode": "xswap", "backend": "disk"}}, "budget": {"guest_attempts": 30, "probe_guest_attempts": 20}, "required_correctness_gates": ["data_roundtrip", "fork_cow", "concurrent_fault", "swapoff_live_pages", "no_new_kernel_warnings"], "accelerator": {"require": "kvm"}, "guest": {"vcpus": 8, "mem_mib": 8192}}
        self.put(f"{self.prefix}/protocol.json", self.protocol)
        self.put("benchmark/config/swap-standard.config", b"CONFIG_SWAP=y\n")
        self.put(f"{self.manifest_dir}/output/.config", b"CONFIG_SWAP=y\nCONFIG_ZSWAP=y\n")
        self.put(f"{self.manifest_dir}/output/arch/x86/boot/bzImage", b"fixture image; no guest boot\n")
        for name in ("run.py", "evidence.py"):
            self.put("benchmark/swap-standard/" + name, (ROOT / "benchmark/swap-standard" / name).read_bytes())
        self.manifest = {"passed": True, "exit_code": 0, "commit": "a" * 40, "instrument_sha256": None, "input_config_sha256": self.digest("benchmark/config/swap-standard.config"), "config_sha256": self.digest(f"{self.manifest_dir}/output/.config"), "image_sha256": self.digest(f"{self.manifest_dir}/output/arch/x86/boot/bzImage")}
        self.put(f"{self.manifest_dir}/result.json", self.manifest)
        self.reservation = {"id": self.run, "campaign": self.campaign, "pool": "fast", "status": "STARTED", "reserved_unix": 100.0, "started_unix": 101.0, "identity": {"build": self.build, "backend": "disk", "mode": "xswap", "workload": "correctness"}, "protocol_sha256": self.digest(f"{self.prefix}/protocol.json")}
        self.put(self.ticket, self.reservation)
        self.put(f"{self.prefix}/ledger/budget.json", {"guests": 1, "probe_guests": 0})
        image_sha = self.manifest["image_sha256"]
        serial = correctness().replace("bench.image_sha=abc", "bench.image_sha=" + image_sha)
        self.put(f"{self.result_dir}/serial.log", serial.encode())
        parsed = parse(serial, image_sha, "disk", "xswap", "correctness")
        self.proof = {"proof_schema_version": 1, "campaign": self.campaign, "run_id": self.run, "result_path": f"{self.result_dir}/result.json", "build": self.build, "backend": "disk", "mode": "xswap", "workload": "correctness", "source_commit": self.manifest["commit"], "image_sha256": image_sha, "input_config_sha256": self.manifest["input_config_sha256"], "config_sha256": self.manifest["config_sha256"], "build_manifest": f"{self.manifest_dir}/result.json", "build_manifest_sha256": self.digest(f"{self.manifest_dir}/result.json"), "reservation": self.ticket, "reservation_sha256": self.digest(self.ticket), "protocol_sha256": self.reservation["protocol_sha256"], "serial_log": f"{self.result_dir}/serial.log", "serial_sha256": self.digest(f"{self.result_dir}/serial.log"), "harness_sha256": {name: self.digest("benchmark/swap-standard/" + name) for name in ("run.py", "evidence.py")}, "protocol_revision": 4, "accelerator": "kvm", "guest_vcpus": 8, "guest_mem_mib": 8192, "integration_pass": True, "run_valid": True, "exit_code": 0, "stop_reason": None, "invalid_reasons": [], "metrics": parsed["metrics"], "gates": dict(parsed["gates"], qemu_exit=True)}
        self.save_proof()

    def put(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else (json.dumps(data, indent=2) + "\n").encode())

    def digest(self, relative):
        return sha((self.root / relative).read_bytes())

    def save_proof(self):
        self.put(self.proof["result_path"], self.proof)
        self.put(f"{self.result_dir}/result.sha256", (self.digest(self.proof["result_path"]) + "\n").encode())

    def validate(self):
        return module.validate(self.proof, self.protocol, self.root)

    def test_valid_counted_runner_result(self):
        summary = self.validate()
        self.assertEqual(summary["result_sha256"], self.digest(self.proof["result_path"]))
        self.assertEqual(summary["source_commit"], "a" * 40)
        self.assertEqual(summary["run_id"], self.run)

    def test_boolean_only_or_missing_raw_result_refused(self):
        with self.assertRaises(ValueError):
            module.validate({"candidate_commit": "a" * 40, "gates": {k: True for k in self.protocol["required_correctness_gates"]}}, self.protocol, self.root)
        (self.root / self.proof["result_path"]).unlink()
        with self.assertRaises(ValueError): self.validate()

    def test_wrong_campaign_mode_backend_or_workload(self):
        original = copy.deepcopy(self.proof)
        for key, value in (("campaign", "foreign"), ("mode", "plain"), ("backend", "zram"), ("workload", "swapin")):
            with self.subTest(key=key):
                self.proof = dict(original, **{key: value})
                self.save_proof()
                with self.assertRaises(ValueError): self.validate()

    def test_wrong_input_or_final_config(self):
        self.manifest["input_config_sha256"] = "f" * 64
        self.put(f"{self.manifest_dir}/result.json", self.manifest)
        self.proof["build_manifest_sha256"] = self.digest(f"{self.manifest_dir}/result.json")
        self.proof["input_config_sha256"] = "f" * 64
        self.save_proof()
        with self.assertRaisesRegex(ValueError, "config"): self.validate()
        self.manifest["input_config_sha256"] = self.digest("benchmark/config/swap-standard.config")
        self.put(f"{self.manifest_dir}/result.json", self.manifest)
        self.proof["build_manifest_sha256"] = self.digest(f"{self.manifest_dir}/result.json")
        self.proof["input_config_sha256"] = self.manifest["input_config_sha256"]
        self.put(f"{self.manifest_dir}/output/.config", b"tampered final configuration")
        self.save_proof()
        with self.assertRaisesRegex(ValueError, "config"): self.validate()

    def test_ticket_must_be_consumed_and_counted(self):
        for change in ({"status": "RESERVED"}, {"campaign": "foreign"}, {"identity": dict(self.reservation["identity"], mode="plain")}):
            self.put(self.ticket, dict(self.reservation, **change))
            self.proof["reservation_sha256"] = self.digest(self.ticket)
            self.save_proof()
            with self.assertRaisesRegex(ValueError, "reservation"): self.validate()
        self.put(self.ticket, self.reservation)
        self.proof["reservation_sha256"] = self.digest(self.ticket)
        self.put(f"{self.prefix}/ledger/budget.json", {"guests": 0})
        self.save_proof()
        with self.assertRaisesRegex(ValueError, "counted"): self.validate()

    def test_stale_protocol(self):
        self.put(f"{self.prefix}/protocol.json", dict(self.protocol, protocol_revision=5))
        with self.assertRaisesRegex(ValueError, "protocol"): self.validate()

    def test_tampered_raw_bytes(self):
        raw = self.root / self.proof["result_path"]
        raw.write_bytes(raw.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "result.*hash"): self.validate()

    def test_proof_dictionary_must_equal_raw_result(self):
        self.proof["gates"]["extra"] = True
        with self.assertRaisesRegex(ValueError, "raw result"): self.validate()

    def test_nonzero_exit_or_invalid_gates(self):
        original = copy.deepcopy(self.proof)
        for change in ({"exit_code": 1}, {"run_valid": False}, {"integration_pass": False}, {"gates": dict(original["gates"], fork_cow=False)}):
            self.proof = dict(original, **change)
            self.save_proof()
            with self.assertRaises(ValueError): self.validate()

    def test_serial_hash_and_reparsed_gates(self):
        path = self.root / self.proof["serial_log"]
        path.write_bytes(path.read_bytes().replace(b"COW_PASS", b"COW_FAIL"))
        with self.assertRaisesRegex(ValueError, "serial"): self.validate()
        self.proof["serial_sha256"] = self.digest(self.proof["serial_log"])
        self.save_proof()
        with self.assertRaisesRegex(ValueError, "serial"): self.validate()

    def test_result_and_ticket_refs_cannot_escape(self):
        original = copy.deepcopy(self.proof)
        for field in ("result_path", "reservation"):
            self.proof = dict(original, **{field: "../outside.json"})
            with self.assertRaises(ValueError): self.validate()

    def test_source_commit_must_match_manifest(self):
        self.manifest["commit"] = "b" * 40
        self.put(f"{self.manifest_dir}/result.json", self.manifest)
        self.proof["build_manifest_sha256"] = self.digest(f"{self.manifest_dir}/result.json")
        self.save_proof()
        with self.assertRaisesRegex(ValueError, "commit"): self.validate()

    def test_ticket_hash_and_unaccounted_extra_ticket(self):
        self.put(self.ticket, dict(self.reservation, started_unix=102))
        with self.assertRaisesRegex(ValueError, "hash"): self.validate()
        self.proof["reservation_sha256"] = self.digest(self.ticket)
        self.put(f"{self.prefix}/ledger/guest-reservations/extra.json", dict(self.reservation, id="extra"))
        self.save_proof()
        with self.assertRaisesRegex(ValueError, "counted"): self.validate()

    def test_reservation_cannot_use_an_unconfigured_pool(self):
        self.protocol["budget"]["guest_attempts"] = 0
        self.put(f"{self.prefix}/protocol.json", self.protocol)
        self.reservation["protocol_sha256"] = self.digest(f"{self.prefix}/protocol.json")
        self.put(self.ticket, self.reservation)
        self.proof["reservation_sha256"] = self.digest(self.ticket)
        self.proof["protocol_sha256"] = self.reservation["protocol_sha256"]
        self.save_proof()
        with self.assertRaisesRegex(ValueError, "guest pool"): self.validate()

    def test_canonical_paths_cannot_be_symlinked(self):
        path = self.root / self.proof["result_path"]
        backup = self.root / "elsewhere.json"
        backup.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(backup)
        with self.assertRaisesRegex(ValueError, "symlink"): self.validate()

    def test_runner_emits_relative_attestation_and_byte_sidecar(self):
        spec = importlib.util.spec_from_file_location("proof_runner_fixture", ROOT / "benchmark/swap-standard/run.py")
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        args = SimpleNamespace(campaign=self.campaign, reservation=self.root / self.ticket)
        destination = self.root / self.result_dir
        with mock.patch.object(runner, "PROJECT", self.root):
            fields = runner.attestation_fields(args, destination, self.root / self.manifest_dir, self.manifest)
        self.assertEqual(fields["reservation"], self.ticket)
        self.assertEqual(fields["reservation_sha256"], self.digest(self.ticket))
        self.assertEqual(fields["result_path"], self.proof["result_path"])
        runner.write_attested_result(destination, self.proof)
        self.assertEqual((destination / "result.sha256").read_text().strip(), self.digest(self.proof["result_path"]))

    def test_bound_counted_failure_exposes_evidence(self):
        path = self.root / self.proof["serial_log"]
        text = path.read_text().replace("COW_PASS", "COW_FAIL")
        path.write_text(text)
        parsed = parse(text, self.proof["image_sha256"], "disk", "xswap", "correctness")
        self.proof.update(parsed, integration_pass=False)
        self.proof["gates"]["qemu_exit"] = True
        self.proof["serial_sha256"] = self.digest(self.proof["serial_log"])
        self.save_proof()
        with self.assertRaises(module.CorrectnessFailure) as failure:
            self.validate()
        evidence = failure.exception.evidence
        self.assertEqual(evidence["source_commit"], "a" * 40)
        self.assertEqual(evidence["result_sha256"], self.digest(self.proof["result_path"]))
        self.assertFalse(evidence["gates"]["fork_cow"])
        self.assertFalse(evidence["passed"])

    def test_forged_failure_or_wrong_identity_is_not_negative_history(self):
        original = copy.deepcopy(self.proof)
        for change in ({"gates": dict(original["gates"], fork_cow=False), "integration_pass": False}, {"mode": "plain", "integration_pass": False}):
            self.proof = dict(original, **change)
            self.save_proof()
            with self.assertRaises(ValueError) as failure:
                self.validate()
            self.assertNotIsInstance(failure.exception, module.CorrectnessFailure)
            self.assertFalse(hasattr(failure.exception, "evidence"))

    def test_unconsumed_ticket_cannot_turn_real_gate_failure_into_negative_history(self):
        path = self.root / self.proof["serial_log"]
        text = path.read_text().replace("COW_PASS", "COW_FAIL")
        path.write_text(text)
        parsed = parse(text, self.proof["image_sha256"], "disk", "xswap", "correctness")
        self.proof.update(parsed, integration_pass=False)
        self.proof["gates"]["qemu_exit"] = True
        self.proof["serial_sha256"] = self.digest(self.proof["serial_log"])
        self.reservation["status"] = "RESERVED"
        self.put(self.ticket, self.reservation)
        self.proof["reservation_sha256"] = self.digest(self.ticket)
        self.save_proof()
        with self.assertRaises(ValueError) as failure: self.validate()
        self.assertNotIsInstance(failure.exception, module.CorrectnessFailure)

    def test_bound_nonzero_guest_exit_is_typed_but_external_stop_is_not(self):
        self.proof.update(exit_code=1, integration_pass=False)
        self.proof["gates"]["qemu_exit"] = False
        self.save_proof()
        with self.assertRaises(module.CorrectnessFailure): self.validate()
        self.proof["stop_reason"] = "STOP"
        self.save_proof()
        with self.assertRaises(ValueError) as failure: self.validate()
        self.assertNotIsInstance(failure.exception, module.CorrectnessFailure)

    def test_plain_mode_capability_is_explicitly_missing(self):
        self.protocol["cases"]["swapin-disk"]["mode"] = "plain"
        self.put(f"{self.prefix}/protocol.json", self.protocol)
        with self.assertRaisesRegex(ValueError, "plain.*correctness"): self.validate()


if __name__ == "__main__":
    unittest.main()
