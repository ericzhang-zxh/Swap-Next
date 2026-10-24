#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Run one bounded integration measurement in KVM; never accept a candidate."""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parent
PROJECT = BASE.parents[1]
sys.path.insert(0, str(PROJECT / "benchmark/kernel"))
from lifetime import bind_child_to_parent
from evidence import parse, DIAGNOSTIC
STOP = PROJECT / "evolve/control/state/STOP"


def run_id(value):
    """Accept a single explicit run directory name, never a path."""
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,96}", value):
        raise argparse.ArgumentTypeError("run ID must be 1..96 ASCII letters, digits, underscores or hyphens")
    return value


def absolute_stop_file(value):
    path = Path(value)
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("stop file must be an absolute path")
    return path


def stop_requested(extra_stop=None):
    return STOP.exists() or (extra_stop is not None and extra_stop.exists())


def create_run_directory(root, name):
    root.mkdir(parents=True, exist_ok=True)
    dest = root / name
    dest.mkdir()  # Exclusive creation preserves earlier evidence, including symlinks.
    return dest


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# xs-desc-lifetime-v1: unpinned cluster lookups survive an xswap shrink.
LIFETIME_FIX = "5e84ca928deeacb4eee656806a003f27d1eca82f"


def has_lifetime_fix(commit):
    return subprocess.run(["git", "-C", str(PROJECT / "linux"), "merge-base", "--is-ancestor",
                           LIFETIME_FIX, commit], capture_output=True).returncode == 0


def validate(build, backend, mode, workload):
    manifest = json.loads((build / "result.json").read_text())
    image = build / "output/arch/x86/boot/bzImage"
    config = build / "output/.config"
    if (manifest.get("passed") is not True or
        manifest.get("instrument_sha256", "missing") is not None or
        sha(image) != manifest.get("image_sha256") or
        sha(config) != manifest.get("config_sha256")):
        raise ValueError("build attestation mismatch")
    required = ["SWAP", "MEMCG", "EXT4_FS", "PROC_PAGE_MONITOR", "DEBUG_FS", "NET", "INET"]
    if backend == "zram":
        required += ["ZRAM"]
    if backend == "brd":
        required += ["BLK_DEV_RAM"]
    required += ["ZSWAP"]
    if mode == "xswap" and workload != "lifetime" and not has_lifetime_fix(manifest["commit"]):
        raise ValueError("xswap performance runs need the descriptor lifetime fix")
    lines = set(config.read_text().splitlines())
    for option in required:
        if f"CONFIG_{option}=y" not in lines:
            raise ValueError("required config missing: " + option)
    provenance = json.loads((BASE / "image.json").read_text())
    for path, key in [(BASE / "bench.img", "image_sha256"),
                      (BASE / "initramfs.cpio.gz", "initrd_sha256")]:
        if sha(path) != provenance.get(key):
            raise ValueError("guest artifact attestation mismatch: " + path.name)
    for name, digest in provenance["sources"].items():
        if sha(BASE / name) != digest:
            raise ValueError("stale guest source: " + name)
    return manifest, provenance, image, config


