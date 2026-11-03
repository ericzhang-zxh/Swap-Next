#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Local trusted-controller scaffold; never runs generated kernel code."""
import argparse
from contextlib import contextmanager
import fcntl
import fnmatch
import hashlib
import importlib.util
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


def review_api():
    sys.path.insert(0, str(CONTROL.parent))
    import reviews
    return reviews


def review_subject(campaign, name, commit):
    record = campaign_store.candidates(campaign).get(name, {}) if name else {}
    return dict(record, id=name, candidate_commit=commit,
                source_tree=git(ROOT, "rev-parse", commit + "^{tree}"))


def require_review_clear(campaign, name, commit):
    vetoes = review_api().blockers(PROJECT, campaign, review_subject(campaign, name, commit))
    require(not vetoes, "unresolved correctness review: " + json.dumps(vetoes))


def record_review(name, path):
    require(CAMPAIGN, "review-record needs --campaign")
    require(name in registry(), "unknown review candidate")
    payload = load_json(path)
    require(payload.get("candidate") == name and payload.get("campaign") == CAMPAIGN,
            "review subject does not match controller selection")
    commit = payload.get("candidate_commit")
    require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit), "review requires exact commit")
    require(git(ROOT, "rev-parse", "--verify", commit + "^{commit}") == commit,
            "review commit is not an exact existing commit")
    require(payload.get("source_tree") == git(ROOT, "rev-parse", commit + "^{tree}"),
            "review tree does not match commit")
    known = []
    population = STATE / "archive/population.json"
    if population.is_file():
        known.append(load_json(population).get("entries", {}).get(name, {}).get("candidate_commit"))
    for filename in ("static.json", "scope.json"):
        artifact = artifacts(name) / filename
        if artifact.is_file():
            known.append(load_json(artifact).get("candidate_commit"))
    if commit not in known:
        known.append(git(ROOT, "rev-parse", "--verify", "refs/heads/agents/" + name + "^{commit}"))
    require(commit in known, "review commit does not belong to the recorded candidate")
    result = review_api().record(PROJECT, CAMPAIGN, payload)
    return {"review": result, "blockers": review_api().blockers(
        PROJECT, CAMPAIGN, review_subject(CAMPAIGN, name, commit))}


def research_contract():
    if not CAMPAIGN or not (STATE / "research.json").is_file():
        return None
    sys.path.insert(0, str(CONTROL.parent))
    import research
    value = load_json(STATE / "research.json")
    require(value.get("protocol_sha256") == digest(STATE / "protocol.json") and
            value.get("policy_sha256") == digest(POLICY), "frozen research inputs changed")
    research.validate_contract(value["line_contract"], PROJECT)
    return value


def scope_profile():
    value = research_contract()
    if value is None:
        return load_json(BASE_POLICY)
    import research
    return research.load_profile(value["line_contract"]["profile"], PROJECT)


