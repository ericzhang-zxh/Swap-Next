#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Replay the reviewed public series through a separate import-only controller."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

PROJECT = Path(__file__).resolve().parents[2]
PATCHES = PROJECT / 'patches/xswap-reference'
NAME = 'xswap-reference-replay'

def command(*args, env=None):
    return subprocess.check_output(args, cwd=PROJECT, text=True, env=env).strip()

def main():
    if os.uname().sysname != 'Linux':
        raise SystemExit('Use the designated Linux worker')
    manifest = json.loads((PATCHES / 'manifest.json').read_text())
    for row in manifest['patches']:
        if Path(row['file']).name != row['file']:
            raise SystemExit('invalid patch name')
        if hashlib.sha256((PATCHES / row['file']).read_bytes()).hexdigest() != row['sha256']:
            raise SystemExit('patch hash mismatch')
    # Fetch the public base explicitly first if this local object is absent.
    command('git', '-C', str(PROJECT / 'linux'), 'cat-file', '-e', manifest['base_commit'] + '^{commit}')
    campaign = PROJECT / 'evolve/control/campaigns' / NAME
    policy = json.loads((PROJECT / 'evolve/control/campaigns/xswap-2026-10-21/import-policy.json').read_text())
    campaign.mkdir(exist_ok=False)
    (campaign / 'policy.json').write_text(json.dumps(policy, indent=2)+'\n')
    controller = ['python3', str(PROJECT / 'evolve/control/controller.py'), '--campaign', NAME]
    created = json.loads(command(*controller, 'new', NAME, '--hypothesis', 'Reproduce the imported public reference using preserved patch and commit identities; no optimization or performance acceptance.'))
    worktree = created['worktree']
    for row in manifest['patches']:
        env = dict(os.environ, GIT_COMMITTER_NAME=row['committer_name'],
                   GIT_COMMITTER_EMAIL=row['committer_email'], GIT_COMMITTER_DATE=row['committer_date'])
        command('git', '-C', worktree, '-c', 'commit.gpgsign=false', 'am', str(PATCHES / row['file']), env=env)
        head = command('git', '-C', worktree, 'rev-parse', 'HEAD')
        if head != row['commit']:
            raise SystemExit('commit replay differs; retained import requires inspection')
    if command('git', '-C', worktree, 'rev-parse', 'HEAD^{tree}') != manifest['reference_tree']:
        raise SystemExit('reference tree mismatch')
    checked = json.loads(command(*controller, 'check', NAME))
    if checked['status'] != 'SCOPE_PASS':
        raise SystemExit('reference static check failed')
    command(*controller, 'close', NAME, '--reason', 'Exact commit and tree replay verified; reference remains experimental.')
    print(json.dumps(dict(reference_commit=manifest['reference_commit'],
                          reference_tree=manifest['reference_tree'], replayed_commits=len(manifest['patches'])), indent=2))

if __name__ == '__main__':
    main()