def validate_workload(backend, mode, workload):
    if workload == "correctness" and (mode != "xswap" or backend not in ("disk", "zswap")):
        raise ValueError("correctness requires xswap with disk or zswap")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True)
    parser.add_argument("--backend", choices=["disk", "zswap", "zram", "brd"], required=True)
    parser.add_argument("--mode", choices=["plain", "xswap"], default="plain")
    parser.add_argument("--workload", choices=["usemem", "usemem-rand", "build", "redis", "swapin", "metadata", "lifetime", "correctness"], required=True)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--run-id", type=run_id, help="explicit unique run directory name")
    parser.add_argument("--stop-file", type=absolute_stop_file,
                        help="additional absolute STOP path checked before and during the run")
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error("host root execution forbidden")
    if not re.fullmatch("[a-z0-9-]{1,48}", args.build):
        parser.error("invalid build name")
    if not 30 <= args.timeout <= 3600:
        parser.error("timeout must be 30..3600 seconds")
    if (args.workload == "metadata") != (args.backend == "brd"):
        parser.error("metadata uses brd exclusively; brd is reserved for metadata")
    validate_workload(args.backend, args.mode, args.workload)
    if stop_requested(args.stop_file):
        raise SystemExit("STOP")
    with (PROJECT / "benchmark/kernel/.runtime.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        build = PROJECT / "benchmark/kernel/builds" / args.build
        manifest, provenance, image, config = validate(build, args.backend, args.mode, args.workload)
        if args.check_only:
            print("INPUTS_VERIFIED; no guest started")
            return
        if shutil.disk_usage(BASE).free < 24 * 1024**3:
            raise SystemExit("need 24 GiB free disk")
        available = int(re.search(r"MemAvailable:\s+(\d+)", Path("/proc/meminfo").read_text()).group(1))
        if available < 10 * 1024**2:
            raise SystemExit("need 10 GiB available host RAM")
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        name = args.run_id or (stamp + "-" + args.build + "-" + args.backend + "-" + args.workload)
        dest = create_run_directory(BASE / "runs", name)
        disk = dest / "swap.raw"
        with disk.open("wb") as stream:
            stream.truncate(16 * 1024**3)
        image_sha = manifest["image_sha256"]
        append = ("console=ttyS0 rdinit=/init panic=-1 loglevel=4 "
                  "zswap.enabled=1 zswap.compressor=zstd brd.rd_size=1073741824 "
                  f"bench.backend={args.backend} bench.mode={args.mode} "
                  f"bench.workload={args.workload} bench.image_sha={image_sha}")
        command = ["qemu-system-x86_64", "-enable-kvm", "-machine", "pc", "-cpu", "host,migratable=off",
                   "-smp", "8", "-m", "8192", "-nodefaults", "-display", "none", "-serial", "stdio",
                   "-monitor", "none", "-nic", "none", "-no-reboot",
                   "-sandbox", "on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny",
                   "-kernel", str(image), "-initrd", str(BASE / "initramfs.cpio.gz"), "-append", append,
                   "-drive", f"file={disk},format=raw,if=virtio,cache=none",
                   "-drive", f"file={BASE / 'bench.img'},format=raw,if=virtio,readonly=on"]
        result = dict(run_id=dest.name, stop_file=str(args.stop_file) if args.stop_file else None,
                      build=args.build, backend=args.backend, mode=args.mode, workload=args.workload,
                      source_commit=manifest["commit"], image_sha256=image_sha,
                      config_sha256=sha(config), guest_provenance=provenance, command=command,
                      performance_accepted=False, calibrated=False, auto_promote=False,
                      harness_sha256={x.name: sha(x) for x in BASE.iterdir() if x.is_file() and x.suffix in (".py", ".sh", ".json", ".c") and x.name != "image.json"})
        snapshot = dest / "harness"
        snapshot.mkdir()
        for name in result["harness_sha256"]:
            shutil.copy2(BASE / name, snapshot / name)
        (dest / "started.json").write_text(json.dumps(result, indent=2) + "\n")
        start = time.monotonic()
        reason = None
        with (dest / "serial.log").open("w") as log:
            if stop_requested(args.stop_file):
                disk.unlink()
                raise SystemExit("STOP")
            proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                    start_new_session=True, preexec_fn=bind_child_to_parent)
            try:
                while proc.poll() is None:
                    if stop_requested(args.stop_file):
                        reason = "STOP"
                    elif time.monotonic() - start > args.timeout:
                        reason = "timeout"
                    elif (dest / "serial.log").stat().st_size > 16 * 1024**2:
                        reason = "log budget"
                    elif DIAGNOSTIC.search((dest / "serial.log").read_text(errors="replace")):
                        reason = "guest kernel diagnostic"
                    if reason:
                        break
                    time.sleep(.5)
            finally:
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
                # Scratch guest swap; nothing reads it after QEMU exits.
                disk.unlink(missing_ok=True)
        result.update(exit_code=proc.returncode, stop_reason=reason, wall_seconds=time.monotonic() - start)
        try:
            result.update(parse((dest / "serial.log").read_text(errors="replace"), image_sha,
                                args.backend, args.mode, args.workload))
        except (ValueError, KeyError, TypeError) as exc:
            result.update(gates={"parse_complete": False}, parse_error=str(exc))
        result["gates"]["qemu_exit"] = proc.returncode == 0 and reason is None
        result["integration_pass"] = all(value is True for value in result["gates"].values())
        result["serial_sha256"] = sha(dest / "serial.log")
        (dest / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps({"run": str(dest), "integration_pass": result["integration_pass"],
                          "gates": result["gates"], "wall_seconds": result["wall_seconds"]}, indent=2))
        raise SystemExit(0 if result["integration_pass"] else 1)


if __name__ == "__main__":
    main()