def export_candidate(name):
    """Preserve source without executing it, including after STOP or a deadline."""
    require(CAMPAIGN, "export needs a campaign")
    campaign_store.require_open(CAMPAIGN)
    records = registry()
    require(name in records, "unknown candidate")
    record = records[name]
    root = (PROJECT / record["worktree"]).resolve()
    require(root.parent == WORKTREES.resolve() and root.name == name, "unexpected worktree")
    target = STATE / "patches" / (name + ".patch")
    if not root.is_dir():
        require(target.is_file(), "worktree and retained patch are both missing")
        return {"status": "EXPORTED", "patch": str(target.relative_to(PROJECT)), "sha256": digest(target)}
    require(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir") ==
            git(ROOT, "rev-parse", "--path-format=absolute", "--git-common-dir"),
            "candidate not in controller repository")
    base = record.get("baseline_commit", record["parent"])
    commit = git(root, "rev-parse", "HEAD")
    git(root, "merge-base", "--is-ancestor", base, commit)
    patch = git(root, "diff", "--no-ext-diff", "--no-textconv", "--binary", base, commit, "--", binary=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(patch)
    dirty = git(root, "diff", "--no-ext-diff", "--no-textconv", "--binary", "HEAD", "--", binary=True)
    if dirty:
        target.with_name(name + "-uncommitted.patch").write_bytes(dirty)
    untracked = git(root, "ls-files", "--others", "--exclude-standard").splitlines()
    result = {"status": "EXPORTED", "candidate": name, "candidate_commit": commit,
              "source_tree": git(root, "rev-parse", "HEAD^{tree}"),
              "patch": str(target.relative_to(PROJECT)), "sha256": digest(target),
              "uncommitted_patch_retained": bool(dirty), "untracked_files_retained_in_worktree": untracked}
    write_json(artifacts(name) / "export.json", result)
    return result


def in_scope(path, status, config):
    if status == "M":
        return path in config["allowed_modify"]
    return any(Path(path).parent == Path(p).parent and
               fnmatch.fnmatchcase(Path(path).name, Path(p).name)
               for p in config["allowed_add"])


def diff_guard(root, base, config, *, head=None):
    root = Path(root)
    base_scope = scope_profile()
    require(git(root, "rev-parse", "--show-toplevel") == str(root.resolve()),
            "not an exact worktree root")
    require(not git(root, "status", "--porcelain", "--untracked-files=all", "--ignored"),
            "dirty/untracked/ignored files in candidate; build outside source")
    head = git(root, "rev-parse", (head or "HEAD") + "^{commit}")
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


def campaign_fingerprint(protocol, directory):
    """Share the evaluator's identity without importing any model provider."""
    path = Path(__file__).resolve().parents[1] / "standard_workflow.py"
    spec = importlib.util.spec_from_file_location("controller_workflow_identity", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.ROOT, module.BENCH = PROJECT, PROJECT / "benchmark/swap-standard"
    module.CAMPAIGN, module.PROTOCOL = directory, directory / "protocol.json"
    return module.fingerprint(protocol)


def evolution_population(protocol=None, directory=None):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from population import Population
    directory = directory or STATE
    protocol = protocol or load_json(directory / "protocol.json")
    return Population(directory, protocol, campaign_fingerprint(protocol, directory))


def line_anchor(line, fallback):
    """The oldest recorded protocol anchors a line; later baselines cannot reset it."""
    records = [campaign_store.load(path.parent.name)
               for path in campaign_store.CAMPAIGNS.glob("*/campaign.json")]
    records = sorted((r for r in records if r["line"] == line), key=lambda r: (r["opened"], r["campaign"]))
    declared = {r["line_anchor_commit"] for r in records if r.get("line_anchor_commit")}
    require(len(declared) <= 1, "line has conflicting anchor identities")
    if declared:
        return next(iter(declared))
    for record in records:
        directory = campaign_store.campaign_dir(record["campaign"])
        path = directory / "protocol.json"
        if not path.exists() and record.get("protocol_ref"):
            path = PROJECT / record["protocol_ref"]
        if path.is_file():
            value = load_json(path).get("baseline_commit")
            if isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value):
                return value
    return fallback


def get_candidate(name, *, retained=False):
    records = registry()
    require(name in records, "unknown candidate")
    record = records[name]
    require(record["status"] == "active" or (retained and record["status"] == "closed"), "candidate is closed")
    root = (PROJECT / record["worktree"]).resolve()
    allowed = WORKTREES.resolve()
    require(root.parent == allowed and root.name == name, "unexpected worktree location")
    require(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir") ==
            git(ROOT, "rev-parse", "--path-format=absolute", "--git-common-dir"),
            "candidate not in controller repository")
    baseline = seed()
    require(record.get("baseline_commit", record["parent"]) == baseline, "candidate has stale baseline")
    parent = record.get("parent_commit", record["parent"])
    require(git(ROOT, "rev-parse", parent + "^{commit}") == parent, "candidate parent is missing")
    git(root, "merge-base", "--is-ancestor", parent, "HEAD")
    require(git(root, "rev-parse", "HEAD^{tree}") != git(ROOT, "rev-parse", parent + "^{tree}"),
            "child source tree is unchanged from its parent")
    if retained and record["status"] == "closed":
        require(record.get("candidate_commit") == git(root, "rev-parse", "HEAD"),
                "closed reference commit changed or missing")
        require(record.get("source_tree") == git(root, "rev-parse", "HEAD^{tree}"),
                "closed reference source tree changed or missing")
    return record, root


def check_reference(name):
    """Read-only scope/veto checks, including references whose worktree is retired."""
    trusted_control()
    records = registry()
    require(name in records, "unknown reference")
    record = records[name]
    require(record.get("status") in {"active", "closed"}, "unknown reference status")
    expected = dict(record)
    exported = artifacts(name) / "export.json"
    if exported.is_file():
        receipt = load_json(exported)
        require(receipt.get("candidate") == name, "reference export subject mismatch")
        for key in ("candidate_commit", "source_tree"):
            if not expected.get(key):
                expected[key] = receipt.get(key)
    worktree = (PROJECT / record["worktree"]).resolve()
    require(worktree.parent == WORKTREES.resolve() and worktree.name == name, "unexpected reference worktree")
    if worktree.exists():
        require(git(worktree, "rev-parse", "--path-format=absolute", "--git-common-dir") ==
                git(ROOT, "rev-parse", "--path-format=absolute", "--git-common-dir"), "reference belongs to another repository")
        commit = git(worktree, "rev-parse", "HEAD")
        tree = git(worktree, "rev-parse", "HEAD^{tree}")
        if record["status"] == "closed":
            require(commit == expected.get("candidate_commit"), "closed reference commit changed or missing")
            require(tree == expected.get("source_tree"), "closed reference tree changed or missing")
        source = worktree
    else:
        require(record["status"] == "closed", "active reference worktree is missing")
        commit, tree = expected.get("candidate_commit"), expected.get("source_tree")
        require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit), "retained reference commit is missing")
        require(git(ROOT, "rev-parse", commit + "^{tree}") == tree, "retained reference tree mismatch")
        source = ROOT
    baseline = record.get("baseline_commit", record["parent"])
    require(baseline == seed(), "reference has stale baseline")
    result = diff_guard(source, baseline, policy(), head=commit)
    if CAMPAIGN:
        require_review_clear(CAMPAIGN, name, commit)
    result.update(source_tree=tree, reference_only=True)
    return result


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


