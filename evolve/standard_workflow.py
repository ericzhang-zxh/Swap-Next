#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Bounded standard-suite adapter; ledger reservation precedes every side effect."""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmark/swap-standard"
WORKFLOW_FILE = Path(__file__).resolve()
sys.path.insert(0, str(ROOT / "benchmark/kernel"))
from lifetime import bind_child_to_parent

_spec = importlib.util.spec_from_file_location("campaign_store", ROOT / "evolve/control/campaign_store.py")
campaign_store = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(campaign_store)


# Module defaults name the standard campaign; select_campaign switches all of them.
CAMPAIGN = ROOT / "campaigns/swap-standard-2026-10-22"
PROTOCOL, STATE, ARCHIVE = CAMPAIGN / "protocol.json", CAMPAIGN / "ledger", CAMPAIGN / "archive"
EVALUATIONS, RUNS, TASKS = CAMPAIGN / "runs/evaluations", CAMPAIGN / "runs/guests", CAMPAIGN / "runs/tasks"


def select_campaign(name):
    """Use one campaign directory: its protocol, ledger, budget, calibration and runs."""
    global CAMPAIGN, PROTOCOL, STATE, ARCHIVE, EVALUATIONS, RUNS, TASKS
    campaign_store.load(name)  # refuses unknown campaigns before any path is used
    CAMPAIGN = campaign_store.campaign_dir(name)
    PROTOCOL, STATE, ARCHIVE = CAMPAIGN / "protocol.json", CAMPAIGN / "ledger", CAMPAIGN / "archive"
    EVALUATIONS, RUNS, TASKS = CAMPAIGN / "runs/evaluations", CAMPAIGN / "runs/guests", CAMPAIGN / "runs/tasks"


