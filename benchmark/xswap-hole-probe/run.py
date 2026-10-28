#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Trusted bounded runner for guest-only high-anchor diagnostics."""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
import pathlib
import re
import shutil
import signal
import subprocess
import time
from evidence import parse
from lifetime import bind_child_to_parent

BASE = pathlib.Path(__file__).resolve().parent
PROJECT = BASE.parents[1]
SOURCES = ('workload.c', 'guest-init', 'prepare-rootfs.py')
HARNESS = (*SOURCES, 'run.py', 'evidence.py', 'lifetime.py', 'protocol.json', 'initramfs.json')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stop_paths(protocol):
    return (PROJECT / 'campaigns/STOP', PROJECT / 'campaigns' / protocol['campaign'] / 'STOP')


def expired(protocol):
    return datetime.datetime.now(datetime.timezone.utc) >= datetime.datetime.fromisoformat(protocol['deadline_utc'])


def attest(build, protocol, backend):
    manifest = json.loads((build / 'result.json').read_text())
    image, config = build / 'output/arch/x86/boot/bzImage', build / 'output/.config'
    initrd = BASE / 'initramfs.cpio.gz'
    if (manifest.get('passed') is not True or manifest.get('commit') != protocol['baseline_commit']
            or sha(image) != manifest.get('image_sha256') or sha(config) != manifest.get('config_sha256')
            or manifest.get('config_sha256') != protocol['config_sha256']):
        raise ValueError('build attestation mismatch')
    if 'instrument_sha256' not in manifest or manifest['instrument_sha256'] is not None:
        raise ValueError('unexpected instrumentation')
    lines = config.read_text().splitlines()
    for key in ('CONFIG_XSWAP', 'CONFIG_SWAP', 'CONFIG_DEBUG_FS', 'CONFIG_PROC_PAGE_MONITOR', 'CONFIG_ZSWAP'):
        if key + '=y' not in lines:
            raise ValueError('required config missing: ' + key)
    # Zswap is required to create xswap even when testing the disk backend.
    for key in ('CONFIG_THP_SWAP', 'CONFIG_TRANSPARENT_HUGEPAGE'):
        if any(line.startswith(key + '=') and line != key + '=n' for line in lines):
            raise ValueError('cluster-size assumption requires disabled ' + key)
    provenance = json.loads((BASE / 'initramfs.json').read_text())
    if sha(initrd) != provenance.get('initrd_sha256'):
        raise ValueError('initrd attestation mismatch')
    for name in SOURCES:
        if provenance.get('sources', {}).get(name) != sha(BASE / name):
            raise ValueError('stale initrd source: ' + name)
    return manifest, image, initrd, config


def read_ledger(path):
    rows = json.loads(path.read_text()) if path.exists() else []
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError('invalid attempt ledger')
    return rows


def check_budgets(protocol, local, shared):
    shared_suite_count = sum(row.get('suite') == protocol['suite'] for row in shared)
    if max(len(local), shared_suite_count) >= protocol['max_guest_attempts']:
        raise ValueError('diagnostic guest attempt budget exhausted')
    if len(shared) >= protocol['global_max_guest_attempts']:
        raise ValueError('shared guest attempt budget exhausted')


