# SPDX-License-Identifier: GPL-2.0-only
"""Prepare comparison contexts for Workflow.run; never launch or reserve guests.

Reusable measurements are read back from their independent report, counted raw
runner results and frozen schedule. An alias points at that source and is never
counted as another trial. The caller retains the existing execution lock,
runner, validity rules, analyzer, budget service and final ledger writes.
"""
import copy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import time

try:
    from . import comparisons, reviews, reference_cache
except ImportError:
    import comparisons
    import reviews
    import reference_cache

TERMINAL = {"FAST_PASS", "REGRESSION", "NEEDS_REVIEW", "INCONCLUSIVE"}


def _need(condition, message):
    if not condition:
        raise comparisons.ComparisonError("BLOCKED: " + message)


def _read(path):
    return json.loads(Path(path).read_bytes())


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _module(project, relative):
    spec = importlib.util.spec_from_file_location(
        "comparison_runtime_" + Path(relative).stem, Path(project) / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _machine(project):
    return _module(project, "evolve/control/campaign_store.py").current_machine()


def _finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _fresh(row, now, max_age):
    return (_finite(row.get("finished")) and _finite(now) and _finite(max_age) and
            0 <= now - row["finished"] <= max_age)


def _git_identity(project, record, expected=None):
    relative = comparisons._relative(record.get("worktree"))
    path = Path(project) / relative
    _need(path.resolve().is_relative_to(Path(project).resolve()), "candidate worktree escapes project")
    try:
        if not path.exists() and record.get("status") == "closed" and expected:
            # The subsequent controller check-reference binds this object to the
            # retained export; no retired worktree or rebuild is required.
            result = subprocess.check_output(["git", "-C", str(Path(project) / "linux"), "rev-parse",
                expected["commit"], expected["commit"] + "^{tree}"], text=True).splitlines()
        else:
            result = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD", "HEAD^{tree}"],
                                             text=True).splitlines()
    except subprocess.CalledProcessError as exc:
        raise comparisons.ComparisonError("BLOCKED: unavailable candidate worktree identity") from exc
    _need(len(result) == 2, "candidate commit/tree identity missing")
    return result[0], result[1]


def _clear_reviews(project, contract, output, flow):
    campaign = contract["campaign"]
    checked = {}
    recorded = reviews.list_reviews(project, campaign)
    for name, arm in contract["arms"].items():
        if arm["compatibility"] != "compatible":
            continue
        subject = {"id": None, "candidate_commit": arm["commit"], "source_tree": arm["tree"]}
        if name == "baseline":
            _need(not reviews.blockers(project, campaign, subject), "baseline has unresolved review findings")
            checked[name] = {"candidate_commit": arm["commit"], "source_tree": arm["tree"]}
            continue
        candidate = arm["candidate"]
        record = _read(comparisons._file(
            project, "campaigns/" + campaign + "/candidates/" + candidate + ".json"))
        _need(record.get("id") == candidate, "comparison candidate record identity mismatch")
        _need(_git_identity(project, record, arm) == (arm["commit"], arm["tree"]),
              name + ": worktree HEAD differs from frozen arm")
        subject = dict(record, candidate_commit=arm["commit"], source_tree=arm["tree"])
        _need(not reviews.blockers(project, campaign, subject), name + ": unresolved review findings")
        clear = [r for r in recorded if r.get("candidate") == candidate
                 and r.get("candidate_commit") == arm["commit"] and r.get("source_tree") == arm["tree"]
                 and r.get("disposition") in ("pass", "resolve")]
        _need(clear, name + ": explicit exact-tree clear review is missing")
        action = "check" if record.get("status") == "active" else "check-reference"
        _need(record.get("status") in ("active", "closed"), "unknown comparison candidate status")
        log = output / ("scope-" + name + ".json")
        flow.command([sys.executable, "evolve/control/controller.py", "--campaign", campaign,
                      action, candidate], log, 180)
        scope = _read(log)
        _need(scope.get("status") == "SCOPE_PASS" and scope.get("candidate_commit") == arm["commit"]
              and scope.get("parent") == contract["common_base"]["commit"],
              name + ": controller scope evidence does not match the frozen arm")
        _need(_git_identity(project, record, arm) == (arm["commit"], arm["tree"]),
              name + ": worktree changed during scope check")
        checked[name] = {"candidate_commit": arm["commit"], "source_tree": arm["tree"],
                         "reviews": [{"id": r["id"], "record_sha256": r["record_sha256"]} for r in clear],
                         "scope": log.relative_to(project).as_posix(), "scope_sha256": _sha(log)}
    return checked


def _independent(rows):
    return [r for r in rows if isinstance(r, dict) and not r.get("source_evaluation_id")
            and r.get("measurement_reused") is not True]


def _started(row):
    return bool(row.get("execution_started") or row.get("runs") or
                row.get("status") in TERMINAL | {"CALIBRATED", "CALIBRATION_NOISY"})


