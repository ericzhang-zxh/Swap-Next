# SPDX-License-Identifier: GPL-2.0-only
"""Immutable correctness reviews, independent of measurement and candidate closure.

``record(project, campaign, payload)`` appends a review; ``list_reviews`` verifies
its bytes and cited evidence; ``blockers(project, campaign, candidate_record)``
is a read-only gate for execution, sampling and advancement. Callers executing
code must supply its actual ``candidate_commit`` and ``source_tree``.

A veto introduces named correctness findings. A pass clears nothing. A resolve
names existing ``campaign/review/finding`` references and clears only those
findings for its exact reviewed commit AND tree. Descendants conservatively
inherit findings, including across campaign baselines, until reviewed on their
own exact identity. Review records never rewrite measurements or population
history. These are trusted reviewer dispositions, not proof of runtime safety.
"""
from contextlib import contextmanager
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import time

NAME = re.compile(r"[a-z][a-z0-9-]{0,95}")
OBJECT = re.compile(r"[0-9a-f]{40}")
SHA = re.compile(r"[0-9a-f]{64}")
FIELDS = {"schema_version", "id", "campaign", "candidate", "candidate_commit",
          "source_tree", "reviewer", "disposition", "summary", "findings", "resolves", "evidence"}


class ReviewError(ValueError):
    pass


