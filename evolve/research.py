# SPDX-License-Identifier: GPL-2.0-only
"""Research agendas, trusted profiles and evidence-bound value decisions.

No evaluator is launched here. Existing campaign ledgers own spending.
Campaigns freeze line_contract() in research.json, independently of mutable
backlogs and baseline choices. Readiness is capability, not authorization.
"""
import argparse
import copy
import fcntl
import fnmatch
import hashlib
import importlib.util
import json
import math
import os
import tempfile
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
NAME = re.compile(r"[a-z][a-z0-9-]{0,47}")
OBJECT = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")
COMPLEXITY_DIMENSIONS = ("state", "lifetime", "locking", "error_paths",
                         "configuration", "test_burden", "interfaces", "memory_cost")
CHANGES = {"decreased", "unchanged", "increased", "mixed", "unknown"}
IDENTITY_FIELDS = ("candidate_commit", "candidate_tree", "parent_commit", "parent_tree",
                   "baseline_commit", "protocol_sha256", "evaluation_id", "evaluation_report")


class ResearchError(ValueError):
    pass


def _need(condition, message):
    if not condition:
        raise ResearchError(message)


def _text(value, what):
    _need(isinstance(value, str) and bool(value.strip()), what + " must be non-empty text")
    return value


def _name(value, what):
    _need(isinstance(value, str) and NAME.fullmatch(value), "invalid " + what)
    return value


def _number(value, what, minimum=0, maximum=None, integer=False):
    _need(not isinstance(value, bool) and isinstance(value, (int, float)) and
          math.isfinite(value), what + " must be finite numeric data")
    _need(not integer or isinstance(value, int), what + " must be an integer")
    _need(value >= minimum and (maximum is None or value <= maximum), what + " is outside its range")
    return value


