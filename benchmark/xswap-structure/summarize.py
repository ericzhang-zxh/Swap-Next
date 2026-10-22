#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Export path-free summaries, retaining incomplete evaluations and attempts."""
import datetime
import hashlib
import json
from pathlib import Path
from evaluate_kernel import verify_run

BASE = Path(__file__).resolve().parent
PROJECT = BASE.parents[1]


def export_run(run):
    keys = ('side', 'pair', 'backend', 'source_commit', 'image_sha256', 'config_sha256',
            'initrd_sha256', 'serial_sha256', 'metrics', 'snapshots', 'swap_delta',
            'disk_delta', 'gates', 'pilot_pass', 'evidence_verified', 'wall_seconds')
    row = {key: run[key] for key in keys if key in run}
    if run.get('boot_id'):
        row['boot_id_sha256'] = hashlib.sha256(run['boot_id'].encode()).hexdigest()
    return row


def main():
    protocol = json.loads((BASE / 'protocol.json').read_text())
    evaluations, attempts, seen = [], [], set()
    for path in sorted((BASE / 'evaluations').glob('*/report.json')):
        report = json.loads(path.read_text())
        rows = []
        for run in report['runs']:
            if run.get('evidence_verified'):
                manifest = report['baseline_build'] if run['side'] == 'A' else report['candidate_build']
                expected = dict(source_commit=manifest['commit'], image_sha256=manifest['image_sha256'],
                                config_sha256=manifest['config_sha256'], initrd_sha256=report['initrd_sha256'])
                verify_run(run, expected, run['backend'], seen)
            rows.append(export_run(run))
        keys = ('evaluation_id', 'candidate_id', 'candidate_commit', 'calibration', 'status',
                'suite_sha256', 'metrics', 'comparison', 'missing_acceptance_gates')
        item = {key: report[key] for key in keys if key in report}
        # Regime groups contain all runs above; omit raw boot IDs from this export.
        regimes = json.loads(json.dumps(report.get('regime_summary', {})))
        for group in regimes.get('groups', {}).values():
            for row in group['runs']:
                boot = row.pop('boot_id', None)
                if boot:
                    row['boot_id_sha256'] = hashlib.sha256(boot.encode()).hexdigest()
        item.update(runs=rows, regime_summary=regimes, performance_accepted=False, auto_promote=False)
        evaluations.append(item)
    ledger = BASE / 'state-runtime-layout-v1/attempts.json'
    raw_attempts = json.loads(ledger.read_text()) if ledger.exists() else []
    for attempt in raw_attempts:
        path = Path(attempt['run']) / 'result.json'
        if path.exists():
            row = export_run(json.loads(path.read_text()))
            row['result_present'] = True
        else:
            row = dict(build=attempt['build'], backend=attempt['backend'], pilot_pass=False, result_present=False)
        attempts.append(row)
    summary = dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   campaign=protocol['campaign'], evaluations=evaluations, attempts=attempts,
                   guest_attempts=len(attempts), guest_pilot_passes=sum(a.get('pilot_pass') is True for a in attempts),
                   performance_accepted=False, auto_promote=False,
                   statistical_limit='Descriptive regime intervals; diagnostic pressure perturbs the guest after the primary snapshot. Missing acceptance gates remain blocking.')
    destination = PROJECT / 'results' / protocol['campaign'] / 'summary.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(dict(evaluations=len(evaluations), guest_attempts=len(attempts),
                          exported=str(destination.relative_to(PROJECT))), indent=2))


if __name__ == '__main__':
    main()