def _logical_match(row, plan, contract, action):
    if row.get("action") != action or row.get("tier") != contract["tier"]:
        return False
    if row.get("fingerprint") != contract["environment"]["fingerprint"]:
        return False
    if row.get("protocol_sha256") not in (None, contract["protocol_sha256"]):
        return False
    comparison = row.get("comparison")
    if isinstance(comparison, dict):
        if action == "calibrate":
            return comparison.get("control_tree") == plan["control"]["tree"]
        trees = (comparison.get("control_tree"), comparison.get("treatment_tree"))
        target = (plan["control"]["tree"], plan["treatment"]["tree"])
        return trees == target or trees == tuple(reversed(target))
    # An older same-commit row still blocks duplicates, but cannot qualify for
    # reuse without the stronger protocol/tree/raw-result checks below.
    if plan["control"]["commit"] != contract["common_base"]["commit"]:
        return False
    treatment = plan["control"] if action == "calibrate" else plan["treatment"]
    return (row.get("candidate_tree") == treatment["tree"] or
            row.get("candidate_commit") == treatment["commit"])


def _extract(metrics, path):
    value = metrics
    for part in path.split("."):
        value = value[part]
    comparisons._number(value, path, positive=True)
    return value


def _report(project, campaign, row):
    ident = row.get("id")
    _need(isinstance(ident, str) and ident and "/" not in ident and ".." not in ident,
          "invalid source evaluation identity")
    path = comparisons._file(project, "campaigns/" + campaign + "/runs/evaluations/" + ident + "/report.json")
    _need(_read(path) == row, "source evaluation report differs from retained ledger")
    return {"source_evaluation_id": ident, "source_report": path.relative_to(project).as_posix(),
            "source_report_sha256": _sha(path)}


def _source_identity(project, protocol, row, plan, contract, action):
    _need(row.get("protocol_sha256") == contract["protocol_sha256"] and
          row.get("fingerprint") == contract["environment"]["fingerprint"] and
          row.get("tier") == contract["tier"] and row.get("action") == action,
          "source measurement lacks exact protocol/fingerprint identity")
    expected = plan["control"] if action == "calibrate" else plan["treatment"]
    _need(row.get("candidate_commit") == expected["commit"] and
          row.get("candidate_tree") == expected["tree"],
          "source measurement commit/tree differs; equivalent code cannot buy another trial")
    comparison = row.get("comparison")
    if comparison is not None:
        _need(isinstance(comparison, dict), "invalid source comparison identity")
        source = comparisons.load(project, contract["campaign"], comparison.get("contract_id"), protocol)
        source_plan = comparisons.execution_plan(source, protocol, comparison.get("contrast_id"), action)
        _need(source_plan["status"] == "PLANNED" and
              all(comparison.get(k) == v for k, v in source_plan["identity"].items()),
              "source comparison does not bind its frozen plan")
        for name in ("control",) if action == "calibrate" else ("control", "treatment"):
            _need(all(source_plan[name].get(key) == plan[name].get(key)
                      for key in ("commit", "tree", "build", "build_manifest_sha256")),
                  "source comparison arms differ from the requested contrast")
    else:
        _need(plan["control"]["commit"] == protocol["baseline_commit"]
              and plan["control"]["build"] == protocol["baseline_build"],
              "ordinary measurements can only bind the frozen baseline control")
        _need(action == "calibrate" or row.get("status") in ("FAST_PASS", "REGRESSION"),
              "only terminal ordinary fast results can be reused")
    return _report(project, contract["campaign"], row)


