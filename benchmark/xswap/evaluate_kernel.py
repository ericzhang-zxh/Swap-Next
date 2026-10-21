# SPDX-License-Identifier: GPL-2.0-only
"""Bounded discovery evaluator for a separately frozen xswap reference."""
import datetime
import fcntl
import hashlib
import json
import math
import pathlib
import re
import subprocess
import uuid
from evidence import parse

BASE = pathlib.Path(__file__).resolve().parent
PROJECT = BASE.parents[1]
KERNEL = BASE.parent / 'kernel'
SUITE = ['protocol.json', 'evaluate_kernel.py', 'run.py', 'workload.c',
         'guest-init', 'prepare-rootfs.py', 'lifetime.py', 'evidence.py']
METRICS = ['mapped_clusters_after_settle', 'sampled_mapped_clusters_max',
           'swapped_first_access_p99_us', 'workload_wall_seconds',
           'grows_after_settle', 'shrinks_after_settle']

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def bounded(protocol):
    for path in (PROJECT / 'system/state/STOP',
                 PROJECT / 'system/state' / protocol['campaign'] / 'STOP'):
        if path.exists():
            raise ValueError('STOP')
    if datetime.datetime.now(datetime.timezone.utc) >= datetime.datetime.fromisoformat(protocol['deadline_utc']):
        raise ValueError('campaign wall budget exhausted')

def invoke(command, log, timeout):
    with log.open('w') as stream:
        result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
    if result.returncode:
        raise ValueError('stage failed: ' + str(log))

def verify_run(run, expected, backend, seen):
    if not run.get('pilot_pass') or not run.get('gates') or not all(run['gates'].values()):
        raise ValueError('guest pilot failed')
    if run.get('backend') != backend:
        raise ValueError('backend identity mismatch')
    for key, value in expected.items():
        if run.get(key) != value:
            raise ValueError('run provenance mismatch: ' + key)
    boot = run.get('boot_id')
    if not boot or boot in seen:
        raise ValueError('missing or duplicate boot ID')
    seen.add(boot)
    for key in METRICS:
        value = run.get('metrics', {}).get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError('invalid metric: ' + key)
        if key not in ('grows_after_settle', 'shrinks_after_settle') and value == 0:
            raise ValueError('zero metric: ' + key)
    raw = pathlib.Path(run['run']) / 'serial.log'
    if digest(raw) != run['serial_sha256']:
        raise ValueError('raw evidence hash mismatch')
    parsed = parse(raw.read_text(errors='replace'))
    for key in ('metrics', 'snapshots', 'swap_delta', 'disk_delta', 'boot_id', 'xswap_type'):
        if parsed[key] != run[key]:
            raise ValueError('raw evidence differs from result: ' + key)
    if not all(parsed['gates'].values()):
        raise ValueError('raw evidence gates failed')
    zkeys = ('zswpin', 'zswpout')
    if backend == 'zswap' and not all(run['swap_delta'].get(k, 0) > 0 for k in zkeys):
        raise ValueError('zswap backend not exercised')
    if backend == 'disk' and (any(run['swap_delta'].get(k, 0) != 0 for k in zkeys) or not all(run['disk_delta'].get(k, 0) > 0 for k in ('sectors_read', 'sectors_written'))):
        raise ValueError('disk backend evidence mismatch')