def parse_mechanism(value):
    pattern = (r"[a-z][a-z0-9-]{0,47}:(?:metadata_delta_bytes_per_capacity_slot|"
               r"swapin_vmstat_delta\.[a-z][a-z0-9_]*|xswap\.[a-z][a-z0-9_]*):(up|down)")
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise argparse.ArgumentTypeError("mechanism must be CASE:KEY:up|down")
    return value


def create(name, hypothesis, mechanism=None, parent=None, brief=None):
    require(re.fullmatch(r"[a-z][a-z0-9-]{0,47}", name), "invalid candidate name")
    require(10 <= len(hypothesis) <= 2000, "hypothesis must be 10..2000 characters")
    trusted_control()
    active()
    config = policy()
    require(not config.get("mechanism_required") or mechanism is not None,
            "campaign policy requires --mechanism CASE:KEY:up|down")
    if isinstance(mechanism, dict):
        sys.path.insert(0, str(CONTROL.parent))
        import mechanisms
        require(CAMPAIGN and research_contract(), "structural mechanisms need a profiled research campaign")
        mechanisms.declaration(mechanism, load_json(STATE / "protocol.json"))
        require("reviewed_structure" in scope_profile()["mechanism_evidence"], "profile has no structural evidence route")
    elif mechanism is not None:
        mechanism = parse_mechanism(mechanism)
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
        baseline = seed()
        chosen = baseline if parent in (None, "baseline") else parent
        parent_candidate, generation = None, 1
        protocol_path = STATE / "protocol.json"
        protocol = load_json(protocol_path) if CAMPAIGN and protocol_path.exists() else {}
        if "probe" in protocol.get("tiers", {}):
            require(brief, "new evolution candidates require a durable --brief")
            require(re.fullmatch(r"[0-9a-f]{40}", chosen), "parent must be an exact commit or baseline")
            population = evolution_population(protocol)
            receipt = population.validate_parent(brief, chosen)
            require(receipt.get("consumed_by") in (None, name), "proposal brief is already consumed")
            binding = receipt["parent_bindings"][chosen]
            git(ROOT, "merge-base", "--is-ancestor", baseline, chosen)
            actual_tree = git(ROOT, "rev-parse", chosen + "^{tree}")
            if binding.get("source_tree"):
                require(actual_tree == binding["source_tree"], "parent tree differs from durable brief")
            parent_candidate = binding.get("candidate")
            if parent_candidate:
                generation = population.eligible_parents()[parent_candidate]["generation"] + 1
            population.consume_brief(brief, chosen, name)
        else:
            require(chosen == baseline and not brief, "legacy campaigns use their frozen baseline")
        if CAMPAIGN and chosen == baseline:
            require_review_clear(CAMPAIGN, None, baseline)
        git(ROOT, "worktree", "add", "-b", "agents/" + name, str(root), chosen)
        record = {"id": name, "parent": chosen, "parent_commit": chosen,
                  "parent_candidate": parent_candidate, "generation": generation,
                  "baseline_commit": baseline, "brief_id": brief,
                  "worktree": str(root.relative_to(PROJECT)),
                  "status": "active", "hypothesis": hypothesis,
                  "created_unix": time.time(), "protocol_sha256": protocol_hash()}
        if mechanism is not None:
            record["mechanism"] = mechanism
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
    active()  # Refuse closed campaigns before creating the lock directory.
    with lock():
        return _check_candidate(name, static)