def read(path):
    return json.loads(Path(path).read_text())


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w") as f:
        f.write(json.dumps(data, indent=2, allow_nan=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def analysis_module():
    spec = importlib.util.spec_from_file_location("standard_analysis", BENCH / "analysis.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validity_module():
    spec = importlib.util.spec_from_file_location(
        "swap_validity", WORKFLOW_FILE.parents[1] / "benchmark/swap-standard/validity.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def child_env(protocol):
    """Pin the revision 3 guest. A TCG protocol forces SWAP_NEXT_ACCEL=tcg."""
    guest = protocol.get("guest") if isinstance(protocol.get("guest"), dict) else {}
    require = (protocol.get("accelerator") or {}).get("require") if isinstance(protocol.get("accelerator"), dict) else None
    if not guest and require != "tcg":
        return None
    env = os.environ.copy()
    if require == "tcg":
        env["SWAP_NEXT_ACCEL"] = "tcg"
    if "mem_mib" in guest:
        env["SWAP_NEXT_TCG_MEM_MIB"] = str(int(guest["mem_mib"]))
    if "vcpus" in guest:
        env["SWAP_NEXT_TCG_SMP"] = str(int(guest["vcpus"]))
    return env


def runner_extra(protocol):
    extra = ["--protocol-revision", str(protocol.get("protocol_revision", 1))]
    if protocol.get("preallocate_swap"):
        extra.append("--preallocate-swap")
    return extra


# Campaigns frozen before the campaign contract; they keep their own metrics.
CONTRACT_EXEMPT = {"swap-standard-2026-10-22", "confirm-h1-ra-phys-2026-10-23", "xswap-swapin-2026-10-23",
                   "xswap-next-2026-10-24", "xswap-tcg-rev3-2026-10-25"}
SWAPIN_PRIMARIES = {"swapin_seq.mean_ns", "swapin_rand.mean_ns"}
METADATA_METRIC = "metadata_delta_bytes_per_capacity_slot"


def contract_errors(p):
    """Every new campaign scores swap-in latency and screens metadata bytes per slot."""
    errors = []
    cases, tiers = p.get("cases", {}), p.get("tiers", {})
    for name, case in cases.items():
        if case.get("primary") not in SWAPIN_PRIMARIES | {None}:
            errors.append(name + ": primary must be a swap-in latency mean or null")
    fast = [cases.get(name, {}) for name in tiers.get("fast", {}).get("cases", [])]
    if not any(c.get("workload") == "swapin" and c.get("primary") in SWAPIN_PRIMARIES for c in fast):
        errors.append("fast tier needs a swapin case whose primary is a swap-in latency mean")
    if not any(c.get("workload") == "metadata" and c.get("metrics", {}).get(METADATA_METRIC) == "lower"
               for c in fast):
        errors.append("fast tier needs a metadata case scoring " + METADATA_METRIC)
    return errors


def fingerprint(p):
    paths = [PROTOCOL, BENCH / "image.json", ROOT / "evolve/loop.py", Path(__file__),
             ROOT / "evolve/control/controller.py", ROOT / "evolve/control/analysis.py",
             CAMPAIGN / "policy.json",
             ROOT / "benchmark/config/swap-standard.config"]
    paths += list(BENCH.glob("*.py")) + list(BENCH.glob("*.sh"))
    paths += [BENCH / name for name in ["guest-init", "tools.json", "swapin.c", "correctness.c", "console-drain.c"]]
    paths += [ROOT / "benchmark/kernel" / name for name in ["build.py", "lifetime.py", "build_namespace.sh"]]
    paths += [ROOT / "benchmark/kernel/builds" / p["baseline_build"] / "result.json"]
    return hashlib.sha256(json.dumps({str(f.relative_to(ROOT)): sha(f) for f in paths}, sort_keys=True).encode()).hexdigest()


def metric_spec(p, tier):
    directions = {}; primary = []
    for name in p["tiers"][tier]["cases"]:
        case = p["cases"][name]
        directions.update({name + "." + k: v for k, v in case["metrics"].items()})
        if case["primary"]:
            primary.append(name + "." + case["primary"])
    return directions, primary


def extract(metrics, path):
    value = metrics
    for name in path.split("."):
        value = value[name]
    return value


class Workflow:
    def __init__(self, p):
        self.p = p
        self.ledger_path = STATE / "ledger.json"
        self.ledger = read(self.ledger_path) if self.ledger_path.exists() else []
        self.budget_path = STATE / "budget.json"
        if self.budget_path.exists():
            self.budget = read(self.budget_path)
        else:
            self.budget = {"created": time.time(), "guests": 0, "builds": 0}
        self.stop = CAMPAIGN / "STOP"
        self.global_stop = campaign_store.GLOBAL_STOP
        # Holding the evaluation lock proves these are abandoned adapter calls.
        changed = False
        for row in self.ledger:
            if row["status"] == "RUNNING":
                changed = True
                report = EVALUATIONS / row["id"] / "report.json"
                if report.exists():
                    row.update(read(report))
                if row["status"] == "RUNNING":
                    row["status"] = "INTERRUPTED"
                    row["reason"] = "Adapter exited before completion; attempt retained, no retry"
                    save(report, row)
        if changed:
            save(self.ledger_path, self.ledger)

    def check(self):
        if self.stop.exists() or self.global_stop.exists():
            raise RuntimeError("STOP")
        if time.time() > self.budget["created"] + self.p["budget"]["wall_seconds"]:
            raise RuntimeError("campaign deadline")

    def reserve(self, kind):
        if kind == "guest":
            try:
                campaign_store.require_claim(self.p["campaign"])
            except campaign_store.CampaignError as exc:
                raise RuntimeError("BLOCKED: machine claim: " + str(exc))
        self.check()
        key, cap = ("guests", "guest_attempts") if kind == "guest" else ("builds", "build_attempts")
        if self.budget[key] >= self.p["budget"][cap]:
            raise RuntimeError("campaign " + key + " budget")
        self.budget[key] += 1
        save(self.budget_path, self.budget)

    def command(self, command, logfile, timeout, accept_failure=False, env=None):
        self.check()
        start = time.monotonic()
        with logfile.open("w") as output:
            proc = subprocess.Popen(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                    start_new_session=True, preexec_fn=bind_child_to_parent,
                                    env=env)
            try:
                while proc.poll() is None:
                    self.check()
                    if time.monotonic() - start > timeout:
                        raise RuntimeError("owned process timeout")
                    time.sleep(.5)
                if proc.returncode and not accept_failure:
                    raise RuntimeError("process failed; see " + str(logfile.relative_to(ROOT)))
            finally:
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
        return proc.returncode

    def calibration(self, tier, fp):
        path = STATE / ("calibration-" + tier + ".json")
        if not path.exists():
            raise RuntimeError("missing " + tier + " calibration")
        data = read(path)
        if data["fingerprint"] != fp or data["tier"] != tier:
            raise RuntimeError("stale calibration fingerprint")
        if time.time() - data["finished"] > self.p["calibration_max_age_seconds"]:
            raise RuntimeError("expired calibration")
        if not data["analysis"].get("passed"):
            raise RuntimeError("calibration noisy; stabilize baseline before comparison")
        return data

    def candidate(self, name, correctness):
        # Historical identities are explicitly held even if supplied as commit IDs.
        if name in campaign_store.candidates("xswap-structure-2026-10-22"):
            raise RuntimeError("BLOCKED: historical xswap candidate; unresolved descriptor lifetime")
        if name in self.p["blocked_commits"]:
            raise RuntimeError("BLOCKED: " + self.p["blocked_commits"][name])
        records = campaign_store.candidates(self.p["campaign"])
        if name not in records:
            raise RuntimeError("candidate absent from frozen controller campaign")
        record = records[name]
        worktree = str(ROOT / record["worktree"])
        commit = subprocess.check_output(["git", "-C", worktree, "rev-parse", "HEAD"], text=True).strip()
        if commit in self.p["blocked_commits"]:
            raise RuntimeError("BLOCKED: " + self.p["blocked_commits"][commit])
        proof = read(correctness) if correctness else {}
        # A direct guest result must pass every runner gate, including exit and identity.
        if "source_commit" in proof and proof.get("integration_pass") is not True:
            raise RuntimeError("guest correctness evidence failed integration")
        # A guest result.json names its kernel as source_commit.
        if proof.get("candidate_commit", proof.get("source_commit")) != commit or not all(proof.get("gates", {}).get(k) is True for k in self.p["required_correctness_gates"]):
            raise RuntimeError("missing exact-commit correctness evidence")
        return commit, record, proof

    def campaign_errors(self):
        """Closed or over-cap campaigns are refused before any ledger row or budget."""
        try:
            return campaign_store.budget_errors(campaign_store.require_open(self.p["campaign"]))
        except campaign_store.CampaignError as exc:
            return [str(exc)]

    def run(self, action, tier, candidate=None, correctness=None):
        ident = uuid.uuid4().hex
        row = {"id": ident, "action": action, "tier": tier, "candidate": candidate,
               "status": "RUNNING", "started": time.time(), "runs": [], "pairs": [],
               "performance_accepted": False, "auto_promote": False}
        errors = self.campaign_errors()
        if errors:
            row.update(status="BLOCKED", reason="BLOCKED: campaign: " + "; ".join(errors), finished=time.time())
            print(json.dumps({k: row.get(k) for k in ["id", "action", "tier", "status", "reason"]}, indent=2), flush=True)
            return row
        dest = EVALUATIONS / ident
        dest.mkdir(parents=True)
        self.ledger.append(row)
        save(self.ledger_path, self.ledger)
        save(dest / "report.json", row)
        try:
            self.check()
            if self.p["campaign"] not in CONTRACT_EXEMPT and contract_errors(self.p):
                raise RuntimeError("BLOCKED: protocol contract: " + "; ".join(contract_errors(self.p)))
            fp = fingerprint(self.p)
            row["fingerprint"] = fp
            if action == "calibrate":
                prior = [r for r in self.ledger[:-1] if r["action"] == action and r["tier"] == tier and
                         r.get("fingerprint") == fp and r.get("execution_started")]
                # A passed calibration may be renewed once it expires. A noisy or
                # incomplete one is never rerun under the same protocol.
                if prior and not (all(r.get("analysis", {}).get("passed") is True for r in prior) and
                                  time.time() - prior[-1].get("finished", time.time()) >
                                  self.p["calibration_max_age_seconds"]):
                    raise RuntimeError("calibration already attempted for this protocol; inspect retained evidence")
            count = self.p["tiers"][tier]["calibration_pairs" if action == "calibrate" else "comparison_pairs"]
            required_guests = count * 2 * len(self.p["tiers"][tier]["cases"])
            if self.budget["guests"] + required_guests > self.p["budget"]["guest_attempts"]:
                raise RuntimeError("insufficient guest budget for complete tier")
            build = self.p["baseline_build"]
            commit = self.p["baseline_commit"]
            calibration = None
            if action == "evaluate":
                commit, record, proof = self.candidate(candidate, correctness)
                row.update(candidate_commit=commit, correctness=proof)
                save(dest / "report.json", row)
                save(self.ledger_path, self.ledger)
                attempts = [r for r in self.ledger[:-1] if r.get("candidate_commit") == commit and r["tier"] == tier and r["action"] == action and r.get("execution_started")]
                if attempts:
                    raise RuntimeError("duplicate candidate tier attempt; retained prior result")
                candidates = {r.get("candidate_commit") for r in self.ledger[:-1] if r["action"] == action and r.get("candidate_commit")}
                if commit not in candidates and len(candidates) >= self.p["max_candidates"]:
                    raise RuntimeError("candidate budget")
                if tier == "slow" and not any(r.get("candidate_commit") == commit and r.get("fingerprint") == fp and r.get("analysis", {}).get("eligible_for_slow") is True and r["tier"] == "fast" and r["action"] == "evaluate" for r in self.ledger[:-1]):
                    raise RuntimeError("slow requires exact-commit current-fingerprint fast pass")
                checklog = dest / "controller-check.log"
                self.command([sys.executable, "evolve/control/controller.py", "--campaign", self.p["campaign"], "check", candidate], checklog, 180)
                checked = read(checklog)
                if checked.get("status") != "SCOPE_PASS" or checked.get("candidate_commit") != commit or checked.get("parent") != self.p["baseline_commit"]:
                    raise RuntimeError("controller scope check missing")
                row["controller_check"] = checked
                calibration = self.calibration(tier, fp)
                build = self.p.get("candidate_builds", {}).get(candidate, "std-" + commit[:12])
                if not re.fullmatch(r"[a-z0-9-]{1,48}", build):
                    raise RuntimeError("invalid protocol candidate build name")
                path = ROOT / "benchmark/kernel/builds" / build / "result.json"
                if not path.exists():
                    self.reserve("build")
                    row["execution_started"] = True
                    save(dest / "report.json", row)
                    self.command([sys.executable, "benchmark/kernel/build.py", "--commit", commit, "--name", build, "--config", "benchmark/config/swap-standard.config", "--no-instrumentation"], dest / "build.log", 1200)
                built = read(path)
                if (built.get("commit") != commit or built.get("input_config_sha256") != sha(ROOT / "benchmark/config/swap-standard.config") or built.get("passed") is not True or built.get("instrument_sha256", "missing") is not None):
                    raise RuntimeError("candidate build provenance mismatch")
            elif action == "reference-check":
                calibration = self.calibration(tier, fp)
            rules = validity_module().protocol_rules(self.p)
            row["protocol_revision"] = rules["protocol_revision"]
            try:
                row["protocol"] = str(PROTOCOL.resolve().relative_to(ROOT.resolve()))
            except ValueError:
                row["protocol"] = PROTOCOL.name
            row["candidate_commit"] = commit
            count = self.p["tiers"][tier]["calibration_pairs" if action == "calibrate" else "comparison_pairs"]
            env = child_env(self.p)
            extra = runner_extra(self.p)
            for pair_index in range(count):
                pair = {"a": {}, "b": {}, "order": "AB" if pair_index % 2 == 0 else "BA"}
                row["pairs"].append(pair)
                for case_name in self.p["tiers"][tier]["cases"]:
                    case = self.p["cases"][case_name]
                    arms = ("a", "b") if pair_index % 2 == 0 else ("b", "a")
                    for arm in arms:
                        prior = [item["wall_seconds"] for item in row["runs"]
                                 if item.get("case") == case_name and item.get("run_valid") is True]
                        reason = None
                        attempts = rules["max_reruns"] + 1 if rules["enforce_validity"] else 1
                        for attempt_index in range(attempts):
                            if fingerprint(self.p) != fp:
                                raise RuntimeError("trusted inputs changed during evaluation")
                            suffix = "" if attempt_index == 0 else "-r" + str(attempt_index)
                            run_id = ident + "-" + str(pair_index) + "-" + case_name + "-" + arm + suffix
                            chosen = self.p["baseline_build"] if arm == "a" else build
                            self.reserve("guest")
                            row["execution_started"] = True
                            attempt = {"id": run_id, "pair": pair_index, "case": case_name, "arm": arm,
                                       "attempt": attempt_index, "status": "STARTED"}
                            row["runs"].append(attempt)
                            save(dest / "report.json", row)
                            self.command([sys.executable, str(BENCH / "run.py"), "--build", chosen,
                                          "--backend", case["backend"], "--mode", case.get("mode", "plain"),
                                          "--workload", case["workload"], "--run-id", run_id,
                                          "--stop-file", str(self.stop), "--run-root", str(RUNS),
                                          "--timeout", str(self.p["budget"]["guest_timeout"]), *extra],
                                         dest / (run_id + ".log"), self.p["budget"]["guest_timeout"] + 60,
                                         accept_failure=True, env=env)
                            result_path = RUNS / run_id / "result.json"
                            if not result_path.is_file():
                                raise RuntimeError("missing run result")
                            result = read(result_path)
                            expected = self.p["baseline_commit"] if arm == "a" else commit
                            if result.get("source_commit") != expected or result.get("run_id") != run_id:
                                raise RuntimeError("run identity failed")
                            attempt.update(result=str(result_path.relative_to(ROOT)), result_sha256=sha(result_path),
                                           wall_seconds=result.get("wall_seconds"),
                                           pre_qemu_seconds=result.get("pre_qemu_seconds"),
                                           host_load=result.get("host_load"),
                                           accelerator=result.get("accelerator"),
                                           guest_mem_mib=result.get("guest_mem_mib"),
                                           guest_vcpus=result.get("guest_vcpus"),
                                           clocksource_invalid=result.get("clocksource_invalid"))
                            if not rules["enforce_validity"]:
                                if (result.get("integration_pass") is not True or
                                        result.get("swap_image_allocation", "sparse") !=
                                        ("preallocated" if self.p.get("preallocate_swap") else "sparse")):
                                    raise RuntimeError("run identity or correctness gate failed")
                                attempt.update(status="PASS", metrics=result["metrics"])
                                pair[arm].update({case_name + "." + key: extract(result["metrics"], key)
                                                  for key in case["metrics"]})
                                save(dest / "report.json", row)
                                break
                            valid, reason = validity_module().classify_attempt(result, prior, rules)
                            attempt["invalid_reason"] = reason
                            if not valid:
                                attempt.update(status="INVALID", run_valid=False)
                                save(dest / "report.json", row)
                                continue
                            guest = self.p.get("guest") if isinstance(self.p.get("guest"), dict) else {}
                            if guest and (result.get("guest_mem_mib") != int(guest["mem_mib"]) or
                                          result.get("guest_vcpus") != int(guest["vcpus"])):
                                raise RuntimeError("guest shape does not match protocol")
                            require_accel = (self.p.get("accelerator") or {}).get("require")
                            if require_accel and result.get("accelerator") != require_accel:
                                raise RuntimeError("accelerator does not match protocol")
                            if self.p.get("preallocate_swap") and result.get("swap_image_allocation") != "preallocated":
                                raise RuntimeError("swap image allocation mismatch")
                            if result.get("integration_pass") is not True:
                                attempt.update(status="FAIL", run_valid=False)
                                raise RuntimeError("run identity or correctness gate failed")
                            attempt.update(status="PASS", run_valid=True, metrics=result["metrics"])
                            pair[arm].update({case_name + "." + key: extract(result["metrics"], key)
                                              for key in case["metrics"]})
                            save(dest / "report.json", row)
                            break
                        else:
                            raise RuntimeError("validity reruns exhausted: " + str(reason))
            if fingerprint(self.p) != fp:
                raise RuntimeError("trusted inputs changed before analysis")
            directions, primary = metric_spec(self.p, tier)
            analysis = analysis_module()
            scored = [{k: pair[k] for k in ("a", "b")} for pair in row["pairs"]]
            if action == "calibrate":
                result = analysis.calibrate(scored, directions, primary=primary, envelope=rules["envelope"],
                                            min_pairs=count, noise_ceiling=rules["noise_ceiling"],
                                            noise_floor=rules["noise_floor"],
                                            advisory_suffixes=rules["advisory_suffixes"])
            else:
                result = analysis.compare(scored, directions, calibration["analysis"], tier,
                                          reference=action == "reference-check", primary=primary,
                                          decision=rules["decision"], min_pairs=count)
                row["calibration_id"] = calibration["id"]
            if fingerprint(self.p) != fp:
                raise RuntimeError("trusted inputs changed during analysis")
            row.update(analysis=result, status=result["status"], finished=time.time())
            if action == "calibrate":
                save(STATE / ("calibration-" + tier + ".json"), row)
            if action == "evaluate" and tier == "slow" and result.get("needs_review"):
                self.archive(row, record)
        except (Exception, KeyboardInterrupt) as exc:
            row.update(status="BLOCKED" if "BLOCKED:" in str(exc) else "INCOMPLETE", reason=str(exc), finished=time.time())
        finally:
            save(dest / "report.json", row)
            save(self.ledger_path, self.ledger)
        print(json.dumps({k: row.get(k) for k in ["id", "action", "tier", "status", "reason", "analysis"]}, indent=2), flush=True)
        return row

    def archive(self, row, record):
        from openevolve.config import DatabaseConfig
        from openevolve.database import Program, ProgramDatabase
        db = ProgramDatabase(DatabaseConfig(in_memory=True, population_size=8, archive_size=8, num_islands=1, random_seed=42))
        path = ARCHIVE / "database"
        if path.exists():
            db.load(str(path))
        patch = subprocess.check_output(["git", "-C", str(ROOT / record["worktree"]), "diff", self.p["baseline_commit"], row["candidate_commit"]], text=True)
        db.add(Program(id=row["id"], code=patch, language="diff", metrics={"combined_score": row["analysis"]["combined_score"]}, metadata={"commit": row["candidate_commit"], "report": str((EVALUATIONS / row["id"] / "report.json").relative_to(ROOT)), "review_required": True}))
        db.save(str(path), iteration=len(self.ledger))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["status", "plan", "next", "calibrate", "evaluate", "reference-check"])
    parser.add_argument("--tier", choices=["fast", "slow", "auto"], default="fast",
                        help="slow (and auto, which continues into slow) needs explicit owner approval; see AGENTS.md")
    parser.add_argument("--candidate")
    parser.add_argument("--correctness", type=Path)
    parser.add_argument("--campaign", default=CAMPAIGN.name,
                        help="campaign directory under campaigns/; revision 3 is xswap-tcg-rev3-2026-10-25")
    args = parser.parse_args(argv)
    select_campaign(args.campaign)
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        p = read(PROTOCOL)
        if p.get("campaign") != args.campaign:
            raise SystemExit("protocol campaign " + repr(p.get("campaign")) + " does not match " + args.campaign)
        validity_module().protocol_rules(p)
        workflow = Workflow(p)
        if args.action in ("status", "plan", "next"):
            fp = fingerprint(p)
            ready = {}
            for tier in p["tiers"]:
                try:
                    ready[tier] = workflow.calibration(tier, fp)["id"]
                except RuntimeError as exc:
                    ready[tier] = str(exc)
            output = {"campaign": p["campaign"], "fingerprint": fp, "budget": workflow.budget, "limits": p["budget"], "tiers": p["tiers"], "calibration": ready, "ledger": [{k: r.get(k) for k in ["id", "action", "tier", "candidate", "status"]} for r in workflow.ledger]}
            if args.action == "next":
                output["instruction"] = "Resolve correctness holds, then calibrate missing/noisy tiers. Only a calibrated fast tier may screen a controller candidate. Slow requires the exact fast-pass commit and explicit owner approval; no automatic promotion."
                output["references"] = []
                if (ARCHIVE / "database").exists():
                    from openevolve.config import DatabaseConfig
                    from openevolve.database import ProgramDatabase
                    db = ProgramDatabase(DatabaseConfig(in_memory=True, population_size=8, archive_size=8, num_islands=1, random_seed=42))
                    db.load(str(ARCHIVE / "database"))
                    if db.programs:
                        parent, inspirations = db.sample(num_inspirations=2)
                        output["references"] = [r.to_dict() for r in [parent, *inspirations]]
                output["required_patch_base"] = p["baseline_commit"]
                output["controller_campaign"] = p["campaign"]
                save(TASKS / ("task-" + uuid.uuid4().hex + ".json"), output)
            print(json.dumps(output, indent=2))
            return
        if args.action == "evaluate" and not args.candidate:
            parser.error("evaluate requires --candidate")
        if args.action == "reference-check" and args.tier == "slow":
            parser.error("reference-check is fast only")
        if args.tier == "auto":
            tiers = ["fast"] if args.action == "reference-check" else [name for name in ("fast", "slow") if name in p["tiers"]]
        else:
            if args.tier not in p["tiers"]:
                parser.error("protocol has no " + args.tier + " tier")
            tiers = [args.tier]
        for tier in tiers:
            row = workflow.run(args.action, tier, args.candidate, args.correctness)
            if row["status"] in ("INCOMPLETE", "BLOCKED"):
                raise SystemExit(1)
            if args.action == "evaluate" and tier == "fast" and not row.get("analysis", {}).get("eligible_for_slow"):
                break


if __name__ == "__main__":
    main()
