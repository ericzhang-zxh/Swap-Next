#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Local trusted-controller scaffold; never runs generated kernel code."""
import argparse
from contextlib import contextmanager
import fcntl
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import campaign_store
from analysis import Invalid, analyze, digest, load_json, require

CONTROL = Path(__file__).resolve().parent
PROJECT = CONTROL.parents[1]
ROOT = PROJECT / "linux"
STATE = CONTROL / "state"
POLICY = CONTROL / "config/policy.json"
BASE_POLICY = POLICY
WORKTREES = PROJECT / "worktrees"
CAMPAIGN = None


def emit(data):
    print(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False))


def git(root, *args, binary=False, timeout=90):
    p = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                       timeout=timeout, check=False)
    require(p.returncode == 0, "git failed: " + p.stderr.decode(errors="replace")[:1000])
    return p.stdout if binary else p.stdout.decode().strip()


def configure_campaign(name):
    """Select a controller-owned frozen campaign, never a worker-supplied path."""
    global POLICY, STATE, WORKTREES, CAMPAIGN
    require(re.fullmatch(r"[a-z][a-z0-9-]{0,47}", name), "invalid campaign name")
    directory = campaign_store.campaign_dir(name)
    require((directory / "policy.json").is_file(), "unknown campaign")
    POLICY, STATE, CAMPAIGN = directory / "policy.json", directory, name
    WORKTREES = PROJECT / "worktrees" / name


def artifacts(name):
    """Per-candidate directory: campaigns/<c>/candidates/<id>/, or state/<id> unscoped."""
    return STATE / ("candidates" if CAMPAIGN else "") / name


def host_check():
    require(platform.system() == "Linux", "Run on a Linux KVM worker")


def policy():
    return load_json(POLICY)


def protocol_hash():
    h = hashlib.sha256()
    for path in sorted([POLICY, CONTROL / "analysis.py", CONTROL / "controller.py"]):
        h.update(path.name.encode())
        h.update(path.read_bytes())
    return h.hexdigest()


def seed():
    return git(ROOT, "rev-parse", policy()["seed_ref"] + "^{commit}")


def trusted_control():
    require(git(ROOT, "status", "--porcelain", "--untracked-files=all") == "",
            "control checkout is dirty; finalize framework separately")
    expected_checkout = policy().get("checkout_ref", seed())
    require(git(ROOT, "rev-parse", "HEAD") ==
            git(ROOT, "rev-parse", expected_checkout + "^{commit}"),
            "control checkout must be at frozen upstream revision")


def stopped():
    """The global STOP always applies; a campaign STOP only adds to it."""
    flags = [campaign_store.GLOBAL_STOP]
    if CAMPAIGN:
        flags.append(campaign_store.campaign_dir(CAMPAIGN) / "STOP")
    return any(flag.exists() for flag in flags)


def active():
    require(not stopped(), "STOP is set; controller halted")
    if CAMPAIGN:
        campaign_store.require_open(CAMPAIGN)


@contextmanager
def lock():
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / ".lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def registry():
    if CAMPAIGN:
        return campaign_store.candidates(CAMPAIGN)
    p = STATE / "candidates.json"
    return load_json(p) if p.exists() else {}


def save(records, record):
    if CAMPAIGN:
        campaign_store.write_candidate(CAMPAIGN, record)
    else:
        write_json(STATE / "candidates.json", records)


def event(kind, payload):
    path = STATE / ("ledger/events.jsonl" if CAMPAIGN else "events.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        stream.write(json.dumps({"time_unix": time.time(), "event": kind,
                                 "payload": payload}, ensure_ascii=False) + "\n")


def in_scope(path, status, config):
    if status == "M":
        return path in config["allowed_modify"]
    return any(Path(path).parent == Path(p).parent and
               fnmatch.fnmatchcase(Path(path).name, Path(p).name)
               for p in config["allowed_add"])


