# SPDX-License-Identifier: GPL-2.0-only
"""Frozen upstream comparison plans for the existing standard-suite evaluator.

This module schedules and validates; it never launches a guest, writes a budget
or decides performance acceptance. The ordinary evaluator owns reservations,
correctness parsing, measurement validity and statistical analysis.
"""
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

NAME = re.compile(r"[a-z][a-z0-9-]{0,47}")
SHA = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")
ROLES = {"baseline", "upstream", "candidate", "combined"}


class ComparisonError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise ComparisonError(message)


def _name(value, label):
    _require(isinstance(value, str) and NAME.fullmatch(value), "invalid " + label)
    return value


def _sha(value, label):
    _require(isinstance(value, str) and SHA.fullmatch(value), "invalid " + label)
    return value


def _commit(value, label):
    _require(isinstance(value, str) and COMMIT.fullmatch(value), "invalid " + label)
    return value


def _number(value, label, *, positive=False):
    try:
        valid = (type(value) in (int, float) and math.isfinite(value) and
                 (value > 0 if positive else value >= 0))
    except OverflowError:
        valid = False
    _require(valid, "invalid " + label)
    return value


def _count(value, label, minimum=0):
    _require(type(value) is int and value >= minimum, "invalid " + label)
    return value


def _text(value, label):
    _require(isinstance(value, str) and bool(value.strip()), "missing " + label)
    return value


def canonical_bytes(value):
    try:
        return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    except (TypeError, ValueError) as exc:
        raise ComparisonError("comparison data must be finite JSON") from exc


