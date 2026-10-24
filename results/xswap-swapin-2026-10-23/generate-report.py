#!/usr/bin/env python3
"""Read-only campaign evidence extraction; outputs are provisional unless --final."""
import argparse, collections, datetime, hashlib, json, math, subprocess
from pathlib import Path
C='xswap-swapin-2026-10-23'
def read(p, default=None):
    return json.loads(p.read_text()) if p.exists() else default
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
def flow(title, labels):
    return {'type':'flow','takeaway':title,'nodes':[{'id':str(i),'label':v,'col':i,'row':0,'tone':'focus' if i==2 else 'default'} for i,v in enumerate(labels)],'edges':[{'from':str(i),'to':str(i+1)} for i in range(len(labels)-1)]}
def table(title, columns, rows):
    return {'type':'table','takeaway':title,'columns':columns,'rows':rows}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--final',action='store_true');a=ap.parse_args()
    root=a.root.resolve();out=a.out.resolve()
    if out==root or root in out.parents:
        raise SystemExit('Output must remain outside canonical repository; primary integrates reviewed outputs.')
    out.mkdir(parents=True,exist_ok=True)
    bench=root/'benchmark/swap-standard'; state=root/'evolve/swap-standard'/('state-'+C); results=root/'results'/C
    protocol_path=bench/('protocol-'+C+'.json');protocol=read(protocol_path);policy=read(root/'evolve/control/campaigns'/C/'policy.json')
    evidence={}
    def record(p):
        if p.exists():
            key=str(p.relative_to(root));evidence[key]={'sha256':sha(p),'bytes':p.stat().st_size};return key
    record(protocol_path)
    registry=read(root/'evolve/control/state'/C/'candidates.json',{})
    ledger_path=state/'ledger.json';ledger=read(ledger_path,[]);record(ledger_path)
    rows=[]
    for entry in ledger:
        report=bench/'evaluations'/entry['id']/'report.json';record(report)
        row=read(report,entry);rows.append(row)
    run_names={p.name for p in (bench/'runs').glob('resume-*') if p.is_dir()}
    for row in rows:
        run_names.update(x['id'] for x in row.get('runs',[]))
        command=row.get('command',[])
        if '--run-id' in command:run_names.add(command[command.index('--run-id')+1])
    active_runs=set()
    for row in rows:
        if row.get('status') == 'RUNNING':
            cmd=row.get('command',[])
            if '--run-id' in cmd:active_runs.add(cmd[cmd.index('--run-id')+1])
            active_runs.update(x['id'] for x in row.get('runs',[]) if x.get('status')=='STARTED')
    runs=[]
    for name in sorted(run_names):
        p=bench/'runs'/name;result=read(p/'result.json',{});started=read(p/'started.json',{})
        row={'id':name,'result_path':record(p/'result.json'),'started_path':record(p/'started.json'),'serial_path':record(p/'serial.log'),'result':result or None}
        row['status']=('PASS' if result.get('integration_pass') is True else 'STOPPED' if result.get('stop_reason')=='STOP' else 'COMPLETED_FAILED' if result else 'RUNNING' if name in active_runs else 'INCOMPLETE_NO_RESULT')
        row['failed_gates']=[k for k,v in result.get('gates',{}).items() if v is not True]
        row['harness_incomplete']=bool(result and (not result.get('gates',{}).get('workload_complete') or not result.get('gates',{}).get('kernel_log_present')))
        row['failure_reason']=result.get('stop_reason') or result.get('parse_error') or row['failed_gates']
        row['build']=(result or started).get('build');runs.append(row)
    builds=[];names={r['build'] for r in runs if r['build']};names.add(protocol['baseline_build'])
    for row in rows:
        cmd=row.get('command',[])
        if row.get('action')=='auxiliary-build' and '--name' in cmd:names.add(cmd[cmd.index('--name')+1])
    for name in sorted(names):
        p=root/'benchmark/kernel/builds'/name;d=read(p/'result.json',{});config=p/'output/.config';lines=set(config.read_text().splitlines()) if config.exists() else set()
        builds.append({'name':name,'path':record(p/'result.json'),'result':d,'config_path':record(config),'config_hash_matches':bool(d and sha(config)==d.get('config_sha256')),'effective':{k:'CONFIG_'+k+'=y' in lines for k in ('SWAP','XSWAP','ZSWAP','KASAN','KASAN_VMALLOC','PROVE_LOCKING','PROVE_RCU','KCSAN','SLUB_TINY')}})
    buildmap={b['name']:b for b in builds}
    for row in runs:
        b=buildmap.get(row['build'],{});row['effective_kasan_pass']=row['status']=='PASS' and b.get('config_hash_matches') is True and b.get('effective',{}).get('KASAN') is True and row['result'].get('config_sha256')==b.get('result',{}).get('config_sha256')
    patches=[]
    for name,entry in registry.items():
        patch=root/'evolve/control/state'/C/name/'candidate.patch'
        if patch.exists():patches.append({'candidate':name,'path':record(patch),'patch':patch.read_text()})
    for p in sorted((root/'patches').glob('xswap-swapin*/*.patch')):
        text=p.read_text();record(p)
        mailbox_commit=text.splitlines()[0].split()[1] if text.startswith('From ') else None
        candidates=[]
        for name,entry in registry.items():
            try:head=subprocess.check_output(['git','-C',entry['worktree'],'rev-parse','HEAD'],text=True).strip()
            except subprocess.CalledProcessError:continue
            if head==mailbox_commit:candidates.append(name)
        # Known campaign exports may omit a mailbox header; map by mechanism.
        if not candidates:
            token='zswap' if 'zswap' in p.name.lower() or 'compressed' in p.name.lower() else 'phys' if 'phys' in p.name.lower() else None
            candidates=[name for name in registry if token and token in name]
        candidate=candidates[0] if len(candidates)==1 else p.stem
        if not any(x['candidate']==candidate for x in patches):patches.append({'candidate':candidate,'path':str(p.relative_to(root)),'patch':text})
    supplemental={}
    for p in sorted(results.glob('*.json')):
        if p.name not in ('summary.json','explainer.json'):
            supplemental[record(p)]=read(p)
    sparse={k:v for k,v in supplemental.items() if 'sparse' in k}
    points=collections.defaultdict(list)
    for row in rows:
        if row.get('action') not in ('calibrate','evaluate','reference-check'):continue
        label=("A/A" if row.get("action")=="calibrate" else "H1" if row.get("candidate")=="xs-ra-phys-v1" else "H2" if row.get("candidate")=="xs-ra-zswap-v1" else "Reference")+" "+str(row.get("tier"))
        for index,pair in enumerate(row.get('pairs',[])):
            for arm in ('a','b'):
                for metric,value in pair.get(arm,{}).items():
                    if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value):
                        points[metric].append({'group':label,'series':arm.upper(),'value':value,'tip':f"{row['id']} pair {index} {pair.get('order')} arm {arm}"})
    static_reports={}
    for name in registry:
        p=root/'evolve/control/state'/C/name/'static.json'
        if p.exists():static_reports[name]={'path':record(p),'data':read(p)}
    missing=[];gate_rows=[]
    commits={protocol['baseline_commit']:'baseline'}
    for name,entry in registry.items():
        try:commit=subprocess.check_output(['git','-C',entry['worktree'],'rev-parse','HEAD'],text=True).strip()
        except subprocess.CalledProcessError:continue
        commits[commit]=name
    for commit,name in commits.items():
        passed=[r for r in runs if r['status']=='PASS' and r['result'].get('source_commit')==commit]
        for gate in policy['required_gates']:
            proof=[r['result_path'] for r in passed if r['result'].get('gates',{}).get(gate) is True]
            if gate=='guest_boot_identity':proof=[r['result_path'] for r in passed if r['result']['gates'].get('cmdline_identity') is True]
            if gate=='kasan':proof=[r['result_path'] for r in passed if r['effective_kasan_pass']]
            if gate=='lockdep':proof=[r['result_path'] for r in passed if buildmap.get(r['build'],{}).get('config_hash_matches') and buildmap.get(r['build'],{}).get('effective',{}).get('PROVE_LOCKING')]
            if gate in ('gcc_swap_on','gcc_swap_off','gcc_zswap_on'):
                option='ZSWAP' if gate=='gcc_zswap_on' else 'SWAP'
                wanted=gate!='gcc_swap_off'
                proof=[b['path'] for b in builds if b['result'].get('commit')==commit and b['result'].get('passed') is True and b['config_hash_matches'] and b['effective'][option] is wanted]
            if gate=='checkpatch':
                static=static_reports.get(name,{})
                if static.get('data',{}).get('candidate_commit')==commit and static['data'].get('checkpatch',{}).get('exit_code')==0:proof=[static['path']]
            if gate=='sparse_no_new_diagnostics':
                proof=[path for path,data in sparse.items() if data.get('no_new_diagnostics') is True and any(buildmap.get(check.get('build'),{}).get('result',{}).get('commit')==commit for check in data.get('checks',[]))]
            status='pass' if proof else 'missing'
            if not proof:missing.append({'candidate':name,'gate':gate})
            gate_rows.append([name,gate,status,'; '.join(proof) or 'No automatically matched exact-commit evidence; inspect supplemental artifacts'])
    counts=dict(collections.Counter(r['status'] for r in runs));counts['running']=counts.get('RUNNING',0);counts['completed_failed']=counts.get('COMPLETED_FAILED',0);counts['stopped']=counts.get('STOPPED',0);counts['incomplete']=counts.get('INCOMPLETE_NO_RESULT',0);performance=[r for r in rows if r.get('action') in ('calibrate','evaluate','reference-check')]
    metric_rows=[];mechanism_rows=[];snapshot_rows=[];findings=[];compressed_latency_rows=[]
    for row in performance:
        analysis=row.get('analysis',{})
        if row.get('action')=='evaluate':
            failed=[key for key,value in analysis.get('metrics',{}).items() if value.get('guard_pass') is False]
            findings.append({'candidate':row.get('candidate'),'tier':row.get('tier'),'status':row.get('status'),'pair_count':analysis.get('pair_count'),'failed_guards':failed,'report':str(Path('benchmark/swap-standard/evaluations')/row['id']/'report.json')})
            for metric,value in analysis.get('metrics',{}).items():
                ratio=value.get('geomean_ratio');change=(1/ratio-1)*100 if isinstance(ratio,(int,float)) and ratio>0 else None
                metric_rows.append([row.get('candidate'),row.get('tier'),analysis.get('pair_count'),metric,round(ratio,6) if ratio is not None else None,round(change,2) if change is not None else None,round(value['noise_relative']*100,2) if 'noise_relative' in value else None,'PASS' if value.get('guard_pass') is True else 'FAIL' if value.get('guard_pass') is False else 'MISSING'])
        for run in row.get('runs',[]):
            metrics=run.get('metrics',{});counters=metrics.get('swapin_vmstat_delta',{})
            if row.get('action')=='evaluate' and 'zswap' in (row.get('candidate') or '') and run.get('case')=='swapin-zswap':
                seq=metrics.get('swapin_seq',{})
                if seq:compressed_latency_rows.append([row.get('candidate'),run.get('pair'),run.get('arm')]+[round(seq[k]/1000,3) if k in seq else None for k in ('p50_ns','p90_ns','mean_ns','p99_ns')])
            if counters:
                mechanism_rows.append([row.get('candidate') or row.get('action'),row.get('tier'),run.get('pair'),run.get('case'),run.get('arm')]+[counters.get(k) for k in ('swap_ra','swap_ra_hit','pswpin','zswpin')])
            for phase,values in metrics.get('swapin_xswap_snapshots',{}).items():
                snapshot_rows.append([row.get('candidate') or row.get('action'),run.get('pair'),run.get('case'),run.get('arm'),phase]+[values.get(k) for k in ('clusters_mapped','usage_pages','grows','shrinks')])
    status_parts=[f"{f['candidate']} {f['tier']}: {f['status']}" for f in findings]
    verdict_label='; '.join(status_parts) if status_parts else 'No candidate evaluation completed'
    verdict_status='needs-review' if any(f['status']=='NEEDS_REVIEW' for f in findings) else 'rejected' if findings and all(f['status']=='REGRESSION' for f in findings) else 'inconclusive'
    next_rows=[['1','H2 compressed residency-aware readahead','Reject if zswap sequential latency fails calibrated noise or random tail regresses.'],['2','Readahead window or clustering','Reject if wasted reads rise without latency improvement.'],['3','Complete promotion coverage','Require missing gates and matched sparse baseline diagnostics before acceptance.']]
    closed=bool(registry) and all(v.get('status')!='active' for v in registry.values())
    idle=counts['running']==0 and not any(r.get('status')=='RUNNING' for r in rows)
    if closed and idle:
        next_rows=[['1','H1 adaptive readahead window with a tail guard','Reject a new candidate if random p99 exceeds its calibrated envelope.'],['2','H2 bound synchronous decompression work','Reject unbounded prefetch or added demand-fault latency.'],['3','Further validation only for a new candidate','Require fresh correctness evidence and a fast pass before slow confirmation.']]
    elif any('zswap' in name for name in registry):
        next_rows[0]=['1','Complete or review the active H2 experiment','Use its own frozen screening and confirmation evidence; no duplicate implementation.']
    all_screened=bool(findings) and all(f['tier']=='fast' and f['status']=='REGRESSION' for f in findings)
    if all_screened and closed and idle:
        verdict_label=f'{len(findings)} candidates screened out; none eligible for slow confirmation'
    limitations=['No processes remain active in the extracted campaign ledger.' if closed and idle else 'Working snapshot can change while active processes finish.','Retained failed harness attempts are not classified as candidate kernel defects.','Gate inventory is conservative and may require manual matching of static reports.','No formal acceptance, promotion, or publication.']
    calibration_starts=[r.get('started') for r in performance if r.get('action')=='calibrate' and r.get('started') is not None]
    first_calibration=min(calibration_starts) if calibration_starts else None
    failed_runs=[r for r in runs if r['status']=='COMPLETED_FAILED']
    harness_failures=[]
    for r in failed_runs:
        matching=[entry for entry in rows if '--run-id' in entry.get('command',[]) and entry['command'][entry['command'].index('--run-id')+1]==r['id']]
        if matching and first_calibration is not None and all(entry.get('finished',float('inf'))<first_calibration for entry in matching):harness_failures.append(r['id'])
    failure_note=f'{len(harness_failures)} retained failed harness attempts preceded calibration; they are not candidate-bug findings.' if harness_failures else 'Retained failure causes require their individual logs.'
    summary={'schema_version':1,'campaign':C,'provisional':not a.final,'generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'performance_accepted':False,'auto_promote':False,'published':False,'protocol':protocol,'policy':policy,'budget':read(state/'budget.json'),'ledger':rows,'runs':runs,'builds':builds,'patches':patches,'supplemental':supplemental,'sparse':sparse,'static_reports':static_reports,'run_counts':counts,'missing_gates':missing,'candidate_findings':findings,'metric_ratios':metric_rows,'compressed_latency_rows':compressed_latency_rows,'mechanism_rows':mechanism_rows,'xswap_snapshot_rows':snapshot_rows,'metric_points':dict(points),'evidence':evidence,'limitations':limitations,'precalibration_harness_failures':harness_failures,'failure_note':failure_note,'next_hypotheses':next_rows}
    (out/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    charts=[]
    for k,v in sorted(points.items()):
        changes=[('H1' if r[0]=='xs-ra-phys-v1' else 'H2')+f' {r[5]:+.2f}%' for r in metric_rows if r[3]==k and r[5] is not None]
        metric_label=k.replace('swapin-disk.','disk ').replace('swapin-zswap.','zswap ').replace('swapin_seq.','sequential ').replace('swapin_rand.','random ').replace('_ns','')
        title='Observed '+metric_label+': '+', '.join(changes)
        charts.append({'type':'strip','takeaway':title,'x_label':'Latency (ns)','groups':list(dict.fromkeys(x['group'] for x in v)),'series':['A','B'],'points':v})
    change=[flow('Fault routing is tested against the repaired baseline',['Fault','Residency check','Readahead','Swap cache'])]+[{'type':'diff','takeaway':p['candidate'],'patch':p['patch']} for p in patches]
    display_gate_rows=[]
    for name,gate,status,full in gate_rows:
        paths=full.split('; ') if status=='pass' else []
        if paths:
            first=Path(paths[0]);label=first.parent.name+'/'+first.name
            compact=label+(f' + {len(paths)-1} more' if len(paths)>1 else '')+'; summary.json'
        else:
            compact='Missing; summary.json'
        display_gate_rows.append([name,gate,status,compact])
    verdict=('Provisional: ' if not a.final else '')+verdict_label
    spec={'title':'xswap swap-in campaign','subtitle':C+' · '+protocol['baseline_commit'][:12],'verdict':{'status':verdict_status,'headline':verdict,'tiles':[{'label':'Guest attempts observed','value':len(runs)},{'label':'Integration passes','value':counts.get('PASS',0)},{'label':'Failed / running / incomplete / stopped','value':f"{counts['completed_failed']} / {counts['running']} / {counts['incomplete']} / {counts['stopped']}"},{'label':'Effective KASAN passes','value':sum(r['effective_kasan_pass'] for r in runs)}]},'sections':[
      {'id':'changes','title':'What changed','blocks':change},
      {'id':'method','title':'How it was measured','blocks':[flow('Fresh boots preserve paired order',['Baseline/build','Correctness','AB / BA','Noise / guards'])]},
      {'id':'data','title':'What the data shows','blocks':[table('Observed latency changes and guard outcomes',['Candidate','Tier','Pairs','Metric','Baseline/candidate','Latency change %','Noise %','Guard'],metric_rows),{'type':'note','text':'Fast screening uses few pairs; failed guards block confirmation. Observed differences do not establish persistent causal effects. Unchanged-path outliers are not mechanism evidence.'}]+(charts or [{'type':'note','text':'No performance pair values exist in this snapshot.'}])},
      {'id':'why','title':'Why','blocks':[flow('Mechanism claims require counters and calibrated latency',['Residency','Backend reads','First touch','Noise check']),table('H2 compressed latency distribution, microseconds',['Candidate','Pair','Arm','p50','p90','Mean','p99'],compressed_latency_rows),{'type':'note','text':'Inference: compressed prefetch shifts synchronous decompression into fewer, longer fault bursts. Source paths, counters and latency distributions support this interpretation; independent profiling has not established causality.'},table('Every run retains mechanism counters',['Candidate/action','Tier','Pair','Case','Arm','swap_ra','swap_ra_hit','pswpin','zswpin'],mechanism_rows),table('Occupancy snapshots accompany each observed phase',['Candidate/action','Pair','Case','Arm','Phase','Mapped','Usage','Grows','Shrinks'],snapshot_rows),table('Every retained performance attempt',['Action','Tier','Candidate','Status','Reason'],[[r.get(k,'') for k in ('action','tier','candidate','status','reason')] for r in performance])]},
      {'id':'gates','title':'Review checklist','blocks':[table('Every policy gate remains visible',['Candidate','Gate','Status','Evidence'],display_gate_rows),table('Sparse diagnostics retain the baseline gap',['Evidence','No new diagnostics','Full tool success'],[[k,v.get('no_new_diagnostics'),v.get('full_tool_success')] for k,v in sparse.items()]),table('Nonpassing and active attempts remain separate',['Run','State','Reason'],[[r['id'],r['status'],str(r['failure_reason'])] for r in runs if r['status']!='PASS'])]},
      {'id':'next','title':'Next','blocks':[table('Ranked next hypotheses require falsifiers',['Rank','Hypothesis','Falsifier'],next_rows),{'type':'note','text':'No formal acceptance, automatic promotion, or publication. Missing evidence remains missing.'}]}]}
    (out/'explainer.json').write_text(json.dumps(spec,indent=2,allow_nan=False)+'\n')
    report=[f'# {C}',f'\nStatus: {verdict}. No formal acceptance, promotion, or publication.\n',failure_note+'\n',f'Observed guest attempts: {len(runs)}; integration passes: {counts.get("PASS",0)}; completed failed: {counts["completed_failed"]}; running: {counts["running"]}; incomplete: {counts["incomplete"]}; stopped: {counts["stopped"]}; effective KASAN passes: {sum(r["effective_kasan_pass"] for r in runs)}.\n','## Evaluations','| Action | Tier | Candidate | Status | Reason |','|---|---|---|---|---|']
    report += ['| '+' | '.join(str(r.get(k,'')) for k in ('action','tier','candidate','status','reason'))+' |' for r in performance]
    report += ['\n## Metric ratios and failed guards','Fast is a screening result; slow is confirmation evidence. Few fast pairs do not establish a persistent causal regression. H1 has no compressed readahead path; observed zswap differences, including baseline random-tail outliers, are not credited as H1 mechanism improvements.','| Candidate | Tier | Pairs | Metric | Baseline/candidate | Latency change % | Noise % | Guard |','|---|---|---|---|---|---|---|---|']
    report += ['| '+' | '.join(map(str,r))+' |' for r in metric_rows]
    report += ['\n## Failed guards']+[f"- {f['candidate']} {f['tier']} {f['status']}: "+(', '.join(f['failed_guards']) or 'none recorded') for f in findings]
    report += ['\n## H2 compressed latency distribution','Inference: synchronous compressed prefetch concentrates decompression cost into fewer fault bursts. Source paths, readahead counters and the p50/p90 distribution support this interpretation; independent profiling has not established causality.','| Candidate | Pair | Arm | p50 us | p90 us | Mean us | p99 us |','|---|---|---|---|---|---|---|']+['| '+' | '.join(map(str,r))+' |' for r in compressed_latency_rows]
    report += ['\n## Mechanism counters','| Candidate/action | Tier | Pair | Case | Arm | swap_ra | swap_ra_hit | pswpin | zswpin |','|---|---|---|---|---|---|---|---|---|']+['| '+' | '.join(map(str,r))+' |' for r in mechanism_rows]
    report += ['\n## Xswap occupancy snapshots','| Candidate/action | Pair | Case | Arm | Phase | Mapped | Usage | Grows | Shrinks |','|---|---|---|---|---|---|---|---|---|']+['| '+' | '.join(map(str,r))+' |' for r in snapshot_rows]
    report += ['\n## Correctness and build evidence','Exact run gates, output-config sanitizer settings, result and serial hashes are preserved in summary.json. Debug names alone do not establish KASAN coverage.','\n## Sparse coverage']+[f'- {k}: no_new_diagnostics={v.get("no_new_diagnostics")}, full_tool_success={v.get("full_tool_success")}. Baseline diagnostics remain a tool-coverage gap.' for k,v in sparse.items()]
    report += ['\n## Missing policy gates']+[f'- {x["candidate"]}: {x["gate"]}' for x in missing]
    report += ['\n## Exact patches']+[f'\n### {p["candidate"]}\nSource: {p["path"]}\n```diff\n{p["patch"]}\n```' for p in patches]
    report += ['\n## Next hypotheses']+['- '+r[1]+': '+r[2] for r in next_rows]+['\n## Limitations']+['- '+x for x in summary['limitations']]
    (out/'REPORT.md').write_text('\n'.join(report)+'\n')
    builder=root/'.agents/skills/explaining-campaign-results/scripts/build_page.py'
    subprocess.run(['python3',str(builder),str(out/'explainer.json'),str(out/'explainer.html')],check=True)
    import re
    html_path=out/'explainer.html'
    html_path.write_text(re.sub(r'(<pre class="diff">.*?</pre>)', r'<details><summary>View exact patch</summary>\1</details>', html_path.read_text(), flags=re.S))
    print(json.dumps({'out':str(out),'attempts':len(runs),'passes':counts.get('PASS',0),'plotted_metrics':len(points),'provisional':not a.final}))
if __name__=='__main__':main()
