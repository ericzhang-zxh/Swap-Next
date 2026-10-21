#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
import argparse,asyncio,fcntl,hashlib,json,pathlib,random,subprocess,sys,time,uuid
from openevolve.config import DatabaseConfig,EvaluatorConfig
from openevolve.database import Program,ProgramDatabase
from openevolve.evaluator import Evaluator
BASE=pathlib.Path(__file__).resolve().parent
PROJECT=BASE.parents[1]
CONTROL=PROJECT/"linux"
def main():
 p=argparse.ArgumentParser();p.add_argument("action",choices=["evaluate","next","status"]);p.add_argument("--candidate")
 a=p.parse_args();state=BASE/"state-v2";state.mkdir(exist_ok=True)
 with (state/".lock").open("a") as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  db=ProgramDatabase(DatabaseConfig(in_memory=True,population_size=8,archive_size=8,num_islands=1,random_seed=42))
  checkpoint=state/"database"
  if checkpoint.exists():db.load(str(checkpoint))
  protocol=json.loads((BASE/"protocol.json").read_text())
  baseline_id="baseline-"+protocol["baseline_commit"][:12]
  if not db.programs:
   db.add(Program(id=baseline_id,code="# Frozen baseline: "+protocol["baseline_commit"],language="diff",
          metrics={"combined_score":1.0},metadata={"type":"baseline_reference","measured":False}))
  ledgerfile=state/"ledger.json";ledger=json.loads(ledgerfile.read_text()) if ledgerfile.exists() else []
  if a.action=="evaluate":
   if len(ledger)>=protocol["max_candidates"]:raise SystemExit("candidate budget exhausted")
   records=json.loads((PROJECT/"system/state/candidates.json").read_text())
   if a.candidate not in records:raise SystemExit("unknown candidate")
   record=records[a.candidate];worktree=pathlib.Path(record["worktree"])
   commit=subprocess.check_output(["git","-C",str(worktree),"rev-parse","HEAD"],text=True).strip()
   if any(x["commit"]==commit for x in ledger):raise SystemExit("already evaluated; inspect retained report")
   patch=subprocess.check_output(["git","-C",str(worktree),"diff",record["parent"],commit],text=True)
   ident=str(uuid.uuid4())
   evaluator=Evaluator(EvaluatorConfig(timeout=7200,max_retries=0,cascade_evaluation=False,parallel_evaluations=1,
                   use_llm_feedback=False),str(BASE/"evaluate_kernel.py"),suffix=".json")
   metrics=asyncio.run(evaluator.evaluate_program(json.dumps({"candidate_id":a.candidate,"candidate_commit":commit,"evaluation_id":ident}),ident))
   report_path=BASE/"evaluations"/ident/"report.json"
   if not report_path.exists():
    report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_text(json.dumps({"evaluation_id":ident,"candidate_commit":commit,"status":"EVALUATOR_FAILED_BEFORE_REPORT","metrics":metrics,"auto_promote":False}))
   report=json.loads(report_path.read_text())
   pointer={"report":str(report_path)}
   if report["candidate_commit"]!=commit or report["evaluation_id"]!=ident:raise SystemExit("evaluation identity mismatch")
   row={"id":ident,"candidate":a.candidate,"commit":commit,"hypothesis":record["hypothesis"],"metrics":metrics,
       "report":pointer["report"],"performance_accepted":False,"auto_promote":False}
   # Failed candidates remain in ledger, never become selectable parents.
   if metrics.get("pilot_pass")==1 and report["status"]=="PILOT_COMPLETE_REVIEW_REQUIRED":
    db.programs[baseline_id].metadata.update(measured=True,report=pointer["report"])
    db.add(Program(id=ident,code=patch,language="diff",parent_id=baseline_id,generation=1,metrics=metrics,
         metadata={"commit":commit,"report":pointer["report"],"hypothesis":record["hypothesis"],"performance_accepted":False}))
   ledger.append(row);ledgerfile.write_text(json.dumps(ledger,indent=2)+"\n")
   db.save(str(checkpoint),iteration=len(ledger));print(json.dumps(row,indent=2))
  elif a.action=="next":
   rngfile=state/"selection-rng.json"
   def tuples(x):return tuple(tuples(y) for y in x) if isinstance(x,list) else x
   if rngfile.exists():random.setstate(tuples(json.loads(rngfile.read_text())))
   parent,inspirations=db.sample(num_inspirations=2)
   rngfile.write_text(json.dumps(random.getstate())+"\n")
   # Current guard requires all candidate patches to be based on the frozen seed.
   task={"selected_reference":parent.to_dict(),"inspirations":[x.to_dict() for x in inspirations],
      "required_patch_base":protocol["baseline_commit"],"controller":str(PROJECT/"system/controller.py"),
      "instruction":"Current assistant proposes one hypothesis and creates a new controller worktree. References are context; rebase the complete patch on the frozen seed. Do not edit evaluator/thresholds. Never auto-merge.",
      "recent_feedback":ledger[-3:],"remaining_candidates":protocol["max_candidates"]-len(ledger)}
   out=state/("task-"+str(time.time_ns())+".json");out.write_text(json.dumps(task,indent=2)+"\n")
   print(json.dumps({"task":str(out),**task},indent=2))
  else:
   print(json.dumps({"evaluated_candidates":len(ledger),"selectable_programs":len(db.programs),
       "ledger":ledger,"mode":"current-conversation proposer; no unattended model worker",
       "performance_acceptance_enabled":False,"auto_promote":False},indent=2))
if __name__=="__main__":main()
