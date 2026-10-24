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
def flow(title,labels):
 return {'type':'flow','takeaway':title,'nodes':[{'id':str(i),'label':x,'col':i,'row':0,'tone':'focus' if i==1 else 'default'} for i,x in enumerate(labels)],'edges':[{'from':str(i),'to':str(i+1)} for i in range(len(labels)-1)]}
context={'id':'context','title':'The problem: each missing page can stop the application','lead':'When a needed page is outside RAM, the application faults and waits for it to return. Xswap gives that page a virtual swap slot: its contents may be compressed in RAM or written back to disk.','blocks':[
 flow('Original path in this 4 KiB test: fetch on demand',['Application needs page','Fetch that page','Application continues']),
 {'type':'note','text':'The baseline routes xswap through synchronous demand reads and skips ordinary readahead. That is reasonable for cheap in-memory reads, but written-back pages now require disk I/O. Sequential access may expose avoidable waiting.'},
 {'type':'table','takeaway':'Two different costs motivated two independent changes','columns':['Experiment','Why try it?','What actually changed'], 'rows':[
 ['Disk-backed pages','Upcoming sequential accesses are predictable. Fetching neighbors could hide disk waiting.','Check physical backing; route those faults through existing readahead. Speculative xswap neighbors must also have physical backing.'],
 ['Compressed pages','Neighbors could enter the swap cache early, potentially reducing repeated demand-fault overhead.','Check actual zswap residency; prefetch compressed neighbors into the swap cache. Each page is still decompressed synchronously.']]},
 flow('Changed path: one fault also prepares likely next pages',['Application needs page','Fetch page + neighbors','Later reads hit cache']),
 {'type':'note','text':'Both patches start from the same descriptor-lifetime repair; they are not stacked. The goal is lower application read latency. The tradeoff is extra work on the current fault, especially when neighbors are not needed.'}
]}
sections=[context,
 {'id':'physical','title':'1. Read disk-backed pages ahead','lead':'Idea: fetch nearby disk pages before they are needed. Sequential reads become much cheaper, but random-access tail latency fails the screening guard.','blocks':[chart('H1',['swapin-disk.swapin_seq.mean_ns','swapin-disk.swapin_rand.p99_ns'],['Sequential mean','Random p99'],f'Sequential average {h1mean:+.1f}%; random p99 {h1tail:+.1f}%'),{'type':'note','text':'Decision: stop this candidate. Random p99 increased beyond its 3% allowance. The sequential benefit is promising, but needs a new design that protects the tail.'}]},
 {'id':'compressed','title':'2. Decompress nearby pages ahead','lead':'Idea: put neighboring compressed pages into the swap cache before demand. This makes many reads cheap, while some faults pay for several pages at once.','blocks':[chart('H2',['swapin-zswap.swapin_seq.mean_ns','swapin-zswap.swapin_seq.p99_ns'],['Sequential mean','Sequential p99'],f'Average {h2mean:+.1f}%: effectively unchanged; p99 {h2tail:+.1f}%'),{'type':'note','text':'Decision: stop this candidate. Its average change is inside 3% noise; p99 exceeds the 7.73% allowance. Inference: synchronous decompression concentrates work into fewer, longer faults, rather than reducing total work.'}]},
 {'id':'next','title':'What we learned — and what to try next','blocks':[{'type':'table','takeaway':'Keep the useful mechanism; address its cost','columns':['Direction','Next hypothesis','What must improve'], 'rows':[['Disk prefetch','Adapt the prefetch window to access behavior','Keep the sequential gain without a random-tail regression.'],['Compressed prefetch','Bound the work performed on a demand fault','Reduce total latency without concentrating decompression into long stalls.']]},{'type':'note','text':'Evidence strength: two independent pairs per workload, after baseline noise calibration. Both candidates passed correctness checks but failed fast performance screening. No slow confirmation was run; new hypotheses require a new experiment.'}]}
]
for section in old['sections']:
 section=dict(section);section['id']='audit-'+section['id'];sections.append(section)
