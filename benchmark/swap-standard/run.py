#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Run one bounded integration measurement in KVM or TCG; never accept a candidate.

KVM is the default and keeps 8 vCPU and 8192 MiB. SWAP_NEXT_ACCEL=tcg selects
TCG, whose guests default to 4 vCPU and 4096 MiB (revision 3). This process
records host load, pre-launch delay and clocksource fallback; the adapter
applies the wall-time median gate and reruns invalid revision 3 attempts.
"""
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
from validity import clocksource_invalid, launch_blocked, read_host_load
STOP = PROJECT / "evolve/control/state/STOP"
# xs-desc-lifetime-v1: unpinned cluster lookups survive an xswap shrink.
LIFETIME_FIX = "5e84ca928deeacb4eee656806a003f27d1eca82f"
SWAP_BYTES = 16 * 1024**3


def run_id(value):
    """Accept a single explicit run directory name, never a path."""
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,96}", value):
        raise argparse.ArgumentTypeError("run ID must be 1..96 ASCII letters, digits, underscores or hyphens")
    return value


def create_swap_image(path, preallocate=False, size=SWAP_BYTES):
    """Allocate only this run's private image, before any guest timing."""
    created = False
    try:
        with path.open("xb") as stream:
            created = True
            if preallocate:
                os.posix_fallocate(stream.fileno(), 0, size)
                os.fsync(stream.fileno())
            else:
                stream.truncate(size)
    except BaseException:
        if created:
            path.unlink(missing_ok=True)
        raise


def guest_shape(env):
    """KVM is the default. Grok Bot's cloud box must set SWAP_NEXT_ACCEL=tcg,
    because starting KVM there crashes its host."""
    accel_name = env.get("SWAP_NEXT_ACCEL", "kvm")
    if accel_name not in ("tcg", "kvm"):
        raise ValueError("SWAP_NEXT_ACCEL must be tcg or kvm")
    if accel_name == "kvm":
        return False, 8192, "8", ["-enable-kvm", "-machine", "pc", "-cpu", "host,migratable=off"]
    mem_text = env.get("SWAP_NEXT_TCG_MEM_MIB", "4096")
    cpu_text = env.get("SWAP_NEXT_TCG_SMP", "4")
    if not str(mem_text).isdigit() or not str(cpu_text).isdigit():
        raise ValueError("TCG guest size")
    mem, cpus = int(mem_text), int(cpu_text)
    if not 256 <= mem <= 8192 or not 1 <= cpus <= 8:
        raise ValueError("TCG guest size")
    return True, mem, str(cpus), ["-accel", "tcg,thread=multi,tb-size=256", "-machine", "pc", "-cpu", "max"]


def needs_lifetime_fix(mode, workload):
    return mode == "xswap" and workload != "lifetime"


def require_linux_checkout():
    """xswap runs prove the lifetime fix from linux/; without it, stop before any work."""
    if not (PROJECT / "linux" / ".git").exists():
        raise SystemExit("linux/ checkout missing; run: git submodule update --init linux")


def has_lifetime_fix(commit):
    require_linux_checkout()
    if not re.fullmatch(r"[0-9a-f]{40}", str(commit)):
        raise ValueError("build manifest commit is not a full SHA: " + str(commit))
    completed = subprocess.run(
        ["git", "-C", str(PROJECT / "linux"), "merge-base", "--is-ancestor", LIFETIME_FIX, commit],
        capture_output=True, text=True)
    if completed.returncode not in (0, 1):
        raise ValueError("cannot check the lifetime fix: " + completed.stderr.strip())
    return completed.returncode == 0


