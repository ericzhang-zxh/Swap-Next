# SPDX-License-Identifier: GPL-2.0-only
"""Validate counted raw correctness evidence for new standard-suite protocols.

Hashes detect accidental drift in trusted same-user artifacts; they are not
security signatures. Callers retain exact candidate-commit and exemption checks.
Legacy plain-mode correctness remains unavailable; revision 8 binds explicit cases.
"""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess


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


def _validate(proof, protocol, root, case_spec=None):
    if not isinstance(proof, dict) or not isinstance(protocol, dict):
        raise ValueError("proof and protocol must be objects")
    cases = protocol.get("cases", {})
    if not isinstance(cases, dict) or not all(isinstance(case, dict) for case in cases.values()):
        raise ValueError("malformed protocol cases")
    revision8 = protocol.get("protocol_revision") == 8
    if revision8:
        if case_spec is None:
            raise ValueError("revision 8 requires a complete correctness matrix")
        expected = configurations(root).correctness_case(protocol, case_spec["id"])
        if expected != case_spec:
            raise ValueError("correctness case differs from trusted catalog")
        for key in ("config_id", "backend", "mode", "workload", "topology_id"):
            if proof.get(key) != case_spec[key]:
                raise ValueError("raw correctness " + key + " differs from frozen case")
        if proof.get("correctness_case") != case_spec["id"]:
            raise ValueError("raw correctness case ID mismatch")
        configurations(root).validate_topology_record(protocol, proof)
    routes = {(case.get("mode", "plain"), case.get("backend")) for case in cases.values() if case.get("workload") == "swapin"}
    if not revision8 and routes and all(mode == "plain" for mode, _ in routes):
        raise ValueError("plain-mode correctness workload capability is missing")
    if not revision8 and not routes:
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
    if not revision8 and mode == "plain":
        raise ValueError("plain-mode correctness workload capability is missing")
    if not revision8 and ((mode, backend) not in routes or mode != "xswap" or backend not in ("disk", "zswap") or proof.get("workload") != "correctness"):
        raise ValueError("proof mode/backend/workload does not match protocol correctness route")
    if (type(proof.get("integration_pass")) is not bool or type(proof.get("run_valid")) is not bool or
            type(proof.get("exit_code")) is not int or not isinstance(proof.get("invalid_reasons"), list) or
            not all(isinstance(reason, str) for reason in proof["invalid_reasons"]) or
            proof.get("stop_reason") is not None and not isinstance(proof["stop_reason"], str)):
        raise ValueError("malformed runner outcome")
    gates = proof.get("gates")
    required = case_spec["required_gates"] if revision8 else protocol.get("required_correctness_gates")
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
    if revision8:
        identity.update({key: proof[key] for key in ("config_id", "correctness_case", "topology_id")})
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
    if revision8:
        catalog = configurations(root)
        pinned = catalog.pinned_config(protocol, case_spec["config_id"], root, "correctness")
        input_config = file_at(root, pinned["path"])
    else:
        input_config = file_at(root, "benchmark/config/swap-standard.config")
    if manifest.get("input_config_sha256") != sha(input_config) or proof.get("input_config_sha256") != sha(input_config):
        raise ValueError("build input config mismatch")
    config = file_at(root, f"benchmark/kernel/builds/{build}/output/.config")
    if manifest.get("config_sha256") != sha(config) or proof.get("config_sha256") != sha(config):
        raise ValueError("build final config mismatch")
    if revision8:
        final_config = catalog.validate_final(case_spec["config_id"], config, "correctness")
        catalog.verify_build_binding(root, manifest_path, commit, case_spec["config_id"])
    image = file_at(root, f"benchmark/kernel/builds/{build}/output/arch/x86/boot/bzImage")
    if manifest.get("image_sha256") != sha(image) or proof.get("image_sha256") != sha(image):
        raise ValueError("build image mismatch")
    serial = hashed(root, proof.get("serial_log"), proof.get("serial_sha256"), run + "/serial.log")
    harness = proof.get("harness_sha256", {})
    if not isinstance(harness, dict): raise ValueError("missing runner/parser harness hashes")
    for name in (("run.py", "evidence.py", "configurations.py") if revision8 else ("run.py", "evidence.py")):
        hashed(root, "benchmark/swap-standard/" + name, harness.get(name))
    if revision8:
        guest_manifest = json.loads(file_at(root, "benchmark/swap-standard/image.json").read_bytes())
        if proof.get("guest_provenance") != guest_manifest:
            raise ValueError("correctness guest image provenance mismatch")
        hashed(root, "benchmark/swap-standard/bench.img", guest_manifest.get("image_sha256"))
        hashed(root, "benchmark/swap-standard/initramfs.cpio.gz", guest_manifest.get("initrd_sha256"))
        for name, digest in guest_manifest.get("sources", {}).items():
            hashed(root, "benchmark/swap-standard/" + name, digest)
    spec = importlib.util.spec_from_file_location("correctness_evidence_parser", root / "benchmark/swap-standard/evidence.py")
    parser = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parser)
    subcases_failed = False
    if revision8:
        reparsed = parser.parse(serial.read_text(errors="replace"), proof["image_sha256"],
            backend, mode, proof["workload"], protocol_revision=8, config_id=case_spec["config_id"],
            correctness_case=case_spec["id"], topology_id=case_spec["topology_id"], expected_case=case_spec)
        if proof["workload"] == "compression":
            subcases = reparsed.get("correctness_subcases")
            if (not isinstance(subcases, dict) or set(subcases) != set(case_spec["subcases"])
                    or proof.get("correctness_subcases") != subcases):
                raise ValueError("correctness subcase evidence mismatch")
            subcases_failed = not all(isinstance(item, dict) and item.get("status") == "PASS"
                                      and item.get("reset") is True for item in subcases.values())
    else:
        reparsed = parser.parse(serial.read_text(errors="replace"), proof["image_sha256"], backend, mode, "correctness")
    parsed_gates = reparsed["gates"]
    if parsed_gates.get("cmdline_identity") is not True:
        raise ValueError("serial parser cannot bind the executed guest identity")
    if revision8 and parsed_gates.get("configuration_identity") is not True:
        raise ValueError("serial parser cannot bind the executed configuration/case/topology")
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
    if revision8:
        summary.update(config_id=case_spec["config_id"], correctness_case=case_spec["id"],
                       case_id=case_spec["id"], topology_id=case_spec["topology_id"],
                       workload=proof["workload"])
    if proof.get("stop_reason") == "STOP":
        raise ValueError("correctness run was externally stopped; no candidate failure established")
    if subcases_failed or not expected_integration or not all(expected_gates[k] is True for k in required):
        summary.update(status="CORRECTNESS_FAIL", passed=False)
        reason = ("required compression subcase failed, incomplete or not reset" if subcases_failed
                  else "counted, identity-bound correctness run failed")
        raise CorrectnessFailure(reason, summary)
    if proof["run_valid"] is not True or proof["invalid_reasons"]:
        raise ValueError("correctness evidence has invalid measurement conditions")
    if revision8:
        values = final_config["values"]
        for flag, gate in (("KASAN", "kasan"), ("PROVE_LOCKING", "lockdep"), ("KCSAN", "kcsan")):
            if values.get(flag) == "y":
                summary["gates"][gate] = True
    summary.update(status="CORRECTNESS_PASS", passed=True)
    return summary


