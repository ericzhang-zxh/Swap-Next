# SPDX-License-Identifier: GPL-2.0-only
"""Validate counted raw correctness evidence for new standard-suite protocols.

Hashes detect accidental drift in trusted same-user artifacts; they are not
security signatures. Callers retain exact candidate-commit and exemption checks.
Plain-mode correctness is an explicit missing workload capability.
"""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re


NAME = re.compile(r"[a-z][a-z0-9-]{0,47}")
RUN = re.compile(r"[a-zA-Z0-9_-]{1,96}")
BUILD = re.compile(r"[a-z0-9-]{1,48}")


class CorrectnessFailure(ValueError):
    """A bound, counted run failed correctness; evidence may invalidate history."""
    def __init__(self, message, evidence):
        super().__init__(message)
        self.evidence = evidence


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_at(root, reference, expected=None):
    if not isinstance(reference, str) or not reference:
        raise ValueError("missing repository-relative evidence reference")
    relative = Path(reference)
    if relative.is_absolute() or ".." in relative.parts or relative.as_posix() != reference:
        raise ValueError("evidence reference escapes its canonical path")
    if expected is not None and reference != expected:
        raise ValueError("evidence reference does not match canonical path: " + reference)
    path = root / relative
    if not path.resolve().is_relative_to(root):
        raise ValueError("evidence reference escapes repository")
    parent = root
    for part in relative.parts:
        parent = parent / part
        if parent.is_symlink():
            raise ValueError("evidence reference uses a symlink")
    if not path.is_file():
        raise ValueError("missing raw evidence: " + reference)
    return path


def hashed(root, reference, digest, expected=None):
    path = file_at(root, reference, expected)
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest) or sha(path) != digest:
        raise ValueError("evidence hash mismatch: " + reference)
    return path