def write_ledger(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.json.tmp')
    with temporary.open('w') as stream:
        stream.write(json.dumps(rows, indent=2) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def reserve_attempt(protocol, local_path, shared_path, attempt):
    local, shared = read_ledger(local_path), read_ledger(shared_path)
    check_budgets(protocol, local, shared)
    row = dict(attempt, suite=protocol['suite'])
    # Reserve globally first. If the local write fails, the shared reservation
    # remains charged and prevents overspending on a later invocation.
    write_ledger(shared_path, shared + [row])
    write_ledger(local_path, local + [row])


def main():
    if os.geteuid() == 0:
        raise SystemExit('host root execution forbidden')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', required=True)
    parser.add_argument('--backend', choices=('disk', 'zswap'), required=True)
    args = parser.parse_args()
    # KVM-only runner. A TCG environment (Grok Bot's cloud box) must not start KVM.
    if os.environ.get("SWAP_NEXT_ACCEL", "kvm") != "kvm":
        raise SystemExit("KVM-only runner; refusing SWAP_NEXT_ACCEL=" + os.environ["SWAP_NEXT_ACCEL"])
    if not re.fullmatch('[a-z0-9-]{1,48}', args.build):
        raise SystemExit('invalid build name')
    with (PROJECT / 'benchmark/kernel/.runtime.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        protocol = json.loads((BASE / 'protocol.json').read_text())
        if any(path.exists() for path in stop_paths(protocol)) or expired(protocol):
            raise SystemExit('STOP or campaign deadline')
        local_path = BASE / 'state-runtime-layout-v1/attempts.json'
        shared_path = BASE.parent / 'xswap-structure/state-runtime-layout-v1/attempts.json'
        check_budgets(protocol, read_ledger(local_path), read_ledger(shared_path))
        if shutil.disk_usage(BASE).free < protocol['min_free_gib'] * 1024**3:
            raise SystemExit('less than required free disk space')
        manifest, image, initrd, config = attest(PROJECT / 'benchmark/kernel/builds' / args.build, protocol, args.backend)
        hashes = {name: sha(BASE / name) for name in HARNESS}
        image_hash, initrd_hash, config_hash = sha(image), sha(initrd), sha(config)
        manifest_path = PROJECT / 'benchmark/kernel/builds' / args.build / 'result.json'
        manifest_hash = sha(manifest_path)
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        dest = BASE / 'runs' / (stamp + '-' + args.build + '-' + args.backend)
        dest.mkdir(parents=True)
        disk = dest / 'swap.raw'
        with disk.open('wb') as stream:
            stream.truncate(8 * 1024**3)
        append = ('console=ttyS0 rdinit=/init panic=-1 loglevel=3 xswap.max=8G zswap.enabled=1 '
                  'evolve.backend=' + args.backend + ' evolve.image_sha=' + image_hash)
        command = ['qemu-system-x86_64', '-enable-kvm', '-machine', 'pc', '-cpu', 'host,migratable=off',
                   '-smp', '2', '-m', '4096', '-nodefaults', '-display', 'none', '-serial', 'stdio',
                   '-monitor', 'none', '-nic', 'none', '-no-reboot',
                   '-sandbox', 'on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny',
                   '-kernel', str(image), '-initrd', str(initrd), '-append', append,
                   '-drive', 'file=' + str(disk) + ',format=raw,if=virtio,cache=none']
        result = dict(run=str(dest), source_commit=manifest['commit'], backend=args.backend, build=args.build,
                      image_sha256=image_hash, initrd_sha256=initrd_hash, config_sha256=config_hash,
                      instrument_sha256=manifest['instrument_sha256'], build_manifest_sha256=manifest_hash, command=command,
                      performance_accepted=False, auto_promote=False, harness_sha256=hashes)
        reserve_attempt(protocol, local_path, shared_path,
                        dict(run=str(dest), build=args.build, backend=args.backend, started_utc=stamp))
        start, reason, exit_code = time.monotonic(), None, None
        try:
            with (dest / 'serial.log').open('w') as stream:
                proc = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT,
                                        start_new_session=True, preexec_fn=bind_child_to_parent)
                try:
                    while proc.poll() is None:
                        if any(path.exists() for path in stop_paths(protocol)):
                            reason = 'STOP'
                        elif expired(protocol):
                            reason = 'campaign deadline'
                        elif time.monotonic() - start > 600:
                            reason = 'timeout'
                        elif (dest / 'serial.log').stat().st_size > 16 * 1024**2:
                            reason = 'log budget'
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
                    disk.unlink(missing_ok=True)  # Scratch guest swap; nothing reads it after QEMU exits.
                    exit_code = proc.returncode
        except Exception as error:
            reason = type(error).__name__ + ': ' + str(error)
        raw = dest / 'serial.log'
        result.update(parse(raw.read_text(errors='replace') if raw.exists() else '', image_hash, args.backend))
        result.update(exit_code=exit_code, stop_reason=reason, wall_seconds=time.monotonic()-start)
        result['gates']['qemu_exit'] = exit_code == 0 and reason is None
        result['gates']['inputs_unchanged'] = (all(sha(BASE / name) == value for name, value in hashes.items())
                                             and sha(image) == image_hash and sha(initrd) == initrd_hash
                                             and sha(config) == config_hash and sha(manifest_path) == manifest_hash)
        result['pilot_pass'] = all(result['gates'].values())
        result['serial_sha256'] = sha(raw) if raw.exists() else None
        (dest / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result['pilot_pass'] else 1)


if __name__ == '__main__':
    main()
