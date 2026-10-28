#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Controller-owned KVM pilot runner. No performance acceptance is implied."""
import argparse,datetime,fcntl,hashlib,json,math,os,pathlib,re,signal,subprocess,time,shutil
from lifetime import bind_child_to_parent
BASE=pathlib.Path(__file__).resolve().parent
PROJECT=BASE.parents[1]
def campaign_stop(protocol):
    return PROJECT/"campaigns"/protocol["campaign"]/"STOP"
STOP=PROJECT/"campaigns/STOP"
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def percentile(a,p):return sorted(a)[math.ceil(len(a)*p)-1]/1000
from evidence import parse
def expired(protocol):
    return datetime.datetime.now(datetime.timezone.utc)>=datetime.datetime.fromisoformat(protocol["deadline_utc"])
def main():
    if os.geteuid()==0:raise SystemExit("host root execution forbidden")
    p=argparse.ArgumentParser();p.add_argument("--build",required=True);p.add_argument("--backend",choices=["disk","zswap"],required=True);a=p.parse_args()
    # KVM-only runner. A TCG environment (Grok Bot's cloud box) must not start KVM.
    if os.environ.get("SWAP_NEXT_ACCEL", "kvm") != "kvm":
        raise SystemExit("KVM-only runner; refusing SWAP_NEXT_ACCEL=" + os.environ["SWAP_NEXT_ACCEL"])
    if not re.fullmatch("[a-z0-9-]{1,48}",a.build):raise SystemExit("invalid build name")
    protocol=json.loads((BASE/"protocol.json").read_text())
    if not re.fullmatch("[0-9a-f]{40}", protocol["baseline_commit"]):raise SystemExit("baseline is not frozen")
    if STOP.exists() or campaign_stop(protocol).exists():raise SystemExit("STOP")
    BASE.joinpath("runs").mkdir(exist_ok=True)
    with (PROJECT/"benchmark/kernel/.runtime.lock").open("a") as lock:
      fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
      protocol=json.loads((BASE/"protocol.json").read_text())
      if expired(protocol):raise SystemExit("campaign deadline")
      if shutil.disk_usage(BASE).free < protocol["min_free_disk_gib"]*1024**3:raise SystemExit("free storage budget")
      state=BASE/"state-runtime-layout-v1";state.mkdir(exist_ok=True)
      ledger=state/"attempts.json"
      attempts=json.loads(ledger.read_text()) if ledger.exists() else []
      if len(attempts)>=protocol["max_guest_attempts"]:raise SystemExit("guest attempt budget exhausted")
      build=PROJECT/"benchmark/kernel/builds"/a.build
      manifest=json.loads((build/"result.json").read_text())
      image=build/"output/arch/x86/boot/bzImage";initrd=BASE/"initramfs.cpio.gz";config=build/"output/.config"
      if manifest.get("passed") is not True or sha(image)!=manifest.get("image_sha256") or sha(config)!=manifest.get("config_sha256"):raise SystemExit("build attestation mismatch")
      if "instrument_sha256" not in manifest or manifest["instrument_sha256"] is not None:raise SystemExit("instrumentation forbidden")
      config_text=config.read_text()
      for key in ["CONFIG_XSWAP", "CONFIG_SWAP", "CONFIG_DEBUG_FS", "CONFIG_PROC_PAGE_MONITOR"]:
        if key+"=y" not in config_text.splitlines():raise SystemExit("required config missing: "+key)
      if a.backend=="zswap" and "CONFIG_ZSWAP=y" not in config_text.splitlines():raise SystemExit("zswap config missing")
      provenance=json.loads((BASE/"initramfs.json").read_text())
      if sha(initrd)!=provenance.get("initrd_sha256"):raise SystemExit("initrd attestation mismatch")
      for name in ("workload.c","guest-init","prepare-rootfs.py"):
        if provenance.get("sources",{}).get(name)!=sha(BASE/name):raise SystemExit("stale initrd source: "+name)
      stamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
      dest=BASE/"runs"/(stamp+"-"+a.build+"-"+a.backend);dest.mkdir()
      disk=dest/"swap.raw"
      with disk.open("wb") as f:f.truncate(8*1024**3)
      append="console=ttyS0 rdinit=/init panic=-1 loglevel=3 xswap.max=8G zswap.enabled=1 evolve.backend="+a.backend+" evolve.image_sha="+sha(image)
      cmd=["qemu-system-x86_64","-enable-kvm","-machine","pc","-cpu","host,migratable=off","-smp","2","-m","4096",
        "-nodefaults","-display","none","-serial","stdio","-monitor","none","-nic","none","-no-reboot",
        "-sandbox","on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny",
        "-kernel",str(image),"-initrd",str(initrd),"-append",append,
        "-drive","file="+str(disk)+",format=raw,if=virtio,cache=none"]
      result={"run":str(dest),"source_commit":manifest["commit"],"backend":a.backend,"build":a.build,
        "image_sha256":sha(image),"initrd_sha256":sha(initrd),"config_sha256":sha(config),
        "instrument_sha256":manifest["instrument_sha256"],"command":cmd,"performance_accepted":False,"auto_promote":False,"harness_sha256":{p.name:sha(p) for p in [BASE/"run.py",BASE/"evidence.py",BASE/"workload.c",BASE/"guest-init",BASE/"lifetime.py",BASE/"prepare-rootfs.py"]}}
      attempts.append({"run":str(dest),"build":a.build,"backend":a.backend,"started_utc":stamp})
      ledger.write_text(json.dumps(attempts,indent=2)+"\n")
      start=time.monotonic();reason=None
      with (dest/"serial.log").open("w") as log:
        proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=bind_child_to_parent)
        try:
          while proc.poll() is None:
            if STOP.exists() or campaign_stop(protocol).exists():reason="STOP";break
            if expired(protocol):reason="campaign deadline";break
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
      result["gates"]["disk_activity"]=result["disk_delta"].get("sectors_read",0)>0 and result["disk_delta"].get("sectors_written",0)>0 if a.backend=="disk" else True
      result["gates"]["qemu_exit"]=proc.returncode==0 and reason is None
      result["pilot_pass"]=all(result["gates"].values())
      result["serial_sha256"]=sha(dest/"serial.log")
      (dest/"result.json").write_text(json.dumps(result,indent=2)+"\n")
      print(json.dumps(result,indent=2))
      raise SystemExit(0 if result["pilot_pass"] else 1)
if __name__=="__main__":main()