def finite(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def _validate(proof, protocol, root):
    if not isinstance(proof, dict) or not isinstance(protocol, dict):
        raise ValueError("proof and protocol must be objects")
    cases = protocol.get("cases", {})
    if not isinstance(cases, dict) or not all(isinstance(case, dict) for case in cases.values()):
        raise ValueError("malformed protocol cases")
    routes = {(case.get("mode", "plain"), case.get("backend")) for case in cases.values() if case.get("workload") == "swapin"}
    if routes and all(mode == "plain" for mode, _ in routes):
        raise ValueError("plain-mode correctness workload capability is missing")
    if not routes:
        raise ValueError("protocol has no swap-in correctness route")
    if type(proof.get("proof_schema_version")) is not int or proof["proof_schema_version"] != 1:
        raise ValueError("missing raw runner proof schema")
    campaign, run_id, build = proof.get("campaign"), proof.get("run_id"), proof.get("build")
    if not isinstance(campaign, str) or not NAME.fullmatch(campaign) or campaign != protocol.get("campaign"):
        raise ValueError("proof campaign mismatch")
    if not isinstance(run_id, str) or not RUN.fullmatch(run_id) or not isinstance(build, str) or not BUILD.fullmatch(build):
        raise ValueError("invalid proof run/build identity")
    run = f"campaigns/{campaign}/runs/guests/{run_id}"
    raw_path = file_at(root, proof.get("result_path"), run + "/result.json")
    sidecar = file_at(root, run + "/result.sha256")
    result_hash = sha(raw_path)
    if sidecar.read_text().strip() != result_hash:
        raise ValueError("raw result byte hash mismatch")
    if json.loads(raw_path.read_bytes()) != proof:
        raise ValueError("proof differs from raw result")
    protocol_path = file_at(root, f"campaigns/{campaign}/protocol.json")
    if json.loads(protocol_path.read_bytes()) != protocol:
        raise ValueError("protocol differs from frozen campaign protocol")
    protocol_hash = sha(protocol_path)
    if proof.get("protocol_sha256") != protocol_hash or proof.get("protocol_revision") != protocol.get("protocol_revision", 1):
        raise ValueError("proof protocol hash/revision mismatch")
    mode, backend = proof.get("mode"), proof.get("backend")
    if mode == "plain":
        raise ValueError("plain-mode correctness workload capability is missing")
    if (mode, backend) not in routes or mode != "xswap" or backend not in ("disk", "zswap") or proof.get("workload") != "correctness":
        raise ValueError("proof mode/backend/workload does not match protocol correctness route")
    if (type(proof.get("integration_pass")) is not bool or type(proof.get("run_valid")) is not bool or
            type(proof.get("exit_code")) is not int or not isinstance(proof.get("invalid_reasons"), list) or
            not all(isinstance(reason, str) for reason in proof["invalid_reasons"]) or
            proof.get("stop_reason") is not None and not isinstance(proof["stop_reason"], str)):
        raise ValueError("malformed runner outcome")
    gates, required = proof.get("gates"), protocol.get("required_correctness_gates")
    if (not isinstance(required, list) or not required or not all(isinstance(k, str) and k for k in required) or
            not isinstance(gates, dict) or not gates or not all(type(v) is bool for v in gates.values())):
        raise ValueError("malformed correctness gate contract")
    expected_accel = protocol.get("accelerator", {}).get("require")
    if expected_accel and proof.get("accelerator") != expected_accel:
        raise ValueError("correctness accelerator mismatch")
    guest = protocol.get("guest", {})
    if guest and (proof.get("guest_vcpus") != guest.get("vcpus") or proof.get("guest_mem_mib") != guest.get("mem_mib")):
        raise ValueError("correctness guest size mismatch")
    ticket_ref = f"campaigns/{campaign}/ledger/guest-reservations/{run_id}.json"
    ticket_path = hashed(root, proof.get("reservation"), proof.get("reservation_sha256"), ticket_ref)
    ticket = json.loads(ticket_path.read_bytes())
    identity = {key: proof[key] for key in ("build", "backend", "mode", "workload")}
    if (ticket.get("campaign") != campaign or ticket.get("id") != run_id or ticket.get("status") != "STARTED" or
            ticket.get("identity") != identity or ticket.get("protocol_sha256") != protocol_hash or
            ticket.get("pool") not in ("fast", "probe") or not finite(ticket.get("reserved_unix")) or
            not finite(ticket.get("started_unix")) or ticket["reserved_unix"] > ticket["started_unix"]):
        raise ValueError("consumed reservation identity/status/protocol mismatch")
    budget = json.loads(file_at(root, f"campaigns/{campaign}/ledger/budget.json").read_bytes())
    counted = budget.get("probe_guests" if ticket["pool"] == "probe" else "guests")
    tickets = [json.loads(path.read_bytes()) for path in ticket_path.parent.glob("*.json")]
    consumed = sum(t.get("pool") == ticket["pool"] for t in tickets)
    if type(counted) is not int or counted < max(1, consumed):
        raise ValueError("reservation has no counted guest budget")
    cap = protocol.get("budget", {}).get("probe_guest_attempts" if ticket["pool"] == "probe" else "guest_attempts", 0)
    if type(cap) is not int or cap <= 0 or counted > cap:
        raise ValueError("reservation exceeds its protocol guest pool")
    manifest_ref = f"benchmark/kernel/builds/{build}/result.json"
    manifest_path = hashed(root, proof.get("build_manifest"), proof.get("build_manifest_sha256"), manifest_ref)
    manifest = json.loads(manifest_path.read_bytes())
    commit = proof.get("source_commit")
    if (not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit) or
            manifest.get("commit") != commit or manifest.get("passed") is not True or
            type(manifest.get("exit_code")) is not int or manifest["exit_code"] != 0 or
            manifest.get("instrument_sha256", "missing") is not None):
        raise ValueError("build manifest source commit/pass mismatch")
    input_config = file_at(root, "benchmark/config/swap-standard.config")
    if manifest.get("input_config_sha256") != sha(input_config) or proof.get("input_config_sha256") != sha(input_config):
        raise ValueError("build input config mismatch")
    config = file_at(root, f"benchmark/kernel/builds/{build}/output/.config")
    if manifest.get("config_sha256") != sha(config) or proof.get("config_sha256") != sha(config):
        raise ValueError("build final config mismatch")
    image = file_at(root, f"benchmark/kernel/builds/{build}/output/arch/x86/boot/bzImage")
    if manifest.get("image_sha256") != sha(image) or proof.get("image_sha256") != sha(image):
        raise ValueError("build image mismatch")
    serial = hashed(root, proof.get("serial_log"), proof.get("serial_sha256"), run + "/serial.log")
    harness = proof.get("harness_sha256", {})
    if not isinstance(harness, dict): raise ValueError("missing runner/parser harness hashes")
    for name in ("run.py", "evidence.py"):
        hashed(root, "benchmark/swap-standard/" + name, harness.get(name))
    spec = importlib.util.spec_from_file_location("correctness_evidence_parser", root / "benchmark/swap-standard/evidence.py")
    parser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser)
    reparsed = parser.parse(serial.read_text(errors="replace"), proof["image_sha256"], backend, mode, "correctness")
    parsed_gates = reparsed["gates"]
    if parsed_gates.get("cmdline_identity") is not True:
        raise ValueError("serial parser cannot bind the executed guest identity")
    expected_gates = dict(parsed_gates, qemu_exit=proof["exit_code"] == 0 and proof.get("stop_reason") is None)
    if gates != expected_gates or proof.get("metrics") != reparsed["metrics"]:
        raise ValueError("serial correctness evidence disagrees with runner gates/metrics")
    expected_integration = all(v is True for v in expected_gates.values())
    if proof["integration_pass"] != expected_integration or not all(k in expected_gates for k in required):
        raise ValueError("runner integration/required gate declaration disagrees with serial evidence")
    summary = {"campaign": campaign, "run_id": run_id, "source_commit": commit, "candidate_commit": commit,
               "result": proof["result_path"], "result_sha256": result_hash,
               "reservation": ticket_ref, "reservation_sha256": proof["reservation_sha256"],
               "build_manifest": manifest_ref, "build_manifest_sha256": proof["build_manifest_sha256"],
               "input_config_sha256": proof["input_config_sha256"], "config_sha256": proof["config_sha256"],
               "serial_log": proof["serial_log"], "serial_sha256": proof["serial_sha256"],
               "protocol_sha256": protocol_hash, "mode": mode, "backend": backend, "workload": "correctness",
               "integration_pass": expected_integration, "gates": dict(expected_gates),
               "exit_code": proof["exit_code"], "stop_reason": proof.get("stop_reason"),
               "run_valid": proof["run_valid"], "invalid_reasons": list(proof["invalid_reasons"])}
    if proof.get("stop_reason") == "STOP":
        raise ValueError("correctness run was externally stopped; no candidate failure established")
    if not expected_integration or not all(expected_gates[k] is True for k in required):
        summary.update(status="CORRECTNESS_FAIL", passed=False)
        raise CorrectnessFailure("counted, identity-bound correctness run failed", summary)
    if proof["run_valid"] is not True or proof["invalid_reasons"]:
        raise ValueError("correctness evidence has invalid measurement conditions")
    summary.update(status="CORRECTNESS_PASS", passed=True)
    return summary


def validate(proof, protocol, root):
    """Return a raw-file-bound summary, or raise ValueError without changing files."""
    try:
        return _validate(proof, protocol, Path(root).resolve())
    except (OSError, KeyError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        raise ValueError("missing or malformed correctness provenance: " + str(exc)) from exc
