#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Render the retained C1 closeouts without changing scientific ledgers."""
import hashlib
import html
import json
from pathlib import Path
import re
import sys

CSS = '''
.scene{border:1px solid var(--line);border-radius:18px;padding:20px;margin:16px 0;background:var(--bg)}
.scene-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:18px;align-items:stretch}
.scene-box{border:1px solid var(--line);border-radius:14px;padding:18px;min-width:0}
.scene-box.focus{border:2px solid #dc944b;background:color-mix(in srgb,#dc944b 9%,transparent)}
.scene-box.memory{border:2px solid #6c93c8;background:color-mix(in srgb,#6c93c8 8%,transparent)}
.scene-label{font-size:12px;letter-spacing:.08em;text-transform:uppercase;opacity:.7;margin:0 0 10px}
.scene h3{font-size:19px;margin:0 0 12px}.scene p{line-height:1.55}.scene-note{font-size:13px;opacity:.8}
.pages{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}.page-object{width:46px;height:61px;border-radius:6px;border:2px solid #6c93c8;background:color-mix(in srgb,#6c93c8 22%,transparent);display:grid;place-items:center;font-weight:700}
.page-object.compressed{height:27px;margin-top:34px;border-color:#dc944b;background:color-mix(in srgb,#dc944b 25%,transparent)}
.owner{padding:12px;border-left:4px solid #9978b2;background:color-mix(in srgb,#9978b2 10%,transparent);margin:10px 0}
.engine{padding:16px;border:2px solid #dc944b;border-radius:12px;margin:12px 0}.engine span{display:inline-block;padding:8px;border-radius:7px;border:1px solid #dc944b;margin:3px}
.scene-route{font-size:15px;line-height:1.7;margin:14px 0}.scene-route strong{color:#b87935}.scene-cost{border-top:1px solid var(--line);padding-top:12px;font-size:14px}
.coverage{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0}.coverage span{padding:9px 12px;border-radius:7px;border:1px solid #5a9975}.coverage .missing{border-color:#ca8b47}
.related{font-size:14px;line-height:1.8}.related a,.patch-source a{color:var(--ink-2)}.patch-source{font-size:12px;overflow-wrap:anywhere}pre.diff{max-width:100%}
@media(max-width:600px){.scene{padding:14px}.scene-grid{grid-template-columns:1fr}.scene-box{padding:14px}.scene h3{font-size:18px}.scene-route{font-size:14px}}
'''

