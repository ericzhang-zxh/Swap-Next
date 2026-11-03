# SPDX-License-Identifier: GPL-2.0-only
"""Read-only validation of retained practical-value decisions.

The original evaluator report is the trusted measurement snapshot. Its hashes,
source identity and derived facts are checked here; raw guests are not replayed.
Population and baseline policy remain the caller's responsibility.
"""
import copy
import hashlib
from pathlib import Path

try:
    from . import research
except ImportError:
    import research


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _file(root, reference):
    research._path(reference)
    path = root
    for part in reference.split("/"):
        path = path / part
        _need(not path.is_symlink(), "value evidence uses a symlink: " + reference)
    _need(path.is_file() and path.resolve().is_relative_to(root),
          "missing value evidence: " + reference)
    return path


def _sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(root, campaign, candidate, expected):
    """Return verified assessment, decision and provenance without changing files.

    ``expected`` is a caller-supplied subset of research.IDENTITY_FIELDS. Missing,
    mismatched or corrupt retained inputs raise ValueError. A verified pending,
    rejected or exploratory disposition remains that disposition.
    """
    try:
        root = Path(root).resolve()
        research._name(campaign, "campaign")
        research._name(candidate, "candidate")
        _need(isinstance(expected, dict) and set(expected) <= set(research.IDENTITY_FIELDS),
              "expected value identity must contain only known identity fields")
        prefix = "campaigns/" + campaign
        frozen = research.read_json(_file(root, prefix + "/research.json"))
        contract = research.validate_contract(frozen["line_contract"], root)
        # validate_contract validates the trusted profile; require its full path
        # to remain inside this project rather than following parent symlinks.
        _file(root, "evolve/profiles/" + contract["profile"] + ".json")
        record = research.read_json(_file(root, prefix + "/candidates/" + candidate + "/value.json"))
        research._version(record)
        _need(set(record) == {"schema_version", "decision", "assessment", "provenance"},
              "invalid retained value record fields")
        decision, provenance = record["decision"], record["provenance"]
        fresh = research.assess_value(decision, contract)
        identity = decision["identity"]
        for key, value in expected.items():
            _need(identity[key] == value, "retained value identity mismatch: " + key)
        _need(record["assessment"] == fresh, "retained value assessment differs from fresh assessment")
        _need(isinstance(provenance, dict) and set(provenance) == {"evaluation_sha256", "evidence_sha256"},
              "invalid retained value provenance")
        protocol_path = _file(root, prefix + "/protocol.json")
        _need(_sha(protocol_path) == identity["protocol_sha256"], "retained value protocol bytes mismatch")
        report_path = _file(root, identity["evaluation_report"])
        _need(report_path.is_relative_to(root / prefix), "retained evaluation path outside campaign")
        _need(_sha(report_path) == provenance["evaluation_sha256"], "retained evaluation hash mismatch")
        report = research.read_json(report_path)
        for key in ("candidate_commit", "candidate_tree"):
            _need(report.get(key) == identity[key], "retained evaluation source mismatch: " + key)
        _need(report.get("id") == identity["evaluation_id"] and report.get("candidate") == candidate,
              "retained evaluation identity mismatch")
        measured = research.performance_from_report(report)
        _need(all(decision.get(key) == value for key, value in measured.items()),
              "retained authored performance differs from trusted evaluation")
        declared = set(decision["evidence"] + decision["upstream_comparison"]["evidence"] +
                       decision.get("advisory_flags", []))
        hashes = provenance["evidence_sha256"]
        _need(isinstance(hashes, dict) and set(hashes) == declared,
              "retained evidence hashes do not cover exactly the declared evidence")
        for reference, expected_hash in hashes.items():
            _need(_sha(_file(root, reference)) == expected_hash,
                  "retained evidence hash mismatch: " + reference)
        return copy.deepcopy({"assessment": fresh, "decision": decision, "provenance": provenance})
    except (OSError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError("invalid retained value evidence: " + str(exc)) from exc
