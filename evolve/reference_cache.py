# SPDX-License-Identifier: GPL-2.0-only
"""Immutable references to existing evidence; never cloned campaigns or budgets.

Exact builds, upstream sources and reviews can be discovered once and reused.
Runtime reuse is narrower: calibration expires, correctness keeps its original
proof, and an intact upstream contrast keeps its original paired observations.
"""
import argparse
import copy
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
KINDS = {"build", "upstream-source", "review", "correctness", "performance", "calibration"}
RUNTIME = {"correctness", "performance", "calibration"}
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
NAME = re.compile(r"[a-z][a-z0-9-]{0,47}")
# Only these exact protocol fields are presentation/location/allocation metadata.
# guest_timeout, validity, calibration age, counts and unknown fields stay in key.
COSMETIC_PROTOCOL_FIELDS = {
    ("campaign",), ("state_directory",), ("report_directory",), ("runs_directory",),
    ("budget", "guest_attempts"), ("budget", "probe_guest_attempts"),
    ("budget", "build_attempts"), ("budget", "wall_seconds"),
    ("max_candidates",), ("max_probe_candidates",),
}
RUNTIME_HARNESS = {
    "benchmark/swap-standard/run.py", "benchmark/swap-standard/evidence.py",
    "benchmark/swap-standard/validity.py",
}


