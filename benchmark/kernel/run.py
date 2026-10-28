#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Controller-owned KVM pilot runner. No performance acceptance is implied."""
import argparse,datetime,fcntl,hashlib,json,math,os,pathlib,re,signal,subprocess,time
from lifetime import bind_child_to_parent
BASE=pathlib.Path(__file__).resolve().parent
PROJECT=BASE.parents[1]
STOP=PROJECT/"campaigns/STOP"
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def percentile(a,p):return sorted(a)[math.ceil(len(a)*p)-1]/1000
def parse(log):
    lines=log.splitlines()
    samples=[int(m.group(1)) for m in re.finditer(r"^LATENCY_NS (\d+)\s*$",log,re.M)]
    hdr=re.search(r"LATENCY_BEGIN samples=(\d+) skipped=(\d+) minor=(\d+) major=(\d+)",log)
    snapshots={}
    for m in re.finditer(r"META_BEGIN (\w+)\s*\n(.*?)META_END",log,re.S):
        snapshots[m.group(1)]={k:int(v) for k,v in re.findall(r"^(\w+) (\d+)\s*$",m.group(2),re.M)}
    after=re.search(r"META_AFTER_SWAPOFF\s*\n(.*?)KERNEL_LOG_BEGIN",log,re.S)
    if after:snapshots["after_swapoff"]={k:int(v) for k,v in re.findall(r"^(\w+) (\d+)\s*$",after.group(1),re.M)}
    counts=[]
    for label in ["VMSTAT_BEFORE","VMSTAT_AFTER"]:
        m=re.search(label+r"\s*\n((?:(?:pswpin|pswpout|zswpin|zswpout) \d+\s*\n)+)",log)
        counts.append({k:int(v) for k,v in re.findall(r"(\w+) (\d+)",m.group(1))} if m else {})
    delta={k:counts[1].get(k,0)-v for k,v in counts[0].items()}
    diagnostics=[l for l in lines if any(x in l for x in ["WARNING:","BUG:","Oops:","Kernel panic","page allocation failure:","Out of memory:","Killed process"])]
    bootids=re.findall(r"^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\s*$",log,re.M)
    gates={"data_roundtrip":"KERNEL_WORKLOAD_PASS" in log,"fork_shared":"FORK_SHARED_PASS" in log,"cow":"COW_PASS" in log,
      "swapoff_live_data":"SWAPOFF_LIVE_PASS" in log,
      "swapoff":"EVOLVE_PASS" in log and snapshots.get("after_swapoff",{}).get("requested_live_bytes")==0,
      "sample_count":bool(hdr and len(samples)==int(hdr[1]) and len(samples)>=1000 and all(x>0 for x in samples)),
      "swap_activity":delta.get("pswpin",0)>0 and delta.get("pswpout",0)>0,
      "extend_path_exercised":snapshots.get("fork_shared",{}).get("extend_allocs",0)>0 and snapshots.get("after_reads",{}).get("extend_retained",0)>0,
      "no_kernel_warnings":not diagnostics,"boot_identity":len(bootids)==1,
      "completed":"EVOLVE_PASS" in log and "EVOLVE_FAIL" not in log}
    metrics={}
    if gates["sample_count"]:
        metrics={"swapped_first_access_p50_us":percentile(samples,.5),"swapped_first_access_p95_us":percentile(samples,.95),
          "swapped_first_access_p99_us":percentile(samples,.99),"samples":len(samples)}
    teardown=re.search(r"FORK_EXIT_NS (\d+)",log)
    if teardown:metrics["fork_exit_wall_ms"]=int(teardown[1])/1e6
    if snapshots.get("after_reads"):
        metrics["selected_metadata_requested_peak_bytes"]=snapshots["after_reads"].get("requested_peak_bytes")
    return {"gates":gates,"metrics":metrics,"snapshots":snapshots,"swap_delta":delta,
       "minor_faults":int(hdr[3]) if hdr else None,"major_faults":int(hdr[4]) if hdr else None,
       "diagnostics":diagnostics,"boot_id":bootids[0].strip() if len(bootids)==1 else None}
