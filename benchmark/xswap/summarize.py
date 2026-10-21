#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Export an allowlisted, path-free discovery summary from retained reports."""
import datetime
import hashlib
import json
from pathlib import Path
from evaluate_kernel import verify_run

BASE = Path(__file__).resolve().parent
PROJECT = BASE.parents[1]

def main():
    reports = sorted((BASE / 'evaluations').glob('*/report.json'))
    evaluations = []
    seen = set()
    for path in reports:
        report = json.loads(path.read_text())
        if report['status'] != 'PILOT_COMPLETE_REVIEW_REQUIRED':
            raise SystemExit('incomplete evaluation: ' + path.parent.name)
        rows = []
        for run in report['runs']:
            manifest = report['baseline_build'] if run['side'] == 'A' else report['candidate_build']
            expected = dict(source_commit=manifest['commit'], image_sha256=manifest['image_sha256'], config_sha256=manifest['config_sha256'], initrd_sha256=report['initrd_sha256'])
            verify_run(run, expected, run['backend'], seen)
            row = {key: run[key] for key in ('side', 'pair', 'backend', 'source_commit', 'image_sha256', 'config_sha256', 'initrd_sha256', 'serial_sha256', 'metrics', 'snapshots', 'swap_delta', 'disk_delta', 'gates', 'pilot_pass', 'wall_seconds')}
            row['boot_id_sha256'] = hashlib.sha256(run['boot_id'].encode()).hexdigest()
            rows.append(row)
        evaluations.append({key: report[key] for key in ('evaluation_id', 'candidate_id', 'candidate_commit', 'calibration', 'status', 'suite_sha256', 'metrics', 'comparison', 'missing_acceptance_gates')} | {'runs': rows, 'performance_accepted': False, 'auto_promote': False})
    attempts = json.loads((BASE / 'state-runtime-layout-v1/attempts.json').read_text())
    passed = 0
    failures = []
    for attempt in attempts:
        result = json.loads((Path(attempt['run']) / 'result.json').read_text())
        passed += int(result['pilot_pass'])
        if not result['pilot_pass']:
            failures.append(dict(build=result['build'], backend=result['backend'], serial_sha256=result['serial_sha256'], failed_gates=[k for k, v in result['gates'].items() if not v]))
    summary = dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), scope='Phase I v4 + Phase II v1 xswap discovery; Phase III excluded', evaluations=evaluations, guest_attempts=len(attempts), guest_pilot_passes=passed, failed_attempts=failures, performance_accepted=False, auto_promote=False, statistical_limit='Two AB/BA pairs per backend; initial A/A shows large mapped-cluster state variation. Scores and mean differences do not establish an optimization.', raw_evidence='Retained privately on the Linux worker; hashes published here. No guest disks, binaries, local paths or raw serial logs are exported.')
    destination = PROJECT / 'results/xswap-2026-10-21/summary.json'
    destination.write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(dict(evaluations=len(evaluations), guest_attempts=len(attempts), guest_pilot_passes=passed, exported=str(destination.relative_to(PROJECT))), indent=2))

if __name__ == '__main__':
    main()