def _raw_pairs(project, protocol, row, plan, contract):
    """Read each counted attempt in original sequence, retaining invalid retries."""
    validity = _module(project, "benchmark/swap-standard/validity.py")
    parser = _module(project, "benchmark/swap-standard/evidence.py")
    rules = validity.protocol_rules(protocol)
    runs, pairs = row.get("runs"), row.get("pairs")
    _need(isinstance(runs, list) and isinstance(pairs, list) and len(pairs) == plan["pair_count"],
          "source does not contain the complete planned pair schedule")
    rebuilt = [{"a": {}, "b": {}} for _ in range(plan["pair_count"])]
    cursor, seen, prior = 0, set(), {}
    campaign, env = contract["campaign"], contract["environment"]
    budget = _read(comparisons._file(project, "campaigns/" + campaign + "/ledger/budget.json"))
    ticket_dir = project / "campaigns" / campaign / "ledger/guest-reservations"
    retained = sum(_read(p).get("pool") == "fast" for p in ticket_dir.glob("*.json"))
    _need(type(budget.get("guests")) is int and retained <= budget["guests"] <= protocol["budget"]["guest_attempts"],
          "source guest reservations do not reconcile with campaign budget")
    source_refs = []
    for step in plan["schedule"]:
        case = protocol["cases"][step["case"]]
        arm = contract["arms"][step["arm"]]
        manifest = _read(comparisons._file(
            project, "benchmark/kernel/builds/" + arm["build"] + "/result.json"))
        _need(_sha(project / "benchmark/kernel/builds" / arm["build"] / "result.json")
              == arm["build_manifest_sha256"], "source build manifest changed")
        allowed = rules["max_reruns"] + 1 if rules["enforce_validity"] else 1
        for attempt_index in range(allowed):
            _need(cursor < len(runs), "missing scheduled source attempt")
            attempt = runs[cursor]; cursor += 1
            _need(isinstance(attempt, dict) and all(attempt.get(key) == value for key, value in
                  (("pair", step["pair"]), ("case", step["case"]), ("arm", step["slot"]),
                   ("attempt", attempt_index))), "source attempt order differs from frozen schedule")
            run_id = attempt.get("id")
            _need(isinstance(run_id, str) and run_id and run_id not in seen and "/" not in run_id,
                  "duplicate or invalid source run identity")
            seen.add(run_id)
            reference = {"path": attempt.get("result"), "sha256": attempt.get("result_sha256")}
            path = comparisons._hashed(project, reference)
            expected_path = "campaigns/" + campaign + "/runs/guests/" + run_id + "/result.json"
            _need(reference["path"] == expected_path, "source result is outside its counted run")
            _need(comparisons._file(project, expected_path[:-4] + "sha256").read_text().strip()
                  == reference["sha256"], "source result sidecar mismatch")
            raw = _read(path)
            _need(raw.get("run_id") == run_id and raw.get("result_path") == expected_path
                  and raw.get("campaign") == campaign and raw.get("source_commit") == arm["commit"]
                  and raw.get("build") == arm["build"] and raw.get("backend") == case["backend"]
                  and raw.get("mode") == case.get("mode", "plain") and raw.get("workload") == case["workload"]
                  and raw.get("protocol_sha256") == contract["protocol_sha256"]
                  and raw.get("protocol_revision") == protocol.get("protocol_revision", 1)
                  and raw.get("build_manifest_sha256") == arm["build_manifest_sha256"]
                  and raw.get("input_config_sha256") == env["input_config_sha256"]
                  and raw.get("config_sha256") == manifest.get("config_sha256")
                  and raw.get("image_sha256") == manifest.get("image_sha256"),
                  "source raw build/protocol identity mismatch")
            _need(raw.get("accelerator") == env["accelerator"]
                  and raw.get("guest_vcpus") == env["guest"]["vcpus"]
                  and raw.get("guest_mem_mib") == env["guest"]["mem_mib"]
                  and raw.get("swap_bytes") == env["guest"]["swap_gib"] * 1024 ** 3
                  and raw.get("guest_provenance", {}).get("image_sha256") == env["guest_image_sha256"]
                  and raw.get("swap_image_allocation") == ("preallocated" if protocol.get("preallocate_swap") else "sparse"),
                  "source raw environment mismatch")
            ticket_path = "campaigns/" + campaign + "/ledger/guest-reservations/" + run_id + ".json"
            _need(raw.get("reservation") == ticket_path and attempt.get("reservation") == ticket_path,
                  "source reservation path mismatch")
            ticket = _read(comparisons._hashed(project, {"path": ticket_path, "sha256": raw.get("reservation_sha256")}))
            identity = {key: raw[key] for key in ("build", "backend", "mode", "workload")}
            _need(ticket.get("campaign") == campaign and ticket.get("id") == run_id
                  and ticket.get("status") == "STARTED" and ticket.get("pool") == "fast"
                  and ticket.get("protocol_sha256") == contract["protocol_sha256"]
                  and ticket.get("identity") == identity, "source reservation identity mismatch")
            walls = prior.setdefault(step["case"], [])
            valid, reason = validity.classify_attempt(raw, walls, rules) if rules["enforce_validity"] else (True, None)
            _need(attempt.get("run_valid", True) is valid, "retained source validity differs from raw evidence")
            source_refs.append(reference)
            if not valid:
                _need(attempt.get("status") == "INVALID" and attempt.get("invalid_reason") == reason,
                      "source invalid attempt was hidden or relabeled")
                continue
            _need(attempt.get("status") == "PASS" and raw.get("integration_pass") is True
                  and raw.get("exit_code") == 0 and raw.get("stop_reason") is None,
                  "source accepted arm lacks passing integration")
            serial_path = expected_path.rsplit("/", 1)[0] + "/serial.log"
            _need(raw.get("serial_log") == serial_path, "source serial identity mismatch")
            serial = comparisons._hashed(project, {"path": serial_path, "sha256": raw.get("serial_sha256")})
            for filename in ("run.py", "evidence.py"):
                _need(raw.get("harness_sha256", {}).get(filename) ==
                      _sha(project / "benchmark/swap-standard" / filename), "source parser/runner drift")
            parsed = parser.parse(serial.read_text(errors="replace"), manifest["image_sha256"],
                                  case["backend"], case.get("mode", "plain"), case["workload"])
            gates = dict(parsed["gates"], qemu_exit=True)
            _need(raw.get("gates") == gates and all(v is True for v in gates.values())
                  and raw.get("metrics") == parsed["metrics"] and attempt.get("metrics") == parsed["metrics"],
                  "source metrics/gates differ from the retained serial log")
            rebuilt[step["pair"]][step["slot"]].update(
                {step["case"] + "." + key: _extract(parsed["metrics"], key) for key in case["metrics"]})
            walls.append(raw["wall_seconds"])
            break
        else:
            _need(False, "source validity retries were exhausted")
    _need(cursor == len(runs), "unexpected source runs outside frozen schedule")
    for index, pair in enumerate(pairs):
        _need(pair.get("order") == ("AB" if index % 2 == 0 else "BA") and
              pair.get("a") == rebuilt[index]["a"] and pair.get("b") == rebuilt[index]["b"],
              "source pair values/order differ from raw runs")
    return rebuilt, source_refs, rules