def validate(proof, protocol, root):
    """Return a raw-file-bound summary, or raise ValueError without changing files."""
    try:
        root = Path(root).resolve()
        if protocol.get("protocol_revision") == 8:
            return _validate_matrix(proof, protocol, root)
        return _validate(proof, protocol, root)
    except (OSError, KeyError, TypeError, AttributeError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        raise ValueError("missing or malformed correctness provenance: " + str(exc)) from exc


def configurations(root):
    spec = importlib.util.spec_from_file_location("proof_configurations",
        Path(root) / "benchmark/swap-standard/configurations.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _configured_build(root, reference, expected_hash, commit, protocol, config_id, purpose, require_counted=True):
    """Verify an immutable build and fixed config, without executing anything."""
    path = hashed(root, reference, expected_hash)
    relative = Path(reference)
    if (relative.parent.parent.as_posix() != "benchmark/kernel/builds" or
            relative.name != "result.json" or not BUILD.fullmatch(relative.parent.name)):
        raise ValueError("non-canonical coverage build manifest")
    manifest = json.loads(path.read_bytes())
    if (manifest.get("commit") != commit or manifest.get("passed") is not True
            or type(manifest.get("exit_code")) is not int or manifest["exit_code"] != 0
            or manifest.get("instrument_sha256", "missing") is not None):
        raise ValueError("coverage build source/pass mismatch")
    catalog = configurations(root)
    config = catalog.pinned_config(protocol, config_id, root, purpose)
    if manifest.get("input_config_sha256") != config["input_config_sha256"]:
        raise ValueError("coverage build input configuration mismatch")
    base = relative.parent.as_posix()
    final = hashed(root, base + "/output/.config", manifest.get("config_sha256"))
    catalog.validate_final(config_id, final, purpose)
    catalog.verify_build_binding(root, path, commit, config_id, require_counted=require_counted)
    hashed(root, base + "/output/arch/x86/boot/bzImage", manifest.get("image_sha256"))
    return manifest


def _matrix_specs(protocol, root):
    catalog = configurations(root)
    return catalog, catalog.validate_protocol(protocol, root)


def _expected_commit(case, protocol, candidate_commit):
    return protocol["baseline_commit"] if case["role"] == "baseline" else candidate_commit


def _validate_matrix(proof, protocol, root):
    catalog, matrix = _matrix_specs(protocol, root)
    commit = proof.get("candidate_commit")
    if (proof.get("proof_schema_version") != 2 or proof.get("workload") != "correctness"
            or not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit)
            or proof.get("source_commit") != commit or proof.get("campaign") != protocol.get("campaign")
            or proof.get("baseline_commit") != protocol.get("baseline_commit")):
        raise ValueError("malformed correctness matrix identity")
    protocol_file = file_at(root, "campaigns/" + protocol["campaign"] + "/protocol.json")
    if json.loads(protocol_file.read_bytes()) != protocol or proof.get("protocol_sha256") != sha(protocol_file):
        raise ValueError("correctness matrix protocol mismatch")
    runs = proof.get("runs")
    builds = proof.get("builds", [])
    if not isinstance(runs, list) or not isinstance(builds, list):
        raise ValueError("correctness matrix evidence lists missing")
    expected_cases = {case["id"]: case for case in matrix["cases"]}
    ids = [row.get("case_id") if isinstance(row, dict) else None for row in runs]
    if len(ids) != len(set(ids)) or set(ids) != set(expected_cases):
        raise ValueError("correctness matrix missing, duplicate or unexpected case")
    summaries, gates, seen_runs = [], {}, set()
    for entry in runs:
        case = expected_cases[entry["case_id"]]
        raw = json.loads(hashed(root, entry.get("result_path"), entry.get("result_sha256")).read_bytes())
        if raw.get("result_path") != entry["result_path"]:
            raise ValueError("matrix row does not name its raw result")
        if raw.get("run_id") in seen_runs:
            raise ValueError("one guest result cannot satisfy multiple correctness cases")
        seen_runs.add(raw.get("run_id"))
        if raw.get("source_commit") != _expected_commit(case, protocol, commit):
            raise ValueError("matrix source role mismatch")
        summary = _validate(raw, protocol, root, case_spec=case)
        summaries.append(dict(summary, case_id=case["id"], role=case["role"]))
        if case["role"] == "candidate":
            gates.update({name: passed for name, passed in summary["gates"].items() if passed})
    expected_builds = {case["id"]: case for case in matrix["build_only"]}
    ids = [row.get("case_id") if isinstance(row, dict) else None for row in builds]
    if len(ids) != len(set(ids)) or set(ids) != set(expected_builds):
        raise ValueError("correctness matrix build-only coverage mismatch")
    build_summaries = []
    for entry in builds:
        case = expected_builds[entry["case_id"]]
        manifest = _configured_build(root, entry.get("build_manifest"), entry.get("build_manifest_sha256"),
            _expected_commit(case, protocol, commit), protocol, case["config_id"], "build-only")
        build_summaries.append(dict(entry, config_id=case["config_id"],
                                    source_commit=manifest["commit"], build_only=True))
    required = protocol.get("required_correctness_gates", [])
    if not required or not all(gates.get(name) is True for name in required):
        raise ValueError("candidate matrix lacks required scientific gates")
    _check_matrix_reservations(protocol, root, commit, seen_runs)
    return {"proof_schema_version": 2, "workload": "correctness",
            "campaign": protocol["campaign"], "candidate_commit": commit, "source_commit": commit,
            "baseline_commit": protocol["baseline_commit"], "protocol_sha256": sha(protocol_file),
            "status": "CORRECTNESS_PASS", "passed": True, "integration_pass": True,
            "gates": gates, "cases": summaries, "builds": build_summaries,
            "backend": "matrix", "mode": "matrix", "run_id": None,
            "coverage": {"cases": [item["case_id"] for item in summaries],
                         "configurations": sorted({item["config_id"] for item in summaries + build_summaries}),
                         "backends": sorted({item["backend"] for item in summaries})}}


def _relevant_reservations(protocol, root, candidate_commit):
    catalog = configurations(root)
    directory = root / "campaigns" / protocol["campaign"]
    rows = []
    for path in sorted((directory / "ledger/guest-reservations").glob("*.json")):
        ticket = json.loads(path.read_bytes())
        identity = ticket.get("identity", {})
        if identity.get("workload") not in ("correctness", "compression"):
            continue
        build = identity.get("build")
        if not isinstance(build, str) or not BUILD.fullmatch(build):
            raise ValueError("malformed correctness reservation build")
        manifest_path = root / "benchmark/kernel/builds" / build / "result.json"
        if not manifest_path.is_file():
            raise ValueError("counted correctness reservation has no build identity")
        source = json.loads(manifest_path.read_bytes()).get("commit")
        if source not in (candidate_commit, protocol["baseline_commit"]):
            continue
        case = catalog.correctness_case(protocol, identity.get("correctness_case"))
        if source != _expected_commit(case, protocol, candidate_commit):
            raise ValueError("counted correctness reservation source role mismatch")
        rows.append((ticket, case))
    return rows


def _check_matrix_reservations(protocol, root, candidate_commit, run_ids):
    relevant = _relevant_reservations(protocol, root, candidate_commit)
    retained = [ticket["id"] for ticket, _ in relevant]
    if len(retained) != len(set(retained)) or set(retained) != set(run_ids):
        raise ValueError("matrix selectively omits or duplicates counted correctness attempts")


def matrix_progress(protocol, root, candidate_commit, manifest=None, manifest_path=None):
    """Read-only progress for the session's agent-driven correctness action.

    Healthy partial coverage continues the same matrix. Failed, invalid, missing
    or duplicate counted attempts block; successful rows never erase them.
    """
    root = Path(root).resolve()
    result = {"passed": False, "failed": False, "attempted": False, "pending": True,
              "verified_cases": [], "missing_builds": []}
    try:
        catalog, matrix = _matrix_specs(protocol, root)
        if not re.fullmatch(r"[0-9a-f]{40}", candidate_commit or ""):
            raise ValueError("invalid matrix candidate identity")
        if manifest_path is not None:
            path = Path(manifest_path)
            if path.is_absolute():
                path = path.relative_to(root)
            result["manifest_path"] = path.as_posix()
            if manifest is None and (root / path).is_file():
                manifest = json.loads(file_at(root, path.as_posix()).read_bytes())
        if manifest is not None:
            if manifest.get("candidate_commit") != candidate_commit:
                raise ValueError("matrix manifest belongs to another candidate")
            summary = _validate_matrix(manifest, protocol, root)
            result.update(passed=True, pending=False, verified_cases=summary["coverage"]["cases"],
                          summary=summary, manifest_data=manifest, path=result.get("manifest_path"),
                          reason="Complete counted configuration-specific correctness matrix.")
            return result
        relevant = _relevant_reservations(protocol, root, candidate_commit)
        result["attempted"] = bool(relevant)
        by_case = {}
        for ticket, case in relevant:
            by_case.setdefault(case["id"], []).append(ticket)
        rows = []
        for case in matrix["cases"]:
            tickets = by_case.get(case["id"], [])
            if len(tickets) > 1:
                raise ValueError("multiple counted attempts for correctness case " + case["id"])
            if not tickets:
                result.setdefault("next_missing_case", case)
                continue
            ticket = tickets[0]
            raw_path = "campaigns/" + protocol["campaign"] + "/runs/guests/" + ticket["id"] + "/result.json"
            if ticket.get("status") != "STARTED" or not (root / raw_path).is_file():
                raise ValueError("counted correctness attempt has no completed raw result: " + ticket["id"])
            raw = json.loads(file_at(root, raw_path).read_bytes())
            if raw.get("source_commit") != _expected_commit(case, protocol, candidate_commit):
                raise ValueError("counted result source role mismatch")
            _validate(raw, protocol, root, case_spec=case)
            result["verified_cases"].append(case["id"])
            rows.append({"case_id": case["id"], "result_path": raw_path, "result_sha256": sha(root / raw_path)})
        builds = []
        ledger_path = root / "campaigns" / protocol["campaign"] / "ledger/ledger.json"
        ledger = json.loads(ledger_path.read_bytes()) if ledger_path.is_file() else []
        for case in matrix["build_only"]:
            matching = [item for item in ledger if item.get("action") == "build-coverage"
                        and item.get("case_id") == case["id"]
                        and item.get("commit") == _expected_commit(case, protocol, candidate_commit)]
            if len(matching) > 1:
                raise ValueError("multiple unresolved build-coverage outcomes: " + case["id"])
            if not matching:
                result["missing_builds"].append(case)
                continue
            item = matching[0]
            if item.get("status") != "BUILD_VERIFIED":
                raise ValueError("build-only coverage failed or incomplete: " + case["id"])
            _configured_build(root, item.get("build_manifest"), item.get("build_manifest_sha256"),
                _expected_commit(case, protocol, candidate_commit), protocol, case["config_id"], "build-only")
            builds.append({"case_id": case["id"], "build_manifest": item["build_manifest"],
                           "build_manifest_sha256": item["build_manifest_sha256"]})
        if len(rows) != len(matrix["cases"]) or result["missing_builds"]:
            result["reason"] = "Complete the next frozen matrix case; existing successful coverage is retained."
            return result
        proposal = {"proof_schema_version": 2, "workload": "correctness",
                    "campaign": protocol["campaign"], "candidate_commit": candidate_commit,
                    "source_commit": candidate_commit, "baseline_commit": protocol["baseline_commit"],
                    "protocol_sha256": sha(root / "campaigns" / protocol["campaign"] / "protocol.json"),
                    "runs": rows, "builds": builds}
        summary = _validate_matrix(proposal, protocol, root)
        result.update(passed=True, pending=False, manifest_data=proposal, summary=summary,
                      path=result.get("manifest_path"), reason="Complete verified matrix; retain the canonical manifest.")
        return result
    except CorrectnessFailure as exc:
        result.update(failed=True, attempted=True, pending=False, reason=str(exc), evidence=exc.evidence)
    except (ValueError, OSError, KeyError, TypeError, AttributeError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        result.update(attempted=True, pending=False, reason=str(exc))
    return result
