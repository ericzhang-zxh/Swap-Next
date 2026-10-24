#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Reserve auxiliary work through the existing standard-suite workflow ledger."""
import argparse, fcntl, importlib.util, json, sys, time, uuid
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "evolve"))
import standard_workflow as sw
C = "xswap-next-2026-10-24"
p = argparse.ArgumentParser()
p.add_argument("kind", choices=["build", "guest"])
p.add_argument("--name", required=True)
p.add_argument("--candidate", required=True)
p.add_argument("--config", default="benchmark/config/swap-standard.config")
p.add_argument("--backend", choices=["disk", "zswap"], default="disk")
a=p.parse_args()
sw.select_protocol(ROOT / "benchmark/swap-standard" / ("protocol-" + C + ".json"))
sw.STATE.mkdir(parents=True, exist_ok=True)
with (sw.STATE / ".lock").open("a") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    w=sw.Workflow(sw.read(sw.PROTOCOL))
    records=sw.read(ROOT / "evolve/control/state" / C / "candidates.json")
    rec=records[a.candidate]
    import subprocess
    commit=subprocess.check_output(["git","-C",rec["worktree"],"rev-parse","HEAD"],text=True).strip()
    ident="aux-"+uuid.uuid4().hex
    dest=ROOT/"benchmark/swap-standard/evaluations"/ident
    dest.mkdir(parents=True)
    if a.kind=="build":
        cmd=[sys.executable,"benchmark/kernel/build.py","--commit",commit,"--name",a.name,"--config",a.config,"--no-instrumentation"]
        result=ROOT/"benchmark/kernel/builds"/a.name/"result.json"
    else:
        cmd=[sys.executable,"benchmark/swap-standard/run.py","--build",a.name,"--backend",a.backend,"--mode","xswap","--workload","correctness","--run-id",ident,"--timeout","900","--stop-file",str(w.stop)]
        if w.p.get("preallocate_swap"):
            cmd.append("--preallocate-swap")
        result=ROOT/"benchmark/swap-standard/runs"/ident/"result.json"
    row=dict(id=ident,action="auxiliary",kind=a.kind,tier="correctness",candidate=a.candidate,candidate_commit=commit,status="RUNNING",started=time.time(),command=cmd,result=str(result.relative_to(ROOT)),performance_accepted=False)
    w.ledger.append(row)
    try:
        w.reserve(a.kind)
        row["execution_started"]=True
        sw.save(dest/"report.json",row);sw.save(w.ledger_path,w.ledger)
        w.command(cmd,dest/"command.log",1200 if a.kind=="build" else 960)
        data=sw.read(result)
        if a.kind=="build":
            assert data.get("passed") is True and data["commit"]==commit
        else:
            assert data.get("integration_pass") is True and data["source_commit"]==commit
        row.update(status="PASS",result_sha256=sw.sha(result))
    except BaseException as exc:
        row.update(status="INCOMPLETE",reason=str(exc))
        raise
    finally:
        row["finished"]=time.time()
        sw.save(dest/"report.json",row);sw.save(w.ledger_path,w.ledger)
        print(json.dumps({k:row.get(k) for k in ["id","kind","candidate","status","reason","result"]},indent=2),flush=True)