def _check_candidate(name, static=False):
    trusted_control()
    active()
    record, root = get_candidate(name)
    baseline = record.get("baseline_commit", record["parent"])
    result = diff_guard(root, baseline, policy())
    out = artifacts(name)
    out.mkdir(parents=True, exist_ok=True)
    if static:
        patch = git(root, "diff", "--no-ext-diff", "--no-textconv",
                    baseline, result["candidate_commit"], binary=True)
        target = STATE / "patches" / (name + ".patch") if CAMPAIGN else out / "candidate.patch"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(patch)
        commands = [
            ("diff-check", ["git", "-C", str(root), "diff", "--check",
                            baseline, result["candidate_commit"]], None),
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


def baseline_from(args, protocol):
    """Check the evidence named on the command line; return campaign.json's baseline_from."""
    source, _, cand = args.baseline_from.partition(":")
    require(source and cand and bool(args.evidence_row) != bool(args.evidence_report),
            "--baseline-from CAMPAIGN:CANDIDATE needs exactly one of --evidence-row, --evidence-report")
    source_dir = campaign_store.campaign_dir(source)
    require(campaign_store.load(source)["line"] == args.line,
            "inherited baseline must come from the same line")
    expected = seed()
    require(protocol.get("baseline_commit") == expected,
            "protocol baseline_commit does not match the campaign policy seed")
    if args.evidence_row:
        rows = load_json(source_dir / "ledger/ledger.json")
        row = next((r for r in rows if r.get("id") == args.evidence_row), None)
        require(row and row.get("candidate") == cand, "no ledger row for that candidate")
        require(row.get("status") == "FAST_PASS", "ledger row is not FAST_PASS")
        commit = row.get("candidate_commit")
        require(isinstance(commit, str) and re.fullmatch(r"[0-9a-f]{40}", commit),
                "ledger row has no full candidate_commit")
        require(git(ROOT, "rev-parse", "--verify", commit + "^{commit}") == commit,
                "inherited commit is not an exact existing commit")
        require(commit == expected, "inherited commit does not match destination baseline")
        require_review_clear(source, cand, commit)
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from population import advancement_evidence
        decision = advancement_evidence(row)
        require(decision["eligible"], "baseline advancement requires improvement above calibrated noise: " + decision["reason"])
        source_protocol = load_json(source_dir / "protocol.json")
        population = evolution_population(source_protocol, source_dir)
        entry = population.eligible_parents().get(cand)
        require(entry and entry["candidate_commit"] == commit and entry.get("fast_evidence_id") == row["id"],
                "baseline advancement requires current eligible archived source evidence")
        require(entry.get("advancement", {}).get("eligible") is True,
                "baseline advancement is blocked by current review or practical-value decision")
        require(entry["source_tree"] == git(ROOT, "rev-parse", commit + "^{tree}"), "inherited tree differs from archive")
        return {"campaign": source, "candidate": cand, "commit": row["candidate_commit"],
                "evidence": {"kind": "fast_pass", "ledger_row": args.evidence_row}}
    report = (PROJECT / args.evidence_report).resolve()
    require(report.is_relative_to(PROJECT.resolve()), "evidence report must be inside the repository")
    require(report.is_file(), "evidence report does not exist")
    commit = git(ROOT, "rev-parse", "--verify", f"refs/heads/agents/{cand}^{{commit}}")
    require(commit == expected, "inherited correctness commit does not match destination baseline")
    require_review_clear(source, cand, commit)
    path = report.relative_to(PROJECT.resolve())
    return {"campaign": source, "candidate": cand, "commit": commit,
            "evidence": {"kind": "correctness_fix", "report": str(path)}}


def open_campaign(args):
    # The scan, claim and record write share one machine lock, across campaign locks.
    with campaign_store.claim_lock():
        return _open_campaign(args)


def _open_campaign(args):
    require(CAMPAIGN, "open-campaign needs --campaign")
    directory = campaign_store.campaign_dir(CAMPAIGN)
    require((directory / "protocol.json").is_file(), "protocol.json is missing")
    require(not (directory / "campaign.json").exists(), "campaign.json already exists")
    config, base = policy(), scope_profile()
    require(set(config["allowed_modify"]) <= set(base["allowed_modify"]) and
            set(config["allowed_add"]) <= set(base["allowed_add"]),
            "campaign policy widens the base scope")
    require(args.machine == campaign_store.current_machine(),
            f"--machine {args.machine} is not this machine")
    for other in sorted(campaign_store.CAMPAIGNS.glob("*/campaign.json")):
        known = campaign_store.load(other.parent.name)
        require(not (known["status"] == "open" and known["machine"] == args.machine),
                f"campaign {known['campaign']} is already open on {args.machine}")
    protocol = load_json(directory / "protocol.json")
    require(protocol.get("campaign") == CAMPAIGN, "protocol campaign does not match directory")
    require(protocol.get("baseline_commit") == seed(), "protocol baseline_commit does not match policy seed")
    budget = dict(protocol["budget"])
    frozen = research_contract()
    if frozen is not None:
        import research
        contract = frozen["line_contract"]
        require(contract["line"] == args.line, "research line mismatch")
        readiness = research.capability_readout(base, protocol, config, PROJECT)
        require(readiness["ready"], "; ".join(readiness["missing_capabilities"]))
        line = research.validate_line(load_json(PROJECT / "campaigns/lines" / (args.line + ".json")))
        require(research.line_contract(line, base) == contract, "prepared scientific contract differs from line")
        spending = research.line_spending(PROJECT, args.line)
        admission = research.line_budget(line, spending, {
            "guest_attempts": budget["guest_attempts"] + budget.get("probe_guest_attempts", 0),
            "build_attempts": budget["build_attempts"]})
        require(admission["ready"], "; ".join(admission["reasons"]))
    if "probe" in protocol.get("tiers", {}):
        require(config["budget"]["max_candidates"] >= protocol["max_probe_candidates"],
                "controller max_candidates must cover max_probe_candidates")
    anchor = line_anchor(args.line, seed())
    if frozen is not None:
        require(frozen["line_contract"]["anchor_commit"] == anchor, "line anchor differs from frozen research contract")
    carried_origin, known_baselines = None, set()
    for path in sorted(campaign_store.CAMPAIGNS.glob("*/campaign.json")):
        old = campaign_store.load(path.parent.name)
        if old["line"] != args.line:
            continue
        source = path.with_name("protocol.json")
        if not source.exists() and old.get("protocol_ref"):
            source = PROJECT / old["protocol_ref"]
        old_baseline = load_json(source).get("baseline_commit") if source.is_file() else None
        if old_baseline:
            known_baselines.add(old_baseline)
            if old_baseline == seed():
                carried_origin = old.get("baseline_from")
    require(args.baseline_from or seed() == anchor or seed() in known_baselines,
            "a new baseline on an existing line requires --baseline-from with advancement or correctness evidence")
    record = {"campaign": CAMPAIGN, "status": "open", "line": args.line,
              "baseline_from": baseline_from(args, protocol) if args.baseline_from else carried_origin,
              "machine": args.machine, "opened": time.strftime("%Y-%m-%d", time.gmtime()),
              "closed": None, "line_anchor_commit": anchor,
              "budget": {"guest_attempts": budget["guest_attempts"],
                         "wall_seconds": budget["wall_seconds"],
                         "probe_guest_attempts": budget.get("probe_guest_attempts", 0),
                         "approved_over_cap": args.over_cap_approval or None}}
    errors = campaign_store.budget_errors(record)
    require(not errors, "; ".join(errors))
    campaign_store.take_claim(CAMPAIGN, locked=True)
    try:
        campaign_store.write(CAMPAIGN, record)
    except (OSError, ValueError):
        campaign_store.release_claim(CAMPAIGN, "open-campaign failed", locked=True)
        raise
    return record


def resume_campaign(reason):
    """Recover the existing campaign's claim without changing its scientific state."""
    require(CAMPAIGN, "resume-campaign needs --campaign")
    require(reason.strip(), "resume-campaign requires a reason")
    with campaign_store.claim_lock():
        record = campaign_store.require_open(CAMPAIGN)
        require(record["machine"] == campaign_store.current_machine(), "campaign belongs to another machine")
        directory = campaign_store.campaign_dir(CAMPAIGN)
        protocol, config, base = load_json(directory / "protocol.json"), policy(), load_json(BASE_POLICY)
        require(protocol.get("campaign") == CAMPAIGN, "protocol campaign does not match directory")
        require(protocol.get("baseline_commit") == seed(), "protocol baseline_commit does not match policy seed")
        require(set(config["allowed_modify"]) <= set(base["allowed_modify"]) and
                set(config["allowed_add"]) <= set(base["allowed_add"]), "campaign policy widens the base scope")
        for key in ("guest_attempts", "probe_guest_attempts", "wall_seconds"):
            require(protocol.get("budget", {}).get(key, 0) == record["budget"][key],
                    "protocol budget." + key + " does not match campaign.json")
        errors = campaign_store.budget_errors(record)
        require(not errors, "; ".join(errors))
        for path in campaign_store.CAMPAIGNS.glob("*/campaign.json"):
            other = campaign_store.load(path.parent.name)
            require(other["campaign"] == CAMPAIGN or other["status"] != "open" or
                    other["machine"] != record["machine"], "another campaign is open on this machine")
        campaign_store.take_claim(CAMPAIGN, locked=True)
        with campaign_store.claim_path().with_suffix(".log").open("a") as stream:
            stream.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} resumed {CAMPAIGN}: {reason}\n")
    return dict(record, claim_recovered=True)


