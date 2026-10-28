# SPDX-License-Identifier: GPL-2.0-only
"""Campaign directories: layout, campaign.json, budget cap, hosts, claim."""
from contextlib import contextmanager, nullcontext
import fcntl
import json
import logging
import os
from pathlib import Path
import platform
import re
import time

PROJECT = Path(__file__).resolve().parents[2]
CAMPAIGNS = PROJECT / "campaigns"
HOSTS = CAMPAIGNS / "hosts.json"
GLOBAL_STOP = CAMPAIGNS / "STOP"
CAP_GUEST_ATTEMPTS = 120
CAP_WALL_SECONDS = 64800
NAME = re.compile(r"[a-z][a-z0-9-]{0,47}")
KEYS = ("campaign", "status", "line", "baseline_from", "machine", "opened", "closed", "budget")
BUDGET = ("guest_attempts", "wall_seconds", "probe_guest_attempts", "approved_over_cap")
EVIDENCE = {"fast_pass": "ledger_row", "correctness_fix": "report"}
log = logging.getLogger("campaign_store")

class CampaignError(ValueError):
    pass

def _name(name, what="campaign"):
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise CampaignError(f"bad {what} name: {name!r}")
    return name

def campaign_dir(name):
    return CAMPAIGNS / _name(name)

def _hosts():
    try:
        return json.loads(HOSTS.read_text())
    except (OSError, ValueError) as e:
        raise CampaignError(f"cannot read {HOSTS}: {e}")

def _check(name, r):
    if not isinstance(r, dict):
        raise CampaignError("campaign.json must be an object")
    missing = [k for k in KEYS if k not in r]
    if missing:
        raise CampaignError(f"campaign.json missing {missing}")
    if r["campaign"] != name:
        raise CampaignError(f"campaign {r['campaign']!r} does not match directory {name!r}")
    if r["status"] not in ("open", "closed"):
        raise CampaignError(f"bad status {r['status']!r}")
    _name(r["line"], "line")
    if "line_anchor_commit" in r and (not isinstance(r["line_anchor_commit"], str)
            or not re.fullmatch(r"[0-9a-f]{40}", r["line_anchor_commit"])):
        raise CampaignError("line_anchor_commit must be an exact commit")
    if r["machine"] not in _hosts():
        raise CampaignError(f"machine {r['machine']!r} is not in hosts.json")
    b = r["baseline_from"]
    if b is not None:
        ev = b.get("evidence") if isinstance(b, dict) else None
        if not (isinstance(ev, dict) and ev.get("kind") in EVIDENCE
                and isinstance(ev.get(EVIDENCE[ev["kind"]]), str)
                and all(isinstance(b.get(k), str) for k in ("campaign", "candidate", "commit"))):
            raise CampaignError(f"bad baseline_from: {b!r}")
    bud = r["budget"]
    if not isinstance(bud, dict) or any(k not in bud for k in BUDGET):
        raise CampaignError(f"budget needs {list(BUDGET)}")
    for k in BUDGET[:3]:
        if not isinstance(bud[k], int) or isinstance(bud[k], bool) or bud[k] < 0:
            raise CampaignError(f"budget.{k} must be a non-negative integer")
    approval = bud["approved_over_cap"]
    if approval is not None and (not isinstance(approval, str) or not approval.strip()):
        raise CampaignError("budget.approved_over_cap must be null or a non-empty approval reference")
    if (r["status"] == "closed") != (r["closed"] is not None):
        raise CampaignError("closed must be set exactly when status is closed")
    return r

def _dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2) + "\n")
    os.replace(tmp, path)

def load(name):
    path = campaign_dir(name) / "campaign.json"
    try:
        r = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise CampaignError(f"cannot read {path}: {e}")
    return _check(name, r)

def write(name, record):
    _dump(campaign_dir(name) / "campaign.json", _check(name, record))

def candidates(name):
    out = {}
    for p in sorted((campaign_dir(name) / "candidates").glob("*.json")):
        try:
            r = json.loads(p.read_text())
        except ValueError as e:
            raise CampaignError(f"{p}: {e}")
        if not isinstance(r, dict) or r.get("id") != p.stem:
            raise CampaignError(f"{p}: id does not match filename")
        out[p.stem] = r
    return out