def _json(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ResearchError("non-finite or unserializable research data") from exc


def digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _path(value, what="evidence path"):
    _text(value, what)
    _need(not PurePosixPath(value).is_absolute() and "\\" not in value and
          all(bit not in ("", ".", "..") for bit in value.split("/")),
          what + " must be a normalized repository-relative path")
    return value


def _paths(values, what, nonempty=True):
    _need(isinstance(values, list) and (not nonempty or values), what + " must be a list")
    for value in values:
        _path(value, what)
    _need(len(set(values)) == len(values), what + " contains duplicates")
    return values


def _mapping(value, what):
    _need(isinstance(value, dict), what + " must be an object")
    return value


def read_json(path):
    try:
        value = json.loads(Path(path).read_text())
        _json(value)
        return value
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchError(str(exc)) from exc


def _version(value):
    _mapping(value, "record")
    _need(type(value.get("schema_version")) is int and value["schema_version"] == 1,
          "schema_version must be 1")


def _strings(values, what):
    _need(isinstance(values, list) and bool(values), what + " must be non-empty")
    for value in values:
        _text(value, what)
    _need(len(set(values)) == len(values), what + " must be distinct")
    return values


def validate_profile(profile):
    _version(profile)
    _name(profile.get("id"), "profile id")
    _number(profile.get("version"), "profile version", minimum=1, integer=True)
    _text(profile.get("description"), "profile description")
    _need(type(profile.get("executable")) is bool, "executable must be boolean")
    _paths(profile.get("allowed_modify"), "profile allowed_modify")
    _paths(profile.get("allowed_add"), "profile allowed_add", nonempty=False)
    for key in ("primary_metrics", "mechanism_evidence", "correctness_gates", "correctness_modes"):
        _strings(profile.get(key), key)
    _need(profile.get("allowed_tiers") == ["probe", "fast"], "automatic profile tiers are probe and fast")
    missing = profile.get("missing_capabilities")
    _need(isinstance(missing, list), "missing_capabilities must be a list")
    for item in missing:
        _text(item, "missing capability")
    _need(not profile["executable"] or not missing, "executable profile declares missing capabilities")
    cap = _mapping(profile.get("resource_cap"), "profile resource cap")
    for key in ("guest_attempts", "build_attempts", "wall_seconds"):
        _number(cap.get(key), "profile resource cap " + key, minimum=1, integer=True)
    _need(cap["guest_attempts"] <= 120 and cap["wall_seconds"] <= 64800,
          "profile exceeds standing campaign cap")
    revisions = profile.get("protocol_revisions")
    _need(isinstance(revisions, list) and revisions and all(type(v) is int for v in revisions), "protocol revisions must be explicit")
    _json(profile)
    return copy.deepcopy(profile)


def load_profile(profile_id, root=ROOT):
    """Only framework-owned profile IDs, never a candidate-supplied file path."""
    _name(profile_id, "profile id")
    path = Path(root) / "evolve/profiles" / (profile_id + ".json")
    _need(not path.is_symlink(), "profile must be a framework-owned regular file")
    profile = validate_profile(read_json(path))
    _need(profile["id"] == profile_id, "profile id differs from filename")
    return profile


def validate_policy_scope(policy, profile):
    """Caller supplies the trusted load_profile result, not candidate JSON."""
    validate_profile(profile)
    errors = []
    for key in ("allowed_modify", "allowed_add"):
        values = policy.get(key)
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
            errors.append(key + " must be a list of paths")
        elif not set(values) <= set(profile[key]):
            errors.append("candidate policy widens trusted profile " + key)
    return errors


def capability_readout(profile, protocol=None, policy=None, root=ROOT):
    """Validate actual parameters through existing trusted protocol_rules.

    Ready still needs runtime checks, ownership, STOP, exact correctness evidence
    and authorization. Historical approvals are not inferred from a profile.
    """
    validate_profile(profile)
    reasons = list(profile["missing_capabilities"])
    if not profile["executable"]:
        reasons.append("profile is not executable")
    if policy is not None:
        reasons += validate_policy_scope(policy, profile)
    if protocol is None:
        reasons.append("a frozen protocol is required")
    else:
        _mapping(protocol, "protocol")
        try:
            _json(protocol)
            source = Path(root) / "benchmark/swap-standard/validity.py"
            spec = importlib.util.spec_from_file_location("swap_research_validity", source)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.protocol_rules(protocol)
        except (ResearchError, ValueError, TypeError, KeyError, OSError, AttributeError) as exc:
            reasons.append("trusted protocol validation: " + str(exc))
        if protocol.get("protocol_revision") not in profile["protocol_revisions"]:
            reasons.append("protocol revision is outside trusted profile")
        if protocol.get("template_only"):
            reasons.append("protocol is a non-executable template")
        tiers = protocol.get("tiers", {})
        if not isinstance(tiers, dict) or not {"probe", "fast"} <= set(tiers):
            reasons.append("profile requires probe and fast tiers")
        if isinstance(tiers, dict) and set(tiers) - set(profile["allowed_tiers"]):
            reasons.append("protocol contains a tier outside automatic profile")
        cases = protocol.get("cases", {})
        if not isinstance(cases, dict):
            reasons.append("protocol cases must be an object")
            cases = {}
        for name, case in cases.items():
            if not isinstance(case, dict):
                reasons.append(str(name) + ": case must be an object")
                continue
            primary = case.get("primary")
            if primary is not None and primary not in profile["primary_metrics"]:
                reasons.append(str(name) + ": primary endpoint is outside profile")
            if case.get("workload") == "swapin" and case.get("mode", "plain") not in profile["correctness_modes"]:
                reasons.append(str(name) + ": missing " + str(case.get("mode", "plain")) + " correctness capability")
        gates = protocol.get("required_correctness_gates", [])
        if not isinstance(gates, list) or any(not isinstance(g, str) for g in gates) or not set(profile["correctness_gates"]) <= set(gates):
            reasons.append("protocol omits profile correctness gates")
        try:
            budget = _mapping(protocol.get("budget"), "protocol budget")
            total = _number(budget.get("guest_attempts"), "latency budget", integer=True) + _number(
                budget.get("probe_guest_attempts"), "probe budget", integer=True)
            _need(total <= profile["resource_cap"]["guest_attempts"], "guest budget exceeds profile")
            for key in ("build_attempts", "wall_seconds"):
                _number(budget.get(key), key, minimum=1, maximum=profile["resource_cap"][key], integer=True)
        except ResearchError as exc:
            reasons.append(str(exc))
    return {"profile": profile["id"], "profile_version": profile["version"],
            "profile_sha256": digest(profile), "ready": not reasons,
            "missing_capabilities": list(dict.fromkeys(reasons)),
            "allowed_tiers": profile["allowed_tiers"], "performance_validated": False,
            "execution_authorized": False}


def validate_complexity(complexity):
    _mapping(complexity, "complexity")
    for comparison in ("parent", "baseline"):
        dimensions = _mapping(complexity.get(comparison), "complexity " + comparison)
        _need(set(dimensions) == set(COMPLEXITY_DIMENSIONS), "complexity must describe every semantic dimension")
        for key, item in dimensions.items():
            _mapping(item, key)
            _need(item.get("change") in CHANGES, "unknown complexity change for " + key)
            _text(item.get("reason"), key + " reasoning")
    return copy.deepcopy(complexity)


def complexity_relation(complexity, comparison="baseline"):
    validate_complexity(complexity)
    _need(comparison in ("parent", "baseline"), "unknown complexity comparison")
    changes = {item["change"] for item in complexity[comparison].values()}
    if "unknown" in changes:
        return "unknown"
    if "mixed" in changes or {"decreased", "increased"} <= changes:
        return "tradeoff"
    if "increased" in changes:
        return "more-complex"
    return "simpler" if "decreased" in changes else "equivalent"


def _upstream(value):
    refs = value.get("upstream_refs")
    _need(isinstance(refs, list), "upstream_refs must be explicit")
    if not refs:
        _text(value.get("no_upstream_reason"), "no relevant upstream alternative reason")
    ids = []
    for ref in refs:
        _mapping(ref, "upstream reference")
        ids.append(_name(ref.get("id"), "upstream reference id"))
        source = urlsplit(_text(ref.get("source_url"), "upstream source URL"))
        _need(source.scheme == "https" and source.netloc and not source.username and not source.password,
              "upstream source must be HTTPS without credentials")
        for key in ("revision", "relevance"):
            _text(ref.get(key), "upstream " + key)
        for key in ("base_commit", "commit", "tree"):
            _need(isinstance(ref.get(key), str) and OBJECT.fullmatch(ref[key]), "upstream " + key + " must be exact")
    _need(len(ids) == len(set(ids)), "duplicate upstream reference")


def validate_idea(idea):
    _mapping(idea, "idea")
    _name(idea.get("id"), "idea id")
    _need(idea.get("status") in {"proposed", "selected", "rejected", "completed", "blocked"}, "unknown idea status")
    _need(idea.get("change_type") in {"optimize", "simplify", "redesign", "repair"}, "unknown change type")
    _number(idea.get("priority"), "idea priority", integer=True)
    for key in ("bottleneck", "mechanism", "expected_benefit", "simpler_alternative", "falsifier"):
        _text(idea.get(key), key)
    _need(idea.get("mechanism_evidence_type") in {"counter_shift", "per_operation_cost", "lock_trace", "state_invariant", "reviewed_structure"}, "unknown mechanism evidence type")
    _paths(idea.get("affected_paths"), "affected paths")
    _strings(idea.get("required_evidence"), "evidence requirements")
    _upstream(idea)
    validate_complexity(idea.get("complexity"))
    for key in ("guest_attempts", "build_attempts"):
        _number(idea.get("estimated_cost", {}).get(key), "estimated " + key, integer=True)
    _text(idea.get("selection_reason"), "idea selection/learning rationale")
    _json(idea)
    return copy.deepcopy(idea)


def _value_policy(policy):
    _mapping(policy, "value_policy")
    for key in ("min_useful_effect", "equivalence_margin"):
        _number(policy.get(key), key, minimum=0, maximum=1)
    _need(type(policy.get("requires_upstream_comparison")) is bool, "upstream comparison requirement must be boolean")
    _text(policy.get("rationale"), "practical-value policy rationale")


def validate_line(line):
    _version(line)
    _name(line.get("line"), "line")
    if "contributor" in line:
        _name(line["contributor"], "contributor")
    _text(line.get("question"), "research question")
    _name(line.get("profile"), "profile")
    _need(line.get("status") in {"active", "paused", "retired"}, "unknown line status")
    for key in ("anchor_commit", "baseline_commit"):
        _need(isinstance(line.get(key), str) and OBJECT.fullmatch(line[key]), key + " must be exact")
    _value_policy(line.get("value_policy"))
    for key in ("guest_attempts", "build_attempts"):
        _number(line.get("resource_ceiling", {}).get(key), "line resource ceiling " + key, minimum=1, integer=True)
    _upstream(line)
    if line["upstream_refs"]:
        _need(line["value_policy"]["requires_upstream_comparison"], "relevant upstream alternatives require comparison")
    ideas = line.get("ideas")
    _need(isinstance(ideas, list), "line ideas must be a list")
    for idea in ideas:
        validate_idea(idea)
    _need(len({idea["id"] for idea in ideas}) == len(ideas), "duplicate idea id")
    if any(idea["upstream_refs"] for idea in ideas):
        _need(line["value_policy"]["requires_upstream_comparison"], "idea upstream alternatives require comparison")
    _json(line)
    return copy.deepcopy(line)


def line_contract(line, profile=None, root=ROOT):
    """Frozen scientific snapshot excludes mutable backlog and current baseline."""
    validate_line(line)
    profile = profile or load_profile(line["profile"], root)
    validate_profile(profile)
    _need(profile["id"] == line["profile"], "line profile mismatch")
    scientific = {"schema_version": 1, "line": line["line"], "profile": profile["id"],
                  "profile_version": profile["version"], "profile_sha256": digest(profile),
                  "anchor_commit": line["anchor_commit"], "value_policy": copy.deepcopy(line["value_policy"])}
    if "contributor" in line:
        scientific["contributor"] = line["contributor"]
    return {**scientific, "scientific_sha256": digest(scientific)}


def validate_contract(contract, root=ROOT):
    _version(contract)
    _name(contract.get("line"), "line")
    if "contributor" in contract:
        _name(contract["contributor"], "contributor")
    profile = load_profile(contract.get("profile"), root)
    _need(contract.get("profile_version") == profile["version"] and
          contract.get("profile_sha256") == digest(profile), "frozen profile identity changed")
    _need(isinstance(contract.get("anchor_commit"), str) and OBJECT.fullmatch(contract["anchor_commit"]), "contract anchor")
    _value_policy(contract.get("value_policy"))
    scientific = {key: value for key, value in contract.items() if key != "scientific_sha256"}
    _need(contract.get("scientific_sha256") == digest(scientific), "scientific contract hash mismatch")
    return copy.deepcopy(contract)


def line_spending(root, line_id):
    """Read existing budgets, retaining closed/failed campaign spending.

    Missing historical budgets are unknown, never zero. Open unused allocations
    are commitments. This function never stores a second total or resets counts.
    """
    _name(line_id, "line")
    root = Path(root)
    spent = {"guest_attempts": 0, "build_attempts": 0}
    committed = dict(spent)
    campaigns, unknown = [], []
    for path in sorted((root / "campaigns").glob("*/campaign.json")):
        record = read_json(path)
        if record.get("line") != line_id:
            continue
        budget_path = path.parent / "ledger/budget.json"
        name = path.parent.name
        if not budget_path.is_file():
            unknown.append(name + ": missing authoritative ledger/budget.json")
            continue
        try:
            _need(record.get("status") in {"open", "closed"}, "unknown campaign status")
            budget = read_json(budget_path)
            counts = {"guest_attempts": _number(budget.get("guests"), "latency guests", integer=True) +
                       _number(budget.get("probe_guests", 0), "probe guests", integer=True),
                      "build_attempts": _number(budget.get("builds"), "builds", integer=True)}
            reserve = {"guest_attempts": 0, "build_attempts": 0}
            if record.get("status") == "open":
                protocol = read_json(path.parent / "protocol.json")
                caps = protocol.get("budget", {})
                limits = {"guest_attempts": _number(caps.get("guest_attempts"), "guest allocation", integer=True) +
                          _number(caps.get("probe_guest_attempts", 0), "probe allocation", integer=True),
                          "build_attempts": _number(caps.get("build_attempts"), "build allocation", integer=True)}
                reserve = {key: max(0, limits[key] - counts[key]) for key in spent}
            for key in spent:
                spent[key] += counts[key]
                committed[key] += reserve[key]
            campaigns.append({"campaign": name, "status": record.get("status"), "spent": counts,
                              "committed": reserve, "source": str(budget_path.relative_to(root))})
        except ResearchError as exc:
            unknown.append(name + ": " + str(exc))
    return {"line": line_id, "spent": spent, "committed": committed, "campaigns": campaigns,
            "complete": not unknown, "unknown": unknown}


def line_budget(line, spending, requested=None, exclude_campaign=None):
    """Pure preflight; caller holds the framework allocation lock when reserving."""
    validate_line(line)
    _need(spending.get("line") == line["line"], "spending line mismatch")
    reasons = list(spending.get("unknown", []))
    if spending.get("complete") is not True:
        reasons.append("line spending is incomplete")
    reserved = copy.deepcopy(spending["committed"])
    if exclude_campaign is not None:
        matches = [row for row in spending["campaigns"] if row["campaign"] == exclude_campaign]
        _need(len(matches) == 1, "campaign allocation is missing or ambiguous")
        for key in reserved:
            reserved[key] -= matches[0]["committed"][key]
    remaining = {}
    for key in ("guest_attempts", "build_attempts"):
        spent = _number(spending["spent"].get(key), "line spent " + key, integer=True)
        _number(reserved[key], "line commitments " + key, integer=True)
        remaining[key] = max(0, line["resource_ceiling"][key] - spent - reserved[key])
        need = _number((requested or {}).get(key, 0), "requested " + key, integer=True)
        if spent + reserved[key] + need > line["resource_ceiling"][key]:
            reasons.append("line " + key + " ceiling exhausted")
    return {"ready": not reasons, "remaining": remaining, "spent": spending["spent"],
            "committed": reserved, "reasons": reasons}


def select_line(root=ROOT, line_id=None, *, contributor=None):
    """Rank only this contributor's priorities; never adopt unowned or foreign work."""
    _name(contributor or os.environ.get("SWAP_NEXT_CONTRIBUTOR"), "contributor")
    contributor = contributor or os.environ["SWAP_NEXT_CONTRIBUTOR"]
    root = Path(root)
    paths = ([root / "campaigns/lines" / (_name(line_id, "line") + ".json")] if line_id else
             sorted((root / "campaigns/lines").glob("*.json")))
    choices, blocked = [], []
    for path in paths:
        try:
            raw = read_json(path)
        except ResearchError as exc:
            if line_id:
                raise
            blocked.append({"line": path.stem, "reasons": ["unreadable agenda: " + str(exc)]})
            continue
        if not isinstance(raw, dict) or raw.get("contributor") != contributor:
            blocked.append({"line": path.stem, "reasons": ["owned by another contributor or unowned historical line"]})
            continue
        line = validate_line(raw)
        _need(line["line"] == path.stem, "line id differs from filename")
        profile = load_profile(line["profile"], root)
        if line["status"] != "active":
            blocked.append({"line": line["line"], "reasons": ["line is " + line["status"]]})
            continue
        spending = line_spending(root, line["line"])
        for idea in line["ideas"]:
            if idea["status"] != "proposed":
                continue
            budget = line_budget(line, spending, idea["estimated_cost"])
            reasons = list(budget["reasons"]) + list(profile["missing_capabilities"])
            if not profile["executable"]:
                reasons.append("profile is not executable")
            if idea["mechanism_evidence_type"] not in profile["mechanism_evidence"]:
                reasons.append("missing mechanism evidence capability: " + idea["mechanism_evidence_type"])
            # Match additions with the controller's same-directory rule.
            if any(path not in profile["allowed_modify"] and not any(
                    PurePosixPath(path).parent == PurePosixPath(pattern).parent and
                    fnmatch.fnmatchcase(PurePosixPath(path).name, PurePosixPath(pattern).name)
                    for pattern in profile["allowed_add"])
                    for path in idea["affected_paths"]):
                reasons.append("idea needs paths outside approved profile")
            item = {"line": line["line"], "idea": idea["id"], "priority": idea["priority"],
                    "reason": idea["selection_reason"], "budget": budget, "profile": profile["id"]}
            if reasons:
                blocked.append({**item, "reasons": list(dict.fromkeys(reasons))})
            else:
                choices.append(item)
    choices.sort(key=lambda row: (-row["priority"], row["line"], row["idea"]))
    return {"selected": choices[0] if choices else None, "alternatives": choices[1:],
            "blocked": blocked, "execution_authorized": False}


def validate_value_decision(decision, contract, expected_identity=None):
    """Validate assessment input: a research disposition is never promotion."""
    _version(decision)
    _value_policy(contract.get("value_policy"))
    scientific = {key: value for key, value in contract.items() if key != "scientific_sha256"}
    _need(contract.get("scientific_sha256") == digest(scientific), "frozen contract hash mismatch")
    identity = _mapping(decision.get("identity"), "value identity")
    for key in IDENTITY_FIELDS:
        value = identity.get(key)
        if key in ("evaluation_id", "evaluation_report"):
            (_path if key == "evaluation_report" else _text)(value, key)
        else:
            pattern = SHA256 if key == "protocol_sha256" else OBJECT
            _need(isinstance(value, str) and pattern.fullmatch(value), "invalid value identity " + key)
    _need(re.fullmatch(r"[a-zA-Z0-9-]{1,96}", identity["evaluation_id"]), "invalid evaluation id")
    _need(decision.get("scientific_sha256") == contract.get("scientific_sha256"),
          "value policy is not bound to frozen contract")
    if expected_identity is not None:
        for key in IDENTITY_FIELDS:
            _need(key in expected_identity and identity[key] == expected_identity[key],
                  "value evidence identity mismatch: " + key)
    _need(decision.get("scientific_result") in {"screen", "incomplete", "regression", "correctness-failure"},
          "unknown scientific result")
    _need(decision.get("review_status") in {"clear", "blocked", "pending"}, "unknown review status")
    validate_complexity(decision.get("complexity"))
    _paths(decision.get("evidence"), "value evidence")
    _text(decision.get("reason"), "value reasoning")
    _text(decision.get("learning_value"), "learning value")
    metrics = decision.get("performance")
    if decision["scientific_result"] in {"incomplete", "correctness-failure"} and metrics is None:
        metrics = {}
    else:
        _mapping(metrics, "performance")
    if metrics:
        for key in ("normalized_gain", "noise_relative"):
            _number(metrics.get(key), key, minimum=-1 if key == "normalized_gain" else 0)
        _need(type(metrics.get("scored_guards_pass")) is bool, "scored guard result must be boolean")
    else:
        _need(decision["scientific_result"] in {"incomplete", "correctness-failure"}, "screen requires measured performance")
    interval = metrics.get("gain_interval")
    if interval is not None:
        _need(isinstance(interval, list) and len(interval) == 2, "gain_interval must have two bounds")
        for value in interval:
            _number(value, "gain interval", minimum=-1)
        _need(interval[0] <= interval[1], "gain interval is reversed")
        _text(metrics.get("interval_method"), "interval method")
    upstream = _mapping(decision.get("upstream_comparison"), "upstream comparison")
    _need(upstream.get("status") in {"complete", "missing", "incomparable", "not-applicable"},
          "unknown upstream comparison status")
    _text(upstream.get("reason"), "upstream comparison reason")
    _paths(upstream.get("evidence"), "upstream evidence", nonempty=upstream["status"] == "complete")
    _paths(decision.get("advisory_flags", []), "advisory evidence", nonempty=False)
    _need(type(decision.get("frontier_eligible")) is bool, "frontier eligibility requires explicit judgment")
    _text(decision.get("frontier_reason"), "frontier reason")
    if complexity_relation(decision["complexity"]) in {"more-complex", "tradeoff"}:
        _text(decision.get("complexity_justification"), "added complexity justification")
    _json(decision)
    return copy.deepcopy(decision)


def assess_value(decision, contract, expected_identity=None):
    """Apply frozen practical thresholds, without inventing a complexity score.

    normalized_gain is the higher-is-better ratio minus one, matching the
    baseline/candidate latency ratio. Equivalence requires an interval wholly
    inside the predeclared margin; lack of significance is insufficient.
    """
    validate_value_decision(decision, contract, expected_identity)
    policy, metrics = contract["value_policy"], decision["performance"] or {}
    relation = complexity_relation(decision["complexity"])
    reasons, disposition = [], "exploratory"
    upstream_ok = decision["upstream_comparison"]["status"] == "complete" or (
        not policy["requires_upstream_comparison"] and decision["upstream_comparison"]["status"] == "not-applicable")
    if decision["review_status"] != "clear":
        disposition = "review-blocked"
        reasons.append("review is " + decision["review_status"])
    elif decision["scientific_result"] == "incomplete":
        reasons.append("scientific comparison is incomplete")
    elif decision["scientific_result"] in {"regression", "correctness-failure"} or not metrics.get("scored_guards_pass"):
        disposition = "rejected"
        reasons.append("scientific guard or correctness failure")
    elif not decision["frontier_eligible"]:
        disposition = "rejected"
        reasons.append("dominated by a simpler or better evidenced alternative")
    elif not upstream_ok:
        reasons.append("relevant upstream comparison is missing or incomparable")
    elif decision.get("advisory_flags"):
        disposition = "review-blocked"
        reasons.append("material advisory findings need a resolved review decision")
    elif relation == "unknown":
        reasons.append("complexity evidence is incomplete")
    elif (decision["identity"]["parent_commit"] != decision["identity"]["baseline_commit"] and
          complexity_relation(decision["complexity"], "parent") in {"more-complex", "tradeoff"}):
        reasons.append("inherited baseline benefit does not establish the child's marginal value; obtain a bound parent comparison")
    else:
        interval = metrics.get("gain_interval")
        margin = policy["equivalence_margin"]
        equivalent = interval is not None and interval[0] >= -margin and interval[1] <= margin
        useful = (metrics["normalized_gain"] >= policy["min_useful_effect"] and
                  metrics["normalized_gain"] > metrics["noise_relative"])
        if relation == "simpler" and equivalent:
            disposition = "simplification"
            reasons.append("simpler obligations with evidence inside frozen equivalence margin")
        elif useful:
            disposition = "worthwhile-to-confirm"
            reasons.append("screened benefit exceeds practical threshold and calibrated noise")
        elif relation in {"more-complex", "tradeoff"}:
            disposition = "rejected"
            reasons.append("benefit does not justify added complexity")
        else:
            reasons.append("retained for declared learning value; practical benefit remains unproven")
    return {"disposition": disposition, "reasons": reasons, "complexity_relation": relation,
            "parent_complexity_relation": complexity_relation(decision["complexity"], "parent"),
            "frontier_eligible": decision["frontier_eligible"], "identity": copy.deepcopy(decision["identity"]),
            "scientific_sha256": decision["scientific_sha256"], "performance_accepted": False,
            "auto_promote": False, "confirmation_required": disposition in {"worthwhile-to-confirm", "simplification"}}



def performance_from_report(report):
    """Extract facts from the trusted evaluator; never accept authored numbers."""
    status = report.get("status")
    if status == "CORRECTNESS_FAIL":
        return {"scientific_result": "correctness-failure", "performance": None}
    if status in {"INCOMPLETE", "INTERRUPTED", "BLOCKED"}:
        return {"scientific_result": "incomplete", "performance": None}
    _need(status in {"FAST_PASS", "REGRESSION", "NEEDS_REVIEW", "INCONCLUSIVE"},
          "unsupported evaluation result for value assessment")
    analysis = _mapping(report.get("analysis"), "evaluation analysis")
    score = _number(analysis.get("combined_score"), "evaluation score", minimum=0)
    _need(score > 0, "evaluation score must be positive")
    primary = _strings(analysis.get("primary"), "evaluation primary metrics")
    metrics = _mapping(analysis.get("metrics"), "evaluation metrics")
    noise = []
    guards = []
    for name, metric in metrics.items():
        _mapping(metric, "evaluation metric")
        if not metric.get("advisory"):
            _need(type(metric.get("guard_pass")) is bool, "scored guard result is missing")
            guards.append(metric["guard_pass"])
        if name in primary:
            _need(not metric.get("advisory"), "primary metric cannot be advisory")
            noise.append(_number(metric.get("noise_relative"), "calibrated noise"))
    _need(len(noise) == len(primary) and guards, "evaluation primary or guard evidence missing")
    performance = {"normalized_gain": score - 1, "noise_relative": max(noise),
                   "scored_guards_pass": all(guards)}
    interval = analysis.get("overall_ci95")
    if interval is not None:
        _need(isinstance(interval, list) and len(interval) == 2, "evaluation interval")
        performance["gain_interval"] = [_number(v, "evaluation interval", minimum=0) - 1 for v in interval]
        _need(interval[0] <= interval[1], "evaluation interval is reversed")
        performance["interval_method"] = "trusted evaluator overall_ci95"
    return {"scientific_result": "regression" if status == "REGRESSION" else "screen",
            "performance": performance}


def record_value(campaign_dir, candidate, decision, contract, expected_identity, root=ROOT):
    """Write-once candidates/<id>/value.json after checking retained evidence.

    The trusted caller reconciles expected_identity independently. This helper
    verifies the on-disk report and protocol binding and refuses overwrites.
    """
    _name(candidate, "candidate")
    root, campaign_dir = Path(root).resolve(), Path(campaign_dir).resolve()
    _need(campaign_dir.parent == root / "campaigns", "campaign directory outside repository")
    validate_contract(contract, root)
    frozen = read_json(campaign_dir / "research.json").get("line_contract")
    _need(frozen == contract, "value contract differs from frozen campaign research.json")
    assessment = assess_value(decision, contract, expected_identity)
    report_path = root / _path(expected_identity["evaluation_report"])
    _need(report_path.resolve().is_relative_to(campaign_dir), "evaluation path outside campaign")
    report = read_json(report_path)
    for key in ("candidate_commit", "candidate_tree"):
        _need(report.get(key) == expected_identity[key], "evaluation " + key + " mismatch")
    _need(report.get("id") == expected_identity["evaluation_id"] and report.get("candidate") == candidate,
          "evaluation identity mismatch")
    measured = performance_from_report(report)
    _need(all(decision.get(key) == value for key, value in measured.items()),
          "authored performance differs from trusted evaluation")
    _need(hashlib.sha256((campaign_dir / "protocol.json").read_bytes()).hexdigest() == expected_identity["protocol_sha256"],
          "protocol bytes mismatch")
    for value in decision["evidence"] + decision["upstream_comparison"]["evidence"] + decision.get("advisory_flags", []):
        path = root / value
        _need(path.resolve().is_relative_to(root) and path.is_file(), "missing evidence: " + value)
    target = campaign_dir / "candidates" / candidate / "value.json"
    _need(target.resolve().is_relative_to(campaign_dir), "value path escapes campaign")
    evidence_paths = list(dict.fromkeys(decision["evidence"] + decision["upstream_comparison"]["evidence"] + decision.get("advisory_flags", [])))
    record = {"schema_version": 1, "decision": copy.deepcopy(decision), "assessment": assessment,
              "provenance": {"evaluation_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
                             "evidence_sha256": {path: hashlib.sha256((root / path).read_bytes()).hexdigest()
                                                for path in evidence_paths}}}
    target.parent.mkdir(parents=True, exist_ok=True)
    runtime = campaign_dir / "runs"
    runtime.mkdir(exist_ok=True)
    with (runtime / ("value-" + candidate + ".lock")).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if target.exists():
            _need(read_json(target) == record, "value record exists; preserve it and append a reviewed revision")
            return record
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=target.parent, prefix=".value-", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(json.dumps(record, indent=2, allow_nan=False) + chr(10))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    commands = parser.add_subparsers(dest="action", required=True)
    p = commands.add_parser("validate")
    p.add_argument("line_file", type=Path)
    p = commands.add_parser("select")
    p.add_argument("--line")
    p.add_argument("--contributor", default=os.environ.get("SWAP_NEXT_CONTRIBUTOR"))
    p = commands.add_parser("profile")
    p.add_argument("name")
    p.add_argument("--protocol", type=Path)
    p = commands.add_parser("value")
    p.add_argument("decision", type=Path)
    p.add_argument("contract", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.action == "validate":
            result = line_contract(validate_line(read_json(args.line_file)), root=args.root)
        elif args.action == "select":
            result = select_line(args.root, args.line, contributor=args.contributor)
        elif args.action == "profile":
            result = capability_readout(load_profile(args.name, args.root),
                read_json(args.protocol) if args.protocol else None, root=args.root)
        else:
            result = assess_value(read_json(args.decision), validate_contract(read_json(args.contract), args.root))
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except ResearchError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