def close_campaign(reason):
    with campaign_store.claim_lock():
        return _close_campaign(reason)


def _close_campaign(reason):
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
            campaign_store.release_claim(CAMPAIGN, reason, locked=True)
    from lines import generate
    generate(PROJECT)
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
    mechanisms_group = p.add_mutually_exclusive_group()
    mechanisms_group.add_argument("--mechanism", type=parse_mechanism)
    mechanisms_group.add_argument("--mechanism-spec", type=Path, help="reviewed_structure declaration for an approved profile")
    p.add_argument("--parent", default="baseline", help="baseline or the sampled exact parent commit")
    p.add_argument("--brief", help="durable proposal brief ID for a new evolution candidate")
    for name in ("guard", "check", "check-reference", "export"):
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
    for name in ("close-campaign", "release-claim", "resume-campaign"):
        commands.add_parser(name).add_argument("--reason", required=True)
    p = commands.add_parser("review-record")
    p.add_argument("name")
    p.add_argument("--review", type=Path, required=True, help="structured exact-tree review with hashed evidence")
    commands.add_parser("review-list")
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
        elif args.command == "resume-campaign":
            result = resume_campaign(args.reason)
        elif args.command == "release-claim":
            campaign_store.release_claim(None, args.reason)
            result = {"status": "RELEASED"}
        elif args.command == "review-record":
            result = record_review(args.name, args.review)
        elif args.command == "review-list":
            require(CAMPAIGN, "review-list needs --campaign")
            result = {"reviews": review_api().list_reviews(PROJECT, CAMPAIGN)}
        elif args.command == "new":
            mechanism = load_json(args.mechanism_spec) if args.mechanism_spec else args.mechanism
            result = create(args.name, args.hypothesis, mechanism, args.parent, args.brief)
        elif args.command == "check-reference":
            result = check_reference(args.name)
        elif args.command == "export":
            result = export_candidate(args.name)
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
