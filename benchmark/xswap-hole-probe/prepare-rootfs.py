#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Package an explicitly supplied, trusted guest rootfs template; no binaries bundled."""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess

BASE = pathlib.Path(__file__).resolve().parent
PROJECT = BASE.parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rootfs-template', type=pathlib.Path, required=True,
                        help='Trusted guest filesystem with /bin/sh, utilities and runtime libraries; see README')
    args = parser.parse_args()
    template = args.rootfs_template.resolve(strict=True)
    root = BASE / 'rootfs'
    archive = BASE / 'initramfs.cpio.gz'
    if not template.is_dir():
        raise SystemExit('rootfs template must be a directory')
    if root.exists() or archive.exists():
        raise SystemExit('rootfs or initrd already exists; version it before changing')
    if template == BASE or template in root.parents:
        raise SystemExit('template must not contain the output directory')
    for name in ('bin/sh', 'bin/mount', 'bin/cat', 'bin/grep',
                 'bin/uname', 'bin/mkswap', 'bin/swapon', 'bin/wc', 'bin/dmesg', 'bin/poweroff', 'bin/mkdir', 'bin/ls'):
        if not os.path.lexists(template / name):
            raise SystemExit('missing template utility: /' + name)
    shutil.copytree(template, root, symlinks=True)
    for name in ('sbin', 'dev', 'proc', 'sys', 'tmp', 'etc'):
        (root / name).mkdir(exist_ok=True)
    os.chmod(root / 'tmp', 0o1777)
    subprocess.run(['gcc', '-O2', '-Wall', '-Wextra', '-Werror', '-static',
                    str(BASE / 'workload.c'), '-o', str(root / 'bin/xswap-workload')], check=True)
    shutil.copyfile(BASE / 'guest-init', root / 'init')
    os.chmod(root / 'init', 0o755)
    with archive.open('wb') as out:
        subprocess.run(['bash', '-o', 'pipefail', '-c',
                        'find . -print0 | cpio --null -o --format=newc | gzip -1'],
                       cwd=root, stdout=out, check=True)

    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    provenance = {"initrd_sha256": digest(archive),
                  "sources": {name: digest(BASE/name) for name in ("workload.c", "guest-init", "prepare-rootfs.py")},
                  "rootfs_template": str(template)}
    (BASE/"initramfs.json").write_text(json.dumps(provenance, indent=2)+"\n")

if __name__ == '__main__':
    main()