def _validate_measurement(project, protocol, row, plan, contract, rows, cache, observed_at=None):
    cache_key = (row.get("id"), plan["action"], plan["control"]["commit"], plan["treatment"]["commit"], observed_at)
    if cache_key in cache:
        return cache[cache_key]
    binding = _source_identity(project, protocol, row, plan, contract, plan["action"])
    if row.get("measurement_reused") and not row.get("comparison") and plan["action"] == "calibrate":
        import calibration_cache
        calibration_cache.validate_alias(project, protocol, row, now=observed_at)
        result = {"row": copy.deepcopy(row), "binding": dict(binding,
            raw_results=[{"path": r["result"], "sha256": r["result_sha256"]} for r in row["runs"]],
            calibration_key=plan["calibration_key"], environment_sha256=comparisons.digest(contract["environment"]),
            native_cache_alias=copy.deepcopy(row["source_binding"]))}
        cache[cache_key] = result
        return result
    expected_status = {"CALIBRATED"} if plan["action"] == "calibrate" else TERMINAL
    _need(row.get("status") in expected_status and _finite(row.get("started")) and
          _finite(row.get("finished")) and row["started"] <= row["finished"],
          "source measurement is not terminal valid evidence")
    raw_pairs, references, rules = _raw_pairs(project, protocol, row, plan, contract)
    analyzer = _module(project, "benchmark/swap-standard/analysis.py")
    if plan["action"] == "calibrate":
        analysis = analyzer.calibrate(raw_pairs, plan["directions"], primary=plan["primary"],
                    envelope=rules["envelope"], min_pairs=plan["pair_count"],
                    noise_ceiling=rules["noise_ceiling"], noise_floor=rules["noise_floor"],
                    advisory_suffixes=rules["advisory_suffixes"])
        _need(analysis.get("passed") is True, "source calibration is noisy")
    else:
        calibration_id = row.get("calibration_id")
        candidates = [r for r in rows if r.get("id") == calibration_id and
                      (not r.get("measurement_reused") or (r.get("action") == "calibrate" and not r.get("comparison")))]
        _need(len(candidates) == 1, "source comparison calibration is missing or ambiguous")
        cal_row = candidates[0]
        cal_plan = comparisons.execution_plan(contract, protocol, plan["contrast"], "calibrate")
        cal = _validate_measurement(project, protocol, cal_row, cal_plan, contract, rows, cache, observed_at=row["started"])
        _need(_fresh(cal_row, row["started"], protocol["calibration_max_age_seconds"]),
              "source comparison used an expired or future calibration")
        analysis = analyzer.compare(raw_pairs, plan["directions"], cal["row"]["analysis"],
                    contract["tier"], primary=plan["primary"], decision=rules["decision"],
                    min_pairs=plan["pair_count"])
    _need(analysis == row.get("analysis") and analysis.get("status") == row.get("status"),
          "source analysis does not reproduce from raw paired evidence")
    result = {"row": copy.deepcopy(row), "binding": dict(binding, raw_results=references,
               calibration_key=plan["calibration_key"], environment_sha256=comparisons.digest(contract["environment"]))}
    cache[cache_key] = result
    return result



def reference_identity(project, contract, protocol, plan):
    """Scientific identity of a whole upstream contrast, with no campaign alias."""
    project = Path(project).resolve()
    _need(plan["action"] == "evaluate" and plan["contrast"] == "upstream-control",
          "only the intact upstream-control contrast is a shared reference")
    builds = {}
    for arm in (plan["control"], plan["treatment"]):
        manifest = _read(comparisons._file(project, "benchmark/kernel/builds/" + arm["build"] + "/result.json"))
        builds[arm["commit"]] = {"tree": arm["tree"], **{key: manifest[key] for key in
            ("image_sha256", "config_sha256", "input_config_sha256")}}
    harness = {path: _sha(comparisons._file(project, path)) for path in (
        "benchmark/swap-standard/run.py", "benchmark/swap-standard/evidence.py",
        "benchmark/swap-standard/validity.py", "benchmark/swap-standard/analysis.py",
        "evolve/comparison_runtime.py", "evolve/comparisons.py")}
    source = copy.deepcopy(contract["arms"]["upstream"]["source"])
    source.pop("artifact", None)  # Raw location belongs to original provenance.
    return {"source_commit": plan["treatment"]["commit"], "source_tree": plan["treatment"]["tree"],
            "protocol": copy.deepcopy(protocol), "machine": contract["environment"]["machine"],
            "accelerator": contract["environment"]["accelerator"],
            "guest": copy.deepcopy(contract["environment"]["guest"]), "builds": builds,
            "guest_image": _read(comparisons._file(project, "benchmark/swap-standard/image.json")),
            "harness": harness, "tier": contract["tier"],
            "contrast": {"baseline_commit": plan["control"]["commit"],
                         "candidate_commit": plan["treatment"]["commit"]},
            "upstream_source": source, "reference_role": "upstream",
            "evaluation_format": "comparison-runtime-v1"}