def evaluate(program_path):
    request = json.loads(pathlib.Path(program_path).read_text())
    if set(request) != {'candidate_id', 'candidate_commit', 'evaluation_id'}:
        raise ValueError('invalid request schema')
    ident = request['candidate_id']
    if not re.fullmatch('[a-z][a-z0-9-]{0,47}', ident):
        raise ValueError('invalid candidate ID')
    evaluation_id = str(uuid.UUID(request['evaluation_id']))
    protocol = json.loads((BASE / 'protocol.json').read_text())
    calibration = ident == 'calibration-aa'
    state = BASE / 'evaluations' / evaluation_id
    state.mkdir(parents=True, exist_ok=False)
    hashes = {name: digest(BASE / name) for name in SUITE}
    hashes['build.py'] = digest(KERNEL / 'build.py')
    hashes['build_namespace.sh'] = digest(KERNEL / 'build_namespace.sh')
    report = dict(evaluation_id=evaluation_id, candidate_id=ident,
                  candidate_commit=request['candidate_commit'], suite_sha256=hashes,
                  calibration=calibration, runs=[], status='RUNNING',
                  performance_accepted=False, auto_promote=False)
    for name in SUITE:
        (state / ('frozen-' + name)).write_bytes((BASE / name).read_bytes())
    result = {'pilot_pass': 0.0, 'combined_score': 0.0}
    try:
        bounded(protocol)
        baseline_path = KERNEL / 'builds' / protocol['baseline_build'] / 'result.json'
        baseline = json.loads(baseline_path.read_text())
        if not baseline['passed'] or baseline['commit'] != protocol['baseline_commit'] or baseline['instrument_sha256'] is not None:
            raise ValueError('invalid baseline')
        if calibration:
            if request['candidate_commit'] != protocol['baseline_commit']:
                raise ValueError('A/A commit mismatch')
            buildname, manifest = protocol['baseline_build'], baseline
        else:
            calibration_path = BASE / 'state-layout-v1/calibration.json'
            calibration_report = json.loads(calibration_path.read_text())
            if calibration_report['suite_sha256'] != hashes or calibration_report['status'] != 'PILOT_COMPLETE_REVIEW_REQUIRED':
                raise ValueError('missing or stale A/A calibration')
            invoke(['python3', str(PROJECT / 'system/controller.py'), '--campaign', protocol['campaign'], 'check', ident], state / 'static.log', 180)
            checked = json.loads((state / 'static.log').read_text())
            if checked['status'] != 'SCOPE_PASS' or checked['candidate_commit'] != request['candidate_commit'] or checked['parent'] != protocol['baseline_commit']:
                raise ValueError('candidate static identity mismatch')
            buildname = ident + '-' + request['candidate_commit'][:8]
            build = KERNEL / 'builds' / buildname
            if not build.exists():
                invoke(['python3', str(KERNEL / 'build.py'), '--commit', request['candidate_commit'], '--name', buildname, '--config', str(PROJECT / 'benchmark/config/xswap-kernel.config'), '--no-instrumentation'], state / 'build.log', 1000)
            manifest = json.loads((build / 'result.json').read_text())
            if not manifest['passed'] or manifest['commit'] != request['candidate_commit']:
                raise ValueError('failed or stale candidate build')
            if manifest['config_sha256'] != baseline['config_sha256'] or manifest['instrument_sha256'] is not None:
                raise ValueError('candidate configuration mismatch')
        initrd = digest(BASE / 'initramfs.cpio.gz')
        report.update(initrd_sha256=initrd, baseline_build=baseline, candidate_build=manifest)
        seen = set()
        for backend in protocol['backends']:
            for pair, order in enumerate(protocol['order']):
                for side in order:
                    bounded(protocol)
                    for name in SUITE:
                        if digest(BASE / name) != hashes[name]:
                            raise ValueError('frozen suite changed')
                    if digest(BASE / 'initramfs.cpio.gz') != initrd:
                        raise ValueError('initrd changed')
                    chosen = baseline if side == 'A' else manifest
                    name = protocol['baseline_build'] if side == 'A' else buildname
                    log = state / (backend + '-' + str(pair) + '-' + side + '.json')
                    invoke(['python3', str(BASE / 'run.py'), '--build', name, '--backend', backend], log, 630)
                    run = json.loads(log.read_text())
                    # Save the raw result before validating it, including a failed result.
                    report['runs'].append(dict(side=side, pair=pair, **run))
                    expected = dict(source_commit=chosen['commit'], image_sha256=chosen['image_sha256'], config_sha256=chosen['config_sha256'], initrd_sha256=initrd)
                    verify_run(run, expected, backend, seen)
                    (state / 'report.json').write_text(json.dumps(report, indent=2)+'\n')
        groups = {}
        for backend in protocol['backends']:
            groups[backend] = {}
            for side in ('A', 'B'):
                rows = [r for r in report['runs'] if r['backend'] == backend and r['side'] == side]
                groups[backend][side] = {k: sum(r['metrics'][k] for r in rows)/len(rows) for k in METRICS}
        latency = min(v['A']['swapped_first_access_p99_us']/v['B']['swapped_first_access_p99_us'] for v in groups.values())
        metadata = min(v['A']['mapped_clusters_after_settle']/v['B']['mapped_clusters_after_settle'] for v in groups.values())
        result = dict(pilot_pass=1.0, combined_score=metadata*min(1.0, latency), latency_worst_backend_relative_score=latency, settled_clusters_worst_backend_relative_score=metadata)
        report.update(status='PILOT_COMPLETE_REVIEW_REQUIRED', comparison=groups, metrics=result)
    except Exception as error:
        report.update(status='FAILED_OR_INCOMPLETE', error=type(error).__name__+': '+str(error))
    report['missing_acceptance_gates'] = protocol['unimplemented_acceptance_gates']
    (state / 'report.json').write_text(json.dumps(report, indent=2)+'\n')
    return result