SCENES = {
'system': '''<section id="system"><h2>1. Whole system: compressed contents still live in RAM</h2>
<p class="lead">The application needs a full page. Compression saves RAM by storing a smaller representation, then spends CPU time to restore it on a fault.</p>
<div class="scene"><div class="scene-grid"><div class="scene-box"><p class="scene-label">Application</p><h3>Read page A</h3><div class="pages"><div class="page-object">A</div></div><p>Access triggers the swap-in path when the page is absent.</p></div>
<div class="scene-box memory"><p class="scene-label">Physical RAM</p><h3>Two representations</h3><div class="pages"><div class="page-object">A</div><div class="page-object compressed">A</div></div><p>Full page after decode; compressed object before decode. The compressed object is inside RAM.</p><div class="engine"><strong>Changed location</strong><br>Codec context + compressed-object store</div></div>
<div class="scene-box"><p class="scene-label">Backing storage</p><h3>Physical swap device</h3><p>A separate fallback path can read stored contents from a device.</p><p class="scene-note">The compressed correctness case excludes lower physical backing.</p></div></div><p class="scene-route">Application fault → selected frontend → <strong>decode object A</strong> → full page A</p><p class="scene-note">Schematic objects and sizes; no latency is illustrated. C1 adds no tier-migration policy.</p></div></section>''',
'subsystem': '''<section id="subsystem"><h2>2. Subsystem: policy owns the object; the library runs the engine</h2>
<p class="lead">At this C1 boundary, XSwap still reaches compressed storage through ZSwap. The new library makes that mechanism reusable while preserving the current owner.</p>
<div class="scene"><div class="scene-grid"><div class="scene-box"><p class="scene-label">Logical swap path</p><h3>XSwap or ordinary swap</h3><p>Logical entry identity and existing physical fallback remain outside the extracted library.</p></div>
<div class="scene-box"><p class="scene-label">ZSwap frontend</p><h3>Keep ownership here</h3><div class="owner">Index · object reference · charge · LRU · admission</div><p>The frontend decides when a handle becomes reachable and when it can be freed.</p></div>
<div class="scene-box focus"><p class="scene-label">Shared page library</p><h3>Execute the mechanism</h3><div class="engine"><span>CPU context</span><span>Codec</span><span>Object allocator</span></div><div class="pages"><div class="page-object compressed">A</div><div class="page-object compressed">B</div></div></div></div><p class="scene-route">Frontend retains handle + length → library store / load / free</p><p class="scene-cost">Independent XSwap is the next capability to implement and verify. The C1 library alone does not supply it.</p></div></section>''',
'changes': '''<section id="changes"><h2>3. Concrete change: move code ownership, retain the stored object</h2>
<p class="lead">The object representation and frontend lifetime rules remain. The codec and allocator implementation cross one new API boundary.</p>
<div class="scene"><div class="scene-grid"><div class="scene-box"><p class="scene-label">Before</p><h3>ZSwap contains both roles</h3><div class="owner">Frontend policy, accounting and references</div><div class="engine"><span>CPU context</span><span>Codec</span><span>Object allocator</span></div><div class="pages"><div class="page-object compressed">A</div></div></div>
<div class="scene-box"><p class="scene-label">After · unchanged K1 source</p><h3>ZSwap calls a shared engine</h3><div class="owner">Same frontend policy, accounting and references</div><div class="engine"><strong>page_compress library</strong><br><span>CPU context</span><span>Codec</span><span>Object allocator</span></div><div class="pages"><div class="page-object compressed">A</div></div></div></div><p class="scene-cost">Benefit: one reusable implementation. Cost: a new API/lifetime boundary, one pool allocation and additional configuration/test obligations. Slab rounding and performance equivalence remain unmeasured.</p></div></section>'''
}


