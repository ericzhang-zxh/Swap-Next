#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""OpenEvolve adapter shared by every benchmark suite.

OpenEvolve stores evaluated candidates and samples references for the next
proposal. The proposer is the assistant in the current session; this script
never calls a model. Each suite keeps its own state under
evolve/<suite>/state-layout-v1.
"""
import argparse
import asyncio
import fcntl
import json
import pathlib
import random
import subprocess
import sys
import time
import uuid

PROJECT = pathlib.Path(__file__).resolve().parents[1]
# Suite name -> whether its evaluator implements an A/A calibration request.
SUITES = {"kernel": False, "xswap": True, "xswap-structure": True}
INSTRUCTION = ("Propose one hypothesis and create a new controller worktree. "
               "References are context; base the complete patch on the frozen seed. "
               "Do not edit the evaluator or thresholds. Never auto-merge.")


def _openevolve():
    from openevolve.config import DatabaseConfig, EvaluatorConfig
    from openevolve.database import Program, ProgramDatabase
    from openevolve.evaluator import Evaluator
    return DatabaseConfig, EvaluatorConfig, Program, ProgramDatabase, Evaluator


class Suite:
    def __init__(self, name):
        self.name = name
        self.bench = PROJECT / "benchmark" / name
        self.state = PROJECT / "evolve" / name / "state-layout-v1"
        self.protocol = json.loads((self.bench / "protocol.json").read_text())
        self.campaign = self.protocol.get("campaign")
        self.baseline_id = "baseline-" + self.protocol["baseline_commit"][:12]

    def candidates(self):
        state = PROJECT / "evolve/control/state"
        if self.campaign:
            state = state / self.campaign
        return json.loads((state / "candidates.json").read_text())

    def report_path(self, ident):
        return self.bench / "evaluations" / ident / "report.json"


def open_database(suite):
    DatabaseConfig, _, Program, ProgramDatabase, _ = _openevolve()
    db = ProgramDatabase(DatabaseConfig(in_memory=True, population_size=8, archive_size=8,
                                        num_islands=1, random_seed=42))
    if (suite.state / "database").exists():
        db.load(str(suite.state / "database"))
    if not db.programs:
        db.add(Program(id=suite.baseline_id, language="diff",
                       code="# Frozen baseline: " + suite.protocol["baseline_commit"],
                       metrics={"combined_score": 1.0},
                       metadata={"type": "baseline_reference", "measured": False}))
    return db


def calibrate(suite, db):
    if not SUITES[suite.name]:
        raise SystemExit(suite.name + " has no A/A calibration step")
    sys.path.insert(0, str(suite.bench))
    from evaluate_kernel import evaluate

    ident = str(uuid.uuid4())
    request = suite.state / ("calibration-" + ident + ".json")
    request.write_text(json.dumps({"candidate_id": "calibration-aa", "evaluation_id": ident,
                                   "candidate_commit": suite.protocol["baseline_commit"]}))
    metrics = evaluate(str(request))
    report = suite.report_path(ident)
    calibration = suite.bench / "state-layout-v1" / "calibration.json"
    calibration.parent.mkdir(exist_ok=True)
    calibration.write_bytes(report.read_bytes())
    passed = metrics.get("pilot_pass") == 1
    if passed:
        db.programs[suite.baseline_id].metadata.update(measured=True,
                                                       calibration_report=str(report))
        db.save(str(suite.state / "database"), iteration=0)
    print(json.dumps({"metrics": metrics, "report": str(report)}, indent=2))
    raise SystemExit(0 if passed else 1)


def evaluate_candidate(suite, db, ledger, name):
    if len(ledger) >= suite.protocol["max_candidates"]:
        raise SystemExit("candidate budget exhausted")
    records = suite.candidates()
    if name not in records:
        raise SystemExit("unknown candidate")
    record = records[name]
    worktree = record["worktree"]
    commit = subprocess.check_output(["git", "-C", worktree, "rev-parse", "HEAD"],
                                     text=True).strip()
    if any(row["commit"] == commit for row in ledger):
        raise SystemExit("already evaluated; inspect the retained report")
    patch = subprocess.check_output(["git", "-C", worktree, "diff", record["parent"], commit],
                                    text=True)

    ident = str(uuid.uuid4())
    _, EvaluatorConfig, Program, _, Evaluator = _openevolve()
    evaluator = Evaluator(EvaluatorConfig(timeout=7200, max_retries=0, cascade_evaluation=False,
                                          parallel_evaluations=1, use_llm_feedback=False),
                          str(suite.bench / "evaluate_kernel.py"), suffix=".json")
    request = json.dumps({"candidate_id": name, "candidate_commit": commit,
                          "evaluation_id": ident})
    metrics = asyncio.run(evaluator.evaluate_program(request, ident))

    report_path = suite.report_path(ident)
    if not report_path.exists():
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps({"evaluation_id": ident, "candidate_commit": commit,
                                           "status": "EVALUATOR_FAILED_BEFORE_REPORT",
                                           "metrics": metrics}))
    report = json.loads(report_path.read_text())
    if report["candidate_commit"] != commit or report["evaluation_id"] != ident:
        raise SystemExit("evaluation identity mismatch")

    row = {"id": ident, "candidate": name, "commit": commit, "hypothesis": record["hypothesis"],
           "metrics": metrics, "report": str(report_path)}
    # Every attempt enters the ledger; only completed pilots become references.
    if metrics.get("pilot_pass") == 1 and report["status"] == "PILOT_COMPLETE_REVIEW_REQUIRED":
        db.programs[suite.baseline_id].metadata.update(measured=True, report=str(report_path))
        db.add(Program(id=ident, code=patch, language="diff", parent_id=suite.baseline_id,
                       generation=1, metrics=metrics,
                       metadata={"commit": commit, "report": str(report_path),
                                 "hypothesis": record["hypothesis"]}))
    ledger.append(row)
    (suite.state / "ledger.json").write_text(json.dumps(ledger, indent=2) + "\n")
    db.save(str(suite.state / "database"), iteration=len(ledger))
    print(json.dumps(row, indent=2))


def next_task(suite, db, ledger):
    rngfile = suite.state / "selection-rng.json"

    def tuples(x):
        return tuple(tuples(y) for y in x) if isinstance(x, list) else x

    if rngfile.exists():
        random.setstate(tuples(json.loads(rngfile.read_text())))
    parent, inspirations = db.sample(num_inspirations=2)
    rngfile.write_text(json.dumps(random.getstate()) + "\n")
    task = {"selected_reference": parent.to_dict(),
            "inspirations": [x.to_dict() for x in inspirations],
            "required_patch_base": suite.protocol["baseline_commit"],
            "controller": str(PROJECT / "evolve/control/controller.py"),
            "campaign": suite.campaign,
            "instruction": INSTRUCTION,
            "recent_feedback": ledger[-3:],
            "remaining_candidates": suite.protocol["max_candidates"] - len(ledger)}
    out = suite.state / ("task-" + str(time.time_ns()) + ".json")
    out.write_text(json.dumps(task, indent=2) + "\n")
    print(json.dumps({"task": str(out), **task}, indent=2))


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "swap-standard":
        from standard_workflow import main as standard_main
        return standard_main(sys.argv[2:])
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("suite", choices=sorted(SUITES))
    parser.add_argument("action", choices=["status", "next", "evaluate", "calibrate"])
    parser.add_argument("--candidate")
    args = parser.parse_args()

    suite = Suite(args.suite)
    suite.state.mkdir(parents=True, exist_ok=True)
    with (suite.state / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        db = open_database(suite)
        ledgerfile = suite.state / "ledger.json"
        ledger = json.loads(ledgerfile.read_text()) if ledgerfile.exists() else []
        if args.action == "calibrate":
            calibrate(suite, db)
        elif args.action == "evaluate":
            if not args.candidate:
                raise SystemExit("evaluate requires --candidate")
            evaluate_candidate(suite, db, ledger, args.candidate)
        elif args.action == "next":
            next_task(suite, db, ledger)
        else:
            print(json.dumps({"suite": suite.name, "campaign": suite.campaign,
                              "evaluated_candidates": len(ledger),
                              "selectable_programs": len(db.programs),
                              "ledger": ledger}, indent=2))


if __name__ == "__main__":
    main()
