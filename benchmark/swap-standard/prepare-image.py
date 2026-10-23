#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build the read-only benchmark root image and the initramfs from pinned inputs."""
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tempfile

BASE = pathlib.Path(__file__).resolve().parent
PROJECT = BASE.parents[1]
# The same host userland the trusted kernel build namespace exposes.
HOST_DIRS = ('etc/alternatives', 'usr/bin', 'usr/sbin', 'usr/include', 'usr/lib/x86_64-linux-gnu',
             'usr/lib/gcc', 'usr/libexec', 'usr/lib/bfd-plugins', 'usr/lib/locale',
             'usr/share/perl', 'usr/share/perl5', 'usr/share/misc', 'usr/share/bison')
SOURCES = ('guest-init', 'bench.sh', 'params.sh', 'swapin.c', 'churn.c', 'prepare-image.py', 'tools.json')


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def git_head(path):
    return subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--src', type=pathlib.Path, required=True,
                        help='directory with built valkey/ and vm-scalability/ checkouts')
    parser.add_argument('--busybox-template', type=pathlib.Path, required=True,
                        help='trusted busybox rootfs used for the initramfs stage')
    args = parser.parse_args()
    source_hashes = {name: sha(BASE / name) for name in SOURCES}
    tools = json.loads((BASE / 'tools.json').read_text())
    image, initrd = BASE / 'bench.img', BASE / 'initramfs.cpio.gz'
    stage, iroot = BASE / 'stage', BASE / 'initramfs-root'
    for path in (image, initrd, stage, iroot):
        if path.exists():
            raise SystemExit(f'{path.name} already exists; version it before rebuilding')

    for name in ('valkey', 'vm-scalability'):
        if git_head(args.src / name) != tools[name]['commit']:
            raise SystemExit(f'{name} is not at the pinned commit')
    linux = PROJECT / 'linux'
    commit = subprocess.check_output(['git', '-C', str(linux), 'rev-parse',
                                      tools['linux_source']['commit'] + '^{commit}'], text=True).strip()

    stage.mkdir()
    subprocess.run(['bash', '-o', 'pipefail', '-c',
                    'tar -C / -cf - "$@" | tar -C "$0" -xf -', str(stage), *HOST_DIRS],
                   check=True)
    for d in ('bin', 'sbin'):
        (stage / d).symlink_to('usr/' + d)
    (stage / 'lib').symlink_to('usr/lib')
    (stage / 'lib64').mkdir()
    (stage / 'lib64/ld-linux-x86-64.so.2').symlink_to('/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2')
    for d in ('proc', 'sys', 'dev', 'tmp', 'etc'):
        (stage / d).mkdir(exist_ok=True)
    (stage / 'etc/passwd').write_text('root:x:0:0:root:/tmp:/bin/bash\n')
    (stage / 'etc/group').write_text('root:x:0:\n')

    opt = stage / 'opt/bench'
    (opt / 'bin').mkdir(parents=True)
    for name in ('bench.sh', 'params.sh'):
        shutil.copyfile(BASE / name, opt / name)
    binary_hashes = {}
    # Rebuild immutable Git archives instead of trusting pre-existing binaries.
    with tempfile.TemporaryDirectory(prefix='swap-standard-tools-') as temp:
        for name in ('vm-scalability', 'valkey'):
            source = pathlib.Path(temp) / name
            source.mkdir()
            archive = pathlib.Path(temp) / (name + '.tar')
            with archive.open('wb') as stream:
                subprocess.run(['git', '-C', str(args.src / name), 'archive', tools[name]['commit']],
                               stdout=stream, check=True)
            subprocess.run(['tar', '-xf', str(archive), '-C', str(source)], check=True)
            command = ['make', '-j4', 'usemem'] if name == 'vm-scalability' else ['make', '-j4', 'BUILD_TLS=no', 'MALLOC=libc']
            with (BASE / (name + '-build.log')).open('w') as log:
                subprocess.run(command, cwd=source, stdout=log, stderr=subprocess.STDOUT,
                               check=True, timeout=600)
            binaries = ['usemem'] if name == 'vm-scalability' else ['src/valkey-server', 'src/valkey-benchmark', 'src/valkey-cli']
            for relative in binaries:
                target = opt / 'bin' / pathlib.Path(relative).name
                shutil.copy2(source / relative, target)
                binary_hashes[target.name] = sha(target)
    for probe in ('swapin', 'churn'):
        subprocess.run(['gcc', '-O2', '-Wall', '-Wextra', '-Werror', str(BASE / (probe + '.c')),
                        '-o', str(opt / 'bin' / probe)], check=True)
    with (opt / 'linux.tar').open('wb') as stream:
        subprocess.run(['git', '-C', str(linux), 'archive', commit], stdout=stream, check=True)

    size = int(subprocess.check_output(['du', '-sb', str(stage)], text=True).split()[0])
    size_mib = size * 5 // 4 // (1 << 20) + 256
    subprocess.run(['mke2fs', '-q', '-t', 'ext4', '-L', 'benchroot', '-E', 'root_owner=0:0',
                    '-d', str(stage), str(image), f'{size_mib}M'], check=True)

    shutil.copytree(args.busybox_template.resolve(strict=True), iroot, symlinks=True)
    for d in ('sbin', 'dev', 'proc', 'sys', 'tmp', 'etc'):
        (iroot / d).mkdir(exist_ok=True)
    shutil.copyfile(BASE / 'guest-init', iroot / 'init')
    os.chmod(iroot / 'init', 0o755)
    with initrd.open('wb') as out:
        subprocess.run(['bash', '-o', 'pipefail', '-c', 'find . -print0 | cpio --null -o --format=newc --owner=0:0 | gzip -1'],
                       cwd=iroot, stdout=out, check=True)
    shutil.rmtree(stage)
    shutil.rmtree(iroot)

    if source_hashes != {name: sha(BASE / name) for name in SOURCES}:
        raise SystemExit('guest sources changed during preparation; retain artifacts and rebuild')
    provenance = {
        'image_sha256': sha(image), 'image_mib': size_mib, 'initrd_sha256': sha(initrd),
        'sources': source_hashes,
        'linux_source_commit': commit,
        'tools': {name: tools[name]['commit'] for name in ('valkey', 'vm-scalability')},
        'calibrated': False,
        'host_dirs': list(HOST_DIRS),
        'binary_sha256': binary_hashes,
        'toolchain': subprocess.check_output(['gcc', '--version'], text=True).splitlines()[0],
    }
    (BASE / 'image.json').write_text(json.dumps(provenance, indent=2) + '\n')
    print(json.dumps(provenance, indent=2))


if __name__ == '__main__':
    main()
