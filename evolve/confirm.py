#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Rotated multi-arm confirmation of a screened candidate; never accepts or promotes.

Each round runs every (case, arm) once through run.py, with the arm order
rotated per round so no arm always runs first. Every attempt is retained.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import time

PROJECT = Path(__file__).resolve().parents[1]
BASE = PROJECT / "benchmark/swap-standard"
sys.path.insert(0, str(PROJECT / "evolve/control"))
import campaign_store
STOP = PROJECT / "campaigns/STOP"


def save(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    tmp.replace(path)


def extract(metrics, key):
    for part in key.split("."):
        metrics = metrics[part]
    return metrics


def gmean(xs):
    from math import exp, log
    return exp(sum(log(x) for x in xs) / len(xs))


def analyze(p, rounds):
    """Per case/metric: each arm's ratio to the reference arm within a round."""
    rng = random.Random(p.get("seed", 1))
    out = {}
    ref = p["reference_arm"]
    for case, spec in p["cases"].items():
        for metric in spec["metrics"]:
            key = case + "." + metric
            values = {a: [r[case][a][metric] for r in rounds if a in r.get(case, {})] for a in spec["arms"]}
            row = {"values": values}
            refs = values[ref]
            mean = sum(refs) / len(refs)
            sd = (sum((x - mean) ** 2 for x in refs) / max(1, len(refs) - 1)) ** .5
            row["reference_cv_pct"] = 100 * sd / mean
            for arm in spec["arms"]:
                if arm == ref:
                    continue
                ratios = [r[case][arm][metric] / r[case][ref][metric] for r in rounds
                          if arm in r.get(case, {}) and ref in r.get(case, {})]
                boot = sorted(gmean([rng.choice(ratios) for _ in ratios]) for _ in range(p["bootstrap_resamples"]))
                lo, hi = boot[int(.025 * len(boot))], boot[int(.975 * len(boot)) - 1]
                row[arm + "/" + ref] = {"n": len(ratios), "gmean_ratio": gmean(ratios),
                                        "ci95": [lo, hi], "change_pct": 100 * (gmean(ratios) - 1),
                                        "ci95_excludes_1": lo > 1 or hi < 1}
            out[key] = row
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--analyze-only", action="store_true")
    args = parser.parse_args()
    p = json.loads(args.protocol.read_text())
    proto_sha = hashlib.sha256(args.protocol.read_bytes()).hexdigest()
    record = (campaign_store.load(p["campaign"]) if args.analyze_only
              else campaign_store.require_execution(p["campaign"]))
    read_only = record["status"] == "closed"
    state = PROJECT / "campaigns" / p["campaign"] / "ledger"
    if not read_only:
        state.mkdir(parents=True, exist_ok=True)
    ledger_path = state / "confirmation.json"
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {
        "campaign": p["campaign"], "protocol_sha256": proto_sha, "attempts": [], "rounds": []}
    if ledger["protocol_sha256"] != proto_sha:
        raise SystemExit("protocol changed after the confirmation started")
    if not args.analyze_only:
        jobs = [(c, a) for c, spec in p["cases"].items() for a in spec["arms"]]
        for index in range(len(ledger["rounds"]), p["rounds"]):
            shift = index % len(jobs)
            order = jobs[shift:] + jobs[:shift]
            rnd = {"index": index, "order": [c + ":" + a for c, a in order]}
            for case, arm in order:
                campaign_store.require_execution(p["campaign"])
                spec, arm_spec = p["cases"][case], p["arms"][arm]
                run_id = f"{p['campaign']}-{index}-{case}-{arm}"
                attempt = {"run_id": run_id, "round": index, "case": case, "arm": arm, "started": time.time()}
                ledger["attempts"].append(attempt)
                save(ledger_path, ledger)
                proc = subprocess.run([sys.executable, str(BASE / "run.py"), "--build", arm_spec["build"],
                                       "--backend", spec["backend"], "--mode", arm_spec["mode"],
                                       "--workload", spec["workload"], "--run-id", run_id,
                                       "--campaign", p["campaign"],
                                       "--run-root", str(PROJECT / "campaigns" / p["campaign"] / "runs/guests"),
                                       "--stop-file", str(PROJECT / "campaigns" / p["campaign"] / "STOP"),
                                       "--timeout", str(p["guest_timeout"])], capture_output=True, text=True)
                result_path = PROJECT / "campaigns" / p["campaign"] / "runs/guests" / run_id / "result.json"
                result = json.loads(result_path.read_text()) if result_path.exists() else {}
                attempt.update(exit=proc.returncode, integration_pass=result.get("integration_pass"),
                               source_commit=result.get("source_commit"), finished=time.time())
                if proc.returncode or result.get("integration_pass") is not True or \
                        result.get("source_commit") != arm_spec["commit"]:
                    attempt["status"] = "FAIL"
                    save(ledger_path, ledger)
                    raise SystemExit("attempt failed; retained: " + run_id + "\n" + proc.stdout[-2000:] + proc.stderr[-2000:])
                attempt.update(status="PASS", result_sha256=hashlib.sha256(result_path.read_bytes()).hexdigest())
                rnd.setdefault(case, {})[arm] = {m: extract(result["metrics"], m) for m in spec["metrics"]}
                save(ledger_path, ledger)
            ledger["rounds"].append(rnd)
            save(ledger_path, ledger)
    analysis = analyze(p, ledger["rounds"])
    if not read_only:
        save(state / "confirmation-analysis.json", {"campaign": p["campaign"], "protocol_sha256": proto_sha,
                                   "rounds": len(ledger["rounds"]), "performance_accepted": False,
                                   "auto_promote": False, "metrics": analysis})
    for key, row in analysis.items():
        cells = [f"{k} {v['change_pct']:+.1f}% [{100*(v['ci95'][0]-1):+.1f},{100*(v['ci95'][1]-1):+.1f}]"
                 for k, v in row.items() if "/" in k]
        print(f"{key:36s} refCV {row['reference_cv_pct']:5.1f}%  " + "  ".join(cells))


if __name__ == "__main__":
    main()