def diff_guard(root, base, config):
    root = Path(root)
    base_scope = load_json(BASE_POLICY)
    require(git(root, "rev-parse", "--show-toplevel") == str(root.resolve()),
            "not an exact worktree root")
    require(not git(root, "status", "--porcelain", "--untracked-files=all", "--ignored"),
            "dirty/untracked/ignored files in candidate; build outside source")
    head = git(root, "rev-parse", "HEAD")
    require(head != base, "empty candidate")
    git(root, "merge-base", "--is-ancestor", base, head)
    require(not git(root, "rev-list", "--merges", base + ".." + head),
            "merge commits forbidden in candidate")
    data = git(root, "diff", "--raw", "--no-renames", "-z", base, head, binary=True)
    parts = data.split(b"\0")
    changes = []
    for i in range(0, len(parts) - 1, 2):
        header = parts[i].decode()
        path = parts[i + 1].decode()
        old, new, _, _, status = header[1:].split()
        require(status in ("M", "A"), "deletion/rename/type change forbidden: " + path)
        require(new == "100644" and old in ("100644", "000000"),
                "mode change/symlink/submodule forbidden: " + path)
        require(path and not Path(path).is_absolute() and ".." not in Path(path).parts,
                "unsafe candidate path")
        # The base file list is fixed; a campaign policy can only narrow it.
        allowed = all(in_scope(path, status, c) for c in (config, base_scope))
        require(allowed, "path outside candidate scope: " + path)
        changes.append(path)
    require(changes and len(changes) <= config["max_changed_files"],
            "candidate file budget exceeded or empty")
    stats = git(root, "diff", "--numstat", "--no-renames", "-z", base, head, binary=True)
    lines = 0
    for row in stats.split(b"\0"):
        if not row:
            continue
        added, removed, _ = row.split(b"\t", 2)
        require(added.isdigit() and removed.isdigit(), "binary patch forbidden")
        lines += int(added) + int(removed)
    require(lines <= config["max_changed_lines"], "candidate line budget exceeded")
    return {"status": "SCOPE_PASS", "parent": base, "candidate_commit": head,
            "changed_paths": changes, "changed_lines": lines}


def get_candidate(name):
    records = registry()
    require(name in records, "unknown candidate")
    record = records[name]
    require(record["status"] == "active", "candidate is closed")
    root = (PROJECT / record["worktree"]).resolve()
    allowed = WORKTREES.resolve()
    require(root.parent == allowed and root.name == name, "unexpected worktree location")
    require(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir") ==
            git(ROOT, "rev-parse", "--path-format=absolute", "--git-common-dir"),
            "candidate not in controller repository")
    require(record["parent"] == seed(), "candidate has stale parent")
    return record, root


def doctor():
    tools = {x: shutil.which(x) for x in
             ("git", "python3", "gcc", "make", "bison", "flex", "bc",
              "sparse", "cpio", "qemu-system-x86_64", "timeout")}
    kvm = os.access("/dev/kvm", os.R_OK | os.W_OK)
    blockers = []
    if not tools["qemu-system-x86_64"]:
        blockers.append("qemu-system-x86_64 not installed")
    if not kvm:
        blockers.append("current user cannot read/write /dev/kvm")
    blockers += ["pilot runner setup and environment require separate verification",
                 "full correctness matrix and holdout not provisioned",
                 "baseline A/A and numerical thresholds not calibrated"]
    return {"host": platform.node(), "kernel_running": platform.release(),
            "source_commit": git(ROOT, "rev-parse", "HEAD"),
            "upstream_commit": policy()["upstream_commit"],
            "tools": tools, "kvm_access": kvm, "runtime_ready": False,
            "blockers": blockers, "protocol_sha256": protocol_hash(),
            "note": "KVM access alone does not verify nested virtualization or boot."}


def create(name, hypothesis):
    require(re.fullmatch(r"[a-z][a-z0-9-]{0,47}", name), "invalid candidate name")
    require(10 <= len(hypothesis) <= 2000, "hypothesis must be 10..2000 characters")
    trusted_control()
    active()
    config = policy()
    with lock():
        active()
        records = registry()
        require(name not in records, "candidate ID already used")
        require(len(records) < config["budget"]["max_candidates"], "campaign candidate budget exhausted")
        require(sum(r["status"] == "active" for r in records.values()) <
                config["budget"]["max_active_candidates"], "active candidate limit reached")
        root = WORKTREES / name
        require(not root.exists(), "worktree path already exists")
        root.parent.mkdir(parents=True, exist_ok=True)
        parent = seed()
        git(ROOT, "worktree", "add", "-b", "agents/" + name, str(root), parent)
        record = {"id": name, "parent": parent, "worktree": str(root.relative_to(PROJECT)),
                  "status": "active", "hypothesis": hypothesis,
                  "created_unix": time.time(), "protocol_sha256": protocol_hash()}
        records[name] = record
        save(records, record)
        names = ("CODE_PATTERNS.md", "PRINCIPLES.md", "METRICS.md")
        reading = (["AGENTS.md"] + ["evolve/control/" + n for n in names] if CAMPAIGN else
                   [str(PROJECT / "AGENTS.md")] + [str(CONTROL / n) for n in names])
        task = dict(record, allowed_modify=config["allowed_modify"],
                    allowed_add=config["allowed_add"], budget=config["budget"],
                    primary_metric=config.get("primary_metric", "throughput_ops_s"),
                    required_reading=reading,
                    boundaries="Execution-only. No delegation, host execution, evaluator edits, credentials, publication, or DCO signing.",
                    execution_status="PREPARED_ONLY; no worker or kernel was launched")
        write_json(artifacts(name) / "task.json", task)
        event("candidate_created", record)
        return task


