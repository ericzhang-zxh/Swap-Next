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
'system': '''<section id="system"><h2>1. The system: keep application data available</h2>
<p class="lead">A memory page is a fixed-size block of application data. When a page is removed from active RAM, the kernel must keep its contents somewhere so the application can use it again.</p>
<div class="scene"><div class="scene-grid"><div class="scene-box"><p class="scene-label">Application</p><h3>Read block A</h3><div class="pages"><div class="page-object">A</div></div><p>If A is no longer in active RAM, the kernel restores it from its stored copy.</p></div>
<div class="scene-box memory"><p class="scene-label">Inside RAM</p><h3>Compress, then restore</h3><div class="pages"><div class="page-object compressed">A</div><div class="page-object">A</div></div><p>The small stored copy saves space. Decompression uses processor time to restore the full block.</p><div class="engine"><strong>This experiment changes</strong><br>The code that compresses and stores data here</div></div>
<div class="scene-box"><p class="scene-label">On disk</p><h3>Another place to store data</h3><p>Pages can also be stored on disk and read back when needed.</p><p class="scene-note">A later stage would move compressed data from RAM to disk when RAM is tight.</p></div></div><p class="scene-route">Application reads A → kernel finds its stored copy → <strong>restore full block A in RAM</strong></p><p class="scene-note">The blocks illustrate the idea; their sizes are not measurements.</p></div></section>''',
'subsystem': '''<section id="subsystem"><h2>2. The boundary: decisions versus compression</h2>
<p class="lead">ZSwap is the existing compressed-memory cache. XSwap is this project's alternative swap design. At this stage, XSwap still uses ZSwap; the extraction makes the compression code available for future callers.</p>
<div class="scene"><div class="scene-grid"><div class="scene-box"><p class="scene-label">Request</p><h3>Store or restore a page</h3><p>Either the ordinary swap path or XSwap asks ZSwap to handle the compressed data.</p></div>
<div class="scene-box"><p class="scene-label">ZSwap keeps the decisions</p><h3>Track and manage data</h3><div class="owner">What to keep · where it is · memory usage · when it can be freed</div><p>Data stays alive while another operation is using it.</p></div>
<div class="scene-box focus"><p class="scene-label">Shared library does the work</p><h3>Compress and store</h3><div class="engine"><span>Compress</span><span>Restore</span><span>Allocate / free storage</span></div><div class="pages"><div class="page-object compressed">A</div><div class="page-object compressed">B</div></div></div></div><p class="scene-route">Swap request → ZSwap's decisions and tracking → <strong>shared compression library</strong></p><p class="scene-cost">Independent XSwap would call the library without ZSwap. That next step still needs implementation and testing.</p></div></section>''',
'changes': '''<section id="changes"><h2>3. The change: extract one reusable library</h2>
<p class="lead">Move the compression and storage implementation out of ZSwap into a library named page_compress. Keep the stored data format and the rules for tracking and freeing it.</p>
<div class="scene"><div class="scene-grid"><div class="scene-box"><p class="scene-label">Before</p><h3>ZSwap contains both roles</h3><div class="owner">Decisions and data tracking</div><div class="engine"><span>Compression</span><span>Storage allocation</span></div><div class="pages"><div class="page-object compressed">A</div></div></div>
<div class="scene-box"><p class="scene-label">After</p><h3>ZSwap calls a shared library</h3><div class="owner">The same decisions and data tracking</div><div class="engine"><strong>Shared page_compress library</strong><br><span>Compression</span><span>Storage allocation</span></div><div class="pages"><div class="page-object compressed">A</div></div></div></div><p class="scene-cost">Benefit: future callers can reuse one implementation. Cost: another interface to maintain and another allocation per storage pool, the container for compressed data. Actual memory overhead and speed remain unmeasured.</p></div></section>'''
}

RESULT_LEAD = ('Functional checks passed, but the speed comparison could not begin. '
              'In the original, unchanged kernel, the timing tool could not confirm '
              'that the measured reads had successfully decompressed stored pages.')
RESULT_DETAIL = ('It therefore produced no complete valid timing sample. The cause is still unknown. '
                 'A later diagnostic attempt was reserved but never launched before its time window expired. '
                 'There is no measured speedup or slowdown for the library change.')