def digest(value):
    """Identity of canonical frozen bytes, not a second experiment fingerprint."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _relative(value):
    _text(value, "evidence path")
    path = Path(value)
    _require(not path.is_absolute() and ".." not in path.parts and
             path.as_posix() == value and value != ".", "noncanonical evidence path")
    return path


def _file(root, reference, expected=None):
    relative = _relative(reference)
    _require(expected is None or reference == expected, "evidence path mismatch")
    current = root
    for part in relative.parts:
        current = current / part
        _require(not current.is_symlink(), "symlink in evidence path")
    _require(current.is_file() and current.resolve().is_relative_to(root),
             "missing or escaped evidence: " + reference)
    return current


def _hashed(root, reference):
    _require(isinstance(reference, dict), "malformed evidence reference")
    path = _file(root, reference.get("path"))
    _sha(reference.get("sha256"), "evidence hash")
    _require(hashlib.sha256(path.read_bytes()).hexdigest() == reference["sha256"],
             "evidence hash mismatch: " + reference["path"])
    return path


def _source(source):
    _require(isinstance(source, dict), "upstream source is required")
    url = urlsplit(_text(source.get("url"), "upstream URL"))
    _require(url.scheme == "https" and bool(url.hostname) and
             not url.username and not url.password, "upstream URL must be public HTTPS")
    _text(source.get("revision"), "upstream series revision")
    _sha(source.get("patch_sha256"), "upstream patch hash")
    deps = source.get("dependencies")
    _require(isinstance(deps, list), "upstream dependencies must be a list")
    for dep in deps:
        _commit(dep, "upstream dependency")
    _require(len(deps) == len(set(deps)), "duplicate upstream dependency")
    if "artifact" in source:
        _require(isinstance(source["artifact"], dict), "invalid upstream artifact")
        _relative(source["artifact"].get("path"))
        _sha(source["artifact"].get("sha256"), "upstream artifact hash")
        _require(source["artifact"]["sha256"] == source["patch_sha256"],
                 "upstream artifact and patch hashes differ")


def _routes(protocol):
    explicit = protocol.get("comparison_correctness_routes")
    if explicit is not None:
        return explicit
    return [{"mode": mode, "backend": backend} for mode, backend in sorted({
        (case.get("mode", "plain"), case.get("backend"))
        for case in protocol.get("cases", {}).values() if case.get("workload") == "swapin"
    })]


def _validate_routes(routes):
    _require(isinstance(routes, list) and bool(routes), "correctness routes are required")
    result = []
    for route in routes:
        _require(isinstance(route, dict) and set(route) == {"mode", "backend"},
                 "invalid correctness route")
        result.append((_name(route["mode"], "correctness mode"),
                       _name(route["backend"], "correctness backend")))
    _require(len(result) == len(set(result)), "duplicate correctness route")
    return sorted(result)


def validate(contract, protocol, protocol_sha256=None):
    """Validate a frozen plan against its unchanged campaign protocol; no I/O."""
    _require(isinstance(contract, dict) and isinstance(protocol, dict),
             "contract and protocol must be objects")
    canonical_bytes(contract)
    _require(type(contract.get("schema_version")) is int and contract["schema_version"] == 1,
             "comparison schema_version must be 1")
    _name(contract.get("id"), "comparison ID")
    _require(_name(contract.get("campaign"), "campaign") == protocol.get("campaign"),
             "comparison campaign mismatch")
    bound_protocol = _sha(contract.get("protocol_sha256"), "protocol hash")
    if protocol_sha256 is not None:
        _require(bound_protocol == protocol_sha256, "comparison protocol hash mismatch")
    env = contract.get("environment")
    _require(isinstance(env, dict), "comparison environment is required")
    _name(env.get("machine"), "machine")
    for field in ("fingerprint", "input_config_sha256", "guest_image_sha256"):
        _sha(env.get(field), field)
    _require(env.get("accelerator") in ("kvm", "tcg") and
             env["accelerator"] == protocol.get("accelerator", {}).get("require"),
             "comparison accelerator mismatch")
    _require(env.get("guest") == protocol.get("guest") and isinstance(env["guest"], dict),
             "comparison guest shape mismatch")
    for key in ("vcpus", "mem_mib", "swap_gib"):
        _count(env["guest"].get(key), "guest " + key, 1)
    common = contract.get("common_base")
    _require(isinstance(common, dict), "common base is required")
    _commit(common.get("commit"), "common-base commit")
    _commit(common.get("tree"), "common-base tree")
    _require(common["commit"] == protocol.get("baseline_commit"),
             "common base differs from the frozen campaign baseline")
    tier = contract.get("tier")
    _require(tier in ("fast", "slow") and tier in protocol.get("tiers", {}),
             "comparison tier must be a protocol latency tier")
    settings = protocol["tiers"][tier]
    count = _count(settings.get("comparison_pairs"), "comparison pairs", 2)
    _count(settings.get("calibration_pairs"), "calibration pairs", 2)
    cases = settings.get("cases")
    _require(isinstance(cases, list) and cases and len(cases) == len(set(cases)),
             "comparison cases are required and unique")
    for name in cases:
        _name(name, "case")
        case = protocol.get("cases", {}).get(name)
        _require(isinstance(case, dict), "missing protocol comparison case")
        metrics = case.get("metrics")
        _require(isinstance(metrics, dict) and bool(metrics) and
                 all(isinstance(k, str) and k and v in ("higher", "lower")
                     for k, v in metrics.items()), "invalid comparison metrics")
        _require(case.get("primary") in metrics or case.get("primary") is None,
                 "primary metric missing from case")
    order = contract.get("pair_order")
    expected_order = ["AB" if i % 2 == 0 else "BA" for i in range(count)]
    _require(order == expected_order, "pair_order must match frozen alternating AB/BA pairs")
    _require(_validate_routes(contract.get("correctness_routes")) ==
             _validate_routes(_routes(protocol)), "correctness route coverage mismatch")
    arms = contract.get("arms")
    _require(isinstance(arms, dict) and {"baseline", "upstream", "candidate"} <= set(arms)
             and set(arms) <= ROLES, "baseline, upstream and candidate arms are required")
    used_builds, used_trees = set(), set()
    for name, arm in arms.items():
        _require(isinstance(arm, dict), "arm must be an object")
        state = arm.get("compatibility")
        _require(state in ("compatible", "incompatible"), "arm compatibility is required")
        if name == "upstream":
            _source(arm.get("source"))
        if state == "incompatible":
            _require(name in ("upstream", "combined"), "baseline and candidate must be compatible")
            _text(arm.get("reason"), "incompatibility reason")
            continue
        for field in ("commit", "tree"):
            _commit(arm.get(field), name + " " + field)
        _name(arm.get("build"), name + " build")
        _sha(arm.get("build_manifest_sha256"), name + " build manifest hash")
        _sha(arm.get("patch_sha256"), name + " cumulative patch hash")
        _require(arm["tree"] not in used_trees, "equivalent source trees cannot be comparison arms")
        _require(arm["build"] not in used_builds, "distinct arms cannot share a build name")
        used_trees.add(arm["tree"]); used_builds.add(arm["build"])
        refs = arm.get("correctness")
        _require(isinstance(refs, list), "arm correctness references must be a list")
        for ref in refs:
            _require(isinstance(ref, dict), "invalid correctness reference")
            _relative(ref.get("path"))
            _sha(ref.get("sha256"), "correctness hash")
        if name == "baseline":
            _require(arm["commit"] == common["commit"] and arm["tree"] == common["tree"]
                     and arm["build"] == protocol.get("baseline_build"),
                     "baseline arm identity mismatch")
        else:
            _name(arm.get("candidate"), name + " controller candidate")
        if name == "combined":
            composition = arm.get("composition")
            _require(isinstance(composition, dict) and
                     arms["upstream"].get("compatibility") == "compatible" and
                     composition.get("upstream_commit") == arms["upstream"]["commit"] and
                     composition.get("candidate_commit") == arms["candidate"]["commit"],
                     "composition must bind the exact upstream and candidate arms")
            _text(composition.get("rationale"), "composition rationale")
    contrasts = contract.get("contrasts")
    _require(isinstance(contrasts, list) and bool(contrasts), "contrasts are required")
    ids, edges = set(), set()
    for contrast in contrasts:
        _require(isinstance(contrast, dict), "contrast must be an object")
        ident = _name(contrast.get("id"), "contrast ID")
        a, b = contrast.get("control"), contrast.get("treatment")
        _require(a in arms and b in arms and a != b, "unknown or identical contrast arms")
        _require(ident not in ids and (a, b) not in edges, "duplicate contrast")
        ids.add(ident); edges.add((a, b))
    _require({("baseline", "upstream"), ("baseline", "candidate")} <= edges,
             "compare both upstream and candidate with the fixed baseline")
    return copy.deepcopy(contract)


def _contrast(contract, contrast_id):
    matches = [c for c in contract["contrasts"] if c["id"] == contrast_id]
    _require(len(matches) == 1, "unknown comparison contrast")
    return matches[0]


def execution_plan(contract, protocol, contrast_id, action="evaluate"):
    """Project explicit arm bindings into the trusted runner without changing p.

    Persist identity as the ordinary ledger row's comparison object.
    Use the normal budget service for every schedule item and any validity retry.
    """
    validate(contract, protocol)
    _require(action in ("calibrate", "evaluate"), "invalid comparison action")
    contrast = _contrast(contract, contrast_id)
    a, b = contrast["control"], contrast["treatment"]
    control, treatment = contract["arms"][a], contract["arms"][b]
    result = {"status": "PLANNED", "contract_sha256": digest(contract),
              "contrast": contrast_id, "tier": contract["tier"],
              "control": copy.deepcopy(control), "treatment": copy.deepcopy(treatment),
              "action": action, "schedule": [], "required_guests": 0}
    if any(arm["compatibility"] == "incompatible" for arm in (control, treatment)):
        result.update(status="NOT_COMPARABLE", reasons=[
            name + ": " + contract["arms"][name]["reason"] for name in (a, b)
            if contract["arms"][name]["compatibility"] == "incompatible"])
        return result
    env_hash = digest(contract["environment"])
    calibration_key = digest({"protocol_sha256": contract["protocol_sha256"],
                              "environment": contract["environment"], "tier": contract["tier"],
                              "control_commit": control["commit"], "control_tree": control["tree"],
                              "control_build": control["build"],
                              "control_manifest": control["build_manifest_sha256"]})
    identity = {"contract_id": contract["id"], "contract_sha256": digest(contract),
                "contrast_id": contrast_id, "control_arm": a, "treatment_arm": b,
                "control_commit": control["commit"], "treatment_commit": treatment["commit"],
                "control_tree": control["tree"], "treatment_tree": treatment["tree"],
                "calibration_key": calibration_key, "environment_sha256": env_hash}
    tier = protocol["tiers"][contract["tier"]]
    count = tier["calibration_pairs" if action == "calibrate" else "comparison_pairs"]
    directions, primary = {}, []
    for name in tier["cases"]:
        case = protocol["cases"][name]
        directions.update({name + "." + k: value for k, value in case["metrics"].items()})
        if case.get("primary"):
            primary.append(name + "." + case["primary"])
    for pair in range(count):
        order = "AB" if pair % 2 == 0 else "BA"
        for case in tier["cases"]:
            for letter in order.lower():
                arm = a if action == "calibrate" or letter == "a" else b
                result["schedule"].append({"ordinal": len(result["schedule"]),
                    "pair": pair, "case": case, "slot": letter, "arm": arm, "order": order})
    result.update(identity=identity, calibration_key=calibration_key,
                  pair_count=count, calibration_pair_count=tier["calibration_pairs"],
                  directions=directions, primary=primary,
                  required_guests=len(result["schedule"]))
    return result


def planned_cost(contract, protocol):
    """Prospective counts only. Existing ledgers remain the spent-budget authority."""
    validate(contract, protocol)
    controls, compare, not_comparable = {}, 0, []
    for contrast in contract["contrasts"]:
        plan = execution_plan(contract, protocol, contrast["id"])
        if plan["status"] == "NOT_COMPARABLE":
            not_comparable.append(contrast["id"])
            continue
        controls.setdefault(plan["calibration_key"],
                            execution_plan(contract, protocol, contrast["id"], "calibrate"))
        compare += plan["required_guests"]
    calibrate = sum(p["required_guests"] for p in controls.values())
    active = {name for c in contract["contrasts"]
              if execution_plan(contract, protocol, c["id"])["status"] == "PLANNED"
              for name in (c["control"], c["treatment"])}
    correctness = len(active) * len(contract["correctness_routes"])
    reruns = _count(protocol.get("validity", {}).get("reruns_per_arm", 0), "validity reruns")
    return {"calibration_guests": calibrate, "comparison_guests": compare,
            "correctness_guests_minimum": correctness,
            "minimum_total_guests": calibrate + compare + correctness,
            "performance_guests_with_maximum_reruns": (calibrate + compare) * (1 + reruns),
            "distinct_builds": len(active), "distinct_controls": len(controls),
            "not_comparable": not_comparable,
            "note": "Planning counts; reserve and count actual attempts in the campaign ledger."}


def freeze(project, contract, protocol):
    """Create canonical immutable plan bytes; identical repeated writes are no-ops."""
    project = Path(project).resolve()
    protocol_path = _file(project, "campaigns/" + _name(contract.get("campaign"), "campaign") +
                          "/protocol.json")
    _require(json.loads(protocol_path.read_bytes()) == protocol, "protocol contents mismatch")
    validate(contract, protocol, hashlib.sha256(protocol_path.read_bytes()).hexdigest())
    directory = project / "campaigns" / contract["campaign"] / "comparisons"
    _require(not directory.is_symlink(), "comparison directory uses a symlink")
    directory.mkdir(exist_ok=True)
    path = directory / (contract["id"] + ".json")
    data = canonical_bytes(contract)
    try:
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        _require(not path.is_symlink() and path.read_bytes() == data,
                 "frozen comparison contract cannot be replaced")
    return {"path": path.relative_to(project).as_posix(), "sha256": digest(contract)}


def load(project, campaign, comparison_id, protocol):
    project = Path(project).resolve()
    path = _file(project, "campaigns/" + _name(campaign, "campaign") +
                 "/comparisons/" + _name(comparison_id, "comparison ID") + ".json")
    contract = json.loads(path.read_bytes())
    _require(contract.get("campaign") == campaign and contract.get("id") == comparison_id,
             "comparison path identity mismatch")
    _require(path.read_bytes() == canonical_bytes(contract), "comparison file is not canonical frozen bytes")
    protocol_path = _file(project, "campaigns/" + campaign + "/protocol.json")
    _require(json.loads(protocol_path.read_bytes()) == protocol, "protocol contents mismatch")
    return validate(contract, protocol, hashlib.sha256(protocol_path.read_bytes()).hexdigest())


def verify_sources(contract, source_repo):
    """Verify actual Git trees, common ancestry and full cumulative diff hashes."""
    def git(*args, binary=False):
        try:
            result = subprocess.run(["git", "-C", str(source_repo), *args],
                                    check=True, capture_output=True)
        except subprocess.CalledProcessError as exc:
            raise ComparisonError("source identity or ancestry could not be verified") from exc
        return result.stdout if binary else result.stdout.decode().strip()

    base = _commit(contract["common_base"]["commit"], "common-base commit")
    _require(git("rev-parse", base + "^{tree}") == contract["common_base"]["tree"],
             "common-base tree mismatch")
    identities = {}
    for name, arm in contract["arms"].items():
        if arm["compatibility"] == "incompatible":
            continue
        _commit(arm["commit"], name + " commit")
        _commit(arm["tree"], name + " tree")
        tree = git("rev-parse", arm["commit"] + "^{tree}")
        _require(tree == arm["tree"], name + ": source tree mismatch")
        git("merge-base", "--is-ancestor", base, arm["commit"])
        patch = git("diff", "--no-ext-diff", "--no-textconv", "--binary", "--full-index",
                    base, arm["commit"], "--", binary=True)
        _require(hashlib.sha256(patch).hexdigest() == arm["patch_sha256"],
                 name + ": cumulative patch mismatch")
        if name == "combined":
            git("merge-base", "--is-ancestor", contract["arms"]["upstream"]["commit"], arm["commit"])
        identities[name] = {"commit": arm["commit"], "tree": tree,
                            "patch_sha256": arm["patch_sha256"]}
    return identities


def validate_evidence(contract, protocol, project, fingerprint, machine,
                      source_repo=None, correctness_validator=None):
    """Revalidate every compatible arm using actual build/proof files.

    The injectable validator is for guest-free fixtures; production callers
    leave it unset to use the trusted raw correctness parser. This method makes
    no claims about a live measurement environment beyond its passed identity.
    """
    project = Path(project).resolve()
    campaign = _name(contract.get("campaign"), "campaign")
    protocol_path = _file(project, "campaigns/" + campaign + "/protocol.json")
    _require(json.loads(protocol_path.read_bytes()) == protocol, "frozen protocol contents mismatch")
    validate(contract, protocol, hashlib.sha256(protocol_path.read_bytes()).hexdigest())
    env = contract["environment"]
    _require(env["fingerprint"] == fingerprint, "comparison evaluator fingerprint mismatch")
    _require(env["machine"] == machine, "comparison machine mismatch")
    campaign_record = json.loads(_file(project, "campaigns/" + campaign + "/campaign.json").read_bytes())
    _require(campaign_record.get("machine") == machine, "campaign machine mismatch")
    config = _file(project, "benchmark/config/swap-standard.config")
    _require(hashlib.sha256(config.read_bytes()).hexdigest() == env["input_config_sha256"],
             "comparison input config mismatch")
    image = json.loads(_file(project, "benchmark/swap-standard/image.json").read_bytes())
    _require(image.get("image_sha256") == env["guest_image_sha256"], "comparison guest image mismatch")
    source = verify_sources(contract, source_repo if source_repo is not None else project / "linux")
    if correctness_validator is None:
        spec = importlib.util.spec_from_file_location(
            "comparison_correctness_proof", project / "evolve/control/correctness_proof.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        correctness_validator = module.validate
    summaries = {}
    required = set(_validate_routes(contract["correctness_routes"]))
    for name, arm in contract["arms"].items():
        if arm["compatibility"] == "incompatible":
            continue
        manifest_ref = "benchmark/kernel/builds/" + arm["build"] + "/result.json"
        manifest_path = _hashed(project, {"path": manifest_ref, "sha256": arm["build_manifest_sha256"]})
        manifest = json.loads(manifest_path.read_bytes())
        _require(manifest.get("commit") == arm["commit"] and manifest.get("passed") is True and
                 type(manifest.get("exit_code")) is int and manifest["exit_code"] == 0 and
                 manifest.get("instrument_sha256", "missing") is None and
                 manifest.get("input_config_sha256") == env["input_config_sha256"],
                 name + ": build provenance mismatch")
        for suffix, key in (("output/.config", "config_sha256"),
                            ("output/arch/x86/boot/bzImage", "image_sha256")):
            _hashed(project, {"path": "benchmark/kernel/builds/" + arm["build"] + "/" + suffix,
                              "sha256": manifest.get(key)})
        if name == "upstream":
            _require("artifact" in arm["source"], "upstream patch artifact is required for execution")
            _hashed(project, arm["source"]["artifact"])
        covered, proofs = set(), []
        for ref in arm["correctness"]:
            raw = json.loads(_hashed(project, ref).read_bytes())
            summary = correctness_validator(raw, protocol, project)
            _require(summary.get("source_commit", summary.get("candidate_commit")) == arm["commit"]
                     and summary.get("build_manifest_sha256") == arm["build_manifest_sha256"]
                     and summary.get("protocol_sha256") == contract["protocol_sha256"]
                     and summary.get("passed") is True and summary.get("integration_pass") is True,
                     name + ": correctness provenance mismatch")
            covered.add((summary.get("mode"), summary.get("backend")))
            proofs.append(summary)
        _require(required <= covered, name + ": missing correctness route evidence")
        summaries[name] = {"source": source[name], "build_manifest_sha256": arm["build_manifest_sha256"],
                           "correctness": proofs}
    return {"contract_id": contract["id"], "contract_sha256": digest(contract),
            "protocol_sha256": contract["protocol_sha256"],
            "fingerprint": fingerprint, "environment_sha256": digest(env), "arms": summaries}


def reusable_calibration(row, plan, contract, now, max_age):
    """Exact control reuse only; failures/stale/foreign controls never qualify."""
    if not isinstance(row, dict) or plan.get("status") != "PLANNED":
        return False
    identity = row.get("comparison") or {}
    finished = row.get("finished")
    analysis = row.get("analysis")
    if not isinstance(identity, dict) or not isinstance(analysis, dict):
        return False
    try:
        canonical_bytes(analysis)
    except ComparisonError:
        return False
    return bool(row.get("action") == "calibrate" and row.get("status") == "CALIBRATED"
                and row.get("tier") == contract["tier"]
                and row.get("fingerprint") == contract["environment"]["fingerprint"]
                and row.get("protocol_sha256") == contract["protocol_sha256"]
                and identity.get("calibration_key") == plan["calibration_key"]
                and identity.get("environment_sha256") == plan["identity"]["environment_sha256"]
                and identity.get("control_commit") == plan["control"]["commit"]
                and identity.get("control_tree") == plan["control"]["tree"]
                and analysis.get("passed") is True and analysis.get("status") == "CALIBRATED"
                and analysis.get("pair_count") == plan["calibration_pair_count"]
                and analysis.get("directions") == plan["directions"]
                and analysis.get("primary") == plan["primary"]
                and type(finished) in (int, float) and math.isfinite(finished)
                and type(now) in (int, float) and math.isfinite(now)
                and type(max_age) in (int, float) and math.isfinite(max_age)
                and 0 <= now - finished <= max_age)


def reconcile(contract, protocol, ledger_rows):
    """Report retained, bound contrasts without combining incompatible measurements.

    Only already-analyzed evaluator rows are reported. Duplicate completed
    attempts are an error; missing/incomplete/foreign rows never become zero or
    PASS. Calibrations and all failed attempts remain in the ordinary ledger.
    """
    validate(contract, protocol)
    _require(isinstance(ledger_rows, list), "ledger must be a list")
    outcomes = []
    for contrast in contract["contrasts"]:
        plan = execution_plan(contract, protocol, contrast["id"])
        if plan["status"] == "NOT_COMPARABLE":
            outcomes.append({"contrast": contrast["id"], "status": "NOT_COMPARABLE",
                             "reasons": plan["reasons"], "analysis": None})
            continue
        rows = [row for row in ledger_rows if isinstance(row, dict) and
                row.get("action") == "evaluate" and isinstance(row.get("comparison"), dict) and
                row["comparison"].get("contract_id") == contract["id"] and
                row["comparison"].get("contrast_id") == contrast["id"]]
        if not rows:
            outcomes.append({"contrast": contrast["id"], "status": "PENDING", "analysis": None})
            continue
        row = rows[-1]
        bound = (all(row["comparison"].get(k) == v for k, v in plan["identity"].items())
                 and row.get("fingerprint") == contract["environment"]["fingerprint"]
                 and row.get("protocol_sha256") == contract["protocol_sha256"]
                 and row.get("tier") == contract["tier"])
        if not bound:
            outcomes.append({"contrast": contrast["id"], "status": "INCOMPLETE",
                             "reasons": ["comparison provenance mismatch"], "analysis": None,
                             "evaluation_id": row.get("id")})
            continue
        completed = [r for r in rows if r.get("status") in ("FAST_PASS", "REGRESSION", "NEEDS_REVIEW", "INCONCLUSIVE")]
        if len(completed) > 1:
            outcomes.append({"contrast": contrast["id"], "status": "INCOMPLETE",
                             "reasons": ["multiple terminal comparisons need explicit reconciliation"],
                             "analysis": None, "evaluation_ids": [r.get("id") for r in rows]})
            continue
        result = {"contrast": contrast["id"], "status": row.get("status", "INCOMPLETE"),
                  "evaluation_id": row.get("id"), "analysis": None}
        analysis = row.get("analysis")
        if row.get("status") in ("FAST_PASS", "REGRESSION", "NEEDS_REVIEW", "INCONCLUSIVE"):
            try:
                _require(isinstance(analysis, dict) and analysis.get("status") == row["status"],
                         "analysis status mismatch")
                _require(type(analysis.get("pair_count")) is int and
                         analysis["pair_count"] == plan["pair_count"], "analysis pair count mismatch")
                _require(analysis.get("performance_accepted") is False and
                         analysis.get("auto_promote") is False, "comparison is review evidence only")
                metrics = analysis.get("metrics")
                _require(isinstance(metrics, dict) and set(metrics) == set(plan["directions"]),
                         "analysis metrics mismatch")
                for key, metric in metrics.items():
                    _require(isinstance(metric, dict), "invalid analyzed metric")
                    _number(metric.get("median_ratio"), key + " median ratio", positive=True)
                    _number(metric.get("noise_relative"), key + " noise")
                    _require(type(metric.get("guard_pass")) is bool, "missing metric guard result")
                _number(analysis.get("combined_score"), "combined score", positive=True)
                canonical_bytes(analysis)
                result["analysis"] = copy.deepcopy(analysis)
            except (ComparisonError, TypeError, KeyError) as exc:
                result.update(status="INCOMPLETE", reasons=[str(exc)])
        elif row.get("reason"):
            result["reasons"] = [row["reason"]]
        outcomes.append(result)
    return {"contract_id": contract["id"], "contract_sha256": digest(contract),
            "outcomes": outcomes, "performance_accepted": False, "auto_promote": False,
            "unmeasured_contrasts": "No derived candidate/upstream delta is inferred."}