def validate_cached_reference(project, identity, provenance):
    """Replay the ORIGINAL protocol/report; never relabel data for the target."""
    project = Path(project).resolve()
    protocol_path = comparisons._hashed(project, {"path": provenance["protocol_path"],
                                                  "sha256": provenance["protocol_sha256"]})
    protocol = _read(protocol_path)
    campaign = provenance["campaign"]
    _need(protocol.get("campaign") == campaign and identity.get("protocol") == protocol,
          "cached reference original protocol identity mismatch")
    artifact = comparisons._hashed(project, {"path": provenance["artifact"],
                                             "sha256": provenance["artifact_sha256"]})
    row = _read(artifact)
    _need(row.get("measurement_reused") is not True and not row.get("source_evaluation_id"),
          "a cached alias cannot become an independent source")
    _need(row.get("finished") == provenance.get("observed_unix") and
          row.get("fingerprint") == provenance.get("fingerprint"),
          "cached source time/fingerprint mismatch")
    frozen = row.get("comparison", {})
    contract = comparisons.load(project, campaign, frozen.get("contract_id"), protocol)
    plan = comparisons.execution_plan(contract, protocol, frozen.get("contrast_id"))
    _need(reference_cache.cache_key("performance", reference_identity(project, contract, protocol, plan)) ==
          reference_cache.cache_key("performance", identity), "cached source scientific identity mismatch")
    ledger = _read(comparisons._file(project, "campaigns/" + campaign + "/ledger/ledger.json"))
    matches = [item for item in _independent(ledger) if item.get("id") == row.get("id")]
    _need(len(matches) == 1 and matches[0] == row, "cached source differs from original campaign ledger")
    prior = _prior(ledger, plan, contract, "evaluate")
    _need(len(prior) == 1 and prior[0] == row, "duplicate original source-tree contrasts")
    verified = {}
    _validate_measurement(project, protocol, row, plan, contract, ledger, verified)
    for name in ("baseline", "upstream"):
        arm = contract["arms"][name]
        _need(not reviews.blockers(project, campaign, {"id": arm.get("candidate"),
              "candidate_commit": arm["commit"], "source_tree": arm["tree"]}),
              "cached source has unresolved review findings")
    # Ledger/budget are deliberately replayed, not pinned: legitimate later
    # measurements append to them. Counted raw source artifacts are immutable.
    paths = {provenance["protocol_path"], provenance["artifact"],
             "campaigns/" + campaign + "/comparisons/" + contract["id"] + ".json"}
    paths.update(identity["harness"])
    for measured in verified.values():
        paths.add(measured["binding"]["source_report"])
        for ref in measured["binding"]["raw_results"]:
            paths.add(ref["path"])
            paths.add(str(Path(ref["path"]).with_suffix(".sha256")))
            raw = _read(comparisons._file(project, ref["path"]))
            paths.update((raw["serial_log"], raw["reservation"]))
    for name in ("baseline", "upstream"):
        arm = contract["arms"][name]
        prefix = "benchmark/kernel/builds/" + arm["build"]
        paths.add(prefix + "/result.json")
        manifest = _read(comparisons._file(project, prefix + "/result.json"))
        for suffix, key in (("/output/.config", "config_sha256"),
                            ("/output/arch/x86/boot/bzImage", "image_sha256")):
            comparisons._hashed(project, {"path": prefix + suffix, "sha256": manifest[key]})
            paths.add(prefix + suffix)
        comparisons._hashed(project, {"path": "benchmark/config/swap-standard.config",
                                       "sha256": manifest["input_config_sha256"]})
        paths.add("benchmark/config/swap-standard.config")
    cases = protocol["tiers"][contract["tier"]]["cases"]
    return {"passed": True, "status": "REFERENCE_VERIFIED",
            "checks": ["original-frozen-contract", "original-ledger-binding", "raw-paired-replay",
                       "source-calibration-replay", "serial-gates", "counted-reservations", "current-source-veto"],
            "coverage": {"cases": list(cases), "backends": sorted({protocol["cases"][case]["backend"] for case in cases}),
                         "gates": ["integration_pass", "paired_analysis"]},
            "evidence": [{"path": path, "sha256": _sha(comparisons._file(project, path))} for path in sorted(paths)]}