def main():
    p=argparse.ArgumentParser();p.add_argument("--build",required=True);p.add_argument("--backend",choices=["disk","zswap"],required=True);a=p.parse_args()
    # KVM-only runner. A TCG environment (Grok Bot's cloud box) must not start KVM.
    if os.environ.get("SWAP_NEXT_ACCEL", "kvm") != "kvm":
        raise SystemExit("KVM-only runner; refusing SWAP_NEXT_ACCEL=" + os.environ["SWAP_NEXT_ACCEL"])
    if not re.fullmatch("[a-z0-9-]{1,48}",a.build):raise SystemExit("invalid build name")
    if STOP.exists():raise SystemExit("STOP")
    BASE.joinpath("runs").mkdir(exist_ok=True)
    with (BASE/".runtime.lock").open("a") as lock:
      fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
      build=BASE/"builds"/a.build
      manifest=json.loads((build/"result.json").read_text())
      image=build/"output/arch/x86/boot/bzImage";initrd=BASE/"initramfs.cpio.gz";config=build/"output/.config"
      if not manifest["passed"] or sha(image)!=manifest["image_sha256"] or sha(config)!=manifest["config_sha256"]:raise SystemExit("build attestation mismatch")
      stamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
      dest=BASE/"runs"/(stamp+"-"+a.build+"-"+a.backend);dest.mkdir()
      disk=dest/"swap.raw"
      with disk.open("wb") as f:f.truncate(8*1024**3)
      append="console=ttyS0 rdinit=/init panic=-1 loglevel=3 zswap.enabled="+("1" if a.backend=="zswap" else "0")+" evolve.image_sha="+sha(image)
      cmd=["qemu-system-x86_64","-enable-kvm","-machine","pc","-cpu","host,migratable=off","-smp","2","-m","4096",
        "-nodefaults","-display","none","-serial","stdio","-monitor","none","-nic","none","-no-reboot",
        "-sandbox","on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny",
        "-kernel",str(image),"-initrd",str(initrd),"-append",append,
        "-drive","file="+str(disk)+",format=raw,if=virtio,cache=none"]
      result={"run":str(dest),"source_commit":manifest["commit"],"backend":a.backend,"build":a.build,
        "image_sha256":sha(image),"initrd_sha256":sha(initrd),"config_sha256":sha(config),
        "instrument_sha256":manifest["instrument_sha256"],"command":cmd,"performance_accepted":False,"auto_promote":False}
      start=time.monotonic();reason=None
      with (dest/"serial.log").open("w") as log:
        proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=bind_child_to_parent)
        try:
          while proc.poll() is None:
            if STOP.exists():reason="STOP";break
            if time.monotonic()-start>600:reason="timeout";break
            if (dest/"serial.log").stat().st_size>16*1024**2:reason="log budget";break
            time.sleep(.5)
        finally:
          if proc.poll() is None:
            os.killpg(proc.pid,signal.SIGTERM)
            try:proc.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
          disk.unlink(missing_ok=True)  # Scratch guest swap; nothing reads it after QEMU exits.
      result.update(exit_code=proc.returncode,stop_reason=reason,wall_seconds=time.monotonic()-start)
      result.update(parse((dest/"serial.log").read_text(errors="replace")))
      result["gates"]["backend_exercised"]=(all(result["swap_delta"].get(k,0)>0 for k in ["zswpin","zswpout"]) if a.backend=="zswap" else all(result["swap_delta"].get(k,0)==0 for k in ["zswpin","zswpout"]))
      result["gates"]["qemu_exit"]=proc.returncode==0 and reason is None
      result["pilot_pass"]=all(result["gates"].values())
      result["serial_sha256"]=sha(dest/"serial.log")
      (dest/"result.json").write_text(json.dumps(result,indent=2)+"\n")
      print(json.dumps(result,indent=2))
      raise SystemExit(0 if result["pilot_pass"] else 1)
if __name__=="__main__":main()