def check_candidate(name, static=False):
    trusted_control()
    active()
    record, root = get_candidate(name)
    result = diff_guard(root, record["parent"], policy())
    out = artifacts(name)
    out.mkdir(parents=True, exist_ok=True)
    if static:
        patch = git(root, "diff", "--no-ext-diff", "--no-textconv",
                    record["parent"], result["candidate_commit"], binary=True)
        target = STATE / "patches" / (name + ".patch") if CAMPAIGN else out / "candidate.patch"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(patch)
        commands = [
            ("diff-check", ["git", "-C", str(root), "diff", "--check",
                            record["parent"], result["candidate_commit"]], None),
            ("checkpatch", ["perl", str(ROOT / "scripts/checkpatch.pl"),
                            "--no-tree", "--no-signoff", "-"], patch),
        ]
        for label, command, input_data in commands:
            proc = subprocess.run(command, input=input_data, capture_output=True,
                                  timeout=120, cwd=ROOT)
            log = out / (label + ".log")
            log.write_bytes(proc.stdout + proc.stderr or b"(no diagnostics)\n")
            result[label] = {"exit_code": proc.returncode, "evidence": str(log.relative_to(PROJECT) if CAMPAIGN else log),
                             "sha256": digest(log)}
            if proc.returncode:
                result["status"] = "STATIC_REJECT"
    write_json(out / ("static.json" if static else "scope.json"), result)
    event("candidate_checked", result)
    return result


def baseline_from(args):
    """Check the evidence named on the command line; return campaign.json's baseline_from."""
    source, _, cand = args.baseline_from.partition(":")
    require(source and cand and bool(args.evidence_row) != bool(args.evidence_report),
            "--baseline-from CAMPAIGN:CANDIDATE needs exactly one of --evidence-row, --evidence-report")
    source_dir = campaign_store.campaign_dir(source)
    if args.evidence_row:
        rows = load_json(source_dir / "ledger/ledger.json")
        row = next((r for r in rows if r.get("id") == args.evidence_row), None)
        require(row and row.get("candidate") == cand, "no ledger row for that candidate")
        require(row.get("status") == "FAST_PASS", "ledger row is not FAST_PASS")
        require(row.get("candidate_commit"), "ledger row has no candidate_commit")
        return {"campaign": source, "candidate": cand, "commit": row["candidate_commit"],
                "evidence": {"kind": "fast_pass", "ledger_row": args.evidence_row}}
    report = PROJECT / args.evidence_report
    require(report.is_file(), "evidence report does not exist")
    commit = git(ROOT, "rev-parse", "--verify", f"refs/heads/agents/{cand}^{{commit}}")
    path = report.relative_to(PROJECT) if report.is_relative_to(PROJECT) else report
    return {"campaign": source, "candidate": cand, "commit": commit,
            "evidence": {"kind": "correctness_fix", "report": str(path)}}


def open_campaign(args):
    require(CAMPAIGN, "open-campaign needs --campaign")
    directory = campaign_store.campaign_dir(CAMPAIGN)
    require((directory / "protocol.json").is_file(), "protocol.json is missing")
    require(not (directory / "campaign.json").exists(), "campaign.json already exists")
    config, base = policy(), load_json(BASE_POLICY)
    require(set(config["allowed_modify"]) <= set(base["allowed_modify"]) and
            set(config["allowed_add"]) <= set(base["allowed_add"]),
            "campaign policy widens the base scope")
    require(args.machine == campaign_store.current_machine(),
            f"--machine {args.machine} is not this machine")
    for other in sorted(campaign_store.CAMPAIGNS.glob("*/campaign.json")):
        known = campaign_store.load(other.parent.name)
        require(not (known["status"] == "open" and known["machine"] == args.machine),
                f"campaign {known['campaign']} is already open on {args.machine}")
    budget = dict(load_json(directory / "protocol.json")["budget"])
    record = {"campaign": CAMPAIGN, "status": "open", "line": args.line,
              "baseline_from": baseline_from(args) if args.baseline_from else None,
              "machine": args.machine, "opened": time.strftime("%Y-%m-%d", time.gmtime()),
              "closed": None,
              "budget": {"guest_attempts": budget["guest_attempts"],
                         "wall_seconds": budget["wall_seconds"],
                         "probe_guest_attempts": budget.get("probe_guest_attempts", 0),
                         "approved_over_cap": args.over_cap_approval or None}}
    errors = campaign_store.budget_errors(record)
    require(not errors, "; ".join(errors))
    campaign_store.take_claim(CAMPAIGN)
    try:
        campaign_store.write(CAMPAIGN, record)
    except ValueError:
        campaign_store.release_claim(CAMPAIGN, "open-campaign failed")
        raise
    return record