LIMITS = [
    'Functional checks cover the retained source, kernel configurations and test image. '
    'They support continuing development; performance and real-world memory overhead remain unmeasured. '
    'The library remains an experimental candidate, with no code promotion or change to the reference kernel.',
    'Independent XSwap test support is incomplete. An automated platform content-safety review interrupted '
    'its test-driver worker; the exact refused operation was not supplied. The partial driver was retained '
    'and the blocked operation was not retried. Independent XSwap and pressure-driven movement to disk have not run.',
    'Earlier failed attempts remain in the resource totals. The final family report also counts '
    'the diagnostic reservation that never launched. '
    'Replaying archived results checks their interpretation; it adds no new experiment.'
]



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
        # The Results section explains this retained timing failure in full.
        spec['sections'] = [s for s in spec['sections'] if s['id'] != 'limits']
        if family:
            spec.update(candidates_count=1, guests=obs['totals']['counted'], builds=obs['totals']['builds'])
            spec['subtitle'] = (
                f"{story['harness']} ({story['model']}) · line: {observed['line']} · "
                f"base {observed['baseline_commit'][:8]} · 1 candidate · "
                f"{obs['totals']['counted']} counted / {obs['totals']['launched']} launched guests / "
                f"{obs['totals']['builds']} builds")
        provenance = spec['subtitle']
        spec['subtitle'] = 'A first step toward sharing compression between Linux swap designs.'
        spec['card_metadata'] = 'Shared compression code · Required functional checks passed'
        spec['verdict']['label'] = 'Performance unmeasured'
        spec['verdict']['tiles'] = [
            {'label': 'Function', 'value': 'Required checks passed', 'note': 'Data, concurrency, cleanup and configuration checks.'},
            {'label': 'Speed', 'value': 'Not measured', 'note': 'Timing failed on the unchanged reference kernel.'},
            {'label': 'Decision', 'value': 'Continue development', 'note': 'Keep the library as an experimental candidate.'}]
        results = next(s for s in spec['sections'] if s['id'] == 'results')
        results['title'] = 'Results: function checked, speed still unknown'
        results['lead'] = RESULT_LEAD
        results['blocks'] = [{'type': 'note', 'text': RESULT_DETAIL}]
        evidence = next(s for s in spec['sections'] if s['id'] == 'evidence')
        evidence['blocks'] += [
            {'type': 'table', 'takeaway': 'Report provenance and verdict meaning',
             'columns': ['Field', 'Meaning'], 'rows': [
                 ['Native status', observed['verdict']],
                 ['Why inconclusive', 'Performance comparison is incomplete; functional coverage passed.'],
                 ['Execution provenance', provenance]]},
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
    coverage_html = '<div class="coverage"><span>Data restored correctly</span><span>Existing behavior preserved</span><span>Memory and locking checks passed</span><span>Concurrent cleanup passed</span><span>Processor and memory placement checked</span><span class="missing">Timing incomplete</span></div>'
    page = page.replace('<section id="results">', '<section id="results">' + coverage_html)
    page, count = re.subn(r'<section id="patches">.*?</section>',
                         lambda m: '<details class="audit"><summary>Implementation details: shared compression library</summary>' + m.group(0) + '</details>',
                         page, count=1, flags=re.S)
    if count != 1:
        raise ValueError('expected one implementation section')
    limits = '<details class="audit"><summary>Limits and follow-up status</summary>' + ''.join('<p>' + html.escape(x) + '</p>' for x in LIMITS) + '</details>'
    page = page.replace('</main>', limits + '</main>')
    page = page.replace('</script>', '''document.querySelectorAll('nav a').forEach(a => a.addEventListener('click', () => {
      let element = document.getElementById(a.getAttribute('href').slice(1));
      while (element) { if (element.tagName === 'DETAILS') element.open = true; element = element.parentElement; }
    }));</script>''')
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
    rows = ['# ' + story['title'], '', '**Functional checks passed; performance unmeasured.** ' + story['headline'], '']
    for section in story['sections']:
        if section['id'] == 'next':
            rows += ['## Results: function checked, speed still unknown', '', RESULT_LEAD, '', RESULT_DETAIL, '']
        rows += ['## ' + section['title'], '', section['lead'], '']
        rows += [b['text'] + '\n' for b in section['blocks'] if b['type'] == 'note']
        rows += ['<details>', '<summary>Sources for this explanation</summary>', '']
        rows += ['- [' + ref + '](https://github.com/ericzhang-zxh/Swap-Next/blob/' + story['source_commit'] + '/' + ref + ')' for ref in section['evidence']]
        rows += ['', '</details>', '']
    rows += ['<details>', '<summary>Implementation details: shared compression library</summary>', '', story['patches_lead'], '']
    for item in story['patches']:
        rows += ['### ' + item['takeaway'], '', 'Source: `' + item['source'] + '`', '', '```diff', item['patch'].rstrip(), '```', '']
    rows += ['</details>', '', '<details>', '<summary>Exact outcomes, functional coverage and resources</summary>', '',
             'Native verdict: `' + summary['verdict'] + '`. It refers to the unfinished performance comparison.', '',
             '| Evaluation | Candidate | Tier | Result |', '| --- | --- | --- | --- |']
    rows += ['| ' + ' | '.join(str(row.get(k) or '').replace('|', '/').replace('\n', ' ') for k in ('id', 'candidate', 'tier', 'status')) + ' |' for row in summary['evaluations']]
    rows += ['', '| Case | Configuration | Gate result | Valid |', '| --- | --- | --- | --- |']
    rows += ['| ' + a['case'] + ' | ' + a['config_id'] + ' | all pass | true |' for a in coverage]
    rows += ['', '| Contract | Counted | Launched | Builds |', '| --- | --- | --- | --- |']
    rows += ['| ' + x['campaign'] + ' | ' + str(x['counted']) + ' | ' + str(x['launched']) + ' | ' + str(x['builds']) + ' |' for x in obs['resources']]
    rows += ['', '[Public observations and exact hashes](observations.json)', '', '</details>', '', '## Limitations', '']
    for text in LIMITS:
        rows += [text, '']
    rows += ['[Interactive explanation](' + dated_name + '/explainer.html)', '']
    (report / 'REPORT.md').write_text('\n'.join(rows))
    receipt['artifacts'] = {name: delivery.digest_bytes(((dated if name in {'explainer.html', 'explainer.json'} else report) / name).read_bytes()) for name in delivery.OUTPUTS}
    delivery.write(report / 'delivery.json', receipt)
    print(json.dumps({'campaign': campaign, 'state': receipt['state'], 'html_sha256': receipt['artifacts']['explainer.html']}))
