#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Strict, offline measurement analysis. Integrity is not provenance or promotion."""
import hashlib
import json
import math
from pathlib import Path
import random
import re
import statistics

HEX = re.compile(r"^[0-9a-f]{64}$")
SHA = re.compile(r"^[0-9a-f]{40}$")
NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,95}$")


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def load_json(path):
    path = Path(path)
    require(path.stat().st_size <= 16 * 1024 * 1024, "JSON file too large")
    def pairs(items):
        obj = {}
        for key, value in items:
            require(key not in obj, "duplicate JSON key: " + key)
            obj[key] = value
        return obj
    def constant(value):
        raise Invalid("non-finite JSON constant: " + value)
    with path.open() as stream:
        return json.load(stream, object_pairs_hook=pairs, parse_constant=constant)


def number(value, name, minimum=0, positive=False, integer=False):
    require(type(value) in (int, float), name + " must be numeric, not boolean")
    require(math.isfinite(value), name + " must be finite")
    require(value >= minimum and (not positive or value > 0),
            name + " out of range")
    if integer:
        require(type(value) is int, name + " must be integer")
    return value


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def artifact(root, descriptor):
    require(isinstance(descriptor, dict), "artifact descriptor must be an object")
    name = descriptor.get("path")
    require(isinstance(name, str) and name, "artifact path missing")
    relative = Path(name)
    require(not relative.is_absolute() and ".." not in relative.parts,
            "artifact path escapes evidence root")
    root = Path(root).resolve()
    p = root
    for part in relative.parts:
        p = p / part
        require(not p.is_symlink(), "symlink artifact forbidden")
    require(p.resolve().is_relative_to(root), "artifact outside evidence root")
    require(p.is_file() and p.stat().st_size > 0, "empty or missing artifact")
    expected = descriptor.get("sha256")
    require(isinstance(expected, str) and HEX.fullmatch(expected),
            "invalid artifact sha256")
    require(digest(p) == expected, "artifact hash mismatch: " + name)
    return p


def percentile(values, fraction):
    require(bool(values), "empty observations")
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1,
                              math.ceil(fraction * len(ordered)) - 1))]


def metrics(raw, policy):
    completed = number(raw.get("completed_operations"), "completed_operations",
                       positive=True, integer=True)
    attempted = number(raw.get("attempted_operations"), "attempted_operations",
                       positive=True, integer=True)
    require(attempted == completed, "incomplete work cannot be scored")
    require(completed >= policy["measurement"]["min_operations"],
            "too few operations")
    elapsed = number(raw.get("elapsed_s"), "elapsed_s", positive=True)
    require(elapsed <= policy["budget"]["run_wall_seconds"],
            "measurement exceeds run budget")
    cpu = number(raw.get("cpu_core_seconds"), "cpu_core_seconds", positive=True)
    require(cpu <= elapsed * policy["budget"]["guest_vcpus"] * 1.05,
            "CPU time exceeds declared guest capacity")
    latency = raw.get("latency_us")
    require(isinstance(latency, list) and len(latency) == completed,
            "latency must cover every completed operation")
    for v in latency:
        number(v, "latency_us", positive=True)
    for key in ("data_mismatches", "timeouts", "kernel_warnings"):
        require(type(raw.get(key)) is int and raw[key] == 0,
                "hard correctness failure or missing counter: " + key)
    for key in ("swapout_pages", "swapin_pages"):
        count = number(raw.get(key), key, integer=True)
        require(count >= policy["measurement"]["min_" + key],
                "no required swap activity: " + key)
    io_read = number(raw.get("backend_read_bytes"), "backend_read_bytes", integer=True)
    io_write = number(raw.get("backend_write_bytes"), "backend_write_bytes", integer=True)
    samples = raw.get("metadata_samples")
    require(isinstance(samples, list) and samples, "metadata samples missing")
    ratios = []
    for sample in samples:
        require(isinstance(sample, dict), "invalid metadata sample")
        used = number(sample.get("occupied_slots"), "occupied_slots",
                      positive=True, integer=True)
        size = number(sample.get("attributable_bytes"), "attributable_bytes",
                      integer=True)
        ratios.append(size / used)
    result = {
        "throughput_ops_s": completed / elapsed,
        "latency_p99_us": percentile(latency, .99),
        "cpu_ns_per_op": cpu * 1e9 / completed,
        "io_bytes_per_op": (io_read + io_write) / completed,
        "metadata_bytes_per_slot_peak": max(ratios),
    }
    require(all(math.isfinite(v) for v in result.values()), "non-finite derived metric")
    return result


