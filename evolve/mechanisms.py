# SPDX-License-Identifier: GPL-2.0-only
"""Bound structural mechanism evidence for hypotheses with unchanged counters."""
import hashlib
import json
from pathlib import Path
import re

import reviews

KINDS = {"counter_shift", "reviewed_structure"}


def declaration(value, protocol):
    if not isinstance(value, dict) or set(value) != {"kind", "claim", "falsifier"}:
        raise ValueError("structural declaration needs kind, claim and falsifier")
    if value["kind"] != "reviewed_structure":
        raise ValueError("unsupported mechanism evidence kind")
    if value["kind"] not in protocol.get("mechanism_evidence_types", ["counter_shift"]):
        raise ValueError("protocol does not admit reviewed structural evidence")
    if not all(isinstance(value[k], str) and 10 <= len(value[k].strip()) <= 2000
               for k in ("claim", "falsifier")):
        raise ValueError("structural claim and falsifier must be 10..2000 characters")
    return value


def validate(root, protocol, record, commit, tree):
    """A reviewed argument supplements, never replaces, correctness/measurement."""
    value = record.get("mechanism")
    if not isinstance(value, dict):
        return None
    declaration(value, protocol)
    root = Path(root).resolve()
    campaign = protocol["campaign"]
    name = record["id"]
    if not all(isinstance(v, str) and re.fullmatch(r"[a-z][a-z0-9-]{0,47}", v)
               for v in (campaign, name)):
        raise ValueError("invalid mechanism subject")
    directory = root / "campaigns" / campaign
    source = directory / "candidates" / name / "mechanism.json"
    if source.is_symlink() or not source.resolve().is_relative_to(directory.resolve()):
        raise ValueError("mechanism evidence escapes campaign")
    proof = json.loads(source.read_text())
    expected = {"schema_version": 1, **value, "candidate_commit": commit, "source_tree": tree,
                "protocol_sha256": hashlib.sha256((directory / "protocol.json").read_bytes()).hexdigest()}
    if any(proof.get(k) != v for k, v in expected.items()):
        raise ValueError("structural evidence identity or declaration mismatch")
    if reviews.blockers(root, campaign, dict(record, candidate_commit=commit, source_tree=tree)):
        raise ValueError("structural evidence has unresolved correctness review")
    matches = [r for r in reviews.list_reviews(root, campaign) if r["id"] == proof.get("review_id")]
    if len(matches) != 1:
        raise ValueError("missing structural review")
    review = matches[0]
    if (review["candidate"] != name or review["candidate_commit"] != commit or
            review["source_tree"] != tree or review["disposition"] not in {"pass", "resolve"} or
            review["record_sha256"] != proof.get("review_record_sha256")):
        raise ValueError("structural review is not a clear exact-tree disposition")
    return {**expected, "review_id": review["id"], "review_record_sha256": review["record_sha256"],
            "evidence": review["evidence"], "performance_accepted": False}
