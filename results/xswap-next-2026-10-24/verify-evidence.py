#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Independently reconcile reserved work, hashes, identities and paired ratios."""
import datetime, hashlib, json, math, statistics, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
C='xswap-next-2026-10-24'
STATE=ROOT/'evolve/swap-standard'/('state-'+C)
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
p=read(ROOT/'benchmark/swap-standard'/('protocol-'+C+'.json'))
ledger=read(STATE/'ledger.json');budget=read(STATE/'budget.json')
cal=read(STATE/'calibration-fast.json')
assert cal['status']=='CALIBRATED' and cal['analysis']['passed'] is True
sys.path.insert(0,str(ROOT/'evolve'))
import standard_workflow as sw
sw.select_protocol(ROOT/'benchmark/swap-standard'/('protocol-'+C+'.json'))
assert sw.fingerprint(p)==cal['fingerprint']
seen=set();builds=0;comparisons=0;ratio_checks=0
for row in ledger:
    report=read(ROOT/'benchmark/swap-standard/evaluations'/row['id']/'report.json')
    assert report['id']==row['id'] and report['status']==row['status']
    assert row['status']!='RUNNING'
    if row.get('kind')=='build':
        builds+=1;b=read(ROOT/row['result'])
        assert b['passed'] is True and b['commit']==row['candidate_commit']
        assert sha(ROOT/row['result'])==row['result_sha256']
        out=(ROOT/row['result']).parent/'output'
        assert sha(out/'.config')==b['config_sha256']
        assert sha(out/'arch/x86/boot/bzImage')==b['image_sha256']
        cfg=row['command'][row['command'].index('--config')+1]
        assert sha(ROOT/cfg)==b['input_config_sha256']
    paths=[]
    if row.get('kind')=='guest':paths.append((ROOT/row['result'],row))
    for attempt in report.get('runs',[]):
        result=ROOT/attempt.get('result','benchmark/swap-standard/runs/'+attempt['id']+'/result.json')
        paths.append((result,attempt))
    for path,attempt in paths:
        r=read(path)
        assert r['run_id'] not in seen;seen.add(r['run_id'])
        assert sha(path)==attempt['result_sha256']
        assert sha(path.parent/'serial.log')==r['serial_sha256']
        if attempt['status']=='PASS':assert r['integration_pass'] is True
        if row['action']!='calibrate' or row['id']==cal['id']:
            assert r['swap_image_allocation']=='preallocated'
        if 'arm' in attempt:
            expected=p['baseline_commit'] if attempt['arm']=='a' else report['candidate_commit']
            assert r['source_commit']==expected and r['metrics']==attempt['metrics']
    if row['action']=='evaluate':
        comparisons+=1
        assert report['fingerprint']==cal['fingerprint'] and report['calibration_id']==cal['id']
        assert len(report['pairs'])==p['tiers']['fast']['comparison_pairs']
        assert [x['order'] for x in report['pairs']]==['AB','BA']
        assert report['performance_accepted'] is False and report['auto_promote'] is False
        for key,result in report['analysis']['metrics'].items():
            ratios=[pair['a'][key]/pair['b'][key] for pair in report['pairs']]
            expected=math.exp(statistics.mean(math.log(r) for r in ratios))
            assert math.isclose(expected,result['geomean_ratio'],rel_tol=1e-12)
            ratio_checks+=1
assert len(seen)==budget['guests']<=p['budget']['guest_attempts']
assert builds==budget['builds']<=p['budget']['build_attempts']
registry=read(ROOT/'evolve/control/state'/C/'candidates.json')
assert len(registry)<=p['max_candidates'] and all(x['status']=='closed' for x in registry.values())
assert subprocess.check_output(['git','-C',str(ROOT/'linux'),'status','--porcelain'],text=True).strip()==''
assert subprocess.check_output(['git','-C',str(ROOT/'linux'),'rev-parse','HEAD'],text=True).strip()=='744e5400b36f84b4816e3ff8531ec2dff52b474c'
assert subprocess.run(['git','-C',str(ROOT/'linux'),'merge-base','--is-ancestor','b2beda7fe460f911b88d27890993347588d70748',p['baseline_commit']],check=False).returncode==0
out=dict(passed=True,verified_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),unique_guest_results=len(seen),builds=builds,candidate_comparisons=comparisons,independent_ratio_checks=ratio_checks,calibration_id=cal['id'],fingerprint=cal['fingerprint'],baseline=p['baseline_commit'],p123_ancestry=True,linux_checkout_clean=True,all_candidates_closed=True,budget=budget)
(ROOT/'results'/C/'evidence-audit.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