def register_reference(flow, project, protocol_path, row):
    """Index a saved original upstream result; never change its report or budget."""
    if (row.get("action") != "evaluate" or row.get("status") not in TERMINAL or
            row.get("measurement_reused") or row.get("source_evaluation_id") or
            row.get("comparison", {}).get("contrast_id") != "upstream-control"):
        return None
    project = Path(project).resolve()
    contract = comparisons.load(project, flow.p["campaign"], row["comparison"]["contract_id"], flow.p)
    plan = comparisons.execution_plan(contract, flow.p, "upstream-control")
    identity = reference_identity(project, contract, flow.p, plan)
    report = _report(project, flow.p["campaign"], row)
    provenance = {"campaign": flow.p["campaign"], "artifact": report["source_report"],
                  "artifact_sha256": report["source_report_sha256"], "observed_unix": row["finished"],
                  "protocol_path": Path(protocol_path).resolve().relative_to(project).as_posix(),
                  "protocol_sha256": contract["protocol_sha256"], "fingerprint": row["fingerprint"]}
    return reference_cache.register(project, "performance", identity, provenance,
                    max_age_seconds=flow.p["calibration_max_age_seconds"])


def _shared_evaluation(flow, project, contract, plan, now):
    if plan["contrast"] != "upstream-control":
        return None
    if not (Path(project) / "benchmark/reference-cache/performance").exists():
        return None
    identity = reference_identity(project, contract, flow.p, plan)
    found = reference_cache.lookup(project, "performance", identity,
        context={"reuse_intact_contrast": True, "purpose": "upstream-reference",
                 "campaign": contract["campaign"], "protocol_sha256": contract["protocol_sha256"],
                 "fingerprint": contract["environment"]["fingerprint"]}, now=now)
    if found["status"] != "reusable":
        return None
    originals = [found] + [item for item in found.get("alternatives", []) if item.get("status") == "reusable"]
    sources = {(item["provenance"]["campaign"], item["provenance"]["artifact"]) for item in originals}
    _need(len(sources) == 1, "ambiguous independent shared upstream measurements; explicit review required")
    origin = found["provenance"]
    source = _read(comparisons._hashed(project, {"path": origin["artifact"], "sha256": origin["artifact_sha256"]}))
    _need(not source.get("source_evaluation_id") and not source.get("measurement_reused"),
          "shared cache source is an alias")
    return {"row": source, "binding": {
        "source_campaign": origin["campaign"], "source_evaluation_id": source["id"],
        "source_report": origin["artifact"], "source_report_sha256": origin["artifact_sha256"],
        "source_protocol_sha256": origin["protocol_sha256"], "source_fingerprint": origin["fingerprint"],
        "reference_cache_record": found["record_sha256"], "semantic_identity_key": found["identity_key"],
        "cross_campaign_reused": origin["campaign"] != contract["campaign"],
        "intact_paired_contrast": True, "may_pair_with_new_arm": False,
        "new_guest_attempts": 0, "independent_measurement": False}}


def _prior(rows, plan, contract, action):
    sources = _independent(rows)
    if action == "calibrate":
        # Multiple local aliases of one original A/A are one observation.
        aliases = {}
        for row in rows:
            if row.get("measurement_reused") and not row.get("comparison") and row.get("action") == "calibrate":
                aliases[row.get("source_binding", {}).get("record_sha256", row["id"])] = row
        sources += list(aliases.values())
    return [r for r in sources if _started(r) and _logical_match(r, plan, contract, action)]


def available_calibration(flow, project, protocol_path, contract, contrast_id, fingerprint, *, now=None, _cache=None):
    """Return a verified calibration copy + binding, None if absent/expired; never writes."""
    project = Path(project).resolve()
    _need(_sha(protocol_path) == contract["protocol_sha256"] and
          fingerprint == contract["environment"]["fingerprint"], "calibration request identity drift")
    plan = comparisons.execution_plan(contract, flow.p, contrast_id, "calibrate")
    if plan["status"] != "PLANNED":
        return None
    now = time.time() if now is None else now
    cache = {} if _cache is None else _cache
    prior = _prior(flow.ledger, plan, contract, "calibrate")
    if any(r.get("status") != "CALIBRATED" or r.get("analysis", {}).get("passed") is not True for r in prior):
        _need(False, "control calibration already failed/noisy/incomplete; preserve the original attempt")
    if not prior:
        return None
    # Renewal is permitted only for expired passed calibration, not selection
    # among multiple independently attempted fresh A/A results.
    for left, right in zip(prior, prior[1:]):
        _need(_finite(right.get("started")) and _finite(left.get("finished")) and
              right["started"] - left["finished"] > flow.p["calibration_max_age_seconds"],
              "control calibration was rerun before its prior pass expired")
    result = _validate_measurement(project, flow.p, prior[-1], plan, contract, flow.ledger, cache)
    return result if _fresh(prior[-1], now, flow.p["calibration_max_age_seconds"]) else None