class CacheError(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise CacheError(message)


def text(value, label):
    need(isinstance(value, str) and bool(value.strip()), label + " must be non-empty text")
    return value


def number(value, label, minimum=0):
    need(not isinstance(value, bool) and isinstance(value, (int, float)) and
         math.isfinite(value) and value >= minimum, label + " must be finite and in range")
    return value


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise CacheError("cache data must be finite JSON") from exc


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def sha(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            result.update(chunk)
    return result.hexdigest()


def read(path):
    try:
        value = json.loads(path.read_text())
        canonical(value)
        return value
    except (OSError, json.JSONDecodeError) as exc:
        raise CacheError(str(exc)) from exc


def relative(value):
    text(value, "evidence path")
    need(not Path(value).is_absolute() and "\\" not in value and
         all(part not in ("", ".", "..") for part in value.split("/")),
         "evidence path must be normalized and repository-relative")
    return value


def file_at(root, value):
    value = relative(value)
    path = root
    for part in value.split("/"):
        path = path / part
        need(not path.is_symlink(), "evidence path uses a symlink: " + value)
    need(path.resolve().is_relative_to(root) and path.is_file(), "missing raw evidence: " + value)
    return path


def _strip_protocol(value, prefix=()):
    if isinstance(value, dict):
        return {key: _strip_protocol(item, prefix + (key,)) for key, item in value.items()
                if prefix + (key,) not in COSMETIC_PROTOCOL_FIELDS}
    if isinstance(value, list):
        return [_strip_protocol(item, prefix) for item in value]
    return copy.deepcopy(value)


def semantic_identity(kind, identity):
    """Unknown fields stay significant. Only an explicit protocol allowlist is omitted."""
    need(kind in KINDS, "unknown cache kind")
    need(isinstance(identity, dict), "cache identity must be an object")
    canonical(identity)
    for key in ("source_commit", "source_tree"):
        need(isinstance(identity.get(key), str) and HEX40.fullmatch(identity[key]), "exact " + key + " required")
    if kind == "upstream-source":
        for key in ("source_url", "revision"):
            text(identity.get(key), key)
        need(isinstance(identity.get("base_commit"), str) and HEX40.fullmatch(identity["base_commit"]), "exact upstream base required")
        need(isinstance(identity.get("source_sha256"), str) and HEX64.fullmatch(identity["source_sha256"]), "source content hash required")
    if kind == "build":
        for key in ("input_config_sha256", "config_sha256", "image_sha256", "build_manifest_sha256"):
            need(isinstance(identity.get(key), str) and HEX64.fullmatch(identity[key]), key + " required")
    if kind == "build" and "config_id" in identity:
        need(isinstance(identity.get("config_id"), str) and NAME.fullmatch(identity["config_id"]),
             "named build configuration required")
        relative(identity.get("config_path"))
        need(isinstance(identity.get("configured_build_sha256"), str)
             and HEX64.fullmatch(identity["configured_build_sha256"]), "configured build hash required")
    if kind == "review":
        need(isinstance(identity.get("review_policy_sha256"), str) and HEX64.fullmatch(identity["review_policy_sha256"]), "review policy hash required")
    if kind in RUNTIME:
        need(isinstance(identity.get("protocol"), dict), "complete source protocol required")
        text(identity.get("machine"), "machine")
        need(identity.get("accelerator") in ("kvm", "tcg"), "accelerator required")
        guest = identity.get("guest")
        need(isinstance(guest, dict), "guest shape required")
        for key in ("vcpus", "mem_mib", "swap_gib"):
            need(type(guest.get(key)) is int and guest[key] > 0, "guest " + key + " required")
        builds = identity.get("builds")
        need(isinstance(builds, dict) and identity["source_commit"] in builds, "exact runtime builds required")
        revision8 = identity["protocol"].get("protocol_revision") == 8
        matrix_builds = revision8 and kind == "correctness"
        expected_configs = {}
        if matrix_builds:
            matrix = identity["protocol"].get("correctness_matrix", {})
            for case in matrix.get("cases", []) + matrix.get("build_only", []):
                commit = (identity["protocol"]["baseline_commit"] if case["role"] == "baseline"
                          else identity["source_commit"])
                expected_configs.setdefault(commit, set()).add(case["config_id"])
            need(set(builds) == set(expected_configs), "matrix runtime source set mismatch")
        for commit, build in builds.items():
            need(isinstance(commit, str) and HEX40.fullmatch(commit) and isinstance(build, dict), "runtime build identity")
            need(isinstance(build.get("tree"), str) and HEX40.fullmatch(build["tree"]), "runtime build tree")
            variants = build.get("configurations") if matrix_builds else {build.get("config_id", "standard"): build}
            need(isinstance(variants, dict) and variants, "runtime configuration builds missing")
            if matrix_builds:
                need(set(variants) == expected_configs[commit], "matrix runtime configuration set mismatch")
            for config_id, variant in variants.items():
                need(isinstance(variant, dict), "runtime configuration build malformed")
                for key in ("image_sha256", "config_sha256", "input_config_sha256"):
                    need(isinstance(variant.get(key), str) and HEX64.fullmatch(variant[key]), "runtime " + key)
                if revision8:
                    need(variant.get("config_id") == config_id
                         and config_id in identity["protocol"].get("configurations", {}),
                         "runtime named configuration mismatch")
                    if not matrix_builds:
                        need(config_id == "c1-common", "timing cache requires c1-common")
                    relative(variant.get("config_path"))
                    need(isinstance(variant.get("configured_build_sha256"), str)
                         and HEX64.fullmatch(variant["configured_build_sha256"]), "runtime configured build hash required")
        need(builds[identity["source_commit"]]["tree"] == identity["source_tree"], "runtime source tree mismatch")
        guest_image = identity.get("guest_image")
        need(isinstance(guest_image, dict), "guest image provenance required")
        for key in ("image_sha256", "initrd_sha256"):
            need(isinstance(guest_image.get(key), str) and HEX64.fullmatch(guest_image[key]), "guest image " + key)
        need(isinstance(guest_image.get("sources"), dict) and guest_image["sources"], "guest source hashes required")
        harness = identity.get("harness")
        required = set(RUNTIME_HARNESS)
        if revision8:
            required.update({"benchmark/swap-standard/configurations.py",
                             "benchmark/swap-standard/compression.c", "evolve/control/correctness_proof.py"})
        required.add("evolve/control/correctness_proof.py" if kind == "correctness" else "benchmark/swap-standard/analysis.py")
        if identity.get("evaluation_format") == "comparison-runtime-v1":
            required.update({"evolve/comparison_runtime.py", "evolve/comparisons.py"})
        if identity.get("tier") == "probe":
            required.add("benchmark/swap-standard/probe.py")
        need(isinstance(harness, dict) and required <= set(harness), "runner/parser/evaluator/proof version hashes required")
        for path, value in harness.items():
            relative(path)
            need(isinstance(value, str) and HEX64.fullmatch(value), "harness content hash required")
        if kind in {"performance", "calibration"}:
            need(identity.get("tier") in {"probe", "fast", "slow"}, "measurement tier required")
            contrast = identity.get("contrast")
            need(isinstance(contrast, dict), "exact measured contrast required")
            for arm in ("baseline_commit", "candidate_commit"):
                need(contrast.get(arm) in builds, "contrast build absent: " + arm)
            if kind == "calibration":
                need(contrast["baseline_commit"] == contrast["candidate_commit"], "calibration must be A/A")
    result = copy.deepcopy(identity)
    if "protocol" in result:
        result["protocol"] = _strip_protocol(result["protocol"])
    return result


def cache_key(kind, identity):
    return digest({"kind": kind, "identity": semantic_identity(kind, identity)})


class Verifier:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.files = {}

    def file(self, reference, expected=None):
        path = file_at(self.root, reference)
        found = self.files.get(reference)
        actual = found["sha256"] if found else sha(path)
        if expected is not None:
            need(isinstance(expected, str) and HEX64.fullmatch(expected) and actual == expected,
                 "evidence hash mismatch: " + reference)
        self.files[reference] = {"path": reference, "sha256": actual}
        return path

    def json(self, reference, expected=None):
        return read(self.file(reference, expected))

    def native(self, relative_path):
        path = self.file(relative_path)
        spec = importlib.util.spec_from_file_location("swap_cache_" + digest(relative_path)[:12], path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def tree(self, commit, expected):
        try:
            actual = subprocess.check_output(["git", "-C", str(self.root / "linux"),
                "rev-parse", commit + "^{tree}"], text=True, stderr=subprocess.PIPE, timeout=15).strip()
        except (OSError, subprocess.SubprocessError) as exc:
            raise CacheError("source Git object unavailable: " + commit) from exc
        need(actual == expected, "source commit/tree mismatch")

    def protocol(self, identity, provenance):
        source = self.json(provenance.get("protocol_path"), provenance.get("protocol_sha256"))
        need(source == identity["protocol"], "identity differs from original source protocol")
        need(source.get("campaign") == provenance.get("campaign"), "original campaign mismatch")
        rules = self.native("benchmark/swap-standard/validity.py").protocol_rules(source)
        need(source.get("accelerator", {}).get("require") == identity["accelerator"] and
             source.get("guest") == identity["guest"], "protocol environment mismatch")
        campaign = read(file_at(self.root, "campaigns/" + provenance["campaign"] + "/campaign.json"))
        need(campaign.get("machine") == identity["machine"], "source measurement machine mismatch")
        for path, expected in identity["harness"].items():
            self.file(path, expected)
        for commit, build in identity["builds"].items():
            self.tree(commit, build["tree"])
        guest = identity["guest_image"]
        need(self.json("benchmark/swap-standard/image.json") == guest, "guest image manifest mismatch")
        self.file("benchmark/swap-standard/bench.img", guest["image_sha256"])
        self.file("benchmark/swap-standard/initramfs.cpio.gz", guest["initrd_sha256"])
        for name, expected in guest["sources"].items():
            self.file("benchmark/swap-standard/" + relative(name), expected)
        return source, rules

    def build(self, manifest_path, expected_commit, expected):
        manifest = self.json(manifest_path)
        need(manifest.get("commit") == expected_commit and manifest.get("passed") is True and
             type(manifest.get("exit_code")) is int and manifest["exit_code"] == 0,
             "build did not pass for exact source")
        need(manifest.get("instrument_sha256", "missing") is None, "instrumented or unidentified build")
        directory = str(Path(manifest_path).parent)
        for suffix, key in (("/output/.config", "config_sha256"),
                            ("/output/arch/x86/boot/bzImage", "image_sha256")):
            need(manifest.get(key) == expected[key], "build manifest " + key + " mismatch")
            self.file(directory + suffix, expected[key])
        need(manifest.get("input_config_sha256") == expected["input_config_sha256"], "input config identity mismatch")
        config_id = expected.get("config_id", "standard")
        if config_id == "standard":
            self.file("benchmark/config/swap-standard.config", expected["input_config_sha256"])
        else:
            catalog = self.native("benchmark/swap-standard/configurations.py")
            config = catalog.get_config(config_id, self.root)
            need(expected.get("config_path") == config["path"], "configured build path mismatch")
            self.file(config["path"], expected["input_config_sha256"])
            catalog.validate_final(config_id, self.root / directory / "output/.config")
            self.file(directory + "/configured-build.json", expected.get("configured_build_sha256"))
            catalog.verify_build_binding(self.root, self.root / manifest_path, expected_commit, config_id)
        self.file(directory + "/build.log")
        return manifest

    def run(self, attempt, protocol, identity, rules, prior_walls):
        result_path = attempt.get("result")
        result = self.json(result_path, attempt.get("result_sha256"))
        run_id = attempt.get("id")
        need(result.get("run_id") == run_id and result.get("campaign") == protocol["campaign"],
             "raw run identity mismatch")
        need(result.get("proof_schema_version") == 1 and result.get("result_path") == result_path,
             "raw runner attestation required")
        sidecar = self.file(str(Path(result_path).with_name("result.sha256")))
        need(sidecar.read_text().strip() == self.files[result_path]["sha256"], "raw result sidecar mismatch")
        need(result.get("protocol_sha256") == sha(self.root / ("campaigns/" + protocol["campaign"] + "/protocol.json")),
             "raw run protocol mismatch")
        case = protocol["cases"][attempt["case"]]
        for key in ("backend", "workload"):
            need(result.get(key) == case[key], "raw run " + key + " mismatch")
        need(result.get("mode") == case.get("mode", "plain"), "raw run mode mismatch")
        revision8 = protocol.get("protocol_revision") == 8
        if revision8:
            need(result.get("config_id") == case.get("config_id") == "c1-common"
                 and result.get("topology_id") == case.get("topology_id", "single") == "single"
                 and result.get("correctness_case") is None,
                 "raw timing configuration/case/topology mismatch")
            self.native("benchmark/swap-standard/configurations.py").validate_topology_record(
                protocol, result, "timing")
        need(result.get("accelerator") == identity["accelerator"] and
             result.get("guest_vcpus") == identity["guest"]["vcpus"] and
             result.get("guest_mem_mib") == identity["guest"]["mem_mib"], "raw environment mismatch")
        need(result.get("guest_provenance") == identity["guest_image"], "raw guest image provenance mismatch")
        commit = result.get("source_commit")
        need(commit in identity["builds"], "raw source not in frozen build set")
        build = identity["builds"][commit]
        for key in ("image_sha256", "config_sha256", "input_config_sha256"):
            need(result.get(key) == build[key], "raw build " + key + " mismatch")
        self.file(result["build_manifest"], result["build_manifest_sha256"])
        self.build(result["build_manifest"], commit, build)
        serial = self.file(result.get("serial_log"), result.get("serial_sha256"))
        parser = self.native("benchmark/swap-standard/evidence.py")
        revision = result.get("protocol_revision", protocol.get("protocol_revision", 1))
        kwargs = ({"config_id": result["config_id"], "correctness_case": None,
                   "topology_id": result["topology_id"]} if revision8 else {})
        parsed = parser.parse(serial.read_text(errors="replace"), result["image_sha256"],
                              result["backend"], result["mode"], result["workload"],
                              revision, **kwargs)
        expected_gates = dict(parsed["gates"], qemu_exit=result.get("exit_code") == 0 and result.get("stop_reason") is None)
        need(result.get("gates") == expected_gates and result.get("metrics") == parsed["metrics"],
             "raw serial differs from result gates/metrics")
        need(result.get("integration_pass") is True and all(expected_gates.values()), "raw correctness failed")
        for name in (("run.py", "evidence.py", "configurations.py") if revision8 else ("run.py", "evidence.py")):
            self.file("benchmark/swap-standard/" + name, result.get("harness_sha256", {}).get(name))
        ticket = self.json(result.get("reservation"), result.get("reservation_sha256"))
        identity_keys = ("build", "backend", "mode", "workload")
        if revision8:
            identity_keys += ("config_id", "correctness_case", "topology_id")
        need(ticket.get("id") == run_id and ticket.get("campaign") == protocol["campaign"] and
             ticket.get("status") == "STARTED" and ticket.get("protocol_sha256") == result["protocol_sha256"] and
             ticket.get("identity") == {key: result[key] for key in identity_keys},
             "raw counted reservation mismatch")
        # This is a live accounting check, not a frozen copy of a mutable ledger.
        budget_path = self.root / ("campaigns/" + protocol["campaign"] + "/ledger/budget.json")
        budget = read(budget_path)
        pool = ticket.get("pool")
        need(pool in {"fast", "probe"}, "reservation pool")
        counted = budget.get("probe_guests" if pool == "probe" else "guests")
        tickets = list((self.root / result["reservation"]).parent.glob("*.json"))
        consumed = sum(read(path).get("pool") == pool for path in tickets)
        cap = protocol["budget"].get("probe_guest_attempts" if pool == "probe" else "guest_attempts", 0)
        need(type(counted) is int and type(cap) is int and max(1, consumed) <= counted <= cap, "original guest was not counted within its source budget")
        need(number(ticket.get("reserved_unix"), "reservation time") <= number(ticket.get("started_unix"), "launch time"), "reservation timing")
        validity = self.native("benchmark/swap-standard/validity.py")
        valid, reason = validity.classify_attempt(result, prior_walls, rules) if rules["enforce_validity"] else (True, None)
        need(valid == (attempt.get("status") == "PASS"), "retained attempt validity differs from source rules")
        if valid:
            need(result.get("run_valid") is True and not result.get("invalid_reasons"), "raw run is not valid")
            need(attempt.get("metrics") == result["metrics"], "attempt metrics differ from raw result")
            if protocol.get("preallocate_swap"):
                need(result.get("swap_image_allocation") == "preallocated", "swap allocation mismatch")
        return result, valid


def _extract(metrics, path):
    for part in path.split("."):
        metrics = metrics[part]
    number(metrics, "measurement")
    return metrics


def _report(verifier, kind, identity, provenance):
    protocol, rules = verifier.protocol(identity, provenance)
    report = verifier.json(provenance["artifact"])
    if protocol.get("protocol_revision") == 8:
        proof = verifier.json(report.get("correctness_manifest"), report.get("correctness_manifest_sha256"))
        summary = verifier.native("evolve/control/correctness_proof.py").validate(proof, protocol, verifier.root)
        need(summary.get("passed") is True
             and summary.get("candidate_commit") == report.get("correctness_candidate_commit"),
             "timing admission lacks a complete counted correctness matrix")
    need(report.get("tier") == identity["tier"], "report tier mismatch")
    need(report.get("fingerprint") == provenance.get("fingerprint") and
         isinstance(provenance.get("fingerprint"), str) and HEX64.fullmatch(provenance["fingerprint"]),
         "original evaluator fingerprint mismatch")
    need(report.get("action") == ("calibrate" if kind == "calibration" else "evaluate"), "report action mismatch")
    need(report.get("candidate_commit") == identity["source_commit"], "report source identity mismatch")
    need(number(report.get("finished"), "report finish") == provenance["observed_unix"], "original measurement time mismatch")
    tier = protocol["tiers"][identity["tier"]]
    cases = tier["cases"]
    need(identity["contrast"]["baseline_commit"] == protocol["baseline_commit"], "contrast baseline mismatch")
    runs = report.get("runs")
    need(isinstance(runs, list) and runs, "raw measurement runs required")
    seen, passed, walls = set(), {}, {case: [] for case in cases}
    for attempt in runs:
        need(isinstance(attempt, dict) and attempt.get("id") not in seen and attempt.get("case") in cases,
             "raw attempt identity/coverage mismatch")
        seen.add(attempt["id"])
        need(attempt.get("status") in {"PASS", "INVALID"}, "unfinished or failed measurement attempt")
        result, valid = verifier.run(attempt, protocol, identity, rules, walls[attempt["case"]])
        if not valid:
            continue
        case = attempt["case"]
        walls[case].append(result["wall_seconds"])
        if identity["tier"] == "probe":
            slot = (attempt.get("index"), case)
            expected_commit = identity["source_commit"]
        else:
            arm = attempt.get("arm")
            need(arm in {"a", "b"}, "measurement arm")
            slot = (attempt.get("pair"), case, arm)
            expected_commit = identity["contrast"]["baseline_commit" if arm == "a" else "candidate_commit"]
        need(result["source_commit"] == expected_commit, "measured arm source mismatch")
        need(slot not in passed, "duplicate measured arm")
        passed[slot] = result["metrics"]
    if identity["tier"] == "probe":
        need(kind == "calibration", "probe evaluations are not performance references")
        count = tier["calibration_runs"]
        expected = {(index, case) for index in range(count) for case in cases}
        need(set(passed) == expected, "incomplete probe calibration")
        samples = {case: [passed[index, case] for index in range(count)] for case in cases}
        analysis = verifier.native("benchmark/swap-standard/probe.py").calibrate(protocol, samples)
    else:
        count = tier["calibration_pairs" if kind == "calibration" else "comparison_pairs"]
        expected = {(index, case, arm) for index in range(count) for case in cases for arm in ("a", "b")}
        need(set(passed) == expected, "incomplete paired measurements")
        pairs = []
        for index in range(count):
            pair = {"a": {}, "b": {}, "order": "AB" if index % 2 == 0 else "BA"}
            for case in cases:
                for arm in ("a", "b"):
                    pair[arm].update({case + "." + metric: _extract(passed[index, case, arm], metric)
                                      for metric in protocol["cases"][case]["metrics"]})
            pairs.append(pair)
        need(report.get("pairs") == pairs, "summary pairs differ from original raw measurements")
        directions, primary = {}, []
        for case in cases:
            spec = protocol["cases"][case]
            directions.update({case + "." + metric: direction for metric, direction in spec["metrics"].items()})
            if spec.get("primary"):
                primary.append(case + "." + spec["primary"])
        analyzer = verifier.native("benchmark/swap-standard/analysis.py")
        scored = [{arm: pair[arm] for arm in ("a", "b")} for pair in pairs]
        if kind == "calibration":
            analysis = analyzer.calibrate(scored, directions, primary=primary, envelope=rules["envelope"],
                min_pairs=count, noise_ceiling=rules["noise_ceiling"], noise_floor=rules["noise_floor"],
                advisory_suffixes=rules["advisory_suffixes"])
        else:
            calibration_path = provenance.get("calibration_report")
            calibration = verifier.json(calibration_path)
            need(calibration.get("id") == report.get("calibration_id"), "calibration source mismatch")
            calibration_time = number(calibration.get("finished"), "original calibration time")
            calibration_age = number(protocol.get("calibration_max_age_seconds"), "original calibration validity", minimum=1)
            need(calibration_time <= provenance["observed_unix"] < calibration_time + calibration_age,
                 "calibration was not valid at the original measurement time")
            baseline_identity = copy.deepcopy(identity)
            baseline = identity["contrast"]["baseline_commit"]
            baseline_identity.update(source_commit=baseline, source_tree=identity["builds"][baseline]["tree"],
                                     contrast={"baseline_commit": baseline, "candidate_commit": baseline})
            calibration_provenance = dict(provenance, artifact=calibration_path,
                                          observed_unix=calibration.get("finished"))
            calibration_provenance.pop("calibration_report", None)
            _report(verifier, "calibration", baseline_identity, calibration_provenance)
            analysis = analyzer.compare(scored, directions, calibration["analysis"], identity["tier"],
                                         primary=primary, decision=rules["decision"], min_pairs=count)
    need(report.get("analysis") == analysis and report.get("status") == analysis["status"],
         "retained analysis differs from native replay")
    need(report["status"] in {"CALIBRATED", "FAST_PASS", "NEEDS_REVIEW"}, "original result is not a passing reusable observation")
    return {"checks": ["raw-results", "serial-reparse", "counted-reservations", "native-analysis-replay"],
            "coverage": {"cases": cases, "backends": sorted({protocol["cases"][c]["backend"] for c in cases}),
                         "gates": [], **({"configurations": ["c1-common"], "topologies": ["single"]}
                                        if protocol.get("protocol_revision") == 8 else {})},
            "status": report["status"]}


def _verify(root, kind, identity, provenance):
    """Check original evidence. No calls here start builds, guests or state transitions."""
    verifier = Verifier(root)
    try:
        artifact = verifier.file(provenance["artifact"], provenance["artifact_sha256"])
        verifier.tree(identity["source_commit"], identity["source_tree"])
        if kind == "upstream-source":
            verifier.file(provenance["artifact"], identity["source_sha256"])
            manifest = verifier.json(provenance["source_manifest"])
            fields = {"source_url": "source_url", "revision": "revision", "base_commit": "base_commit",
                      "commit": "source_commit", "tree": "source_tree", "source_sha256": "source_sha256"}
            need(all(manifest.get(key) == identity[value] for key, value in fields.items()), "upstream source provenance mismatch")
            result = {"checks": ["source-hash", "git-tree", "pinned-upstream-manifest"],
                      "coverage": {"gates": [], "cases": [], "backends": []}, "status": "SOURCE_VERIFIED"}
        elif kind == "build":
            need(provenance["artifact_sha256"] == identity["build_manifest_sha256"], "build manifest identity mismatch")
            verifier.build(provenance["artifact"], identity["source_commit"], identity)
            result = {"checks": ["git-tree", "build-pass", "config-hash", "image-hash"],
                      "coverage": {"gates": ["build"], "cases": [], "backends": [],
                                   **({"configurations": [identity["config_id"]]}
                                      if "config_id" in identity else {})}, "status": "BUILD_VERIFIED"}
        elif kind == "review":
            policy = provenance.get("review_policy")
            verifier.file(policy, identity["review_policy_sha256"])
            native = verifier.native("evolve/reviews.py")
            records = native.list_reviews(verifier.root, provenance["campaign"])
            saved = read(artifact)
            need(saved in records and saved.get("disposition") in {"pass", "resolve"} and
                 saved.get("candidate_commit") == identity["source_commit"] and
                 saved.get("source_tree") == identity["source_tree"], "exact-tree passing native review is missing")
            need(any(item.get("path") == policy and item.get("sha256") == identity["review_policy_sha256"]
                     for item in saved["evidence"]), "original review does not bind its review policy")
            need(saved.get("recorded_unix") == provenance["observed_unix"], "original review time mismatch")
            for item in saved["evidence"]:
                verifier.file(item["path"], item["sha256"])
            candidate = {"id": saved["candidate"], "candidate_commit": saved["candidate_commit"], "source_tree": saved["source_tree"]}
            need(not native.blockers(verifier.root, provenance["campaign"], candidate), "current review veto or integrity blocker")
            result = {"checks": ["native-review-record", "exact-tree-pass", "current-veto-check"],
                      "coverage": {"gates": ["exact-tree-review"], "cases": [], "backends": []}, "status": "REVIEW_VERIFIED"}
        elif kind == "correctness":
            protocol, rules = verifier.protocol(identity, provenance)
            proof = read(artifact)
            need(proof.get("source_commit") == identity["source_commit"], "proof source mismatch")
            summary = verifier.native("evolve/control/correctness_proof.py").validate(proof, protocol, verifier.root)
            if protocol.get("protocol_revision") == 8:
                for entry in proof["runs"]:
                    raw = verifier.json(entry["result_path"], entry["result_sha256"])
                    for path_key, hash_key in (("build_manifest", "build_manifest_sha256"),
                            ("reservation", "reservation_sha256"), ("serial_log", "serial_sha256")):
                        verifier.file(raw[path_key], raw[hash_key])
                    verifier.file(str(Path(raw["result_path"]).with_name("result.sha256")))
                    expected = identity["builds"][raw["source_commit"]]["configurations"][raw["config_id"]]
                    verifier.build(raw["build_manifest"], raw["source_commit"], expected)
                    need(raw.get("guest_provenance") == identity["guest_image"], "proof guest image provenance mismatch")
                for item in summary["builds"]:
                    expected = identity["builds"][item["source_commit"]]["configurations"][item["config_id"]]
                    verifier.file(item["build_manifest"], item["build_manifest_sha256"])
                    verifier.build(item["build_manifest"], item["source_commit"], expected)
                coverage = dict(summary["coverage"],
                    gates=sorted(key for key, passed in summary["gates"].items() if passed))
            else:
                for path_key, hash_key in (("build_manifest", "build_manifest_sha256"), ("reservation", "reservation_sha256"),
                                           ("serial_log", "serial_sha256")):
                    verifier.file(proof[path_key], proof[hash_key])
                verifier.file(str(Path(proof["result_path"]).with_name("result.sha256")))
                verifier.build(proof["build_manifest"], identity["source_commit"], identity["builds"][identity["source_commit"]])
                need(proof.get("guest_provenance") == identity["guest_image"], "proof guest image provenance mismatch")
                coverage = {"gates": sorted(key for key, passed in summary["gates"].items() if passed),
                            "cases": ["correctness"], "backends": [summary["backend"]]}
            result = {"checks": ["native-counted-raw-proof", "original-campaign-binding"],
                      "coverage": coverage, "status": "CORRECTNESS_PASS"}
        elif kind == "performance" and identity.get("evaluation_format") == "comparison-runtime-v1":
            verifier.protocol(identity, provenance)
            bridge = verifier.native("evolve/comparison_runtime.py")
            result = bridge.validate_cached_reference(verifier.root, identity, provenance)
            need(isinstance(result, dict) and result.get("passed") is True, "native comparison reference validation failed")
            for evidence in result.get("evidence", []):
                verifier.file(evidence["path"], evidence["sha256"])
            need(result.get("evidence") and result.get("checks") and isinstance(result.get("coverage"), dict),
                 "native comparison validator omitted raw evidence or checks")
            result = {key: result[key] for key in ("checks", "coverage", "status")}
        else:
            result = _report(verifier, kind, identity, provenance)
        return {"passed": True, "reasons": [], **result}, list(verifier.files.values())
    except (CacheError, ValueError, OSError, KeyError, TypeError, AttributeError, subprocess.SubprocessError) as exc:
        return {"passed": False, "status": "HISTORICAL", "checks": [], "coverage": {},
                "reasons": [str(exc)]}, list(verifier.files.values())


def _provenance(root, kind, provenance):
    need(isinstance(provenance, dict), "original provenance is required")
    original = copy.deepcopy(provenance)
    relative(original.get("artifact"))
    path = file_at(root, original["artifact"])
    need(isinstance(original.get("artifact_sha256"), str) and HEX64.fullmatch(original["artifact_sha256"]) and
         sha(path) == original["artifact_sha256"], "original artifact hash mismatch")
    number(original.get("observed_unix"), "original observation time")
    if kind in RUNTIME or kind == "review":
        need(isinstance(original.get("campaign"), str) and NAME.fullmatch(original["campaign"]), "original campaign required")
    if kind in RUNTIME:
        relative(original.get("protocol_path"))
        need(isinstance(original.get("protocol_sha256"), str) and HEX64.fullmatch(original["protocol_sha256"]), "original protocol raw hash required")
    return original


def _directory(root, kind):
    need(kind in KINDS, "unknown cache kind")
    root = Path(root).resolve()
    directory = root / "benchmark/reference-cache" / kind
    for path in (root / "benchmark", directory.parent, directory):
        need(not path.is_symlink(), "reference cache directory uses a symlink")
    return directory


def register(root, kind, identity, provenance, coverage=None, max_age_seconds=None):
    """Register original artifacts once; invalid evidence remains historical.

    Multiple observations with identical science get distinct immutable records.
    The semantic key is for lookup; record identity also includes original
    provenance. No original data, protocol or budget is rewritten.
    """
    root = Path(root).resolve()
    key = cache_key(kind, identity)
    original = _provenance(root, kind, provenance)
    verified, files = _verify(root, kind, identity, original)
    if coverage is not None:
        need(isinstance(coverage, dict) and set(coverage) <= {"gates", "cases", "backends", "configurations", "topologies"}, "coverage fields")
        for name, required in coverage.items():
            need(isinstance(required, list) and all(isinstance(item, str) for item in required), "coverage values")
            if not set(required) <= set(verified.get("coverage", {}).get(name, [])):
                verified["passed"] = False
                verified["reasons"].append("unverified requested coverage: " + name)
    expires = None
    if kind == "calibration":
        ceiling = number(identity["protocol"].get("calibration_max_age_seconds"), "source calibration max age", minimum=1)
        age = ceiling if max_age_seconds is None else number(max_age_seconds, "calibration max age", minimum=1)
        need(age <= ceiling, "cache cannot extend original calibration validity")
        expires = original["observed_unix"] + age
    elif max_age_seconds is not None:
        age = number(max_age_seconds, "max age", minimum=1)
        expires = original["observed_unix"] + age
    record = {"schema_version": 1, "kind": kind, "identity_key": key,
              "identity": copy.deepcopy(identity), "provenance": original,
              "verification": verified, "evidence": sorted(files, key=lambda item: item["path"]),
              "expires_unix": expires, "original_budget_unchanged": True}
    ident = digest(record)
    stored = {**record, "record_sha256": ident}
    directory = _directory(root, kind)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (ident + ".json")
    with (directory / ".registry.lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        if target.exists():
            need(read(target) == stored, "immutable reference identity collision")
            return stored
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=directory, prefix=".reference-", delete=False) as out:
                temporary = Path(out.name)
                out.write(json.dumps(stored, indent=2, allow_nan=False) + "\n")
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, target)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
    return stored


def _stored(path):
    need(not path.is_symlink(), "reference record uses a symlink")
    value = read(path)
    need(value.get("schema_version") == 1, "reference schema")
    payload = {key: item for key, item in value.items() if key != "record_sha256"}
    need(value.get("record_sha256") == digest(payload) == path.stem, "reference record hash mismatch")
    need(value["identity_key"] == cache_key(value["kind"], value["identity"]), "reference semantic key mismatch")
    return value


def inventory(root=ROOT, kind=None):
    """Cheap read-only inventory. Evidence usability is checked by lookup."""
    kinds = [kind] if kind is not None else sorted(KINDS)
    items = []
    for current in kinds:
        for path in sorted(_directory(root, current).glob("*.json")):
            value = _stored(path)
            items.append({"record_sha256": value["record_sha256"], "kind": current,
                          "identity_key": value["identity_key"], "identity": value["identity"],
                          "provenance": value["provenance"], "expires_unix": value["expires_unix"],
                          "verification_passed": value["verification"]["passed"],
                          "path": str(path.relative_to(Path(root).resolve()))})
    return items


def _differences(a, b, prefix=""):
    if isinstance(a, dict) and isinstance(b, dict):
        found = []
        for key in sorted(set(a) | set(b)):
            name = (prefix + "." if prefix else "") + key
            if key not in a or key not in b:
                found.append(name)
            else:
                found += _differences(a[key], b[key], name)
        return found
    return [] if a == b else [prefix]


def lookup(root, kind, identity, context=None, now=None):
    """Return reusable/new-measurement-needed/historical, with original provenance.

    Performance may reuse its original context or an explicitly requested intact
    upstream contrast within finite validity. Correctness requires explicit coverage
    and protocol reconciliation; it is never relabeled for a new campaign.
    """
    root = Path(root).resolve()
    key, semantic = cache_key(kind, identity), semantic_identity(kind, identity)
    now = time.time() if now is None else number(now, "lookup time")
    context = context or {}
    matches, mismatches = [], []
    for item in inventory(root, kind):
        record = _stored(root / item["path"])
        if record["identity_key"] != key:
            mismatches.append({"record_sha256": record["record_sha256"],
                               "fields": _differences(semantic, semantic_identity(kind, record["identity"]))})
            continue
        reasons = []
        original = record["provenance"]
        status = "reusable"
        if record["verification"].get("passed") is not True:
            status = "historical"
            reasons += ["original verification failed"] + record["verification"].get("reasons", [])
        if now < original["observed_unix"]:
            status = "historical"
            reasons.append("original observation time is in the future")
        if record["expires_unix"] is not None and now >= record["expires_unix"]:
            status = "new-measurement-needed"
            reasons.append("original validity window expired")
        for evidence in record["evidence"]:
            try:
                path = file_at(root, evidence["path"])
                need(sha(path) == evidence["sha256"], "raw evidence changed: " + evidence["path"])
            except CacheError as exc:
                status = "new-measurement-needed"
                reasons.append(str(exc))
        if status == "reusable":
            fresh, _ = _verify(root, kind, record["identity"], original)
            if not fresh["passed"]:
                status = "new-measurement-needed"
                reasons += fresh["reasons"]
        cross_campaign = kind == "performance" and any(context.get(key) != original.get(key)
                for key in ("campaign", "protocol_sha256", "fingerprint"))
        intact_reference = (cross_campaign and context.get("reuse_intact_contrast") is True and
                            context.get("purpose") == "upstream-reference" and
                            identity.get("reference_role") == "upstream" and
                            record["expires_unix"] is not None)
        if cross_campaign and not intact_reference:
            if status == "reusable":
                status = "historical"
            reasons.append("cross-campaign performance is reference-only without an intact upstream contrast and finite validity")
        if intact_reference and status == "reusable":
            reasons.append("intact upstream contrast reused with original paired observations and timestamp; no new independent measurement")
        if context.get("review_blocked") is True:
            status = "historical"
            reasons.append("current review veto supersedes cached evidence")
        required = context.get("required_coverage", {})
        need(isinstance(required, dict), "required coverage must be an object")
        for field, values in required.items():
            need(field in {"gates", "cases", "backends", "configurations", "topologies"} and isinstance(values, list), "required coverage")
            if not set(values) <= set(record["verification"].get("coverage", {}).get(field, [])):
                status = "new-measurement-needed"
                reasons.append("missing required coverage: " + field)
        matches.append({"status": status, "record_sha256": record["record_sha256"],
                        "provenance": original, "coverage": record["verification"].get("coverage", {}),
                        "reasons": list(dict.fromkeys(reasons)), "reference_only": status != "reusable",
                        "new_measurement_required": status == "new-measurement-needed",
                        "reconciliation_required": kind == "correctness",
                        "cross_campaign_reused": bool(intact_reference and status == "reusable"),
                        "independent_measurement": False, "may_pair_with_new_arm": False,
                        "original_budget_unchanged": True})
    if not matches:
        return {"status": "new-measurement-needed", "identity_key": key, "record_sha256": None,
                "reasons": ["no exact reusable scientific identity"], "mismatches": mismatches,
                "reference_only": True, "new_measurement_required": True,
                "original_budget_unchanged": True}
    ranking = {"reusable": 0, "historical": 1, "new-measurement-needed": 2}
    matches.sort(key=lambda value: (ranking[value["status"]], -value["provenance"]["observed_unix"]))
    return {**matches[0], "identity_key": key, "alternatives": matches[1:], "mismatches": mismatches}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    commands = parser.add_subparsers(dest="action", required=True)
    p = commands.add_parser("inventory")
    p.add_argument("--kind", choices=sorted(KINDS))
    for name in ("lookup", "register"):
        p = commands.add_parser(name)
        p.add_argument("kind", choices=sorted(KINDS))
        p.add_argument("identity", type=Path)
        if name == "register":
            p.add_argument("provenance", type=Path)
            p.add_argument("--max-age-seconds", type=float)
        else:
            p.add_argument("--context", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == "inventory":
            result = inventory(args.root, args.kind)
        elif args.action == "lookup":
            result = lookup(args.root, args.kind, read(args.identity),
                            read(args.context) if args.context else None)
        else:
            result = register(args.root, args.kind, read(args.identity), read(args.provenance),
                              max_age_seconds=args.max_age_seconds)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (CacheError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