def close_campaign(reason):
    require(CAMPAIGN, "close-campaign needs --campaign")
    record = campaign_store.require_open(CAMPAIGN)
    with lock():
        records = registry()
        unexported = [i for i, r in records.items() if r["status"] == "active"
                      and not (STATE / "patches" / (i + ".patch")).is_file()]
        require(not unexported, "active candidates without an exported patch: " + ", ".join(unexported))
        for i, r in records.items():
            if r["status"] == "active":
                r.update(status="closed", reason=reason)
                save(records, r)
                event("candidate_closed", r)
        record.update(status="closed", closed=time.strftime("%Y-%m-%d", time.gmtime()))
        campaign_store.write(CAMPAIGN, record)
        if campaign_store.read_claim() == CAMPAIGN:
            campaign_store.release_claim(CAMPAIGN, reason)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", help="controller-owned campaign name")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("doctor", "status", "protocol"):
        commands.add_parser(name)
    p = commands.add_parser("new")
    p.add_argument("name")
    p.add_argument("--hypothesis", required=True)
    for name in ("guard", "check"):
        commands.add_parser(name).add_argument("name")
    p = commands.add_parser("close")
    p.add_argument("name")
    p.add_argument("--reason", required=True)
    p = commands.add_parser("open-campaign")
    p.add_argument("--line", required=True)
    p.add_argument("--machine", required=True)
    p.add_argument("--baseline-from", help="CAMPAIGN:CANDIDATE")
    p.add_argument("--evidence-report")
    p.add_argument("--evidence-row")
    p.add_argument("--over-cap-approval")
    for name in ("close-campaign", "release-claim"):
        commands.add_parser(name).add_argument("--reason", required=True)
    p = commands.add_parser("analyze")
    p.add_argument("name")
    p.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        host_check()
        if args.campaign and args.command != "release-claim":
            configure_campaign(args.campaign)
        if args.command == "doctor":
            result = doctor()
        elif args.command == "status":
            result = {"stopped": stopped(), "candidates": registry(),
                      "runtime_enabled": policy()["runtime_enabled"],
                      "thresholds_calibrated": policy()["thresholds_calibrated"],
                      "auto_promote": False}
        elif args.command == "protocol":
            result = {"protocol_sha256": protocol_hash(), "baseline_commit": seed()}
        elif args.command == "open-campaign":
            result = open_campaign(args)
        elif args.command == "close-campaign":
            result = close_campaign(args.reason)
        elif args.command == "release-claim":
            campaign_store.release_claim(None, args.reason)
            result = {"status": "RELEASED"}
        elif args.command == "new":
            result = create(args.name, args.hypothesis)
        elif args.command in ("guard", "check"):
            result = check_candidate(args.name, args.command == "check")
        elif args.command == "close":
            if CAMPAIGN:
                campaign_store.require_open(CAMPAIGN)
            with lock():
                records = registry()
                require(args.name in records, "unknown candidate")
                records[args.name]["status"] = "closed"
                records[args.name]["reason"] = args.reason
                save(records, records[args.name])
                event("candidate_closed", records[args.name])
                result = records[args.name]
        else:
            scope = check_candidate(args.name)
            result = analyze(args.manifest, policy(), protocol_hash(),
                             scope["parent"], scope["candidate_commit"])
            # No amount of submitted JSON enables automatic acceptance.
            result["runtime_enabled"] = policy()["runtime_enabled"]
            result["candidate_id"] = args.name
            write_json(artifacts(args.name) / "analysis.json", result)
            with lock():
                event("analysis_complete", result)
        emit(result)
        return 1 if result.get("status") == "STATIC_REJECT" else 0
    except (Invalid, OSError, ValueError, KeyError, TypeError,
            subprocess.TimeoutExpired) as error:
        emit({"status": "BLOCKED_OR_REJECTED", "error": str(error),
              "auto_promote": False})
        return 2


if __name__ == "__main__":
    sys.exit(main())