def _evaluation(flow, project, contract, plan, now, cache):
    prior = _prior(flow.ledger, plan, contract, "evaluate")
    if not prior:
        return _shared_evaluation(flow, project, contract, plan, now)
    _need(len(prior) == 1, "duplicate independent measurements exist for the same source-tree contrast")
    result = _validate_measurement(project, flow.p, prior[0], plan, contract, flow.ledger, cache)
    _need(_fresh(prior[0], now, flow.p["calibration_max_age_seconds"]),
          "existing contrast is stale; a new plan ID cannot buy another source-tree attempt")
    return result


def _remaining_cost(flow, project, protocol_path, contract, fingerprint, now, cache):
    calibrations, comparison_guests = {}, 0
    for contrast in contract["contrasts"]:
        plan = comparisons.execution_plan(contract, flow.p, contrast["id"])
        if plan["status"] != "PLANNED" or _evaluation(flow, project, contract, plan, now, cache):
            continue
        comparison_guests += plan["required_guests"]
        existing = available_calibration(flow, project, protocol_path, contract,
                    contrast["id"], fingerprint, now=now, _cache=cache)
        if existing is None:
            calibrations[plan["calibration_key"]] = comparisons.execution_plan(
                contract, flow.p, contrast["id"], "calibrate")["required_guests"]
    return {"comparison_guests": comparison_guests,
            "calibration_guests": sum(calibrations.values()),
            "minimum_remaining_guests": comparison_guests + sum(calibrations.values())}


def _alias(row, source, contract, action, now):
    original = source["row"]
    for field in ("analysis", "pairs", "runs", "status", "calibration_id", "protocol_revision"):
        if field in original:
            row[field] = copy.deepcopy(original[field])
    row.update(source_evaluation_id=original["id"], measurement_reused=True,
               independent_measurement=False, execution_started=False, finished=now,
               performance_accepted=False, auto_promote=False,
               measurement_started=original["started"], measurement_finished=original["finished"],
               reused_from={"campaign": source["binding"].get("source_campaign", contract["campaign"]), "evaluation_id": original["id"],
                            "measurement_time": original["finished"]},
               source_binding=copy.deepcopy(source["binding"]),
               new_guest_attempts=0, may_pair_with_new_arm=False)
    if action == "calibrate":
        row["calibration_binding"] = copy.deepcopy(source["binding"])


def prepare(flow, project, protocol_path, comparison_id, contrast_id, action, row, output_dir, fingerprint):
    """Prepare one existing Workflow.run A/B loop or return explicit reuse.

    Caller already holds its normal workflow lock and persists row afterward.
    PLANNED exposes control/treatment build+commit, count and calibration.
    REUSED carries the original science with an explicit source binding.
    NOT_COMPARABLE contains no score. No build, guest, reservation or original
    source-row mutation occurs here.
    """
    flow.check()
    project, protocol_path, output = Path(project).resolve(), Path(protocol_path), Path(output_dir).resolve()
    _need(output.is_dir() and output.is_relative_to(project), "comparison output directory is outside project")
    _need(protocol_path.resolve() == project / "campaigns" / flow.p["campaign"] / "protocol.json",
          "comparison protocol is not the current campaign protocol")
    contract = comparisons.load(project, flow.p["campaign"], comparison_id, flow.p)
    plan = comparisons.execution_plan(contract, flow.p, contrast_id, action)
    _need(row.get("tier", contract["tier"]) == contract["tier"], "comparison tier mismatch")
    _need(fingerprint == contract["environment"]["fingerprint"], "comparison fingerprint drift")
    if plan["status"] == "NOT_COMPARABLE":
        row.update(comparison_contract_id=contract["id"], comparison_contrast_id=contrast_id,
                   comparison_contract_sha256=comparisons.digest(contract),
                   protocol_sha256=contract["protocol_sha256"], status="NOT_COMPARABLE",
                   reason="; ".join(plan["reasons"]), analysis=None, performance_accepted=False, auto_promote=False)
        return {"status": "NOT_COMPARABLE", "reasons": plan["reasons"]}
    row.update(comparison=copy.deepcopy(plan["identity"]), protocol_sha256=contract["protocol_sha256"],
               candidate_commit=plan["control" if action == "calibrate" else "treatment"]["commit"],
               candidate_tree=plan["control" if action == "calibrate" else "treatment"]["tree"],
               fingerprint=fingerprint)
    evidence = comparisons.validate_evidence(contract, flow.p, project, fingerprint, _machine(project))
    clear = _clear_reviews(project, contract, output, flow)
    row.update(comparison_evidence=evidence, comparison_reviews=clear)
    now, cache = time.time(), {}
    for contrast in contract["contrasts"]:
        if contrast["id"] == contrast_id:
            break
        previous = comparisons.execution_plan(contract, flow.p, contrast["id"])
        _need(previous["status"] == "NOT_COMPARABLE" or
              _evaluation(flow, project, contract, previous, now, cache) is not None,
              "frozen contrast order requires " + contrast["id"] + " first")
    source = (available_calibration(flow, project, protocol_path, contract, contrast_id,
                                   fingerprint, now=now, _cache=cache) if action == "calibrate"
              else _evaluation(flow, project, contract, plan, now, cache))
    context = {"status": "PLANNED", "count": plan["pair_count"], "identity": plan["identity"],
               "control_build": plan["control"]["build"], "control_commit": plan["control"]["commit"],
               "treatment_build": plan["control" if action == "calibrate" else "treatment"]["build"],
               "treatment_commit": plan["control" if action == "calibrate" else "treatment"]["commit"],
               "plan": plan, "calibration": None, "contract": contract}
    if source:
        _alias(row, source, contract, action, now)
        context.update(status="REUSED", source_evaluation_id=source["row"]["id"])
        return context
    remaining = _remaining_cost(flow, project, protocol_path, contract, fingerprint, now, cache)
    _need(type(flow.budget.get("guests")) is int and
          flow.budget["guests"] + remaining["minimum_remaining_guests"] <= flow.p["budget"]["guest_attempts"],
          "insufficient shared campaign budget for remaining comparison work")
    context["remaining_cost"] = remaining
    row["comparison_remaining_cost"] = remaining
    if action == "evaluate":
        calibration = available_calibration(flow, project, protocol_path, contract,
                        contrast_id, fingerprint, now=now, _cache=cache)
        _need(calibration is not None, "comparison needs a fresh exact-control A/A calibration")
        context["calibration"] = calibration["row"]
        row["calibration_binding"] = calibration["binding"]
    flow.check()
    return context



