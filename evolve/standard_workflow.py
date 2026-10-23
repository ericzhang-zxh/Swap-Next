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
STATE = ROOT / "evolve/swap-standard/state-layout-v1"
PROTOCOL = BENCH / "protocol.json"


def select_protocol(path):
    """Use another frozen protocol with its own ledger, budget and calibration."""
    global STATE, PROTOCOL
    PROTOCOL = path.resolve()
    if PROTOCOL != (BENCH / "protocol.json").resolve():
        STATE = ROOT / "evolve/swap-standard" / ("state-" + read(PROTOCOL)["campaign"])
sys.path.insert(0, str(ROOT / "benchmark/kernel"))
from lifetime import bind_child_to_parent


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


def fingerprint(p):
    paths = [PROTOCOL, BENCH / "image.json", ROOT / "evolve/loop.py", Path(__file__),
             ROOT / "evolve/control/controller.py", ROOT / "evolve/control/analysis.py",
             ROOT / "evolve/control/campaigns" / p["campaign"] / "policy.json",
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
        self.stop = ROOT / "evolve/control/state" / p["campaign"] / "STOP"
        self.global_stop = ROOT / "evolve/control/state/STOP"
        # Holding the evaluation lock proves these are abandoned adapter calls.
        for row in self.ledger:
            if row["status"] == "RUNNING":
                report = BENCH / "evaluations" / row["id"] / "report.json"
                if report.exists():
                    row.update(read(report))
                if row["status"] == "RUNNING":
                    row["status"] = "INTERRUPTED"
                    row["reason"] = "Adapter exited before completion; attempt retained, no retry"
                    save(report, row)
        save(self.ledger_path, self.ledger)

    def check(self):
        if self.stop.exists() or self.global_stop.exists():
            raise RuntimeError("STOP")
        if time.time() > self.budget["created"] + self.p["budget"]["wall_seconds"]:
            raise RuntimeError("campaign deadline")

    def reserve(self, kind):
        self.check()
        key, cap = ("guests", "guest_attempts") if kind == "guest" else ("builds", "build_attempts")
        if self.budget[key] >= self.p["budget"][cap]:
            raise RuntimeError("campaign " + key + " budget")
        self.budget[key] += 1
        save(self.budget_path, self.budget)

    def command(self, command, logfile, timeout):
        self.check()
        start = time.monotonic()
        with logfile.open("w") as output:
            proc = subprocess.Popen(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                    start_new_session=True, preexec_fn=bind_child_to_parent)
            try:
                while proc.poll() is None:
                    self.check()
                    if time.monotonic() - start > timeout:
                        raise RuntimeError("owned process timeout")
                    time.sleep(.5)
                if proc.returncode:
                    raise RuntimeError("process failed; see " + str(logfile.relative_to(ROOT)))
            finally:
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()

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
        old = ROOT / "evolve/control/state/xswap-structure-2026-10-22/candidates.json"
        if old.exists():
            records = read(old)
            if name in records:
                raise RuntimeError("BLOCKED: historical xswap candidate; unresolved descriptor lifetime")
        if name in self.p["blocked_commits"]:
            raise RuntimeError("BLOCKED: " + self.p["blocked_commits"][name])
        path = ROOT / "evolve/control/state" / self.p["campaign"] / "candidates.json"
        records = read(path) if path.exists() else {}
        if name not in records:
            raise RuntimeError("candidate absent from frozen controller campaign")
        record = records[name]
        worktree = record["worktree"]
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

    def run(self, action, tier, candidate=None, correctness=None):
        ident = uuid.uuid4().hex
        dest = BENCH / "evaluations" / ident
        dest.mkdir(parents=True)
        row = {"id": ident, "action": action, "tier": tier, "candidate": candidate,
               "status": "RUNNING", "started": time.time(), "runs": [], "pairs": [],
               "performance_accepted": False, "auto_promote": False}
        self.ledger.append(row)
        save(self.ledger_path, self.ledger)
        save(dest / "report.json", row)
        try:
            self.check()
            fp = fingerprint(self.p)
            row["fingerprint"] = fp
            if action == "calibrate" and any(r["action"] == action and r["tier"] == tier and r.get("fingerprint") == fp and r.get("execution_started") for r in self.ledger[:-1]):
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
            row["candidate_commit"] = commit
            count = self.p["tiers"][tier]["calibration_pairs" if action == "calibrate" else "comparison_pairs"]
            for pair_index in range(count):
                pair = {"a": {}, "b": {}, "order": "AB" if pair_index % 2 == 0 else "BA"}
                row["pairs"].append(pair)
                for case_name in self.p["tiers"][tier]["cases"]:
                    case = self.p["cases"][case_name]
                    for arm in ("a", "b") if pair_index % 2 == 0 else ("b", "a"):
                        if fingerprint(self.p) != fp:
                            raise RuntimeError("trusted inputs changed during evaluation")
                        run_id = ident + "-" + str(pair_index) + "-" + case_name + "-" + arm
                        chosen = self.p["baseline_build"] if arm == "a" else build
                        self.reserve("guest")
                        row["execution_started"] = True
                        attempt = {"id": run_id, "pair": pair_index, "case": case_name, "arm": arm, "status": "STARTED"}
                        row["runs"].append(attempt)
                        save(dest / "report.json", row)
                        self.command([sys.executable, str(BENCH / "run.py"), "--build", chosen, "--backend", case["backend"], "--mode", case.get("mode", "plain"), "--workload", case["workload"], "--run-id", run_id, "--stop-file", str(self.stop), "--timeout", str(self.p["budget"]["guest_timeout"])], dest / (run_id + ".log"), self.p["budget"]["guest_timeout"] + 60)
                        result_path = BENCH / "runs" / run_id / "result.json"
                        result = read(result_path)
                        expected = self.p["baseline_commit"] if arm == "a" else commit
                        if result.get("source_commit") != expected or result.get("integration_pass") is not True or result.get("run_id") != run_id:
                            raise RuntimeError("run identity or correctness gate failed")
                        attempt.update(status="PASS", result=str(result_path.relative_to(ROOT)), result_sha256=sha(result_path), metrics=result["metrics"])
                        pair[arm].update({case_name + "." + key: extract(result["metrics"], key) for key in case["metrics"]})
                        save(dest / "report.json", row)
            if fingerprint(self.p) != fp:
                raise RuntimeError("trusted inputs changed before analysis")
            directions, primary = metric_spec(self.p, tier)
            analysis = analysis_module()
            if action == "calibrate":
                result = analysis.calibrate([{k: pair[k] for k in ("a", "b")} for pair in row["pairs"]], directions, primary=primary)
            else:
                result = analysis.compare([{k: pair[k] for k in ("a", "b")} for pair in row["pairs"]], directions, calibration["analysis"], tier, reference=action == "reference-check", primary=primary)
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
        path = STATE / "database"
        if path.exists():
            db.load(str(path))
        patch = subprocess.check_output(["git", "-C", record["worktree"], "diff", self.p["baseline_commit"], row["candidate_commit"]], text=True)
        db.add(Program(id=row["id"], code=patch, language="diff", metrics={"combined_score": row["analysis"]["overall_geomean_ratio"]}, metadata={"commit": row["candidate_commit"], "report": str((BENCH / "evaluations" / row["id"] / "report.json").relative_to(ROOT)), "review_required": True}))
        db.save(str(path), iteration=len(self.ledger))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["status", "plan", "next", "calibrate", "evaluate", "reference-check"])
    parser.add_argument("--tier", choices=["fast", "slow", "auto"], default="auto")
    parser.add_argument("--candidate")
    parser.add_argument("--correctness", type=Path)
    parser.add_argument("--protocol", type=Path, default=PROTOCOL)
    args = parser.parse_args(argv)
    select_protocol(args.protocol)
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        p = read(PROTOCOL)
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
                output["instruction"] = "Resolve correctness holds, then calibrate missing/noisy tiers. Only a calibrated fast tier may screen a controller candidate. Slow requires the exact fast-pass commit; no automatic promotion."
                output["references"] = []
                if (STATE / "database").exists():
                    from openevolve.config import DatabaseConfig
                    from openevolve.database import ProgramDatabase
                    db = ProgramDatabase(DatabaseConfig(in_memory=True, population_size=8, archive_size=8, num_islands=1, random_seed=42))
                    db.load(str(STATE / "database"))
                    if db.programs:
                        parent, inspirations = db.sample(num_inspirations=2)
                        output["references"] = [r.to_dict() for r in [parent, *inspirations]]
                output["required_patch_base"] = p["baseline_commit"]
                output["controller_campaign"] = p["campaign"]
                save(STATE / ("task-" + uuid.uuid4().hex + ".json"), output)
            print(json.dumps(output, indent=2))
            return
        if args.action == "evaluate" and not args.candidate:
            parser.error("evaluate requires --candidate")
        if args.action == "reference-check" and args.tier == "slow":
            parser.error("reference-check is fast only")
        tiers = (["fast"] if args.action == "reference-check" else ["fast", "slow"]) if args.tier == "auto" else [args.tier]
        for tier in tiers:
            row = workflow.run(args.action, tier, args.candidate, args.correctness)
            if row["status"] in ("INCOMPLETE", "BLOCKED"):
                raise SystemExit(1)
            if args.action == "evaluate" and tier == "fast" and not row.get("analysis", {}).get("eligible_for_slow"):
                break


if __name__ == "__main__":
    main()
