#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Extract the campaign review from retained trusted reports, never invented scores."""
import datetime, hashlib, importlib.util, json, math, re, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
C='xswap-next-2026-10-24'
OUT=ROOT/'results'/C
STATE=ROOT/'evolve/swap-standard'/('state-'+C)
def read(p, default=None):
    return json.loads(p.read_text()) if p.exists() else default
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def relative(p): return str(p.relative_to(ROOT))
def table(title,columns,rows): return dict(type='table',takeaway=title,columns=columns,rows=rows)
def flow(title,nodes,edges): return dict(type='flow',takeaway=title,nodes=nodes,edges=edges)
def main():
    protocol=read(ROOT/'benchmark/swap-standard'/('protocol-'+C+'.json'))
    policy=read(ROOT/'evolve/control/campaigns'/C/'policy.json')
    registry=read(ROOT/'evolve/control/state'/C/'candidates.json',{})
    ledger=read(STATE/'ledger.json',[])
    evidence={}
    def record(p):
        if p.exists(): evidence[relative(p)]=dict(sha256=sha(p),bytes=p.stat().st_size)
    reports=[];runs=[];builds=[]
    for row in ledger:
        p=ROOT/'benchmark/swap-standard/evaluations'/row['id']/'report.json';record(p)
        d=read(p,row);reports.append(d)
        paths=[ROOT/x.get('result','benchmark/swap-standard/runs/'+x['id']+'/result.json') for x in d.get('runs',[])]
        if d.get('kind')=='guest' and d.get('result'): paths.append(ROOT/d['result'])
        for p in paths:
            record(p);r=read(p)
            if r:
                r.update(evaluation_id=d['id'],candidate=d.get('candidate'),action=d['action'])
                runs.append(r);record(p.parent/'serial.log')
        if d.get('kind')=='build' and d.get('result'):
            p=ROOT/d['result'];record(p);b=read(p)
            if b:
                config=(p.parent/'output/.config').read_text().splitlines()
                flags={k:('CONFIG_'+k+'=y') in config for k in ['SWAP','ZSWAP','XSWAP','KASAN','KASAN_GENERIC','KASAN_VMALLOC','PROVE_LOCKING','KCSAN']}
                builds.append(dict(name=p.parent.name,commit=b['commit'],passed=b.get('passed'),result=relative(p),config_sha256=b.get('config_sha256'),flags=flags))
    mechanisms=[dict(run_id=r['run_id'],candidate=r.get('candidate'),action=r['action'],backend=r['backend'],source_commit=r['source_commit'],counters=r['metrics'].get('swapin_vmstat_delta',{}),snapshots=r['metrics'].get('swapin_xswap_snapshots',{})) for r in runs if r.get('workload')=='swapin']
    costs=[]
    for r in runs:
        if r.get('workload')!='swapin':continue
        serial=(ROOT/'benchmark/swap-standard/runs'/r['run_id']/'serial.log').read_text()
        blocks={}
        for label,body in re.findall(r'CGSTAT_BEGIN (\w+)\s+(.*?)CGSTAT_END \1',serial,re.S):
            blocks[label]={key:int(value) for key,value in re.findall(r'^([a-z_.]+) (\d+)\s*$',body,re.M)}
        end=blocks.get('end',{});start=blocks.get('start',{})
        cost=dict(run_id=r['run_id'],candidate=r.get('candidate'),source_commit=r['source_commit'],backend=r['backend'],scored=False)
        cost.update({key:end[key]-start.get(key,0) for key in ['usage_usec','system_usec','user_usec'] if key in end})
        cost.update({key:end[key] for key in ['memory.peak','memory.swap.peak'] if key in end})
        for phase in ['swapin_seq','swapin_rand']:
            v=r['metrics'][phase];cost[phase+'_pages_per_second']=v['samples']/(v['total_ms']/1000)
        costs.append(cost)
    comparisons=[x for x in reports if x['action']=='evaluate']
    metrics=[]
    for d in comparisons:
        for name,m in d.get('analysis',{}).get('metrics',{}).items():
            metrics.append(dict(candidate=d['candidate'],metric=name,ratio=m['geomean_ratio'],latency_change_percent=(1/m['geomean_ratio']-1)*100,noise_percent=m['noise_relative']*100,guard_pass=m['guard_pass']))
    candidate_rows=[];patches=[]
    for name,rec in registry.items():
        commit=subprocess.check_output(['git','-C',rec['worktree'],'rev-parse','HEAD'],text=True).strip()
        patch=subprocess.check_output(['git','-C',rec['worktree'],'diff',protocol['baseline_commit'],commit],text=True)
        p=ROOT/'evolve/control/state'/C/name/'candidate.patch';record(p)
        ev=[d for d in comparisons if d.get('candidate')==name]
        correctness=[r for r in runs if r.get('candidate')==name and r['workload']=='correctness']
        candidate_rows.append(dict(name=name,commit=commit,hypothesis=rec['hypothesis'],controller_status=rec['status'],decision_reason=rec.get('reason','active'),evaluation_status=[d['status'] for d in ev],correctness_passes=sum(r.get('integration_pass') is True for r in correctness)))
        patches.append(dict(type='diff',takeaway=name+' exact patch',patch=patch))
    gate_rows=[]
    for item in candidate_rows:
        commit=item['commit'];name=item['name']
        cr=[r for r in runs if r.get('candidate')==name and r.get('workload')=='correctness' and r.get('source_commit')==commit]
        cb=[b for b in builds if b['commit']==commit and b.get('passed') is True]
        static=read(ROOT/'evolve/control/state'/C/name/'static.json',{})
        observed={}
        for gate in policy['required_gates']:
            passed=False
            if gate in ['data_roundtrip','fork_cow','concurrent_fault','swapoff_live_pages','no_new_kernel_warnings']:
                passed=bool(cr) and all(r.get('integration_pass') is True and r.get('gates',{}).get(gate) is True for r in cr)
            elif gate=='guest_boot_identity': passed=bool(cr) and all(r.get('gates',{}).get('boot') is True and r.get('gates',{}).get('cmdline_identity') is True for r in cr)
            elif gate=='gcc_swap_on': passed=any(b['flags']['SWAP'] for b in cb)
            elif gate=='gcc_zswap_on': passed=any(b['flags']['ZSWAP'] for b in cb)
            elif gate=='gcc_swap_off': passed=any(not b['flags']['SWAP'] for b in cb)
            elif gate=='checkpatch': passed=static.get('candidate_commit')==commit and static.get('checkpatch',{}).get('exit_code')==0
            elif gate in ['kasan','lockdep']:
                flag='KASAN' if gate=='kasan' else 'PROVE_LOCKING'
                valid={b['name'] for b in cb if b['flags'][flag]}
                passed=any(r['build'] in valid and r.get('integration_pass') is True and r.get('gates',{}).get('no_kernel_warnings') is True for r in cr)
            observed[gate]='observed' if passed else 'missing'
            gate_rows.append([name,gate,observed[gate]])
        item['observed_gates']=observed
    running=[d['id'] for d in reports if d['status']=='RUNNING']
    failed=[d for d in reports if d['status'] in ['INCOMPLETE','BLOCKED','CALIBRATION_NOISY']]
    admitted=[d['candidate'] for d in comparisons if d['status']=='FAST_PASS']
    counts=dict(reserved=read(STATE/'budget.json',{}),completed_guests=len(runs),integration_passes=sum(r.get('integration_pass') is True for r in runs),candidate_comparisons=len(comparisons),fast_passes=len(admitted),running_evaluations=len(running))
    summary=dict(campaign=C,generated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),baseline_commit=protocol['baseline_commit'],protocol_revision=protocol.get('protocol_revision',1),counts=counts,candidates=candidate_rows,metrics=metrics,builds=builds,mechanisms=mechanisms,descriptive_costs=costs,reports=[{k:d.get(k) for k in ['id','action','kind','candidate','status','reason','fingerprint']} for d in reports],running=running,performance_accepted=False,promotion=False,publication=False)
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    lines=['# '+C,'','Status: '+('RUNNING' if running else 'CLOSED')+'. Fast discovery only; human promotion remains disabled.','','[Visual review](explainer.html) · [Machine-readable summary](summary.json)','','## Results','','| Candidate | Commit | Evaluation | Correctness passes |','|---|---|---|---|']
    lines += [f"| {r['name']} | `{r['commit']}` | {', '.join(r['evaluation_status']) or 'not measured'} | {r['correctness_passes']} |" for r in candidate_rows]
    lines += ['','## Candidate decisions','']+[r['name']+': '+r['decision_reason']+'\n' for r in candidate_rows]
    lines += ['','## Per-workload latency','','| Candidate | Metric | Change % | Noise % | Guard |','|---|---|---:|---:|---|']
    lines += [f"| {m['candidate']} | {m['metric']} | {m['latency_change_percent']:+.2f} | {m['noise_percent']:.2f} | {'PASS' if m['guard_pass'] else 'FAIL'} |" for m in metrics]
    lines += ['','## Retained attempts','',f"Reserved guests: {counts['reserved'].get('guests',0)}/{protocol['budget']['guest_attempts']}; builds: {counts['reserved'].get('builds',0)}/{protocol['budget']['build_attempts']}. Completed guest results: {len(runs)}. Running evaluations: {len(running)}.",'','| Action | Candidate | Status | Evidence |','|---|---|---|---|']
    lines += [f"| {d['action']} {d.get('kind','')} | {d.get('candidate') or 'baseline'} | {d['status']} | benchmark/swap-standard/evaluations/{d['id']}/report.json |" for d in reports]
    lines += ['','## Confidence and falsifiers','','| Finding | Confidence | Observation that changes it |','|---|---|---|','| Reported pass/fail and per-run values match retained evidence | High | Hash mismatch, parser defect or missing result |','| Two-pair effects describe this fast screen | High for these samples; low for generalization | Independent confirmation under the same frozen protocol |','| Source mechanisms explain an observed latency effect | Medium pending profiling | Path counters or targeted profiles contradict the proposed cause |']
    lines += ['','## Mechanism counters','','| Run | Candidate | Backend | swap_ra | swap_ra_hit | pswpin | zswpin |','|---|---|---|---:|---:|---:|---:|']+[f"| {m['run_id']} | {m['candidate'] or 'baseline'} | {m['backend']} | {m['counters'].get('swap_ra',0)} | {m['counters'].get('swap_ra_hit',0)} | {m['counters'].get('pswpin',0)} | {m['counters'].get('zswpin',0)} |" for m in mechanisms]
    lines += ['','## Descriptive cost readback','','Extracted after scoring from retained raw logs; these values were not admission metrics. CPU spans fill, page-out, faults and verification. The page rate is derived from the timed first-touch phase.','','| Run | Candidate | Arm | Backend | System CPU ms | Peak MiB | Seq pages/s | Rand pages/s |','|---|---|---|---|---:|---:|---:|---:|']+[f"| {m['run_id']} | {m['candidate'] or 'A/A'} | {'A' if m['source_commit']==protocol['baseline_commit'] else 'B'} | {m['backend']} | {m.get('system_usec',0)/1000:.2f} | {m.get('memory.peak',0)/2**20:.2f} | {m['swapin_seq_pages_per_second']:.2f} | {m['swapin_rand_pages_per_second']:.2f} |" for m in costs]
    lines += ['','## Required policy gates','','Observed applies only to the tested configuration and workload; full promotion remains disabled.','','| Candidate | Gate | Evidence state |','|---|---|---|']+[f'| {n} | {g} | {v} |' for n,g,v in gate_rows]
    lines += ['','## Judgment and next steps','','A fast pass is a screening result. Retain useful mechanisms for owner review; do not launch a slow tier without explicit approval. A noisy A/A blocks its matching performance comparison. Confidence in correctness is limited to the actual configurations and guests recorded. A correctness failure or failed latency guard changes candidate disposition.','','## Limitations','','The first sparse-image A/A failed with 23.8% disk-random mean variation. Revision 2 preallocates private guest images; allocation is a plausible confounder rather than an established root cause. Every attempt counts against the same budget. Four-KiB application first-touch latency includes cache, timer, scheduling and readahead costs. Full promotion still needs allocation/I/O failure injection, memcg/large-folio/KCSAN coverage, confirmation and holdout. No candidate code is merged or published.','']
    (OUT/'REPORT.md').write_text('\n'.join(lines))
    metricrows=[[m['candidate'],m['metric'],round(m['latency_change_percent'],2),round(m['noise_percent'],2),'PASS' if m['guard_pass'] else 'FAIL'] for m in metrics]
    strips=[]
    for case in protocol['tiers']['fast']['cases']:
        for metric in ['swapin_seq','swapin_rand']:
            for stat in ['mean_ns','p99_ns']:
                points=[]
                for r in runs:
                    if r.get('workload')!='swapin' or (case=='swapin-disk')!=(r['backend']=='disk'): continue
                    group=('A/A allocated' if r.get('swap_image_allocation')=='preallocated' else 'A/A sparse') if r['action']=='calibrate' else r.get('candidate','baseline')
                    points.append(dict(group=group,series='baseline' if r['source_commit']==protocol['baseline_commit'] else 'candidate',value=r['metrics'][metric][stat]/1000,tip=r['run_id']))
                if points:
                    preferred='xs-zswap-linear-v1' if case=='swapin-zswap' else ('xs-ra-cluster-v1' if 'xs-ra-cluster-v1' in registry else 'xs-ra-sequential-v1')
                    effect=next((m for m in metrics if m['candidate']==preferred and m['metric']==case+'.'+metric+'.'+stat),None)
                    label=('Disk' if case=='swapin-disk' else 'Compressed')+' '+('sequential' if metric=='swapin_seq' else 'random')+' '+('mean' if stat=='mean_ns' else 'p99')
                    title=label+(': '+format(effect['latency_change_percent'],'+.1f')+'% for '+preferred if effect else ': every retained baseline and candidate run')
                    strips.append(dict(type='strip',takeaway=title,x_label='microseconds per first touch',groups=list(dict.fromkeys(p['group'] for p in points)),series=['baseline','candidate'],points=points))
    ra_points=[]
    for r in runs:
        if r.get('workload')!='swapin' or r['backend']!='disk':continue
        group=('A/A allocated' if r.get('swap_image_allocation')=='preallocated' else 'A/A sparse') if r['action']=='calibrate' else r.get('candidate','baseline')
        ra_points.append(dict(group=group,series='baseline' if r['source_commit']==protocol['baseline_commit'] else 'candidate',value=r['metrics'].get('swapin_vmstat_delta',{}).get('swap_ra_hit',0),tip=r['run_id']))
    if ra_points:strips.append(dict(type='strip',takeaway='Prefetch hits reveal whether the physical mechanism ran',x_label='swap_ra_hit per guest',groups=list(dict.fromkeys(p['group'] for p in ra_points)),series=['baseline','candidate'],points=ra_points))
    system=flow('xswap separates virtual slots from compressed and physical backing',[
        dict(id='ram',label='Anonymous RAM',sub='resident folios',col=0,row=0),dict(id='slot',label='xswap slots',sub='PTE entry + descriptor',col=1,row=0,tone='focus'),dict(id='zswap',label='zswap pool',sub='compressed objects',col=2,row=0),dict(id='disk',label='Physical swap',sub='optional backend slots',col=2,row=1)], [dict(**{'from':'ram','to':'slot'}),dict(**{'from':'slot','to':'zswap'}),dict(**{'from':'slot','to':'disk'})])
    blocks=[system,table('Each hypothesis changes one cost on the fault path',['Candidate','Hypothesis'],[[r['name'],r['hypothesis']] for r in candidate_rows])]+patches
    status='inconclusive' if running else ('needs-review' if admitted else ('rejected' if comparisons and all(d['status']=='REGRESSION' for d in comparisons) else 'inconclusive'))
    headline=(f'{len(candidate_rows)} candidates fail calibrated fast guards' if not running and not admitted and comparisons else (f'{len(admitted)} fast passes; {len(comparisons)} candidate comparisons' if comparisons else 'Calibration and correctness evidence retained'))
    checks=[dict(status='pass' if not running else 'warn',label=f"{len(runs)} completed guest results; {counts['integration_passes']} integration passes",evidence='summary.json'),dict(status='warn',label=f"{len(failed)} failed or incomplete retained attempts",evidence='REPORT.md'),dict(status='missing',label='Promotion, independent confirmation and holdout',evidence='policy.json required gates')]
    overview_tiles=[dict(label='Guest attempts',value=counts['reserved'].get('guests',0),note='includes calibration and failures'),dict(label='Candidates compared',value=len(comparisons),note=str(len(admitted))+' pass every fast guard')]
    for key,label in [('swapin-disk.swapin_seq.mean_ns','Disk sequential mean'),('swapin-disk.swapin_rand.p99_ns','Disk random p99')]:
        effect=next((m for m in metrics if m['candidate']=='xs-ra-cluster-v1' and m['metric']==key),None)
        if effect:overview_tiles.append(dict(label=label,value=format(effect['latency_change_percent'],'+.1f')+'%',note='round 3; two fast pairs'))
    spec=dict(title='xswap continuation',subtitle=C+' · repaired baseline '+protocol['baseline_commit'][:8],verdict=dict(status=status,headline=headline,tiles=overview_tiles),sections=[dict(id='context',title='Context and changes',lead='Reduce xswap fault cost while preserving data and random-tail guards.',blocks=blocks),dict(id='method',title='Measurement',blocks=[table('A/A and candidate comparisons share frozen inputs',['Item','Value'],[['Baseline',protocol['baseline_commit']],['Protocol revision',protocol.get('protocol_revision',1)],['Pair order',protocol['order']],['Allocation','preallocated after revision 1'],['Calibration gate','20% ceiling; 3% floor'],['Budget','48 guests; 10 builds; six hours']])]),dict(id='data',title='Observed results',blocks=[table('Every latency guard stays visible',['Candidate','Metric','Latency %','Noise %','Guard'],metricrows)]+strips),dict(id='checks',title='Evidence and limits',blocks=[dict(type='checklist',takeaway='Runtime evidence and missing acceptance gates',items=checks),table('Every required policy gate',['Candidate','Gate','Evidence state'],gate_rows),dict(type='note',text='Sparse-image A/A noise is retained. Preallocation tests a possible confounder; causal attribution remains open. Only measured fast evidence informs the next hypothesis.')]),dict(id='next',title='Next',blocks=[table('Owner review determines confirmation',['Action','Condition'],[['Retain useful mechanisms','Fast guards and targeted correctness pass'],['Run slow confirmation','Exceptional fast evidence plus explicit owner approval'],['Promote candidate','Complete full project gates and independent evidence']])])])
    (OUT/'explainer.json').write_text(json.dumps(spec,indent=2)+'\n')
    builder=ROOT/'.agents/skills/explaining-campaign-results/scripts/build_page.py'
    module_spec=importlib.util.spec_from_file_location('page_builder',builder);m=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(m)
    for kind in ['diff','table']:
        original=m.BLOCKS[kind]
        def collapsed(b,budget,original=original):
            return '<details><summary>'+m.esc(b['takeaway'])+'</summary>'+original(b,budget)+'</details>'
        m.BLOCKS[kind]=collapsed
    page,budget=m.build(spec)
    if budget.errors or budget.words>m.MAX_PAGE_WORDS: raise RuntimeError(budget.errors or budget.words)
    scene=(OUT/'prefetch-scene.svg').read_text()+'<p class="chart-title">Compressed-object path: the second hypothesis</p>'+(OUT/'decompression-scene.svg').read_text()
    page=page.replace('<section id="method">','<div class="card"><p class="chart-title">Locate each change, then compare its before/after mechanism</p>'+scene+'</div><section id="method">')
    page=page.replace('</style>', 'details{max-width:100%;overflow-x:auto}.svg-scroll{overflow-x:auto;padding:0 4px}.svg-scroll svg{min-width:760px}@media(max-width:600px){.tiles{grid-template-columns:repeat(2,minmax(0,1fr))}.verdict{flex-direction:column;align-items:flex-start;font-size:18px}.svg-scroll:before{content:"Swipe to view chart";display:block;font-size:11px;color:var(--muted);margin-bottom:8px}}'+'</style>')
    page=page.replace('<svg ', '<div class="svg-scroll"><svg ').replace('</svg>','</svg></div>')
    (OUT/'explainer.html').write_text(page)
    for p in [STATE/'ledger.json',STATE/'budget.json',ROOT/'benchmark/swap-standard'/('protocol-'+C+'.json'),ROOT/'evolve/control/campaigns'/C/'policy.json']:record(p)
    (OUT/'evidence-manifest.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(dict(counts=counts,words=budget.words,html_bytes=len(page)),indent=2))
if __name__=='__main__':main()
