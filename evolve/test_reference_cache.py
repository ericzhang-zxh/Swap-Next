# SPDX-License-Identifier: GPL-2.0-only
"""Synthetic guest-free source/measurement fixtures, never actual kernel results."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from evolve import reference_cache as cache

sys.path.insert(0, str(cache.ROOT / "benchmark/swap-standard"))
from evidence import parse
from test_evidence import fixture, block, correctness


class ReferenceCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        linux = self.root / "linux"
        linux.mkdir()
        subprocess.run(["git", "init", "-q", str(linux)], check=True)
        (linux / "fixture.txt").write_text("Synthetic source; no kernel execution.\n")
        subprocess.run(["git", "-C", str(linux), "add", "fixture.txt"], check=True)
        subprocess.run(["git", "-C", str(linux), "-c", "user.name=Fixture",
                        "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture"], check=True)
        self.commit = subprocess.check_output(["git", "-C", str(linux), "rev-parse", "HEAD"], text=True).strip()
        self.tree = subprocess.check_output(["git", "-C", str(linux), "rev-parse", "HEAD^{tree}"], text=True).strip()
        for relative in ("benchmark/swap-standard/run.py", "benchmark/swap-standard/evidence.py",
                         "benchmark/swap-standard/validity.py", "benchmark/swap-standard/analysis.py",
                         "benchmark/swap-standard/probe.py", "evolve/control/correctness_proof.py"):
            self.put(relative, (cache.ROOT / relative).read_bytes())
        self.put("benchmark/config/swap-standard.config", b"CONFIG_SWAP=y\n")
        self.put("benchmark/kernel/builds/build/output/.config", b"CONFIG_SWAP=y\n")
        self.put("benchmark/kernel/builds/build/output/arch/x86/boot/bzImage", b"Fixture image, no build or boot.\n")
        self.put("benchmark/kernel/builds/build/build.log", b"Synthetic fixture only.\n")
        self.build = {"commit": self.commit, "passed": True, "exit_code": 0, "instrument_sha256": None,
                      "input_config_sha256": self.sha("benchmark/config/swap-standard.config"),
                      "config_sha256": self.sha("benchmark/kernel/builds/build/output/.config"),
                      "image_sha256": self.sha("benchmark/kernel/builds/build/output/arch/x86/boot/bzImage")}
        self.put("benchmark/kernel/builds/build/result.json", self.build)
        self.put("benchmark/swap-standard/bench.img", b"fixture image")
        self.put("benchmark/swap-standard/initramfs.cpio.gz", b"fixture initrd")
        self.put("benchmark/swap-standard/fixture-source.txt", b"fixture guest source")
        self.guest_image = {"image_sha256": self.sha("benchmark/swap-standard/bench.img"),
                            "initrd_sha256": self.sha("benchmark/swap-standard/initramfs.cpio.gz"),
                            "sources": {"fixture-source.txt": self.sha("benchmark/swap-standard/fixture-source.txt")}}
        self.put("benchmark/swap-standard/image.json", self.guest_image)
        self.protocol = {
            "campaign": "source", "protocol_revision": 1, "baseline_commit": self.commit, "baseline_build": "build",
            "guest": {"vcpus": 4, "mem_mib": 4096, "swap_gib": 16}, "accelerator": {"require": "tcg"},
            "cases": {"swapin-disk": {"workload": "swapin", "mode": "xswap", "backend": "disk",
                                     "primary": "swapin_seq.mean_ns", "metrics": {"swapin_seq.mean_ns": "lower"}}},
            "tiers": {"fast": {"cases": ["swapin-disk"], "calibration_pairs": 2, "comparison_pairs": 2}},
            "required_correctness_gates": ["data_roundtrip", "fork_cow", "concurrent_fault", "swapoff_live_pages", "no_new_kernel_warnings"],
            "budget": {"guest_attempts": 100, "probe_guest_attempts": 20, "guest_timeout": 900, "build_attempts": 10, "wall_seconds": 1000},
            "calibration_max_age_seconds": 10, "preallocate_swap": True,
        }
        self.put("campaigns/source/protocol.json", self.protocol)
        self.put("campaigns/source/campaign.json", {"campaign": "source", "machine": "fixture", "status": "open"})
        self.put("campaigns/source/ledger/budget.json", {"guests": 0, "probe_guests": 0})
        self.count = 0

    def tearDown(self):
        self.temporary.cleanup()

    def put(self, reference, value):
        path = self.root / reference
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else (json.dumps(value, indent=2) + "\n").encode())
        return path

    def sha(self, reference):
        return cache.sha(self.root / reference)

    def build_identity(self):
        return {"source_commit": self.commit, "source_tree": self.tree,
                **{key: self.build[key] for key in ("input_config_sha256", "config_sha256", "image_sha256")},
                "build_manifest_sha256": self.sha("benchmark/kernel/builds/build/result.json")}

    def identity(self, kind="calibration"):
        harness = {path: self.sha(path) for path in cache.RUNTIME_HARNESS}
        harness["evolve/control/correctness_proof.py" if kind == "correctness" else
                "benchmark/swap-standard/analysis.py"] = self.sha(
                    "evolve/control/correctness_proof.py" if kind == "correctness" else "benchmark/swap-standard/analysis.py")
        result = {"source_commit": self.commit, "source_tree": self.tree, "protocol": copy.deepcopy(self.protocol),
                  "machine": "fixture", "accelerator": "tcg", "guest": copy.deepcopy(self.protocol["guest"]),
                  "builds": {self.commit: {"tree": self.tree, **{key: self.build[key] for key in
                             ("input_config_sha256", "config_sha256", "image_sha256")}}},
                  "guest_image": self.guest_image, "harness": harness}
        if kind != "correctness":
            result.update(tier="fast", contrast={"baseline_commit": self.commit, "candidate_commit": self.commit})
        return result

    def provenance(self, artifact, observed=100):
        return {"artifact": artifact, "artifact_sha256": self.sha(artifact), "observed_unix": observed,
                "campaign": "source", "protocol_path": "campaigns/source/protocol.json",
                "protocol_sha256": self.sha("campaigns/source/protocol.json"), "fingerprint": "f" * 64}

    def raw_run(self, run_id, pair=0, arm="a", workload="swapin"):
        prefix = "campaigns/source/runs/guests/" + run_id
        serial = (fixture("swapin", "disk").replace("bench.mode=plain", "bench.mode=xswap")
                  .replace("/dev/vda 1024", "/dev/vda 1024\n/dev/xswap0 4096"))
        serial += ("SWAPIN_SEQ samples=4 mean_ns=100 p99_ns=200\n"
                   "SWAPIN_RAND samples=4 mean_ns=100 p99_ns=200\n"
                   "SWAPIN_SWAPPED pages=100\nSWAPIN_DATA_PASS\n")
        for tag, count in (("swapin_start", 0), ("swapin_end", 4)):
            serial += block("VMSTAT", tag, f"swap_ra {count}\nswap_ra_hit {count}")
            serial += block("XSWAP", tag, f"clusters_mapped 1\nusage_pages 100\ngrows 1\nshrinks 0")
        if workload == "correctness":
            serial = correctness(backend="disk") if "backend" in correctness.__code__.co_varnames else correctness()
        serial = serial.replace("bench.image_sha=abc", "bench.image_sha=" + self.build["image_sha256"])
        parsed = parse(serial, self.build["image_sha256"], "disk", "xswap", workload)
        self.assertTrue(all(parsed["gates"].values()), parsed["gates"])
        self.put(prefix + "/serial.log", serial.encode())
        ticket_path = "campaigns/source/ledger/guest-reservations/" + run_id + ".json"
        ticket = {"id": run_id, "campaign": "source", "pool": "fast", "status": "STARTED",
                  "reserved_unix": 50, "started_unix": 51,
                  "protocol_sha256": self.sha("campaigns/source/protocol.json"),
                  "identity": {"build": "build", "backend": "disk", "mode": "xswap", "workload": workload}}
        self.put(ticket_path, ticket)
        self.count += 1
        self.put("campaigns/source/ledger/budget.json", {"guests": self.count, "probe_guests": 0})
        raw = {"proof_schema_version": 1, "run_id": run_id, "campaign": "source", "build": "build",
               "result_path": prefix + "/result.json", "source_commit": self.commit,
               "backend": "disk", "mode": "xswap", "workload": workload,
               "protocol_revision": 1, "protocol_sha256": self.sha("campaigns/source/protocol.json"),
               "build_manifest": "benchmark/kernel/builds/build/result.json",
               "build_manifest_sha256": self.sha("benchmark/kernel/builds/build/result.json"),
               "reservation": ticket_path, "reservation_sha256": self.sha(ticket_path),
               "serial_log": prefix + "/serial.log", "serial_sha256": self.sha(prefix + "/serial.log"),
               "harness_sha256": {name: self.sha("benchmark/swap-standard/" + name) for name in ("run.py", "evidence.py")},
               "image_sha256": self.build["image_sha256"], "config_sha256": self.build["config_sha256"],
               "input_config_sha256": self.build["input_config_sha256"],
               "guest_provenance": self.guest_image, "accelerator": "tcg", "guest_vcpus": 4, "guest_mem_mib": 4096,
               "swap_image_allocation": "preallocated", "integration_pass": True, "exit_code": 0,
               "stop_reason": None, "run_valid": True, "invalid_reasons": [], "wall_seconds": 1,
               "metrics": parsed["metrics"], "gates": dict(parsed["gates"], qemu_exit=True)}
        self.put(raw["result_path"], raw)
        self.put(prefix + "/result.sha256", (self.sha(raw["result_path"]) + "\n").encode())
        return {"id": run_id, "pair": pair, "arm": arm, "case": "swapin-disk", "status": "PASS",
                "result": raw["result_path"], "result_sha256": self.sha(raw["result_path"]),
                "metrics": raw["metrics"], "run_valid": True}, raw

    def measurement(self, kind, ident, observed=100, calibration=None):
        runs, pairs = [], []
        for index in range(2):
            pair = {"a": {}, "b": {}, "order": "AB" if index == 0 else "BA"}
            for arm in ("a", "b") if index == 0 else ("b", "a"):
                attempt, raw = self.raw_run(f"{ident}-{index}-{arm}", index, arm)
                runs.append(attempt)
                pair[arm]["swapin-disk.swapin_seq.mean_ns"] = raw["metrics"]["swapin_seq"]["mean_ns"]
            pairs.append(pair)
        analyzer = cache.Verifier(self.root).native("benchmark/swap-standard/analysis.py")
        directions = {"swapin-disk.swapin_seq.mean_ns": "lower"}
        primary = list(directions)
        scored = [{arm: pair[arm] for arm in ("a", "b")} for pair in pairs]
        if kind == "calibration":
            analysis = analyzer.calibrate(scored, directions, primary=primary, min_pairs=2)
        else:
            analysis = analyzer.compare(scored, directions, calibration["analysis"], "fast", primary=primary, min_pairs=2)
        report = {"id": ident, "action": "calibrate" if kind == "calibration" else "evaluate",
                  "tier": "fast", "candidate_commit": self.commit, "fingerprint": "f"*64,
                  "finished": observed, "runs": runs, "pairs": pairs,
                  "analysis": analysis, "status": analysis["status"]}
        if calibration:
            report["calibration_id"] = calibration["id"]
        path = "campaigns/source/runs/evaluations/" + ident + "/report.json"
        self.put(path, report)
        return report, self.provenance(path, observed)

    def test_upstream_source_is_pinned_once(self):
        self.put("sources/upstream.patch", b"synthetic upstream patch bytes")
        identity = {"source_commit": self.commit, "source_tree": self.tree,
                    "source_url": "https://example.invalid/patch-v1", "revision": "v1",
                    "base_commit": self.commit, "source_sha256": self.sha("sources/upstream.patch")}
        self.put("sources/upstream.json", {"source_url": identity["source_url"], "revision": "v1",
                 "base_commit": self.commit, "commit": self.commit, "tree": self.tree,
                 "source_sha256": identity["source_sha256"]})
        provenance = self.provenance("sources/upstream.patch")
        provenance["source_manifest"] = "sources/upstream.json"
        record = cache.register(self.root, "upstream-source", identity, provenance)
        self.assertTrue(record["verification"]["passed"], record)
        self.assertEqual(cache.lookup(self.root, "upstream-source", identity, now=100000)["status"], "reusable")
        changed = copy.deepcopy(identity)
        changed["revision"] = "v2"
        self.assertEqual(cache.lookup(self.root, "upstream-source", changed, now=101)["status"], "new-measurement-needed")

    def test_review_revalidates_native_record_and_current_veto(self):
        native_path = Path(os.environ.get("SWAP_NEXT_REVIEW_MODULE", cache.ROOT / "evolve/reviews.py"))
        if not native_path.is_file():
            self.skipTest("native review module is not integrated in this isolated snapshot")
        self.put("evolve/reviews.py", native_path.read_bytes())
        policy = "evolve/control/CODE_PATTERNS.md"
        self.put(policy, b"Fixture exact-tree review policy.")
        native = cache.Verifier(self.root).native("evolve/reviews.py")
        self.put("campaigns/source/candidates/candidate.json", {"id":"candidate",
                 "candidate_commit":self.commit, "source_tree":self.tree})
        payload = {"schema_version":1, "id":"pass-review", "campaign":"source", "candidate":"candidate",
                   "candidate_commit":self.commit, "source_tree":self.tree, "reviewer":"fixture",
                   "summary":"Synthetic exact-tree review", "disposition":"pass", "findings":[], "resolves":[],
                   "evidence":[{"path":policy,"sha256":self.sha(policy)}]}
        saved = native.record(self.root, "source", payload)
        identity = {"source_commit":self.commit,"source_tree":self.tree,"review_policy_sha256":self.sha(policy)}
        provenance = self.provenance("campaigns/source/reviews/pass-review.json", saved["recorded_unix"])
        provenance["review_policy"] = policy
        record = cache.register(self.root,"review",identity,provenance)
        self.assertTrue(record["verification"]["passed"],record)
        self.assertEqual(cache.lookup(self.root,"review",identity,now=saved["recorded_unix"]+1)["status"],"reusable")
        veto = dict(payload, id="later-veto",disposition="veto",findings=[{"id":"unsafe","summary":"Unresolved fixture finding"}])
        native.record(self.root,"source",veto)
        result = cache.lookup(self.root,"review",identity,now=saved["recorded_unix"]+2)
        self.assertNotEqual(result["status"],"reusable")
        self.assertTrue(any("veto" in reason for reason in result["reasons"]))

    def test_semantic_key_ignores_only_explicit_cosmetic_fields(self):
        identity = self.identity()
        changed = copy.deepcopy(identity)
        changed["protocol"]["campaign"] = "new"
        changed["protocol"]["budget"]["guest_attempts"] = 60
        self.assertEqual(cache.cache_key("calibration", identity), cache.cache_key("calibration", changed))
        for field in ("guest_timeout", "unknown_scientific_field"):
            changed = copy.deepcopy(identity)
            changed["protocol"]["budget"][field] = 5
            self.assertNotEqual(cache.cache_key("calibration", identity), cache.cache_key("calibration", changed))
        changed = copy.deepcopy(identity)
        changed["protocol"]["noise_floor"] = float("nan")
        with self.assertRaises(cache.CacheError):
            cache.cache_key("calibration", changed)

    def test_exact_build_reuses_without_budget_or_source_mutation(self):
        identity = self.build_identity()
        provenance = self.provenance("benchmark/kernel/builds/build/result.json")
        before = self.sha("campaigns/source/ledger/budget.json")
        first = cache.register(self.root, "build", identity, provenance)
        self.assertTrue(first["verification"]["passed"], first)
        self.assertEqual(cache.register(self.root, "build", identity, provenance), first)
        result = cache.lookup(self.root, "build", identity, now=200)
        self.assertEqual(result["status"], "reusable", result)
        self.assertEqual(before, self.sha("campaigns/source/ledger/budget.json"))
        self.assertEqual(len(cache.inventory(self.root, "build")), 1)
        (self.root/"benchmark/kernel/builds/build/output/arch/x86/boot/bzImage").unlink()
        result = cache.lookup(self.root, "build", identity, now=200)
        self.assertEqual(result["status"], "new-measurement-needed")
        self.assertTrue(any("missing raw" in why for why in result["reasons"]))

    def test_failed_build_never_becomes_pass(self):
        self.build["passed"] = False
        self.put("benchmark/kernel/builds/build/result.json", self.build)
        identity = self.build_identity()
        record = cache.register(self.root, "build", identity, self.provenance("benchmark/kernel/builds/build/result.json"))
        self.assertFalse(record["verification"]["passed"])
        self.assertEqual(cache.lookup(self.root, "build", identity, now=101)["status"], "historical")

    def test_calibration_replays_raw_and_preserves_original_expiry(self):
        report, provenance = self.measurement("calibration", "cal")
        identity = self.identity()
        record = cache.register(self.root, "calibration", identity, provenance)
        self.assertTrue(record["verification"]["passed"], record)
        other = copy.deepcopy(identity)
        other["protocol"]["campaign"] = "new"
        other["protocol"]["budget"]["guest_attempts"] = 80
        result = cache.lookup(self.root, "calibration", other, now=105)
        self.assertEqual(result["status"], "reusable", result)
        self.assertEqual(result["provenance"]["campaign"], "source")
        self.assertEqual(cache.lookup(self.root, "calibration", other, now=110)["status"], "new-measurement-needed")
        with self.assertRaises(cache.CacheError):
            cache.register(self.root, "calibration", identity, provenance, max_age_seconds=11)
        # Closing the original campaign changes no measured input or observed time.
        self.put("campaigns/source/campaign.json", {"campaign":"source","machine":"fixture","status":"closed"})
        self.assertEqual(cache.lookup(self.root, "calibration", identity, now=106)["status"], "reusable")

    def test_missing_raw_log_and_changed_environment_require_new_measurement(self):
        report, provenance = self.measurement("calibration", "cal")
        identity = self.identity()
        cache.register(self.root, "calibration", identity, provenance)
        changed = copy.deepcopy(identity)
        changed["machine"] = "other"
        result = cache.lookup(self.root, "calibration", changed, now=105)
        self.assertEqual(result["status"], "new-measurement-needed")
        self.assertIn("machine", result["mismatches"][0]["fields"])
        (self.root/"campaigns/source/runs/guests/cal-0-a/serial.log").unlink()
        result = cache.lookup(self.root, "calibration", identity, now=105)
        self.assertEqual(result["status"], "new-measurement-needed")

    def test_summary_only_cannot_be_registered_as_passing_calibration(self):
        report = {"status":"CALIBRATED","analysis":{"passed":True},"tier":"fast","action":"calibrate",
                  "candidate_commit":self.commit,"fingerprint":"f"*64,"finished":100}
        path = "campaigns/source/runs/evaluations/fake/report.json"
        self.put(path, report)
        record = cache.register(self.root, "calibration", self.identity(), self.provenance(path))
        self.assertFalse(record["verification"]["passed"])
        self.assertEqual(cache.lookup(self.root, "calibration", self.identity(), now=105)["status"], "historical")

    def test_performance_only_reuses_whole_upstream_contrast_with_finite_age(self):
        calibration, calprov = self.measurement("calibration", "cal")
        report, provenance = self.measurement("performance", "perf", observed=105, calibration=calibration)
        provenance["calibration_report"] = calprov["artifact"]
        identity = self.identity("performance")
        identity["reference_role"] = "upstream"
        record = cache.register(self.root, "performance", identity, provenance, max_age_seconds=20)
        self.assertTrue(record["verification"]["passed"], record)
        context = {"campaign": "new", "protocol_sha256":"1"*64, "fingerprint":"2"*64}
        result = cache.lookup(self.root, "performance", identity, context, now=110)
        self.assertEqual(result["status"], "historical")
        context.update(reuse_intact_contrast=True, purpose="upstream-reference")
        result = cache.lookup(self.root, "performance", identity, context, now=110)
        self.assertEqual(result["status"], "reusable", result)
        self.assertTrue(result["cross_campaign_reused"])
        self.assertFalse(result["independent_measurement"])
        self.assertFalse(result["may_pair_with_new_arm"])
        self.assertEqual(result["provenance"]["observed_unix"], 105)
        context["review_blocked"] = True
        self.assertEqual(cache.lookup(self.root, "performance", identity, context, now=110)["status"], "historical")
        context.pop("review_blocked")
        self.assertEqual(cache.lookup(self.root, "performance", identity, context, now=125)["status"], "new-measurement-needed")
        stale, stale_provenance = self.measurement("performance", "stale-perf", observed=110, calibration=calibration)
        stale_provenance["calibration_report"] = calprov["artifact"]
        invalid = cache.register(self.root, "performance", identity, stale_provenance, max_age_seconds=20)
        self.assertFalse(invalid["verification"]["passed"])
        self.assertTrue(any("valid" in reason for reason in invalid["verification"]["reasons"]))

    def test_correctness_calls_native_raw_validator_and_retains_campaign(self):
        attempt, proof = self.raw_run("correct", workload="correctness")
        identity = self.identity("correctness")
        provenance = self.provenance(proof["result_path"])
        record = cache.register(self.root, "correctness", identity, provenance)
        self.assertTrue(record["verification"]["passed"], record)
        query = copy.deepcopy(identity)
        query["protocol"]["campaign"] = "target"
        result = cache.lookup(self.root, "correctness", query, now=105)
        self.assertEqual(result["status"], "reusable", result)
        self.assertTrue(result["reconciliation_required"])
        self.assertEqual(result["provenance"]["campaign"], "source")
        result = cache.lookup(self.root, "correctness", query,
                              {"required_coverage":{"gates":["kcsan"]}}, now=105)
        self.assertEqual(result["status"], "new-measurement-needed")


if __name__ == "__main__":
    unittest.main()
