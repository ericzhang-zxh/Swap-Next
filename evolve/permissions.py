# SPDX-License-Identifier: GPL-2.0-only
"""Single-run owner authorization receipts for non-default slow measurements."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
from pathlib import Path
import re
import time

NAME = re.compile(r"[a-z][a-z0-9-]{0,47}")


def validate(root, protocol, approval_id, action, commit, tree, fingerprint, execution_id):
    if not isinstance(approval_id, str) or not NAME.fullmatch(approval_id):
        raise ValueError("slow requires an explicit owner approval ID")
    campaign = protocol["campaign"]
    if not NAME.fullmatch(campaign):
        raise ValueError("invalid approval campaign")
    root = Path(root).resolve()
    directory = root / "campaigns" / campaign
    path = directory / "approvals" / (approval_id + ".json")
    if path.is_symlink() or path.parent.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
        raise ValueError("approval path escapes campaign")
    approval = json.loads(path.read_text())
    expected = {"schema_version": 1, "id": approval_id, "campaign": campaign, "action": action,
                "tier": "slow", "candidate_commit": commit, "candidate_tree": tree,
                "protocol_sha256": hashlib.sha256((directory / "protocol.json").read_bytes()).hexdigest(),
                "fingerprint": fingerprint, "max_executions": 1}
    if any(approval.get(k) != v for k, v in expected.items()):
        raise ValueError("owner approval does not match this exact slow measurement")
    if not isinstance(approval.get("owner_authorization"), str) or not approval["owner_authorization"].strip():
        raise ValueError("approval must cite the owner's explicit authorization")
    expires = approval.get("expires_unix")
    if type(expires) not in (int, float) or not math.isfinite(expires) or expires <= time.time():
        raise ValueError("owner approval has expired")
    receipt = directory / "ledger/approval-uses" / (approval_id + ".json")
    binding = {"approval_id": approval_id, "approval_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
               "execution_id": execution_id}
    if receipt.exists() and json.loads(receipt.read_text()) != binding:
        raise ValueError("owner approval was already consumed by another execution")
    return {"path": str(path.relative_to(root)), "receipt": str(receipt.relative_to(root)),
            "binding": binding, "expires_unix": expires}


def consume(root, permit):
    """Consume immediately before the first counted build or guest reservation."""
    root = Path(root).resolve()
    source = root / permit["path"]
    receipt = root / permit["receipt"]
    if (hashlib.sha256(source.read_bytes()).hexdigest() != permit["binding"]["approval_sha256"] or
            time.time() >= permit["expires_unix"]):
        raise ValueError("owner approval changed or expired before execution")
    receipt.parent.mkdir(parents=True, exist_ok=True)
    with receipt.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if receipt.exists():
            if json.loads(receipt.read_text()) != permit["binding"]:
                raise ValueError("owner approval was consumed by another execution")
            return
        temporary = receipt.with_suffix(".tmp")
        temporary.write_text(json.dumps(permit["binding"], indent=2) + "\n")
        temporary.replace(receipt)