def improvement(before, after, direction):
    if before == 0:
        require(after == 0, "zero baseline metric regressed; ratio undefined")
        return 0.0
    effect = (after - before) / before if direction == "higher" else (before - after) / before
    require(math.isfinite(effect), "non-finite relative effect")
    return effect


def interval(effects, resamples, tail, seed):
    rng = random.Random(seed)
    means = [statistics.fmean(rng.choices(effects, k=len(effects)))
             for _ in range(resamples)]
    return [percentile(means, tail), percentile(means, 1 - tail)]


def analyze(manifest_path, policy, protocol_sha256, expected_base=None,
            expected_candidate=None):
    manifest_path = Path(manifest_path)
    root = manifest_path.parent
    manifest = load_json(manifest_path)
    require(isinstance(manifest, dict), "manifest must be an object")
    require(manifest.get("schema_version") == 1, "unsupported result schema")
    require(manifest.get("protocol_sha256") == protocol_sha256,
            "protocol/evaluator hash mismatch")
    base, candidate = manifest.get("baseline_commit"), manifest.get("candidate_commit")
    require(isinstance(base, str) and SHA.fullmatch(base), "invalid baseline commit")
    require(isinstance(candidate, str) and SHA.fullmatch(candidate), "invalid candidate commit")
    require(base != candidate, "performance analysis needs distinct candidate commit")
    if expected_base:
        require(base == expected_base, "wrong baseline")
    if expected_candidate:
        require(candidate == expected_candidate, "wrong candidate")
    experiment = manifest.get("experiment_id")
    require(isinstance(experiment, str) and NAME.fullmatch(experiment),
            "experiment_id missing or invalid")
    environment = manifest.get("environment")
    required_env = {"compiler_sha256", "config_sha256", "rootfs_sha256",
                    "suite_sha256", "machine_profile_sha256"}
    require(isinstance(environment, dict) and set(environment) == required_env,
            "environment hashes incomplete or unknown")
    require(all(isinstance(v, str) and HEX.fullmatch(v)
                for v in environment.values()), "invalid environment hash")
    require(manifest.get("execution_kind") == "isolated_guest",
            "host execution is not eligible")
    gates = manifest.get("gates")
    require(isinstance(gates, dict) and set(gates) == set(policy["required_gates"]),
            "required gate set mismatch")
    for name, gate in gates.items():
        require(isinstance(gate, dict) and gate.get("status") == "pass",
                "gate not passed: " + name)
        require(gate.get("candidate_commit") == candidate, "stale gate: " + name)
        artifact(root, gate.get("evidence"))
    descriptors = manifest.get("runs")
    require(isinstance(descriptors, list) and descriptors, "raw runs missing")
    require(len(descriptors) <= 2000, "too many runs")
    grouped, run_ids, boot_ids, paths = {}, set(), set(), set()
    time_ranges = []
    for desc in descriptors:
        path = artifact(root, desc)
        require(path not in paths, "reused raw evidence")
        paths.add(path)
        raw = load_json(path)
        require(isinstance(raw, dict), "raw run must be an object")
        require(raw.get("schema_version") == 1, "bad raw schema")
        require(raw.get("status") == "completed", "run did not complete")
        require(raw.get("experiment_id") == experiment, "wrong run experiment")
        run_id = raw.get("run_id")
        require(isinstance(run_id, str) and NAME.fullmatch(run_id) and
                run_id not in run_ids, "duplicate or invalid run_id")
        run_ids.add(run_id)
        boot_id = raw.get("boot_id")
        require(isinstance(boot_id, str) and NAME.fullmatch(boot_id) and
                boot_id not in boot_ids, "run must use an independent boot_id")
        boot_ids.add(boot_id)
        variant = raw.get("variant")
        require(variant in ("baseline", "candidate"), "invalid variant")
        expected = base if variant == "baseline" else candidate
        require(raw.get("kernel_commit") == expected and
                raw.get("booted_commit") == expected, "boot/source identity mismatch")
        require(raw.get("environment") == environment, "mismatched environment")
        require(raw.get("partition") in policy["measurement"]["required_partitions"],
                "unknown partition")
        require(raw.get("workload") in policy["measurement"]["required_workloads"],
                "unknown workload")
        pair_id = raw.get("pair_id")
        require(isinstance(pair_id, str) and NAME.fullmatch(pair_id), "invalid pair_id")
        require(raw.get("order") in ("AB", "BA"), "counterbalanced order missing")
        number(raw.get("seed"), "seed", integer=True)
        # Timestamps come from the trusted collector; validation alone cannot
        # establish authenticity or prove which kernel actually booted.
        started = number(raw.get("started_unix"), "started_unix", positive=True)
        finished = number(raw.get("finished_unix"), "finished_unix", positive=True)
        require(finished > started, "invalid time interval")
        time_ranges.append((started, finished))
        computed = metrics(raw, policy)
        require(finished - started <= policy["budget"]["run_wall_seconds"],
                "run exceeded wall-time budget")
        require(finished - started >= raw["elapsed_s"],
                "measurement longer than run interval")
        key = (raw["partition"], raw["workload"], pair_id)
        pair = grouped.setdefault(key, {})
        require(variant not in pair, "duplicate member of pair")
        pair[variant] = (raw, computed)
    planned = manifest.get("planned_run_ids")
    require(isinstance(planned, list) and all(isinstance(x, str) for x in planned),
            "planned run roster missing")
    require(len(planned) == len(set(planned)) and set(planned) == run_ids,
            "run roster incomplete or unexpected run")
    ordered_times = sorted(time_ranges)
    require(all(a[1] <= b[0] for a, b in zip(ordered_times, ordered_times[1:])),
            "overlapping measurements violate single-run policy")
    expected_groups = {(p, w) for p in policy["measurement"]["required_partitions"]
                       for w in policy["measurement"]["required_workloads"]}
    groups = {}
    for (partition, workload, pair_id), pair in grouped.items():
        require(set(pair) == {"baseline", "candidate"}, "incomplete pair")
        a, b = pair["baseline"][0], pair["candidate"][0]
        for key in ("seed", "order", "attempted_operations"):
            require(a[key] == b[key], "paired run mismatch: " + key)
        first, second = (a, b) if a["order"] == "AB" else (b, a)
        require(first["finished_unix"] <= second["started_unix"],
                "declared AB/BA order disagrees with timestamps")
        groups.setdefault((partition, workload), []).append(pair)
    require(set(groups) == expected_groups, "missing workload/partition coverage")
    comparisons = len(groups) * len(policy["metrics"])
    tail = (1 - policy["measurement"]["confidence"]) / (2 * comparisons)
    require(policy["measurement"]["bootstrap_resamples"] * tail >=
            policy["measurement"]["min_bootstrap_tail_samples"],
            "insufficient bootstrap tail resolution")
    result, regressions = {}, []
    seeds_by_workload = {}
    for (part, work), pairs in groups.items():
        seeds = {p["baseline"][0]["seed"] for p in pairs}
        require(len(seeds) == len(pairs), "reused seed within workload partition")
        seen = seeds_by_workload.setdefault(work, set())
        require(not seen.intersection(seeds), "confirmation reuses discovery seeds")
        seen.update(seeds)
    for group_key, pairs in sorted(groups.items()):
        require(len(pairs) >= policy["measurement"]["min_pairs"], "too few pairs")
        orders = [p["baseline"][0]["order"] for p in pairs]
        require(abs(orders.count("AB") - orders.count("BA")) <= 1,
                "unbalanced AB/BA")
        rows = {}
        for metric, spec in policy["metrics"].items():
            effects = [improvement(p["baseline"][1][metric], p["candidate"][1][metric],
                                   spec["direction"]) for p in pairs]
            seed = int(hashlib.sha256(("/".join(group_key) + metric).encode()).hexdigest()[:16], 16)
            ci = interval(effects, policy["measurement"]["bootstrap_resamples"], tail, seed)
            rows[metric] = {"mean_paired_improvement": statistics.fmean(effects),
                            "adjusted_ci": ci, "pairs": len(pairs)}
            if policy["thresholds_calibrated"]:
                limit = spec.get("min_gain") if spec["role"] == "primary" else spec.get("max_regression")
                number(limit, "calibrated threshold: " + metric)
                threshold = limit if spec["role"] == "primary" else -limit
                failed = ci[0] <= threshold if spec["role"] == "primary" else ci[0] < threshold
                if failed:
                    regressions.append("/".join(group_key) + ":" + metric)
        result["/".join(group_key)] = rows
    verdict = ("NEEDS_CALIBRATION" if not policy["thresholds_calibrated"] else
               "REJECT_OR_NO_GAIN" if regressions else "REVIEW_REQUIRED")
    return {"verdict": verdict, "experiment_id": experiment, "metrics": result,
            "failed_constraints": regressions, "auto_promote": False,
            "provenance_verified": False, "holdout_verified": False,
            "note": "Hashes check integrity only. Independent collection, holdout and owner review are mandatory."}
