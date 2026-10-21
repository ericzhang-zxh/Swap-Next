#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build a pinned source snapshot inside unprivileged Linux namespaces."""
import argparse, hashlib, json, os, pathlib, shutil, signal, subprocess, time
from lifetime import bind_child_to_parent
BASE=pathlib.Path(__file__).resolve().parent
PROJECT=BASE.parents[1]
CONTROL=PROJECT/"linux"
STOP=PROJECT/"evolve/control/state/STOP"
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def run(cmd, log, timeout=900, output=None):
    start=time.monotonic(); why=None
    with log.open("w") as f:
        proc=subprocess.Popen(cmd,stdout=f,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=bind_child_to_parent)
        try:
            while proc.poll() is None:
                if STOP.exists(): why="STOP"; break
                if time.monotonic()-start>timeout: why="timeout"; break
                if output and sum(x.stat().st_size for x in output.rglob("*") if x.is_file() and not x.is_symlink())>2*1024**3:
                    why="build output budget";break
                time.sleep(1)
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid,signal.SIGTERM)
                try: proc.wait(timeout=5)
                except subprocess.TimeoutExpired: os.killpg(proc.pid,signal.SIGKILL);proc.wait()
    return {"exit_code":proc.returncode,"reason":why,"wall_seconds":time.monotonic()-start}
def main():
    p=argparse.ArgumentParser();p.add_argument("--commit",required=True);p.add_argument("--name",required=True)
    p.add_argument("--config",type=pathlib.Path,required=True);p.add_argument("--probe",action="store_true")
    p.add_argument("--no-instrumentation",action="store_true",help="Build without the legacy swap metadata overlay; requires a separate evaluation protocol")
    a=p.parse_args()
    if STOP.exists(): raise SystemExit("STOP")
    if not __import__("re").fullmatch("[a-z0-9-]{1,48}",a.name): raise SystemExit("invalid name")
    commit=subprocess.check_output(["git","-C",str(CONTROL),"rev-parse",a.commit+"^{commit}"],text=True).strip()
    dest=BASE/"builds"/a.name
    dest.mkdir(parents=True,exist_ok=False)
    source=dest/"source";source.mkdir()
    # Only immutable Git objects, never uncommitted worker scripts.
    archive=dest/"source.tar"
    with archive.open("wb") as f: subprocess.run(["git","-C",str(CONTROL),"archive",commit],stdout=f,check=True,timeout=120)
    subprocess.run(["tar","-xf",str(archive),"-C",str(source)],check=True,timeout=120)
    archive.unlink()
    overlay=BASE/"instrument.py"
    if not a.no_instrumentation and overlay.exists():
        subprocess.run(["python3",str(overlay),str(source)],check=True,timeout=30)
    out=dest/"output";out.mkdir();shutil.copyfile(a.config,out/".config")
    root=dest/"root";root.mkdir()
    cmd=["unshare","--user","--map-root-user","--mount","--net","--pid","--fork","--kill-child",
         "bash",str(BASE/"build_namespace.sh"),str(root),str(source),str(out),"probe" if a.probe else "build"]
    meta={"commit":commit,"input_config_sha256":sha(a.config),"instrument_sha256":sha(overlay) if not a.no_instrumentation and overlay.exists() else None,
          "isolation":"user/mount/pid/net namespaces, readonly source/toolchain, capabilities dropped",
          "security_limit":"shared host kernel; same-user controller/proposer not isolated; per-process AS limit, monitored disk budget",
          "command":cmd}
    meta.update(run(cmd,dest/"build.log",timeout=900,output=out))
    image=out/"arch/x86/boot/bzImage"
    meta["passed"]=meta["exit_code"]==0 and (a.probe or image.is_file())
    if image.exists():meta.update(image=str(image),image_sha256=sha(image),config_sha256=sha(out/".config"))
    (dest/"result.json").write_text(json.dumps(meta,indent=2)+"\n")
    print(json.dumps(meta,indent=2))
    raise SystemExit(0 if meta["passed"] else 1)
if __name__=="__main__":main()