spec={'title':'Can prefetch make xswap reads faster?','subtitle':'Two ways to read pages before demand — their motivation, implementation and measured cost','verdict':{'status':'rejected','headline':'Neither candidate is ready to advance','tiles':[{'label':'Disk: sequential average','value':f'{h1mean:.1f}%','note':f'Sequential average; random p99 +{h1tail:.1f}%.'},{'label':'Compressed: sequential p99','value':f'+{h2tail:.1f}%','note':f'Sequential p99; average {h2mean:.1f}%.'}]},'sections':sections}
# Visual-first overview; exact measurements remain in closed chart/audit details.
context['blocks'][2:3]=[
 flow('Disk: predictable neighbors could hide the next I/O wait', ['Disk-backed fault','Read neighbors','Fewer later waits']),
 flow('Compressed RAM: early cache entries could avoid later fault work', ['Resident in zswap','Decompress ahead','Fill swap cache'])
]
sections[1]['blocks'][0]['takeaway']='Disk reads: faster sequential access, worse random tail'
sections[1]['blocks'][1]['text']='Decision: stop this candidate. Random tail latency fails its guard. Preserve the sequential benefit while protecting the tail.'
sections[2]['blocks'][0]['takeaway']='Compressed reads: similar average, much longer tail'
sections[2]['blocks'][1]['text']='Decision: stop this candidate. Average latency stays within noise and tail latency fails its guard. Inference: synchronous decompression concentrates work into fewer, longer faults.'
sections[3]['blocks'][0:1]=[
 flow('Disk: adapt the window to protect unpredictable reads', ['Detect access','Adapt window','Protect the tail']),
 flow('Compressed RAM: limit work on the critical path', ['Demand fault','Bound extra work','Avoid long stalls'])
]
spec['verdict']['tiles']=[
 {'label':'Disk prefetch','value':'Mixed result','note':'Sequential reads improve; random tail worsens.'},
 {'label':'Compressed prefetch','value':'Longer stalls','note':'Average stays similar; tail worsens.'}
]
# Lead with the verdict, then zoom from the system into the changed read policy.
context['lead']='An application needs a page that has been swapped out. It must wait for the kernel to restore it. The goal is to reduce that application-visible waiting.'
context['blocks']=[
 flow('Before: demand reads wait for one page at a time', ['Application waits','Fetch needed page','Application resumes']),
 {'type':'note','text':'This baseline skips ordinary readahead for xswap. That can suit cheap compressed-memory reads, but written-back pages require disk I/O. Predictable neighboring reads motivate prefetch.'}
]
system={'id':'system','title':'Where the change fits in the system','blocks':[
 {'type':'flow','takeaway':'The change sits on a swap-cache miss, before backend retrieval','nodes':[
  {'id':'app','label':'Application','col':0,'row':0},
  {'id':'fault','label':'Kernel swap fault','col':1,'row':0},
  {'id':'cache','label':'Swap cache','sub':'Reuse page if present','col':2,'row':0},
  {'id':'policy','label':'Xswap read path','sub':'Changed prefetch policy','col':1,'row':1,'tone':'focus'},
  {'id':'ram','label':'Zswap in RAM','sub':'Decompress page','col':0,'row':2},
  {'id':'disk','label':'Physical backing','sub':'Read page from disk','col':2,'row':2}],
  'edges':[{'from':'app','to':'fault'},{'from':'fault','to':'cache'},{'from':'cache','to':'policy','label':'miss'},{'from':'policy','to':'ram'},{'from':'policy','to':'disk'}]},
 {'type':'note','text':'Fetched pages enter the swap cache and satisfy application reads. The patches change which neighbors are prepared, leaving the application, cache role and storage backends in place. Extra work now may save a later wait—or lengthen the current fault.'},
 flow('H1: physical-backing checks enable disk readahead', ['Disk-backed page','Read neighbors','Fill swap cache']),
 flow('H2: residency checks select compressed neighbors', ['Resident in zswap','Decompress ahead','Fill swap cache']),
 {'type':'note','text':'H1 reuses existing readahead and filters speculative xswap pages for physical backing. H2 still decompresses synchronously. Both start from the same lifetime repair; they are independent patches.'}
]}
sections.insert(1,system)
(p/'explainer.json').write_text(json.dumps(spec,indent=2)+'\n')
subprocess.run(['python3',str(root/'.agents/skills/explaining-campaign-results/scripts/build_page.py'),str(p/'explainer.json'),str(p/'explainer.html')],check=True)
h=(p/'explainer.html').read_text()
# Keep the overview navigation short; audit material is explicitly opt-in.
h=re.sub(r'<a href="#audit-[^"]+">.*?</a>','',h)
h=re.sub(r'(<section id="audit-[^"]+">)(.*?)(</section>)',lambda m:'<details class="audit"><summary>'+re.search(r'<h2>(.*?)</h2>',m[2]).group(1)+'</summary>'+m[0]+'</details>',h,flags=re.S)
h=h.replace('<details class="audit">','<h2 id="audit">Evidence, when you need it</h2><p>Full samples, counters, patches and checks. Expand only what you want to inspect.</p><details class="audit">',1)
h=h.replace('<section id="physical">', '<p class="lead">Average latency describes overall cost. P99 is the time within which 99% of measured reads finish: a higher p99 means a slower tail.</p><section id="physical">')
h=h.replace('</style>','details.audit{margin:12px 0;border:1px solid var(--grid);border-radius:10px;padding:14px 18px;background:var(--surface-1)}details.audit>summary{font-weight:600;cursor:pointer}details.audit section{margin-top:20px}details.audit pre{overflow:auto} nav{flex-wrap:wrap}</style>')
# Keep diagrams visible on phones; allow local horizontal scrolling at readable size.
h=re.sub(r'(<svg\b.*?</svg>)',r'<div class="visual-scroll">\1</div>',h,flags=re.S)
h=h.replace('</style>', '.visual-scroll{overflow-x:auto}.visual-scroll svg{min-width:640px}@media(max-width:600px){.visual-scroll{padding-bottom:8px}} </style>')
h=h.replace('<summary>Table view</summary>','<summary>Show exact measurements</summary>')

(p/'explainer.html').write_text(h)
