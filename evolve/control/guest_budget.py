#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Count guest attempts before launch and bind each reservation to one execution."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
from pathlib import Path
import re
import time

import campaign_store as store

IDENTITY_KEYS = ("build", "backend", "mode", "workload")


def load(path):
    return json.loads(path.read_text())


def save(path, value):
    store._dump(path, value)


def protocol(name):
    directory = store.campaign_dir(name)
    p = load(directory / "protocol.json")
    store.require_execution(name, p)
    return p


@contextmanager
def budget_lock(name):
    directory = store.campaign_dir(name) / "ledger"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".budget.lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def read_budget(name):
    path = store.campaign_dir(name) / "ledger/budget.json"
    tickets = list((path.parent / "guest-reservations").glob("*.json"))
    if not path.exists() and tickets:
        raise store.CampaignError("budget missing while guest reservations exist; reconcile retained evidence")
    budget = load(path) if path.exists() else {"created": time.time(), "guests": 0, "probe_guests": 0, "builds": 0}
    counts = {"fast": 0, "probe": 0}
    for ticket in tickets:
        record = load(ticket)
        pool = record.get("pool")
        if record.get("campaign") != name or pool not in counts:
            raise store.CampaignError("invalid retained guest reservation identity")
        counts[pool] += 1
    for pool, key in (("fast", "guests"), ("probe", "probe_guests")):
        if budget.get(key, 0) < counts[pool]:
            raise store.CampaignError("budget is below retained " + pool + " reservations; reconcile evidence")
    return budget


def ticket_path(name, run_id):
    if not isinstance(run_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,96}", run_id):
        raise store.CampaignError("invalid reservation run ID")
    return store.campaign_dir(name) / "ledger/guest-reservations" / (run_id + ".json")


def _deadline(budget, p):
    if time.time() > budget["created"] + p["budget"]["wall_seconds"]:
        raise store.CampaignError("campaign deadline")


def reserve_guest(campaign, run_id, build, backend, mode, workload, pool="fast"):
    """Return a tracked ticket. Failures after reservation keep the spent attempt."""
    p = protocol(campaign)
    path = ticket_path(campaign, run_id)
    identity = dict(zip(IDENTITY_KEYS, (build, backend, mode, workload)))
    if (not isinstance(build, str) or not re.fullmatch(r"[a-z0-9-]{1,48}", build)
            or backend not in ("disk", "zswap", "zram", "brd")
            or mode not in ("plain", "xswap") or not isinstance(workload, str) or not workload):
        raise store.CampaignError("invalid guest reservation identity")
    if pool not in ("fast", "probe"):
        raise store.CampaignError("reservation pool must be fast or probe")
    with budget_lock(campaign):
        protocol(campaign)
        if path.exists():
            raise store.CampaignError("guest reservation already exists; prior attempt retained")
        budget = read_budget(campaign)
        _deadline(budget, p)
        key, cap = ("probe_guests", "probe_guest_attempts") if pool == "probe" else ("guests", "guest_attempts")
        if budget.get(key, 0) >= p["budget"].get(cap, 0):
            raise store.CampaignError("campaign " + pool + " guest budget")
        # Budget is saved first: an interrupted write can lose capacity, never reuse it.
        budget[key] = budget.get(key, 0) + 1
        save(store.campaign_dir(campaign) / "ledger/budget.json", budget)
        ticket = {"id": run_id, "campaign": campaign, "pool": pool, "status": "RESERVED",
                  "reserved_unix": time.time(), "identity": identity,
                  "protocol_sha256": hashlib.sha256((store.campaign_dir(campaign) / "protocol.json").read_bytes()).hexdigest()}
        save(path, ticket)
    return dict(ticket, reservation=str(path.relative_to(store.PROJECT)))


def consume_guest(campaign, run_id, reservation, identity):
    """A runner consumes one matching ticket before any runtime files or launch."""
    p = protocol(campaign)
    path = ticket_path(campaign, run_id)
    supplied = Path(reservation)
    if not supplied.is_absolute():
        supplied = store.PROJECT / supplied
    if supplied.resolve() != path.resolve():
        raise store.CampaignError("reservation path does not match campaign and run ID")
    with budget_lock(campaign):
        protocol(campaign)
        _deadline(read_budget(campaign), p)
        if not path.is_file():
            raise store.CampaignError("missing counted guest reservation")
        ticket = load(path)
        if (ticket.get("campaign") != campaign or ticket.get("id") != run_id
                or ticket.get("status") != "RESERVED" or ticket.get("identity") != identity):
            raise store.CampaignError("guest reservation identity mismatch or already consumed")
        digest = hashlib.sha256((store.campaign_dir(campaign) / "protocol.json").read_bytes()).hexdigest()
        if ticket.get("protocol_sha256") != digest:
            raise store.CampaignError("guest reservation protocol changed")
        ticket.update(status="STARTED", started_unix=time.time())
        save(path, ticket)
    return ticket


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--run-id", required=True)
    for key in IDENTITY_KEYS:
        parser.add_argument("--" + key, required=True)
    parser.add_argument("--pool", choices=("fast", "probe"), default="fast")
    args = parser.parse_args()
    try:
        print(json.dumps(reserve_guest(**vars(args)), indent=2))
    except (store.CampaignError, OSError, ValueError) as exc:
        raise SystemExit("BLOCKED: " + str(exc))


if __name__ == "__main__":
    main()