def generate(root, campaign):
    root = Path(root).resolve()
    sys.path[:0] = [str(root / 'evolve'), str(root / 'evolve/control')]
    import delivery
    report = root / 'campaigns' / campaign / 'report'
    script = report / 'generate_report.py'
    script_bytes = script.read_bytes()
    summary = delivery.extract(root, campaign)
    story = delivery.read(report / 'story.json')
    obs_path = report / 'observations.json'
    obs = delivery.read(obs_path)
    delivery.validate_story(story, summary)
    if delivery.digest_bytes(obs_path.read_bytes()) != story['observations_sha256']:
        raise ValueError('observations changed without an authored update')
    if obs['native_evidence_sha256'] != summary['evidence_sha256']:
        raise ValueError('observations belong to a different native closeout')
    for ref, digest in obs['source_pins'].items():
        if delivery.digest_bytes(delivery.at(root, ref).read_bytes()) != digest:
            raise ValueError('retained source changed: ' + ref)
    for item in obs['resources']:
        d = root / 'campaigns' / item['campaign']
        b = delivery.read(d / 'ledger/budget.json')
        tickets = [delivery.read(p) for p in (d / 'ledger/guest-reservations').glob('*.json')]
        actual = {'counted': b['guests'] + b['probe_guests'],
                  'launched': sum(t['status'] == 'STARTED' for t in tickets), 'builds': b['builds']}
        if any(actual[k] != item[k] for k in actual) or actual['counted'] != len(tickets):
            raise ValueError('resource observations no longer reconcile')
    if summary['status'] != 'closed' or summary['verdict'] != 'inconclusive':
        raise ValueError('closed inconclusive source required')
    r5 = [a for a in obs['attempts'] if a['campaign'] == 'codex-compress-lib-r5-2026-11-10']
    coverage = [a for a in r5 if a['case']]
    failure = [a for a in r5 if not a['case']]
    if len(coverage) != 8 or any(not a['integration_pass'] or not a['run_valid'] or not all(a['gates'].values()) for a in coverage):
        raise ValueError('R5 coverage observations changed')
    if len(failure) != 1 or failure[0]['integration_pass'] or failure[0]['gates'].get('parse_complete') is not False:
        raise ValueError('R5 failed baseline observation changed')
    family = '-r6-' in campaign
    if family and (len(obs['current_reservations']) != 1 or obs['current_reservations'][0]['status'] != 'RESERVED'):
        raise ValueError('R6 unlaunched reservation changed')
    make_spec = delivery.make_spec

    def report_spec(observed, explanation):
        spec = make_spec(observed, explanation)
        if family:
            spec.update(candidates_count=1, guests=obs['totals']['counted'], builds=obs['totals']['builds'])
            spec['subtitle'] = (
                f"{story['harness']} ({story['model']}) · line: {observed['line']} · "
                f"base {observed['baseline_commit'][:8]} · 1 candidate · "
                f"{obs['totals']['counted']} counted / {obs['totals']['launched']} launched guests / "
                f"{obs['totals']['builds']} builds")
        spec['verdict']['tiles'] = [
            {'label': 'Shared library', 'value': 'Functional pass', 'note': 'Full R5 matrix and disabled builds.'},
            {'label': 'Performance', 'value': 'Unresolved', 'note': 'Baseline decode observation failed.'},
            {'label': 'Decision', 'value': 'Retain for development', 'note': 'Original baseline and promotion gate remain.'}]
        results = next(s for s in spec['sections'] if s['id'] == 'results')
        results['lead'] = 'R5 completed correctness before its first baseline timing attempt. The latter produced no valid timing sample. R6 later expired before guest admission.'
        evidence = next(s for s in spec['sections'] if s['id'] == 'evidence')
        evidence['blocks'] += [
            {'type': 'table', 'takeaway': 'R5 complete functional coverage',
             'columns': ['Case', 'Configuration', 'Topology', 'Functional gates', 'Valid'],
             'rows': [[a['case'], a['config_id'], a['topology_id'], str(sum(a['gates'].values())) + ' / ' + str(len(a['gates'])), a['run_valid']] for a in coverage]},
            {'type': 'table', 'takeaway': 'All retained C1 attempts',
             'columns': ['Contract', 'Run', 'Functional pass', 'Run valid', 'Failure / invalid reason'],
             'rows': [[a['campaign'], a['run_id'], a['integration_pass'], a['run_valid'], ', '.join([k for k, v in a['gates'].items() if not v] + a['invalid_reasons']) or 'none'] for a in obs['attempts']]},
            {'type': 'table', 'takeaway': 'Counted reservations and actual launches',
             'columns': ['Contract', 'Counted', 'Launched', 'Builds'],
             'rows': [[r['campaign'], r['counted'], r['launched'], r['builds']] for r in obs['resources']] + [['Cumulative C1', obs['totals']['counted'], obs['totals']['launched'], obs['totals']['builds']]]},
            {'type': 'table', 'takeaway': 'R5 timing failure retained exactly',
             'columns': ['Field', 'Value'], 'rows': [['run', failure[0]['run_id']], ['source', failure[0]['source_commit']], ['integration_pass', False], ['run_valid', failure[0]['run_valid']], ['parse_error', failure[0]['parse_error']], ['result SHA-256', failure[0]['result_sha256']], ['serial SHA-256', failure[0]['serial_sha256']]]},
            {'type': 'table', 'takeaway': 'Historical proof and observation pins',
             'columns': ['Artifact', 'SHA-256'],
             'rows': [['R5 canonical correctness', obs['r5_correctness']['sha256']], ['R5 runtime archive', obs['r5_runtime_archive']['sha256']], ['Public observations', story['observations_sha256']]]},
        ]
        return spec

    try:
        delivery.make_spec = report_spec
        receipt = delivery.render(root, campaign)
    finally:
        delivery.make_spec = make_spec
        script.write_bytes(script_bytes)
    page = (report / 'explainer.html').read_text()
    for section, scene in SCENES.items():
        page, count = re.subn(r'<section id="' + section + r'">.*?</section>', lambda _: scene, page, count=1, flags=re.S)
        if count != 1:
            raise ValueError('expected one scene: ' + section)
    page = page.replace('</style>', CSS + '</style>')
    coverage_html = '<div class="coverage"><span>Roundtrip + physical regression: pass</span><span>Legacy ZSwap: pass</span><span>KASAN / lockdep: pass</span><span>KCSAN lifecycle: pass</span><span>NUMA + hotplug: pass</span><span class="missing">Timing: unresolved</span></div>'
    page = page.replace('<section id="results">', '<section id="results">' + coverage_html)
    for item in story['patches']:
        source = item['source']
        href = 'https://github.com/ericzhang-zxh/Swap-Next/blob/' + story['source_commit'] + '/' + source
        citation = '<p class="patch-source">Source: <a href="' + html.escape(href, quote=True) + '">' + html.escape(source) + '</a><br>SHA-256: <code>' + summary['sources'][source] + '</code></p>'
        target = '<p class="chart-title">' + html.escape(item['takeaway']) + '</p>'
        if page.count(target) != 1:
            raise ValueError('expected exact core patch card')
        page = page.replace(target, target + citation)
    links = ['<a href="' + html.escape(x['url'], quote=True) + '">' + html.escape(x['title']) + '</a>' for x in story['related_reports']]
    page = page.replace('</main>', '<details class="audit related"><summary>Retained contract reports</summary>' + ' · '.join(links) + '</details></main>')
    dated_name = campaign + '-' + story['date']
    dated = report / dated_name
    dated.mkdir(exist_ok=True)
    (dated / 'explainer.html').write_text(page)
    (report / 'explainer.html').unlink()
    (report / 'explainer.json').replace(dated / 'explainer.json')
    markdown = (report / 'REPORT.md').read_text()
    marker = markdown.index('## Limitations\n')
    rows = ['<details>', '<summary>Functional coverage and cumulative resources</summary>', '',
            '| Case | Configuration | Gate result | Valid |', '| --- | --- | --- | --- |']
    rows += ['| ' + a['case'] + ' | ' + a['config_id'] + ' | all pass | true |' for a in coverage]
    rows += ['', '| Contract | Counted | Launched | Builds |', '| --- | --- | --- | --- |']
    rows += ['| ' + x['campaign'] + ' | ' + str(x['counted']) + ' | ' + str(x['launched']) + ' | ' + str(x['builds']) + ' |' for x in obs['resources']]
    rows += ['', '[Public observations and exact hashes](observations.json)', '', '</details>', '',
             '## Limitations', '',
             'C1 functional coverage is complete on the retained R5 source/config/image. Its first baseline timing guest failed before complete latency samples. The saved run validity and failed integration fields remain separate. No calibration, performance equivalence, speedup, baseline advancement or code promotion is established.', '',
             'H26 diagnostics are source-reviewed, while R6 expired before final admission and collected no runtime trace. One unlaunched R6 reservation remains counted. The earlier observer cause remains unproven. C2/C3 implementation and runtime are not C1 outcomes.', '',
             'The archived-parser reconciliation reproduces historical gates and metrics; it creates no fresh runtime sample. Per-object/context representation is preserved by source review. Requested pool overhead and unmeasured allocator rounding remain distinct.', '',
             '[Interactive explanation](' + dated_name + '/explainer.html)', '']
    (report / 'REPORT.md').write_text(markdown[:marker] + '\n'.join(rows))
    receipt['artifacts'] = {name: delivery.digest_bytes(((dated if name in {'explainer.html', 'explainer.json'} else report) / name).read_bytes()) for name in delivery.OUTPUTS}
    delivery.write(report / 'delivery.json', receipt)
    print(json.dumps({'campaign': campaign, 'state': receipt['state'], 'html_sha256': receipt['artifacts']['explainer.html']}))
