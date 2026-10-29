#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Void one STOP-blocked or pre-launch-refused calibration so the protocol can retry.

The calibration fingerprint hashes the workflow. This command does not change
that file or any measured-evidence parser. It appends a ledger receipt and
clears the attempt's execution_started flag, which is the slot the existing
retry gate already consults. Guests, budget counters and run results stay.
A noisy, failed, invalid or scored calibration cannot be voided, and each
attempt can be voided only once.

A host-resource void is allowed only when every guest that did not complete
was refused before QEMU. The proof is that guest's run log: one preflight
line from run.py, and no guest directory from a launch that got past it.
"""
import argparse
from contextlib import contextmanager
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid

import campaign_store as store

STOP_REASONS = {"STOP", "BLOCKED: campaign: STOP"}
PREFLIGHT_LINE = re.compile(r"need (?:\d+ MiB available host RAM|24 GiB free disk)\Z")
BOOT_MARKER = "qemu-system-x86_64"
ATTEMPT_ID = re.compile(r"[0-9a-f]{8,64}")
TEXT_LIMIT = 4096
REASON_LIMIT = 2000


class VoidError(ValueError):
    pass


def clean_reason(reason):
    if not isinstance(reason, str) or not reason.strip() or reason != reason.strip():
        raise VoidError("reason must be non-empty written text")
    if len(reason) > REASON_LIMIT or any(ord(char) < 32 for char in reason):
        raise VoidError("reason must be a single line of at most 2000 characters")
    return reason


def _relative(path):
    try:
        return str(path.resolve().relative_to(store.PROJECT.resolve()))
    except ValueError:
        raise VoidError("STOP path escapes the project") from None


def stop_files(campaign):
    """Snapshot campaign and global STOP files. Absence is recorded, not invented."""
    evidence = []
    for role, path in (("campaign", store.campaign_dir(campaign) / "STOP"),
                       ("global", store.GLOBAL_STOP)):
        item = {"role": role, "path": _relative(path), "exists": path.is_file()}
        if path.is_file():
            data = path.read_bytes()
            item.update(sha256=hashlib.sha256(data).hexdigest(), size=len(data))
            if len(data) <= TEXT_LIMIT and b"\0" not in data:
                item["text"] = data.decode("utf-8", errors="replace")
            else:
                item["text"] = None
        evidence.append(item)
    return evidence


def _save(path, value):
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w") as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


@contextmanager
def _lock(directory):
    with (directory / ".lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                raise
            raise VoidError("ledger lock held; refusing to void during another workflow write") from exc
        yield


def resolve_attempt(ledger, token):
    if not isinstance(token, str) or not ATTEMPT_ID.fullmatch(token):
        raise VoidError("attempt id must be 8 to 64 hexadecimal characters")
    rows = [row for row in ledger
            if isinstance(row, dict) and isinstance(row.get("id"), str)
            and (row["id"] == token or row["id"].startswith(token))]
    exact = [row for row in rows if row["id"] == token]
    chosen = exact or rows
    if not chosen:
        raise VoidError("calibration attempt not found")
    if len(chosen) != 1:
        raise VoidError("attempt id is ambiguous")
    return chosen[0]


def _completed(run):
    return run.get("status") == "PASS" and run.get("run_valid") is not False


def _component(value):
    return isinstance(value, str) and value not in ("", ".", "..") and "/" not in value and "\\" not in value


def _preflight_proof(campaign, attempt_id, run):
    """Evidence that this guest was refused before QEMU, or a refusal string."""
    run_id = run["id"]
    if run.get("metrics") is not None or run.get("result") or run.get("result_sha256"):
        return "guest has a measurement result: " + run_id
    if not _component(attempt_id) or not _component(run_id):
        return "guest id is not a single path component: " + str(run_id)
    root = store.campaign_dir(campaign)
    guest_dir = root / "runs/guests" / run_id
    log_path = root / "runs/evaluations" / attempt_id / (run_id + ".log")
    if guest_dir.exists():
        return "guest run directory exists; launch setup began: " + run_id
    if not log_path.is_file():
        return "missing preflight log for " + run_id
    if log_path.stat().st_size > TEXT_LIMIT:
        return "preflight log is too large to be a pre-launch refusal: " + run_id
    data = log_path.read_bytes()
    if b"\0" in data:
        return "preflight log is not text: " + run_id
    text = data.decode("utf-8", errors="replace")
    if BOOT_MARKER in text:
        return "guest log shows a boot: " + run_id
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != 1 or not PREFLIGHT_LINE.fullmatch(lines[0]):
        return "guest log is not a single host-resource preflight refusal: " + run_id
    return {"run_id": run_id, "log": _relative(log_path), "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data), "message": lines[0], "guest_directory": False}


def _host_resource_refusal(campaign, row):
    """Proofs for every unfinished guest, or a string explaining the refusal."""
    runs = row.get("runs", [])
    pending = [run for run in runs if not _completed(run)]
    if not pending:
        return "attempt did not end because of STOP or a proven pre-launch host-resource refusal"
    proofs = []
    for run in pending:
        proof = _preflight_proof(campaign, row["id"], run)
        if isinstance(proof, str):
            return proof
        proofs.append(proof)
    return proofs


def refusal(row, campaign):
    """Return why this calibration cannot be voided, or None when it can."""
    if row.get("action") != "calibrate":
        return "not a calibration attempt"
    analysis = row.get("analysis")
    if row.get("status") == "CALIBRATION_NOISY" or (isinstance(analysis, dict) and analysis.get("status") == "CALIBRATION_NOISY"):
        return "noisy calibration cannot be voided"
    if row.get("status") not in ("BLOCKED", "INCOMPLETE"):
        return "only a STOP-blocked incomplete calibration can be voided"
    if analysis is not None:
        return "scored calibration cannot be voided"
    runs = row.get("runs", [])
    if not isinstance(runs, list):
        return "guest evidence is not a list"
    for run in runs:
        if not isinstance(run, dict) or not isinstance(run.get("id"), str) or not run["id"]:
            return "guest id missing"
        if run.get("status") in ("FAIL", "INVALID") or run.get("run_valid") is False:
            return "guest FAIL or run_invalid cannot be voided: " + run["id"]
    if not isinstance(row.get("tier"), str) or row["tier"] not in ("probe", "fast", "slow"):
        return "calibration tier is missing"
    if row.get("reason") in STOP_REASONS:
        return None
    proved = _host_resource_refusal(campaign, row)
    return proved if isinstance(proved, str) else None


def _already_voided(ledger, attempt_id):
    return any(isinstance(row, dict) and row.get("action") == "void-calibration" and row.get("attempt_id") == attempt_id
               for row in ledger)


def void_calibration(campaign, attempt, reason):
    """Append one void receipt and release that attempt's calibration slot."""
    reason = clean_reason(reason)
    if not isinstance(attempt, str) or not ATTEMPT_ID.fullmatch(attempt):
        raise VoidError("attempt id must be 8 to 64 hexadecimal characters")
    record = store.require_open(campaign)
    machine = store.current_machine()
    if record["machine"] != machine:
        raise VoidError(f"campaign {campaign} belongs to {record['machine']}, not {machine}")
    store.require_claim(campaign)
    directory = store.campaign_dir(campaign) / "ledger"
    path = directory / "ledger.json"
    if not path.is_file():
        raise VoidError("no calibration ledger")
    with _lock(directory):
        try:
            ledger = json.loads(path.read_text())
        except ValueError as exc:
            raise VoidError("ledger is unreadable") from exc
        if not isinstance(ledger, list):
            raise VoidError("ledger is not a list")
        row = resolve_attempt(ledger, attempt)
        if row.get("void_receipt") or _already_voided(ledger, row["id"]):
            raise VoidError("calibration attempt already voided")
        why = refusal(row, campaign)
        if why:
            raise VoidError(why)
        proved = None if row.get("reason") in STOP_REASONS else _host_resource_refusal(campaign, row)
        if isinstance(proved, str):
            raise VoidError(proved)
        proofs = {item["run_id"]: item for item in proved or []}
        guests = []
        for run in row.get("runs", []):
            guest = {"id": run["id"], "status": run.get("status")}
            if "run_valid" in run:
                guest["run_valid"] = run["run_valid"]
            if run["id"] in proofs:
                guest["preflight"] = proofs[run["id"]]
            guests.append(guest)
        receipt = {
            "schema_version": 1,
            "id": uuid.uuid4().hex,
            "action": "void-calibration",
            "tier": row["tier"],
            "status": "VOIDED",
            "attempt_id": row["id"],
            "reason": reason,
            "attempt_status": row["status"],
            "attempt_reason": row.get("reason"),
            "stop_files": stop_files(campaign),
            "preflight": [guest["preflight"] for guest in guests if "preflight" in guest] or None,
            "guests": guests,
            "execution_started": bool(row.get("execution_started")),
            "fingerprint": row.get("fingerprint"),
            "recorded": time.time(),
        }
        row["execution_started"] = False
        row["void_receipt"] = receipt["id"]
        ledger.append(receipt)
        _save(path, ledger)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--attempt", required=True, help="calibration attempt id, or a unique 8+ hex prefix")
    parser.add_argument("--reason", required=True, help="written operator reason; stored in the void receipt")
    args = parser.parse_args(argv)
    try:
        receipt = void_calibration(args.campaign, args.attempt, args.reason)
    except (VoidError, store.CampaignError) as exc:
        print(json.dumps({"status": "REFUSED", "error": str(exc)}), file=sys.stderr)
        return 2
    print(json.dumps({"status": "VOIDED", "id": receipt["id"], "attempt_id": receipt["attempt_id"],
                      "tier": receipt["tier"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
