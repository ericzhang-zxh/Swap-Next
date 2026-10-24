#!/usr/bin/env python3
"""Build the readable overview and retain the full audit material on demand."""
import json,pathlib,subprocess,re,html
p=pathlib.Path(__file__).resolve().parent
root=p.parents[1]
s=json.loads((p/'summary.json').read_text());old=json.loads((p/'evidence-spec.json').read_text())
def chart(candidate,metrics,groups,title):
 points=[]
 for metric,group in zip(metrics,groups):
  values=[x for x in s['metric_points'][metric] if x['group']==candidate+' fast']
  arms={arm:[x['value'] for x in values if x['series']==arm] for arm in ('A','B')}
  assert len(arms['A'])==len(arms['B'])==2
  for i,(a,b) in enumerate(zip(arms['A'],arms['B'])):
   points.extend([{'group':group,'series':'Original','value':100,'tip':f'Pair {i+1}: original {a:g} ns'}, {'group':group,'series':'With prefetch','value':100*b/a,'tip':f'Pair {i+1}: prefetch {b:g} ns; original {a:g} ns'}])
 return {'type':'strip','takeaway':title,'x_label':'Latency relative to original (100) — lower is better','groups':groups,'series':['Original','With prefetch'],'points':points,'note':'Each dot is one paired run. Original latency = 100. The two rows measure different parts of the workload.'}
def change(c,m):
 return next(r[5] for r in s['metric_ratios'] if r[0]==c and r[3]==m)
h1mean=change('xs-ra-phys-v1','swapin-disk.swapin_seq.mean_ns');h1tail=change('xs-ra-phys-v1','swapin-disk.swapin_rand.p99_ns');h2mean=change('xs-ra-zswap-v1','swapin-zswap.swapin_seq.mean_ns');h2tail=change('xs-ra-zswap-v1','swapin-zswap.swapin_seq.p99_ns')
sections=[
 {'id':'physical','title':'1. Read disk-backed pages ahead','lead':'Idea: fetch nearby disk pages before they are needed. Sequential reads become much cheaper, but random-access tail latency fails the screening guard.','blocks':[chart('H1',['swapin-disk.swapin_seq.mean_ns','swapin-disk.swapin_rand.p99_ns'],['Sequential mean','Random p99'],f'Sequential average {h1mean:+.1f}%; random p99 {h1tail:+.1f}%'),{'type':'note','text':'Decision: stop this candidate. Random p99 increased beyond its 3% allowance. The sequential benefit is promising, but needs a new design that protects the tail.'}]},
 {'id':'compressed','title':'2. Decompress nearby pages ahead','lead':'Idea: put neighboring compressed pages into the swap cache before demand. This makes many reads cheap, while some faults pay for several pages at once.','blocks':[chart('H2',['swapin-zswap.swapin_seq.mean_ns','swapin-zswap.swapin_seq.p99_ns'],['Sequential mean','Sequential p99'],f'Average {h2mean:+.1f}%: effectively unchanged; p99 {h2tail:+.1f}%'),{'type':'note','text':'Decision: stop this candidate. Its average change is inside 3% noise; p99 exceeds the 7.73% allowance. Inference: synchronous decompression concentrates work into fewer, longer faults, rather than reducing total work.'}]},
 {'id':'next','title':'What we learned — and what to try next','blocks':[{'type':'table','takeaway':'Keep the useful mechanism; address its cost','columns':['Direction','Next hypothesis','What must improve'], 'rows':[['Disk prefetch','Adapt the prefetch window to access behavior','Keep the sequential gain without a random-tail regression.'],['Compressed prefetch','Bound the work performed on a demand fault','Reduce total latency without concentrating decompression into long stalls.']]},{'type':'note','text':'Evidence strength: two independent pairs per workload, after baseline noise calibration. Both candidates passed correctness checks but failed fast performance screening. No slow confirmation was run; new hypotheses require a new experiment.'}]}
]
for section in old['sections']:
 section=dict(section);section['id']='audit-'+section['id'];sections.append(section)
spec={'title':'Why neither prefetch change advanced','subtitle':'Swap-in experiments · 23 October 2026 · completed fast screening','verdict':{'status':'rejected','headline':'Neither candidate is ready to advance','tiles':[{'label':'Disk: sequential average','value':f'{h1mean:.1f}%','note':f'Sequential average; random p99 +{h1tail:.1f}%.'},{'label':'Compressed: sequential p99','value':f'+{h2tail:.1f}%','note':f'Sequential p99; average {h2mean:.1f}%.'}]},'sections':sections}
(p/'explainer.json').write_text(json.dumps(spec,indent=2)+'\n')
subprocess.run(['python3',str(root/'.agents/skills/explaining-campaign-results/scripts/build_page.py'),str(p/'explainer.json'),str(p/'explainer.html')],check=True)
h=(p/'explainer.html').read_text()
# Keep the overview navigation short; audit material is explicitly opt-in.
h=re.sub(r'<a href="#audit-[^"]+">.*?</a>','',h)
h=re.sub(r'(<section id="audit-[^"]+">)(.*?)(</section>)',lambda m:'<details class="audit"><summary>'+re.search(r'<h2>(.*?)</h2>',m[2]).group(1)+'</summary>'+m[0]+'</details>',h,flags=re.S)
h=h.replace('<details class="audit">','<h2 id="audit">Evidence, when you need it</h2><p>Full samples, counters, patches and checks. Expand only what you want to inspect.</p><details class="audit">',1)
h=h.replace('<section id="physical">', '<p class="lead">Average latency describes overall cost. P99 is the time within which 99% of measured reads finish: a higher p99 means a slower tail.</p><section id="physical">')
h=h.replace('</style>','details.audit{margin:12px 0;border:1px solid var(--grid);border-radius:10px;padding:14px 18px;background:var(--surface-1)}details.audit>summary{font-weight:600;cursor:pointer}details.audit section{margin-top:20px}details.audit pre{overflow:auto} nav{flex-wrap:wrap}</style>')
h=h.replace('</style>', '@media(max-width:600px){#physical svg,#compressed svg{display:none}}</style>')
h=h.replace('</body>', '<script>if(matchMedia("(max-width:600px)").matches){document.querySelectorAll("#physical details,#compressed details").forEach(d=>d.open=true)}</script></body>')
(p/'explainer.html').write_text(h)
