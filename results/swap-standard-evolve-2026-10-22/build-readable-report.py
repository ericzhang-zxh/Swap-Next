#!/usr/bin/env python3
"""Rebuild a visual overview, preserving the original report as closed evidence."""
import copy
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
old = json.loads((HERE / 'evidence-spec.json').read_text())
summary = json.loads((HERE / 'summary.json').read_text())
assert summary['performance_accepted'] is False
assert summary['candidate_kernel_patch'] is None

def flow(title, labels, focus=1):
    return {'type': 'flow', 'takeaway': title,
            'nodes': [{'id': str(i), 'label': label, 'col': i, 'row': 0,
                       'tone': 'focus' if i == focus else 'default'}
                      for i, label in enumerate(labels)],
            'edges': [{'from': str(i), 'to': str(i + 1)} for i in range(len(labels) - 1)]}

def note(text):
    return {'type': 'note', 'text': text}

plots = [copy.deepcopy(b) for s in old['sections'] for b in s['blocks'] if b['type'] == 'strip'][:2]
for plot, title in zip(plots, ['Throughput varies widely on the same kernel', 'Free latency also fails repeatability']):
    plot['takeaway'] = title
    plot['x_label'] = 'Direction-adjusted ratio to paired A (1) — higher is better'
    plot['note'] = 'A and B run the same kernel. Each dot is one run; throughput uses B/A, latency uses A/B.'

sections = [
    {'id': 'context', 'title': 'Why calibrate before comparing kernels?', 'blocks': [
        flow('Noise can look like a candidate improvement', ['Repeated workload', 'Timing variation', 'Uncertain winner']),
        note('Disconnected runs make changes hard to judge. The integration tests repeatability first, then admits comparisons only when the baseline is stable.')
    ]},
    {'id': 'system', 'title': 'Where this change fits', 'blocks': [
        {'type': 'flow', 'takeaway': 'The controller changes; the measured kernel path stays intact',
         'nodes': [
             {'id': 'goal', 'label': 'Choose safe changes', 'col': 0, 'row': 0},
             {'id': 'control', 'label': 'Tiered controller', 'sub': 'Changed orchestration', 'col': 1, 'row': 0, 'tone': 'focus'},
             {'id': 'guest', 'label': 'Guest workloads', 'sub': 'Application performance', 'col': 2, 'row': 0},
             {'id': 'kernel', 'label': 'Kernel and storage', 'sub': 'Same baseline', 'col': 2, 'row': 1},
             {'id': 'evidence', 'label': 'Verified evidence', 'col': 1, 'row': 1},
             {'id': 'reviewer', 'label': 'Human review', 'col': 0, 'row': 1}],
         'edges': [{'from': 'goal', 'to': 'control'}, {'from': 'control', 'to': 'guest'},
                   {'from': 'guest', 'to': 'kernel'}, {'from': 'kernel', 'to': 'evidence'},
                   {'from': 'evidence', 'to': 'reviewer'}]},
        note('Frozen builds feed fresh guests; measurements return to admission and review. More calibration work buys confidence before expensive comparisons. This is one orchestration change, with no candidate kernel patch.')
    ]},
    {'id': 'mechanism', 'title': 'From isolated runs to staged evidence', 'blocks': [
        flow('Before: individual runs leave repeatability unresolved', ['Build inputs', 'Single runs', 'Manual comparison']),
        flow('After: repeatability gates the comparison', ['Paired calibration', 'Fast admission', 'Slow evidence', 'Human review'])
    ]},
    {'id': 'findings', 'title': 'The baseline fails its own comparison', 'blocks': plots + [
        note('Fast calibration is noisy. Slow calibration stopped incomplete; reference comparison did not boot. The historical candidate remains blocked by descriptor lifetime. Candidate correctness gates remain missing; completed guest integration checks passed.')
    ]},
    {'id': 'next-steps', 'title': 'Next: make the comparison trustworthy', 'blocks': [
        flow('Stabilize measurement before spending on candidate scoring', ['Investigate noise', 'New frozen A/A', 'Eligible comparison']),
        note('High confidence: no winner is established. A stable new calibration, closed lifetime finding and complete candidate correctness evidence would permit a new comparison. No new experiment is launched here.')
    ]}
]
for section in old['sections']:
    audit = copy.deepcopy(section)
    audit['id'] = 'audit-' + audit['id']
    sections.append(audit)
spec = {'title': old['title'], 'subtitle': old['subtitle'],
        'verdict': {'status': old['verdict']['status'], 'headline': old['verdict']['headline'],
                    'tiles': [{'label': 'Decision', 'value': 'Hold scoring', 'note': 'No candidate winner.'},
                              {'label': 'Benefit', 'value': 'Traceable runs', 'note': 'Failed and interrupted attempts retained.'},
                              {'label': 'Cost', 'value': 'Calibration work', 'note': 'Noise must be resolved first.'}]},
        'sections': sections}
(HERE / 'explainer.json').write_text(json.dumps(spec, indent=2) + '\n')
subprocess.run(['python3', str(ROOT / '.agents/skills/explaining-campaign-results/scripts/build_page.py'),
                str(HERE / 'explainer.json'), str(HERE / 'explainer.html')], check=True)
page = (HERE / 'explainer.html').read_text()
page = re.sub(r'<a href="#audit-[^"]+">.*?</a>', '', page)
page = re.sub(r'(<section id="audit-[^"]+">)(.*?)(</section>)',
              lambda m: '<details class="audit"><summary>' + re.search(r'<h2>(.*?)</h2>', m[2]).group(1)
              + '</summary>' + m[0] + '</details>', page, flags=re.S)
page = page.replace('<details class="audit">', '<h2 id="audit">Evidence on demand</h2><p>Original protocol, samples, statuses and missing gates. Expand to inspect.</p><details class="audit">', 1)
page = re.sub(r'(<svg\b.*?</svg>)', r'<div class="visual-scroll">\1</div>', page, flags=re.S)
page = page.replace('<summary>Table view</summary>', '<summary>Show exact measurements</summary>')
page = page.replace('</style>', '''
.visual-scroll{overflow-x:auto}.visual-scroll svg{min-width:640px}
details.audit{margin:12px 0;border:1px solid var(--grid);border-radius:10px;padding:14px 18px;background:var(--surface-1)}
details.audit>summary{font-weight:600}details.audit section{margin-top:20px}details.audit pre{overflow:auto}
details.audit table{display:block;overflow-x:auto}nav{flex-wrap:wrap}
@media(max-width:600px){.verdict{flex-wrap:wrap}.card{padding:14px}.visual-scroll{padding-bottom:8px}}
</style>''')
assert '<details open' not in page
(HERE / 'explainer.html').write_text(page)