def snapshot_host_load():
    return read_host_load(Path("/proc/loadavg"), Path("/proc/pressure"))


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
    if needs_lifetime_fix(mode, workload) and not has_lifetime_fix(manifest["commit"]):
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
    parser.add_argument("--preallocate-swap", action="store_true",
                        help="Preallocate the private swap image before guest launch")
    parser.add_argument("--protocol-revision", type=int, default=1)
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
    if not 1 <= args.protocol_revision <= 9:
        parser.error("protocol revision must be 1..9")
    if (args.workload == "metadata") != (args.backend == "brd"):
        parser.error("metadata uses brd exclusively; brd is reserved for metadata")
    validate_workload(args.backend, args.mode, args.workload)
    if needs_lifetime_fix(args.mode, args.workload):
        require_linux_checkout()
    try:
        guest_shape(os.environ)
    except ValueError as exc:
        parser.error(str(exc))
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
        # KVM unless SWAP_NEXT_ACCEL=tcg; TCG guests default to 4 vCPU and
        # 4096 MiB unless the size env vars override them.
        tcg, guest_mib, guest_cpus, accel = guest_shape(os.environ)
        need_kib = (guest_mib + 1024) * 1024 if tcg else 10 * 1024**2
        if available < need_kib:
            raise SystemExit(f"need {need_kib // 1024} MiB available host RAM")
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        name = args.run_id or (stamp + "-" + args.build + "-" + args.backend + "-" + args.workload)
        dest = create_run_directory(BASE / "runs", name)
        disk = dest / "swap.raw"
        setup_started = time.monotonic()
        create_swap_image(disk, args.preallocate_swap)
        image_sha = manifest["image_sha256"]
        append = ("console=ttyS0 rdinit=/init panic=-1 loglevel=4 "
                  "zswap.enabled=1 zswap.compressor=zstd brd.rd_size=1073741824 "
                  f"bench.backend={args.backend} bench.mode={args.mode} "
                  f"bench.workload={args.workload} bench.image_sha={image_sha}")
        command = ["qemu-system-x86_64", *accel,
                   "-smp", guest_cpus, "-m", str(guest_mib), "-nodefaults", "-display", "none", "-serial", "stdio",
                   "-monitor", "none", "-nic", "none", "-no-reboot",
                   "-sandbox", "on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny",
                   "-kernel", str(image), "-initrd", str(BASE / "initramfs.cpio.gz"), "-append", append,
                   "-drive", f"file={disk},format=raw,if=virtio,cache=none",
                   "-drive", f"file={BASE / 'bench.img'},format=raw,if=virtio,readonly=on"]
        result = dict(swap_image_allocation="preallocated" if args.preallocate_swap else "sparse",
                      swap_bytes=SWAP_BYTES, protocol_revision=args.protocol_revision,
                      accelerator="tcg" if tcg else "kvm", qemu_accel=accel,
                      guest_vcpus=int(guest_cpus), guest_mem_mib=guest_mib,
                      run_id=dest.name, stop_file=str(args.stop_file) if args.stop_file else None,
                      build=args.build, backend=args.backend, mode=args.mode, workload=args.workload,
                      source_commit=manifest["commit"], image_sha256=image_sha,
                      config_sha256=sha(config), guest_provenance=provenance, command=command,
                      performance_accepted=False, calibrated=False, auto_promote=False,
                      harness_sha256={x.name: sha(x) for x in BASE.iterdir() if x.is_file() and x.suffix in (".py", ".sh", ".json", ".c") and x.name != "image.json"})
        snapshot = dest / "harness"
        snapshot.mkdir()
        for name in result["harness_sha256"]:
            shutil.copy2(BASE / name, snapshot / name)
        host_before = snapshot_host_load()
        pre_qemu = time.monotonic() - setup_started
        (dest / "started.json").write_text(json.dumps(result, indent=2) + "\n")

        def write_result(exit_status):
            if args.preallocate_swap:
                disk.unlink(missing_ok=True)
            (dest / "result.json").write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps({"run": str(dest), "integration_pass": result["integration_pass"],
                              "run_valid": result["run_valid"], "invalid_reasons": result["invalid_reasons"],
                              "gates": result["gates"], "wall_seconds": result["wall_seconds"],
                              "pre_qemu_seconds": result["pre_qemu_seconds"],
                              "accelerator": result["accelerator"], "guest_mem_mib": result["guest_mem_mib"],
                              "guest_vcpus": result["guest_vcpus"]}, indent=2))
            raise SystemExit(exit_status)

        if launch_blocked(args.protocol_revision, pre_qemu):
            result.update(exit_code=None, stop_reason="pre_qemu_delay", wall_seconds=0,
                          gates={"parse_complete": False, "qemu_exit": False}, integration_pass=False,
                          pre_qemu_seconds=pre_qemu, clocksource_invalid=False,
                          host_load={"before_launch": host_before, "after_exit": None},
                          invalid_reasons=["pre_qemu_delay"], run_valid=False)
            write_result(2)
        start = time.monotonic()
        reason = None
        with (dest / "serial.log").open("w") as log:
            if stop_requested(args.stop_file):
                disk.unlink(missing_ok=True)
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
        serial = (dest / "serial.log").read_text(errors="replace")
        result.update(exit_code=proc.returncode, stop_reason=reason, wall_seconds=time.monotonic() - start,
                      pre_qemu_seconds=pre_qemu, clocksource_invalid=clocksource_invalid(serial),
                      host_load={"before_launch": host_before, "after_exit": snapshot_host_load()})
        reasons = ["clocksource_fallback"] if result["clocksource_invalid"] else []
        result["invalid_reasons"] = reasons
        # run_valid here covers clocksource and pre-launch delay. The adapter
        # also rejects wall times above 1.5x the running median.
        result["run_valid"] = not reasons
        try:
            result.update(parse(serial, image_sha, args.backend, args.mode, args.workload))
        except (ValueError, KeyError, TypeError) as exc:
            result.update(gates={"parse_complete": False}, parse_error=str(exc))
        result["gates"]["qemu_exit"] = proc.returncode == 0 and reason is None
        result["integration_pass"] = all(value is True for value in result["gates"].values())
        result["serial_sha256"] = sha(dest / "serial.log")
        write_result(0 if result["integration_pass"] else 1)


if __name__ == "__main__":
    main()
