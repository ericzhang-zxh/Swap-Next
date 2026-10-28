#!/usr/bin/env python3
"""Build a visual integration review from the retained validation records."""
import html,json,pathlib,re,subprocess
p=pathlib.Path(__file__).resolve().parent
root=p.parents[1]
v=json.loads((p/'validation.json').read_text())
def flow(title,labels,focus=1):
 return {'type':'flow','takeaway':title,'nodes':[{'id':str(i),'label':x,'col':i,'row':0,'tone':'focus' if i==focus else 'default'} for i,x in enumerate(labels)],'edges':[{'from':str(i),'to':str(i+1)} for i in range(len(labels)-1)]}
def section(id,title,blocks,lead=''):
 return {'id':id,'title':title,'lead':lead,'blocks':blocks}
spec={'title':'Can the standard workloads exercise swap reliably?','subtitle':'Benchmark integration · historical review · 2026-10-22','verdict':{'status':'needs-review','headline':'Core integration works; performance scoring is not ready','tiles':[{'label':'Execution','value':'Working','note':'Main workloads completed with swap activity.'},{'label':'Random usemem','value':'Excluded','note':'Guest OOM interrupted the run.'},{'label':'Performance','value':'Uncalibrated','note':'No accepted comparative result.'}]},'sections':[
 section('context','Why a new workload suite was needed',[
 flow('Move from metadata observations toward application-facing costs',['Swap mechanism','Real workload cost','Optimization decision']),
 {'type':'note','text':'A mapped-cluster count does not describe application throughput or latency. The new suite adds memory pressure, kernel builds and Valkey operations so later studies can measure workload-specific cost.'}]),
 section('system','Where the suite sits in the larger system',[
 flow('The new harness surrounds the guest; kernel code is unchanged',['Frozen inputs','Isolated KVM guest','Trusted evaluator']),
 flow('Inside the guest, workload pressure reaches the selected swap backend',['Workload + memcg','Guest kernel swap','Disk / zswap / zram']),
 {'type':'note','text':'Pinned inputs feed bounded runs. The evaluator checks completion, backend activity and kernel diagnostics. Host locking and stop handling isolate execution; Valkey networking stays inside the guest.'}]),
 section('changes','What changed in the measurement path',[
 flow('Require evidence of useful work, not just process exit',['Workload output','Per-phase checks','Retained run record']),
 flow('Retain diagnostics and fail incomplete work early',['Kernel diagnostics','Stop failing run','Keep failed attempt']),
 {'type':'note','text':'Swapon memory deltas replace mapped-cluster count as the metadata observation. Historical protocols remain frozen. Extra validation improves evidence quality; it does not establish a performance gain.'}]),
 section('results','What worked and what failed',[
 flow('Main workloads completed on their tested backends',['usemem / disk','build / zswap','Valkey / zram']),
 flow('Random usemem exceeded its memory envelope',['Memory pressure','Guest OOM kills','Interrupted run']),
 {'type':'note','text':'The initial usemem parser misread byte-count semantics; corrected analysis and a direct rerun passed. Both failures are retained. Random usemem stays excluded from scoring. Metadata and supplemental swap-in checks completed.'}]),
 section('next','What must happen before performance review',[
 flow('Integration is the entry point, not the acceptance test',['Freeze protocol','Calibrate baseline','Compare candidates']),
 {'type':'note','text':'At this report date: partial backend coverage, no calibration or comparison, and xswap held by lifetime review. Revise the random profile separately. A failed replay on frozen artifacts would challenge confidence in basic execution.'}])
]}
spec['sections'][3]['blocks'][0]['edges']=[]
(p/'explainer.json').write_text(json.dumps(spec,indent=2)+'\n')
subprocess.run(['python3',str(root/'.agents/skills/explaining-campaign-results/scripts/build_page.py'),str(p/'explainer.json'),str(p/'explainer.html')],check=True)
h=(p/'explainer.html').read_text()
rows=''.join('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in [r['run'],r['workload'],r['backend'],r['status'],round(r['wall_seconds'],2),', '.join(r['failed_gates'])])+'</tr>' for r in v['runs'])
evidence='<section id="evidence"><h2>Evidence, when you need it</h2><details><summary>Exact run outcomes and integration timings</summary><p>Guest seconds include boot and setup; interrupted runs are not completed measurements.</p><div class="visual-scroll"><table><thead><tr><th>Run</th><th>Workload</th><th>Backend</th><th>Status</th><th>Guest seconds</th><th>Failed gates</th></tr></thead><tbody>'+rows+'</tbody></table></div></details><details><summary>Full validation records and provenance</summary><pre>'+html.escape(json.dumps(v,indent=2))+'</pre></details><details><summary>Original report, checks and limitations</summary><pre>'+html.escape((p/'README.md').read_text())+'</pre></details></section>'
h=h.replace('</main>',evidence+'</main>')
h=re.sub(r'(<svg\b.*?</svg>)',r'<div class="visual-scroll">\1</div>',h,flags=re.S)
h=h.replace('</style>','.visual-scroll{overflow-x:auto}.visual-scroll svg{min-width:640px}details{border:1px solid var(--grid);border-radius:10px;padding:14px}summary{cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere}nav{flex-wrap:wrap}</style>')
(p/'explainer.html').write_text(h)
