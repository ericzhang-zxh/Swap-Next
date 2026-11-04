#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Replay retained guest evidence; starts no build or guest."""
from collections import defaultdict
from pathlib import Path
import hashlib
import json
import statistics
import sys

ROOT = Path(__file__).resolve().parents[3]
DIRECTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmark/swap-standard"))
import evidence
import probe
import validity

def read(path):
    return json.loads(path.read_text())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(name, value):
    (DIRECTORY / "report" / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")

protocol = read(DIRECTORY / "protocol.json")
calibration = read(DIRECTORY / "ledger/calibration-probe.json")
baseline_proof = read(DIRECTORY / "report/baseline-correctness-summary.json")
rules = validity.protocol_rules(protocol)
rows = [dict(baseline_proof, id=baseline_proof["run_id"], case="baseline-correctness")]
rows += calibration["runs"]
samples = defaultdict(list)
prior = defaultdict(list)
summaries = []
for row in rows:
    path = ROOT / row["result"]
    raw = read(path)
    assert sha(path) == row["result_sha256"] == (path.parent / "result.sha256").read_text().strip()
    assert raw["campaign"] == DIRECTORY.name
    assert raw["source_commit"] == protocol["baseline_commit"]
    assert raw["protocol_sha256"] == sha(DIRECTORY / "protocol.json")
    assert raw["accelerator"] == "tcg" and raw["guest_vcpus"] == 4 and raw["guest_mem_mib"] == 4096
    assert raw["swap_bytes"] == 16 * 1024**3
    assert raw["qemu_accel"] == protocol["accelerator"]["qemu"]
    reservation = ROOT / raw["reservation"]
    assert sha(reservation) == raw["reservation_sha256"]
    reserved = read(reservation)
    assert reserved["id"] == raw["run_id"] and reserved["status"] == "STARTED"
    assert reserved["campaign"] == DIRECTORY.name
    assert reserved["protocol_sha256"] == raw["protocol_sha256"]
    assert sha(ROOT / raw["build_manifest"]) == raw["build_manifest_sha256"]
    build = read(ROOT / raw["build_manifest"])
    assert build["commit"] == raw["source_commit"]
    assert build["image_sha256"] == raw["image_sha256"]
    assert build["config_sha256"] == raw["config_sha256"]
    assert build["passed"] is True
    assert raw["input_config_sha256"] == protocol["input_config_sha256"]
    serial = ROOT / raw["serial_log"]
    assert sha(serial) == raw["serial_sha256"]
    for name, expected in raw["harness_sha256"].items():
        assert sha(path.parent / "harness" / name) == expected
        assert sha(ROOT / "benchmark/swap-standard" / name) == expected
    parsed = evidence.parse(serial.read_text(), raw["image_sha256"], raw["backend"], raw["mode"], raw["workload"])
    assert parsed["metrics"] == raw["metrics"]
    assert all(value is True and raw["gates"][key] is True for key, value in parsed["gates"].items())
    assert raw["exit_code"] == 0 and raw["stop_reason"] is None and raw["gates"]["qemu_exit"] is True
    assert raw["clocksource_invalid"] == validity.clocksource_invalid(serial.read_text()) is False
    valid, reason = validity.classify_attempt(raw, prior[row["case"]], rules)
    assert valid is raw["run_valid"] is raw["integration_pass"] is True and reason is None
    prior[row["case"]].append(raw["wall_seconds"])
    if row["case"] != "baseline-correctness":
        assert row["metrics"] == raw["metrics"]
        samples[row["case"]].append(raw["metrics"])
    summaries.append({
        "run_id": raw["run_id"], "case": row["case"], "source_commit": raw["source_commit"],
        "result_sha256": sha(path), "serial_sha256": sha(serial),
        "reservation_sha256": sha(reservation), "build_manifest_sha256": raw["build_manifest_sha256"],
        "image_sha256": raw["image_sha256"], "config_sha256": raw["config_sha256"],
        "input_config_sha256": raw["input_config_sha256"], "protocol_sha256": raw["protocol_sha256"],
        "accelerator": raw["accelerator"], "guest_vcpus": raw["guest_vcpus"],
        "guest_mem_mib": raw["guest_mem_mib"], "workload": raw["workload"],
        "backend": raw["backend"], "mode": raw["mode"], "run_valid": valid,
        "integration_pass": raw["integration_pass"], "gates": raw["gates"],
        "wall_seconds": raw["wall_seconds"], "metrics": parsed["metrics"],
    })
replayed = probe.calibrate(protocol, samples)
assert replayed == calibration["analysis"]
metadata = [r["metadata_delta_bytes_per_capacity_slot"] for r in samples["metadata-brd"]]
spread = (max(metadata) - min(metadata)) / statistics.median(metadata)
budget = read(DIRECTORY / "ledger/budget.json")
assert budget["guests"] == 1 and budget["probe_guests"] == 9 and budget["builds"] == 0
assert len(list((DIRECTORY / "ledger/guest-reservations").glob("*.json"))) == len(rows)
assert len(list((DIRECTORY / "runs/guests").glob("*/result.json"))) == len(rows)
summary = {
    "schema_version": 1, "campaign": DIRECTORY.name, "verdict": "inconclusive",
    "reason": replayed["reasons"], "protocol_revision": protocol["protocol_revision"],
    "baseline_commit": protocol["baseline_commit"],
    "candidate_commit": "3fe7af01da59a8ade95823a13c25a8c796c6321f",
    "candidate_tree": "0c83218561a357c129c5d93ac45a0530e0ad1df6",
    "candidate_built": False, "candidate_booted": False, "candidate_performance_measured": False,
    "candidate_runtime_correctness": "not_run",
    "metadata_samples_bytes_per_capacity_slot": metadata,
    "metadata_range_over_median": spread,
    "metadata_spread_gate_fraction": protocol["probe_band"]["metadata_spread_fraction"],
    "calibration_status": replayed["status"], "budget": budget,
    "fresh_guests": len(rows), "all_runs_valid": True,
    "baseline_correctness": baseline_proof["status"],
    "raw_evidence_replayed": True, "performance_accepted": False, "auto_promote": False,
    "runs": summaries,
}
write("public-runtime-summary.json", summary)
write("outcome-verification.json", {
    "campaign": DIRECTORY.name, "all_passed": True,
    "checks": ["all result sidecar and ledger hashes", "all serial hashes and parser replay",
               "all counted reservation bindings", "source/config/build/protocol identities",
               "retained and current harness hashes", "guest shape and accelerator",
               "run validity replay", "probe analysis exact replay", "budget and run reconciliation"],
    "verified_guest_results": len(rows),
    "calibration_analysis_sha256": hashlib.sha256(json.dumps(replayed, sort_keys=True).encode()).hexdigest(),
    "public_runtime_summary_sha256": sha(DIRECTORY / "report/public-runtime-summary.json"),
    "interpretation": "Evidence integrity passed. The metadata calibration stability gate failed."
})
print(json.dumps({"verified_guests": len(rows), "calibration": replayed["status"], "metadata_spread": spread, "new_builds": budget["builds"]}))
