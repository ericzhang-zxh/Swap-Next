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
from analysis import Invalid, analyze, digest, load_json, require

CONTROL = Path(__file__).resolve().parent
PROJECT = CONTROL.parents[1]
ROOT = PROJECT / "linux"
STATE = CONTROL / "state"
POLICY = CONTROL / "config/policy.json"
BASE_POLICY = POLICY
WORKTREES = PROJECT / "worktrees"


def emit(data):
    print(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False))


def git(root, *args, binary=False, timeout=90):
    p = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                       timeout=timeout, check=False)
    require(p.returncode == 0, "git failed: " + p.stderr.decode(errors="replace")[:1000])
    return p.stdout if binary else p.stdout.decode().strip()


def configure_campaign(name):
    """Select a controller-owned frozen campaign, never a worker-supplied path."""
    global POLICY, STATE, WORKTREES
    require(re.fullmatch(r"[a-z][a-z0-9-]{0,47}", name), "invalid campaign name")
    candidate = CONTROL / "campaigns" / name / "policy.json"
    require(candidate.is_file(), "unknown campaign")
    POLICY = candidate
    STATE = CONTROL / "state" / name
    WORKTREES = PROJECT / "worktrees" / name


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
    return (CONTROL / "state/STOP").exists() or (STATE / "STOP").exists()


def active():
    require(not stopped(), "STOP is set; controller halted")


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
    p = STATE / "candidates.json"
    return load_json(p) if p.exists() else {}


def event(kind, payload):
    with (STATE / "events.jsonl").open("a") as stream:
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
    root = Path(record["worktree"]).resolve()
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
        record = {"id": name, "parent": parent, "worktree": str(root),
                  "status": "active", "hypothesis": hypothesis,
                  "created_unix": time.time(), "protocol_sha256": protocol_hash()}
        records[name] = record
        write_json(STATE / "candidates.json", records)
        task = dict(record, allowed_modify=config["allowed_modify"],
                    allowed_add=config["allowed_add"], budget=config["budget"],
                    primary_metric=config.get("primary_metric", "throughput_ops_s"),
                    required_reading=[str(PROJECT / "AGENTS.md"), str(CONTROL / "CODE_PATTERNS.md"),
                                      str(CONTROL / "PRINCIPLES.md"), str(CONTROL / "METRICS.md")],
                    boundaries="Execution-only. No delegation, host execution, evaluator edits, credentials, publication, or DCO signing.",
                    execution_status="PREPARED_ONLY; no worker or kernel was launched")
        write_json(STATE / name / "task.json", task)
        event("candidate_created", record)
        return task


def check_candidate(name, static=False):
    trusted_control()
    active()
    record, root = get_candidate(name)
    result = diff_guard(root, record["parent"], policy())
    out = STATE / name
    out.mkdir(parents=True, exist_ok=True)
    if static:
        patch = git(root, "diff", "--no-ext-diff", "--no-textconv",
                    record["parent"], result["candidate_commit"], binary=True)
        (out / "candidate.patch").write_bytes(patch)
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
            result[label] = {"exit_code": proc.returncode, "evidence": str(log),
                             "sha256": digest(log)}
            if proc.returncode:
                result["status"] = "STATIC_REJECT"
    write_json(out / ("static.json" if static else "scope.json"), result)
    event("candidate_checked", result)
    return result


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
    p = commands.add_parser("analyze")
    p.add_argument("name")
    p.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        host_check()
        if args.campaign:
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
        elif args.command == "new":
            result = create(args.name, args.hypothesis)
        elif args.command in ("guard", "check"):
            result = check_candidate(args.name, args.command == "check")
        elif args.command == "close":
            with lock():
                records = registry()
                require(args.name in records, "unknown candidate")
                records[args.name]["status"] = "closed"
                records[args.name]["reason"] = args.reason
                write_json(STATE / "candidates.json", records)
                event("candidate_closed", records[args.name])
                result = records[args.name]
        else:
            scope = check_candidate(args.name)
            result = analyze(args.manifest, policy(), protocol_hash(),
                             scope["parent"], scope["candidate_commit"])
            # No amount of submitted JSON enables automatic acceptance.
            result["runtime_enabled"] = policy()["runtime_enabled"]
            result["candidate_id"] = args.name
            write_json(STATE / args.name / "analysis.json", result)
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
