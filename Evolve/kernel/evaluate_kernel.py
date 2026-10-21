# SPDX-License-Identifier: GPL-2.0-only
"""Manifest evaluator; every accepted observation is bound to frozen inputs."""
import hashlib,json,math,pathlib,re,subprocess,time,uuid
BASE=pathlib.Path(__file__).resolve().parent
PROJECT=BASE.parents[1]
CONTROL=PROJECT/"linux"
SUITE=["protocol.json","evaluate_kernel.py","run.py","workload.c","guest-init","instrument.py","prepare-rootfs.py","lifetime.py"]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def invoke(cmd,log,timeout):
    with log.open("w") as out:
        p=subprocess.run(cmd,stdout=out,stderr=subprocess.STDOUT,timeout=timeout)
    if p.returncode:raise ValueError("stage failed: "+str(log))
def verify_run(run,expected,backend,seen):
    if not run.get("pilot_pass") or not all(run.get("gates",{}).values()):raise ValueError("guest pilot failed")
    if run.get("backend")!=backend:raise ValueError("backend identity mismatch")
    for k,v in expected.items():
        if run.get(k)!=v:raise ValueError("run provenance mismatch: "+k)
    boot=run.get("boot_id")
    if not boot or boot in seen:raise ValueError("missing/duplicate boot ID")
    seen.add(boot)
    delta=run.get("swap_delta",{})
    if backend=="zswap" and not all(delta.get(k,0)>0 for k in ["zswpin","zswpout"]):
        raise ValueError("zswap path was not exercised")
    if backend=="disk" and any(delta.get(k,0)!=0 for k in ["zswpin","zswpout"]):
        raise ValueError("unexpected zswap activity in disk run")
    for k in ["swapped_first_access_p99_us","selected_metadata_requested_peak_bytes","fork_exit_wall_ms"]:
        v=run.get("metrics",{}).get(k)
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0:
            raise ValueError("invalid measured metric: "+k)
    raw=pathlib.Path(run["run"])/"serial.log"
    if digest(raw)!=run["serial_sha256"]:raise ValueError("raw evidence hash mismatch")
def evaluate(program_path):
    request=json.loads(pathlib.Path(program_path).read_text())
    if set(request)!={"candidate_id","candidate_commit","evaluation_id"}:raise ValueError("invalid request schema")
    ident=request["candidate_id"];evaluation_id=str(uuid.UUID(request["evaluation_id"]))
    if not re.fullmatch("[a-z][a-z0-9-]{0,47}",ident):raise ValueError("invalid candidate ID")
    protocol=json.loads((BASE/"protocol.json").read_text())
    state=BASE/"evaluations"/evaluation_id;state.mkdir(parents=True,exist_ok=False)
    hashes={p:digest(BASE/p) for p in SUITE}
    for name in SUITE:(state/("frozen-"+name)).write_bytes((BASE/name).read_bytes())
    report={"evaluation_id":evaluation_id,"candidate_id":ident,"candidate_commit":request["candidate_commit"],
       "protocol_sha256":hashes["protocol.json"],"suite_sha256":hashes,
       "auto_promote":False,"performance_accepted":False,"status":"running","runs":[],
       "aggregation":"arithmetic mean of per-run p99, not pooled p99"}
    result={"pilot_pass":0.0,"combined_score":0.0}
    try:
        invoke(["python3",str(PROJECT/"system/controller.py"),"check",ident],state/"static.log",180)
        checked=json.loads((state/"static.log").read_text())
        if checked["status"]!="SCOPE_PASS" or checked["candidate_commit"]!=request["candidate_commit"]:
            raise ValueError("candidate SHA/static mismatch")
        if checked["parent"]!=protocol["baseline_commit"]:raise ValueError("stale baseline")
        baseline_path=BASE/"builds"/protocol["baseline_build"]/"result.json"
        baseline=json.loads(baseline_path.read_text())
        if baseline["commit"]!=protocol["baseline_commit"] or not baseline["passed"]:
            raise ValueError("baseline commit or pass mismatch")
        buildname=ident+"-"+request["candidate_commit"][:8];build=BASE/"builds"/buildname
        if not build.exists():
            invoke(["python3",str(BASE/"build.py"),"--commit",request["candidate_commit"],"--name",buildname,
              "--config",str(PROJECT/"config/kernel.config")],state/"build.log",1500)
        bm=json.loads((build/"result.json").read_text())
        if not bm["passed"] or bm["commit"]!=request["candidate_commit"]:raise ValueError("failed/stale build")
        if bm["instrument_sha256"]!=baseline["instrument_sha256"] or bm["instrument_sha256"]!=hashes["instrument.py"]:
            raise ValueError("instrumentation mismatch")
        if bm["config_sha256"]!=baseline["config_sha256"]:raise ValueError("config mismatch")
        frozen_initrd=digest(BASE/"initramfs.cpio.gz")
        report.update(build=bm,baseline_build=baseline,initrd_sha256=frozen_initrd,
           build_manifest_sha256=digest(build/"result.json"),baseline_manifest_sha256=digest(baseline_path))
        bootids=set()
        def unchanged():
            if hashes!={p:digest(BASE/p) for p in SUITE}:raise ValueError("suite changed during evaluation")
            if digest(BASE/"initramfs.cpio.gz")!=frozen_initrd:raise ValueError("initrd changed during evaluation")
        for backend in protocol["backends"]:
          for pair,order in enumerate(protocol["order"]):
            for side in order:
              unchanged()
              manifest=baseline if side=="A" else bm
              name=protocol["baseline_build"] if side=="A" else buildname
              log=state/(backend+"-"+str(pair)+"-"+side+".json")
              invoke(["python3",str(BASE/"run.py"),"--build",name,"--backend",backend],log,630)
              run=json.loads(log.read_text())
              expected={"source_commit":manifest["commit"],"image_sha256":manifest["image_sha256"],
                 "config_sha256":manifest["config_sha256"],"instrument_sha256":hashes["instrument.py"],"initrd_sha256":frozen_initrd}
              verify_run(run,expected,backend,bootids)
              report["runs"].append({"side":side,"pair":pair,**run})
        unchanged()
        keys=["swapped_first_access_p99_us","selected_metadata_requested_peak_bytes","fork_exit_wall_ms"]
        groups={}
        for backend in protocol["backends"]:
          groups[backend]={}
          for side in ["A","B"]:
            rs=[r for r in report["runs"] if r["backend"]==backend and r["side"]==side]
            groups[backend][side]={k:sum(r["metrics"][k] for r in rs)/len(rs) for k in keys}
        score=min(groups[b]["A"]["swapped_first_access_p99_us"]/groups[b]["B"]["swapped_first_access_p99_us"] for b in groups)
        if not math.isfinite(score) or score<=0:raise ValueError("invalid score")
        result={"pilot_pass":1.0,"combined_score":score,"latency_worst_backend_relative_score":score,
          "metadata_peak_ratio":max(groups[b]["B"]["selected_metadata_requested_peak_bytes"]/groups[b]["A"]["selected_metadata_requested_peak_bytes"] for b in groups)}
        report.update(status="PILOT_COMPLETE_REVIEW_REQUIRED",metrics=result,comparison=groups)
    except Exception as e:
        report.update(status="FAILED_OR_INCOMPLETE",error=type(e).__name__+": "+str(e))
    report["missing_acceptance_gates"]=protocol["unimplemented_acceptance_gates"]
    (state/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    return result