def validate_alias(project, protocol, row):
    """Revalidate a retained alias without commands, reservations or state writes."""
    from types import SimpleNamespace
    project = Path(project).resolve()
    _need(row.get("measurement_reused") is True and row.get("action") in ("calibrate", "evaluate"),
          "expected a comparison alias")
    info = row.get("comparison", {})
    contract = comparisons.load(project, protocol["campaign"], info.get("contract_id"), protocol)
    plan = comparisons.execution_plan(contract, protocol, info.get("contrast_id"), row["action"])
    _need(plan["status"] == "PLANNED" and row.get("comparison") == plan["identity"], "alias comparison identity changed")
    _need(row.get("fingerprint") == contract["environment"]["fingerprint"] and
          row.get("protocol_sha256") == contract["protocol_sha256"], "alias target fingerprint changed")
    expected_arm = plan["control" if row["action"] == "calibrate" else "treatment"]
    _need(row.get("candidate_commit") == expected_arm["commit"] and row.get("candidate_tree") == expected_arm["tree"],
          "alias target source changed")
    comparisons.validate_evidence(contract, protocol, project, row["fingerprint"], _machine(project))
    for arm in contract["arms"].values():
        if arm.get("compatibility") == "compatible":
            _need(not reviews.blockers(project, protocol["campaign"], {"id": arm.get("candidate"),
                  "candidate_commit": arm["commit"], "source_tree": arm["tree"]}), "alias current review veto")
    ledger = _read(project / "campaigns" / protocol["campaign"] / "ledger/ledger.json")
    flow = SimpleNamespace(p=protocol, ledger=ledger)
    protocol_path = project / "campaigns" / protocol["campaign"] / "protocol.json"
    source = (available_calibration(flow, project, protocol_path, contract, info["contrast_id"], row["fingerprint"])
              if row["action"] == "calibrate" else _evaluation(flow, project, contract, plan, time.time(), {}))
    _need(source is not None, "alias original measurement unavailable or expired")
    expected = {}
    _alias(expected, source, contract, row["action"], row["finished"])
    _need(_finite(row.get("finished")) and row["finished"] >= source["row"]["finished"], "alias observation time changed")
    _need(all(row.get(key) == value for key, value in expected.items()), "alias differs from original measurement or provenance")
    return True


def planning_step(project, protocol, ledger, contract, contrast, fingerprint, *, now=None):
    """Share the runtime's validated reuse/cost decision with the session planner."""
    from types import SimpleNamespace
    now = time.time() if now is None else now
    project = Path(project).resolve()
    flow = SimpleNamespace(p=protocol, ledger=ledger)
    path = project / "campaigns" / protocol["campaign"] / "protocol.json"
    plan = comparisons.execution_plan(contract, protocol, contrast)
    _need(plan["status"] == "PLANNED", "comparison is not executable")
    cached = _evaluation(flow, project, contract, plan, now, {})
    calibration = available_calibration(flow, project, path, contract, contrast, fingerprint, now=now)
    action = "evaluate" if cached or calibration else "calibrate"
    execution = comparisons.execution_plan(contract, protocol, contrast, action)
    cost = 0 if cached else _remaining_cost(flow, project, path, contract, fingerprint, now, {})["minimum_remaining_guests"]
    return {"command": "compare" if action == "evaluate" else "compare-calibrate",
            "comparison": contract["id"], "contrast": contrast, "required_guests": cost,
            "identity": dict(execution["identity"],
                             source_evaluation_id=cached["row"]["id"] if cached else None,
                             prior_calibration=calibration["row"]["id"] if calibration else None)}
