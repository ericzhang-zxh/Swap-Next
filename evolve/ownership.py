# SPDX-License-Identifier: GPL-2.0-only
"""Contributor routing for cooperative agents sharing a repository.

This is a workflow boundary, not authentication against users with filesystem
write access. Identity must come from the caller, never the target campaign.
"""
import json
import os
from pathlib import Path
import re

NAME = re.compile(r"[a-z][a-z0-9-]{0,47}")


def contributor(value=None):
    value = value if value is not None else os.environ.get("SWAP_NEXT_CONTRIBUTOR")
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise ValueError("Set --contributor or SWAP_NEXT_CONTRIBUTOR to your own stable contributor ID")
    return value


def owner(root, campaign):
    if not isinstance(campaign, str) or not NAME.fullmatch(campaign):
        raise ValueError("invalid ownership campaign")
    directory = Path(root) / "campaigns" / campaign
    path = directory / "owner.json"
    if directory.is_symlink() or path.is_symlink():
        raise ValueError("ownership must not traverse a symlink")
    if not path.exists():
        return None
    record = json.loads(path.read_text())
    if not isinstance(record, dict) or record.get("schema_version") != 1 or record.get("campaign") != campaign:
        raise ValueError("campaign ownership identity mismatch")
    if not isinstance(record.get("contributor"), str) or not NAME.fullmatch(record["contributor"]):
        raise ValueError("campaign ownership is missing a valid contributor")
    return record["contributor"]


def require(root, campaign, actor=None, *, allow_legacy=False):
    expected = owner(root, campaign)
    if expected is None:
        if allow_legacy:
            return None
        raise ValueError("Campaign has no contributor ownership; do not automatically adopt historical work")
    actual = contributor(actor)
    if actual != expected:
        raise ValueError("Campaign belongs to contributor " + expected + "; caller " + actual + " cannot continue it")
    return expected


def claim(root, campaign, actor):
    """Create ownership only for fresh preparation; caller holds its session lock."""
    actor = contributor(actor)
    if owner(root, campaign) is not None:
        return require(root, campaign, actor)
    directory = Path(root) / "campaigns" / campaign
    evidence = [directory / "campaign.json", directory / "research.json"]
    for suffix in ("ledger", "candidates", "runs", "patches", "archive", "report"):
        evidence += [path for path in (directory / suffix).rglob("*")
                     if path.is_file() and path != directory / "ledger/.session.lock"]
    if any(path.exists() for path in evidence):
        raise ValueError("Existing unowned work needs explicit provenance reconciliation; automatic adoption is forbidden")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "owner.json"
    record = {"schema_version": 1, "campaign": campaign, "contributor": actor}
    try:
        with path.open("x") as stream:
            stream.write(json.dumps(record, indent=2) + "\n")
    except FileExistsError:
        return require(root, campaign, actor)
    return actor