def _require(condition, message):
    if not condition:
        raise ReviewError(message)


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _hash(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _name(value, field):
    _require(isinstance(value, str) and NAME.fullmatch(value), "invalid review " + field)
    return value


def _directory(project, campaign):
    path = Path(project).resolve() / "campaigns" / _name(campaign, "campaign")
    _require(path.is_dir() and path.resolve().is_relative_to(Path(project).resolve()),
             "review campaign is missing or outside project")
    return path


def _read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ReviewError("cannot read review input " + path.name) from exc


def _evidence(project, evidence):
    _require(isinstance(evidence, list) and evidence, "review needs hashed evidence")
    seen = set()
    root = Path(project).resolve()
    for item in evidence:
        _require(isinstance(item, dict) and set(item) == {"path", "sha256"}, "invalid review evidence")
        name, sha = item["path"], item["sha256"]
        _require(isinstance(name, str) and name and not Path(name).is_absolute()
                 and ".." not in Path(name).parts and name not in seen, "evidence must be unique project-relative paths")
        path = root / name
        _require(path.is_file() and path.resolve().is_relative_to(root), "review evidence missing or outside project: " + name)
        _require(isinstance(sha, str) and SHA.fullmatch(sha)
                 and hashlib.sha256(path.read_bytes()).hexdigest() == sha, "review evidence hash mismatch: " + name)
        seen.add(name)


def _payload(project, campaign, value):
    _require(isinstance(value, dict) and set(value) == FIELDS, "review payload fields do not match schema")
    _require(value["schema_version"] == 1 and value["campaign"] == campaign, "review schema or campaign mismatch")
    for field in ("id", "candidate"):
        _name(value[field], field)
    for field in ("candidate_commit", "source_tree"):
        _require(isinstance(value[field], str) and OBJECT.fullmatch(value[field]), "review requires exact " + field)
    for field in ("reviewer", "summary"):
        _require(isinstance(value[field], str) and value[field].strip(), "review needs " + field)
    findings, resolves = value["findings"], value["resolves"]
    _require(isinstance(findings, list) and isinstance(resolves, list), "review findings and resolves must be lists")
    ids = set()
    for item in findings:
        _require(isinstance(item, dict) and set(item) == {"id", "summary"}, "invalid correctness finding")
        ident = _name(item["id"], "finding ID")
        _require(ident not in ids and isinstance(item["summary"], str) and item["summary"].strip(), "duplicate or empty correctness finding")
        ids.add(ident)
    _require(all(isinstance(ref, str) and len(ref.split("/")) == 3
                 and all(NAME.fullmatch(part) for part in ref.split("/")) for ref in resolves), "invalid finding reference")
    _require(len(set(resolves)) == len(resolves), "duplicate finding resolution")
    disposition = value["disposition"]
    _require((disposition == "veto" and findings and not resolves)
             or (disposition == "pass" and not findings and not resolves)
             or (disposition == "resolve" and resolves and not findings), "invalid review disposition; a pass cannot resolve findings")
    _evidence(project, value["evidence"])
    return copy.deepcopy(value)


def list_reviews(project, campaign):
    """Read and verify recorded reviews, including evidence hashes; never writes."""
    directory = _directory(project, campaign) / "reviews"
    records = []
    for path in sorted(directory.glob("*.json")):
        _require(path.resolve().is_relative_to(Path(project).resolve()), "review path outside project")
        value = _read(path)
        _require(isinstance(value, dict), "invalid review record")
        body = {key: item for key, item in value.items() if key != "record_sha256"}
        _require(value.get("record_sha256") == _hash(body), "review record hash mismatch: " + path.name)
        _require(set(body) == FIELDS | {"recorded_unix"}, "invalid stored review fields")
        payload = {key: body[key] for key in FIELDS}
        _payload(project, campaign, payload)
        _require(payload["id"] == path.stem, "review ID does not match filename")
        records.append(value)
    return records


def _all_reviews(project):
    records = []
    for path in sorted((Path(project) / "campaigns").glob("*/reviews")):
        if path.is_dir():
            records.extend(list_reviews(project, path.parent.name))
    return records


def _candidate(project, campaign, name):
    directory = _directory(project, campaign)
    record = {}
    archive = directory / "archive/population.json"
    if archive.is_file():
        state = _read(archive)
        _require(isinstance(state, dict) and isinstance(state.get("entries"), dict), "invalid review population input")
        entry = state["entries"].get(name, {})
        _require(isinstance(entry, dict), "invalid review population entry")
        record.update(entry)
    path = directory / "candidates" / (_name(name, "candidate") + ".json")
    if path.is_file():
        candidate = _read(path)
        _require(isinstance(candidate, dict) and candidate.get("id") == name, "invalid review candidate input")
        record.update(candidate)
    return record


def _lineage(project, campaign, candidate_record):
    nodes, seen = [], set()
    current = dict(candidate_record)
    while True:
        ident = current.get("id", current.get("candidate"))
        key = campaign, ident
        _require(key not in seen, "review lineage cycle")
        seen.add(key)
        known = _candidate(project, campaign, ident) if ident else {}
        known.update(current)
        node = dict(known, campaign=campaign, id=ident)
        nodes.append(node)
        parent = known.get("parent_candidate")
        if parent:
            current = _candidate(project, campaign, parent)
            _require(current, "review parent identity is unavailable: " + parent)
            expected = known.get("parent_commit", known.get("parent"))
            if current.get("candidate_commit") and expected:
                _require(current["candidate_commit"] == expected, "review parent commit mismatch")
            if expected:
                current["candidate_commit"] = expected
            continue
        metadata = _directory(project, campaign) / "campaign.json"
        metadata = _read(metadata) if metadata.is_file() else {}
        _require(isinstance(metadata, dict), "invalid review campaign input")
        origin = metadata.get("baseline_from")
        if not origin:
            break
        _require(isinstance(origin, dict) and all(key in origin for key in ("campaign", "candidate", "commit")),
                 "invalid review inherited baseline input")
        campaign = origin["campaign"]
        current = _candidate(project, campaign, origin["candidate"])
        _require(current, "review inherited baseline identity is unavailable")
        _require(not current.get("candidate_commit") or current["candidate_commit"] == origin["commit"],
                 "review inherited baseline commit mismatch")
        current["candidate_commit"] = origin["commit"]
    return nodes


def _applicable(project, campaign, candidate_record, records):
    nodes = _lineage(project, campaign, candidate_record)
    identities = {(node["campaign"], node["id"]) for node in nodes if node["id"]}
    trees = {node.get("source_tree", node.get("candidate_tree")) for node in nodes} - {None}
    findings = []
    for review in records:
        if review["disposition"] != "veto":
            continue
        baseline_commit_match = any(node.get("id") is None and node.get("candidate_commit") == review["candidate_commit"]
                                    for node in nodes)
        if (review["campaign"], review["candidate"]) not in identities and review["source_tree"] not in trees and not baseline_commit_match:
            continue
        for finding in review["findings"]:
            findings.append({"kind": "correctness_review", "finding": "/".join((review["campaign"], review["id"], finding["id"])),
                             "summary": finding["summary"], "review_candidate": review["candidate"],
                             "review_commit": review["candidate_commit"], "review_tree": review["source_tree"],
                             "inherited": (review["campaign"], review["candidate"]) != (campaign, nodes[0]["id"])})
    return nodes[0], findings


def blockers(project, campaign, candidate_record):
    """Return structured veto/integrity blockers for this exact candidate and ancestry.

    Missing/mismatched review inputs fail closed. No recorded reviews preserves
    legacy behavior. A changed commit or unrelated pass never erases a finding.
    """
    try:
        records = _all_reviews(project)
        if not records:
            return []
        target, findings = _applicable(project, campaign, candidate_record, records)
        commit = target.get("candidate_commit", target.get("source_commit"))
        tree = target.get("source_tree", target.get("candidate_tree"))
        # An inherited baseline is the very same source revision, not a changed
        # descendant. Its source review can establish the missing historical tree.
        if tree is None and target.get("id") is None:
            trees = {review["source_tree"] for review in records if review["candidate_commit"] == commit}
            if len(trees) == 1:
                tree = next(iter(trees))
        resolved = {ref for review in records if review["disposition"] == "resolve"
                    and review["candidate_commit"] == commit and review["source_tree"] == tree
                    for ref in review["resolves"]}
        return [finding for finding in findings if finding["finding"] not in resolved]
    except (ReviewError, OSError, ValueError, KeyError, TypeError) as exc:
        return [{"kind": "review_integrity", "summary": str(exc)}]


@contextmanager
def _lock(directory):
    runtime = directory / "runs"
    _require(runtime.resolve().is_relative_to(directory.resolve()), "review runtime path outside campaign")
    runtime.mkdir(parents=True, exist_ok=True)
    with (runtime / "reviews.lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def record(project, campaign, payload):
    """Append an immutable review (idempotent for identical payloads).

    CLI callers also verify commit/tree identity against the Linux object store.
    The API verifies known archive identity, evidence hashes and explicit finding
    ancestry. It may append a review after execution closes; frozen inputs and
    old candidate/review/measurement files are never modified.
    """
    directory = _directory(project, campaign)
    payload = _payload(project, campaign, payload)
    with _lock(directory):
        records = _all_reviews(project)
        existing = next((item for item in records if item["campaign"] == campaign and item["id"] == payload["id"]), None)
        if existing:
            _require({key: existing[key] for key in FIELDS} == payload, "immutable review ID already exists")
            return existing
        candidate = _candidate(project, campaign, payload["candidate"])
        _require(candidate, "review candidate is unknown")
        for key in ("candidate_commit", "source_tree"):
            _require(not candidate.get(key) or candidate[key] == payload[key], "review " + key + " differs from archived candidate")
        candidate.update(id=payload["candidate"], candidate_commit=payload["candidate_commit"], source_tree=payload["source_tree"])
        if payload["disposition"] == "resolve":
            _, findings = _applicable(project, campaign, candidate, records)
            relevant = {finding["finding"] for finding in findings}
            _require(set(payload["resolves"]) <= relevant, "resolution must name existing applicable correctness findings")
        body = dict(payload, recorded_unix=time.time())
        saved = dict(body, record_sha256=_hash(body))
        path = directory / "reviews" / (payload["id"] + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        _require(path.resolve().is_relative_to(Path(project).resolve()), "review output outside project")
        temporary = path.with_name("." + path.name + ".tmp")
        with temporary.open("w") as stream:
            stream.write(json.dumps(saved, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        return saved
