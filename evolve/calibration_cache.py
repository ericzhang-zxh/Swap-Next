# SPDX-License-Identifier: GPL-2.0-only
"""Reuse complete verified A/A observations without extending their validity."""
import copy
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import time

import reference_cache as cache
import reviews


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def identity(root, protocol, tier):
    root = Path(root).resolve()
    commit = protocol["baseline_commit"]
    tree = subprocess.check_output(["git", "-C", str(root / "linux"), "rev-parse", commit + "^{tree}"], text=True).strip()
    manifest = read(root / "benchmark/kernel/builds" / protocol["baseline_build"] / "result.json")
    build = {key: manifest[key] for key in ("image_sha256", "config_sha256", "input_config_sha256")}
    build["tree"] = tree
    bench = root / "benchmark/swap-standard"
    files = list(bench.glob("*.py")) + list(bench.glob("*.sh")) + list(bench.glob("*.c"))
    files += [bench / name for name in ("guest-init", "tools.json")]
    files += [root / relative for relative in (
        "evolve/standard_workflow.py", "evolve/calibration_cache.py", "evolve/reference_cache.py",
        "evolve/control/controller.py", "evolve/control/campaign_store.py",
        "evolve/control/guest_budget.py", "evolve/control/correctness_proof.py",
        "benchmark/kernel/build.py", "benchmark/kernel/lifetime.py", "benchmark/kernel/build_namespace.sh",
        "benchmark/config/swap-standard.config")]
    environment = {"kernel": platform.release(), "architecture": platform.machine(),
                   "qemu": subprocess.check_output(["qemu-system-x86_64", "--version"], text=True, timeout=15).strip()}
    return {"source_commit": commit, "source_tree": tree, "protocol": protocol,
            "machine": read(root / "campaigns" / protocol["campaign"] / "campaign.json")["machine"],
            "accelerator": protocol["accelerator"]["require"], "guest": protocol["guest"],
            "builds": {commit: build}, "guest_image": read(bench / "image.json"),
            "harness": {str(path.relative_to(root)): sha(path) for path in sorted(set(files))},
            "host_environment": environment, "tier": tier,
            "contrast": {"baseline_commit": commit, "candidate_commit": commit}}


def _context(root, protocol, key):
    blocked = reviews.blockers(root, protocol["campaign"],
        {"id": None, "candidate_commit": key["source_commit"], "source_tree": key["source_tree"]})
    return {"review_blocked": bool(blocked),
            "required_coverage": {"cases": protocol["tiers"][key["tier"]]["cases"]}}


def register(root, protocol, row):
    if (row.get("action") != "calibrate" or row.get("tier") not in ("probe", "fast") or
            row.get("status") != "CALIBRATED" or row.get("measurement_reused") or row.get("comparison")):
        return {"status": "not-applicable"}
    root = Path(root).resolve()
    source = root / "campaigns" / protocol["campaign"] / "runs/evaluations" / row["id"] / "report.json"
    key = identity(root, protocol, row["tier"])
    provenance = {"artifact": str(source.relative_to(root)), "artifact_sha256": sha(source),
                  "observed_unix": row["finished"], "campaign": protocol["campaign"],
                  "protocol_path": "campaigns/" + protocol["campaign"] + "/protocol.json",
                  "protocol_sha256": sha(root / "campaigns" / protocol["campaign"] / "protocol.json"),
                  "fingerprint": row["fingerprint"]}
    result = cache.register(root, "calibration", key, provenance,
                            max_age_seconds=protocol["calibration_max_age_seconds"])
    return {"status": "registered" if result["verification"]["passed"] else "historical",
            "record_sha256": result["record_sha256"], "verification": result["verification"]}


def reuse(root, protocol, row, fingerprint):
    """Mutate only the new alias row; original report and budgets stay untouched."""
    root = Path(root).resolve()
    if not (root / "benchmark/reference-cache/calibration").is_dir():
        return False
    key = identity(root, protocol, row["tier"])
    result = cache.lookup(root, "calibration", key, _context(root, protocol, key))
    if result["status"] != "reusable":
        return False
    provenance = result["provenance"]
    original = read(root / provenance["artifact"])
    for field in ("analysis", "runs", "pairs", "probe_signals", "candidate_commit", "candidate_tree", "started", "finished"):
        if field in original:
            row[field] = copy.deepcopy(original[field])
    row.update(status="CALIBRATED", fingerprint=fingerprint,
               protocol_sha256=sha(root / "campaigns" / protocol["campaign"] / "protocol.json"),
               candidate_commit=key["source_commit"], candidate_tree=key["source_tree"],
               measurement_reused=True, independent_measurement=False, reused_at=time.time(),
               source_evaluation_id=original["id"], source_campaign=provenance["campaign"],
               source_binding={"record_sha256": result["record_sha256"], "identity_key": result["identity_key"],
                               **provenance}, may_pair_with_new_arm=False)
    return True


def validate_alias(root, protocol, row, *, now=None):
    """Recheck current science, original raw evidence, expiry and current vetoes."""
    root = Path(root).resolve()
    if (row.get("measurement_reused") is not True or row.get("comparison") or
            row.get("action") != "calibrate" or row.get("status") != "CALIBRATED" or
            row.get("tier") not in ("probe", "fast")):
        raise ValueError("expected native calibration cache alias")
    key = identity(root, protocol, row["tier"])
    result = cache.lookup(root, "calibration", key, _context(root, protocol, key), now=now)
    choices = [result, *result.get("alternatives", [])]
    binding = row.get("source_binding", {})
    selected = next((item for item in choices if item.get("record_sha256") == binding.get("record_sha256")
                     and item.get("status") == "reusable"), None)
    if selected is None or binding.get("identity_key") != result["identity_key"]:
        raise ValueError("cached calibration no longer matches current evidence")
    original = read(root / selected["provenance"]["artifact"])
    if (row.get("source_evaluation_id") != original["id"] or
            row.get("source_campaign") != selected["provenance"]["campaign"]):
        raise ValueError("cached calibration alias source identity changed")
    for field in ("analysis", "runs", "pairs", "probe_signals", "candidate_commit", "started", "finished"):
        if row.get(field) != original.get(field):
            raise ValueError("cached calibration alias differs from original " + field)
    if row.get("candidate_tree") != key["source_tree"] or row.get("independent_measurement") is not False:
        raise ValueError("cached calibration target tree or independence changed")
    if any(binding.get(key) != value for key, value in selected["provenance"].items()):
        raise ValueError("cached calibration original provenance changed")
    if row.get("protocol_sha256") != sha(root / "campaigns" / protocol["campaign"] / "protocol.json"):
        raise ValueError("cached calibration target protocol changed")
    return True