def write_candidate(name, record):
    cid = _name(record.get("id"), "candidate")
    _dump(campaign_dir(name) / "candidates" / f"{cid}.json", record)

def budget_errors(record):
    if record.get("status") == "closed":
        return []
    b, over = record["budget"], record["budget"].get("approved_over_cap")
    if over:
        return []
    errs = []
    used = b["guest_attempts"] + b.get("probe_guest_attempts", 0)
    if used > CAP_GUEST_ATTEMPTS:
        errs.append(f"guest_attempts {b['guest_attempts']} + probe {b.get('probe_guest_attempts', 0)}"
                    f" exceeds cap {CAP_GUEST_ATTEMPTS} without approved_over_cap")
    if b["wall_seconds"] > CAP_WALL_SECONDS:
        errs.append(f"wall_seconds {b['wall_seconds']} exceeds cap {CAP_WALL_SECONDS} without approved_over_cap")
    return errs

def require_open(name):
    r = load(name)
    if r["status"] != "open":
        raise CampaignError(f"campaign {name} is closed")
    return r

def current_machine():
    hosts, env = _hosts(), os.environ.get("SWAP_NEXT_MACHINE")
    if env:
        if env not in hosts:
            raise CampaignError(f"SWAP_NEXT_MACHINE={env!r} is not in hosts.json")
        return env
    node = platform.node().lower()
    for m, h in hosts.items():
        if node in [x.lower() for x in h.get("hostnames", [])]:
            return m
    raise CampaignError(f"host {platform.node()!r} is not in hosts.json; set SWAP_NEXT_MACHINE")

def claim_path():
    return Path(os.environ.get("SWAP_NEXT_CLAIM") or Path.home() / ".cache/swap-next/campaign.claim")

def read_claim():
    try:
        return claim_path().read_text().strip() or None
    except FileNotFoundError:
        return None

@contextmanager
def claim_lock():
    """Serialize host-wide open/close/claim transitions across processes."""
    path = claim_path().with_suffix(".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def take_claim(name, *, locked=False):
    with nullcontext() if locked else claim_lock():
        _take_claim(name)


def _take_claim(name):
    _name(name)
    held = read_claim()
    if held not in (None, name):
        try:
            closed = load(held)["status"] == "closed"
        except CampaignError:
            closed = False
        if not closed:
            raise CampaignError(f"claim held by {held}; release it with release-claim --reason")
        log.warning("replacing stale claim on closed campaign %s", held)
    _dump_text(claim_path(), name + "\n")

def _dump_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)

def release_claim(name, reason, *, locked=False):
    with nullcontext() if locked else claim_lock():
        _release_claim(name, reason)


def _release_claim(name, reason):
    held = read_claim()
    if name is not None and held != name:
        raise CampaignError(f"claim is {held!r}, not {name!r}")
    if held is None:
        return
    with claim_path().with_suffix(".log").open("a") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} released {held}: {reason}\n")
    claim_path().unlink()

def require_claim(name):
    held = read_claim()
    if held != name:
        raise CampaignError(f"claim is {held!r}, expected {name!r}; run open-campaign")


def require_execution(name, protocol=None):
    """Validate every guest entry point before creating runtime evidence or launching."""
    if not name:
        raise CampaignError("guest execution needs an explicit campaign")
    record = require_open(name)
    machine = current_machine()
    if record["machine"] != machine:
        raise CampaignError(f"campaign {name} belongs to {record['machine']}, not {machine}")
    if GLOBAL_STOP.exists() or (campaign_dir(name) / "STOP").exists():
        raise CampaignError("STOP")
    require_claim(name)
    errors = budget_errors(record)
    if protocol is not None:
        if protocol.get("campaign") != name:
            errors.append("protocol campaign does not match campaign.json")
        for key in ("guest_attempts", "wall_seconds", "probe_guest_attempts"):
            if protocol.get("budget", {}).get(key, 0) != record["budget"][key]:
                errors.append(f"protocol budget.{key} does not match campaign.json")
    if errors:
        raise CampaignError("; ".join(errors))
    return record
