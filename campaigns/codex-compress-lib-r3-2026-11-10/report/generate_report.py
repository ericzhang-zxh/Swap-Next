#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Render the native closed-R3 report with public observations and dated output.

--evidence-root allows an isolated report checkout to read retained central
campaign records in memory. Only this report directory is written.
"""
import argparse
import html
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root', type=Path)
    args = parser.parse_args()
    script = Path(__file__).resolve()
    report = script.parent
    root = script.parents[3]
    campaign = script.parents[1].name
    evidence_root = (args.evidence_root or root).resolve()
    sys.path.insert(0, str(root / 'evolve'))
    import delivery

    original_script = script.read_bytes()
    extract, make_spec = delivery.extract, delivery.make_spec
    summary = extract(evidence_root, campaign)
    story = delivery.read(report / 'story.json')
    delivery.validate_story(story, summary)
    obs_path = report / 'observations.json'
    if delivery.digest_bytes(obs_path.read_bytes()) != story['observations_sha256']:
        raise ValueError('public observations changed without an explanation update')
    obs = delivery.read(obs_path)
    if obs['native_evidence_sha256'] != summary['evidence_sha256']:
        raise ValueError('public observations belong to different closed evidence')
    if summary['status'] != 'closed' or summary['verdict'] != 'inconclusive':
        raise ValueError('the report requires the closed inconclusive R3 contract')
    if any(row.get('action') in {'evaluate', 'calibrate'} for row in summary['evaluations']):
        raise ValueError('new measurements require a new explanation')
    stops = [item for item in summary['execution_closeout']['decisions'] if item['kind'] == 'stop']
    bound = stops[-1]['input_hashes']
    for attempt in obs['attempts']:
        refs = [(attempt['result_source'], attempt['result_sha256']),
                (str(Path(attempt['result_source']).with_name('serial.log')), attempt['serial_sha256']),
                (attempt['reservation_source'], attempt['reservation_sha256'])]
        if any(bound.get(ref) != expected for ref, expected in refs):
            raise ValueError('guest evidence is not pinned by the closed session')
    failure = obs['numa_failure']
    if summary['sources'].get(failure['diagnosis_source']) != failure['diagnosis_sha256']:
        raise ValueError('diagnosis differs from the closed evidence')
    if [item['integration_pass'] for item in obs['attempts']] != [True, True, False]:
        raise ValueError('retained per-run outcomes changed')
    if obs['attempts'][2]['failed_gates'] != ['no_kernel_warnings', 'no_new_kernel_warnings']:
        raise ValueError('the explanation no longer matches the failed gates')
    builds = [row for row in summary['evaluations'] if row.get('action') == 'build-coverage']
    if not builds or any(not row.get('build_reused') or row.get('build_reserved') for row in builds):
        raise ValueError('R3 build reuse changed')
    manifests = {item['manifest_sha256'] for item in obs['reused_builds']}
    if manifests != {row['build_manifest_sha256'] for row in builds}:
        raise ValueError('reused build identities differ from the ledger')
    resources = obs['resources']
    totals = {key: sum(resources[contract][key] for contract in ['original_C1', 'R2', 'R3'])
              for key in ['guests', 'builds']}
    if totals != resources['cumulative_C1']:
        raise ValueError('logical-phase resource accounting does not reconcile')

    def source_summary(requested_root, requested_campaign):
        if Path(requested_root).resolve() != root or requested_campaign != campaign:
            raise ValueError('report extraction escaped the assigned campaign')
        return summary

    def report_spec(observed, explanation):
        spec = make_spec(observed, explanation)
        spec['verdict']['tiles'] = [
            {'label': 'Baseline and debug', 'value': 'Passed', 'note': 'Complete gates for those two runs.'},
            {'label': 'NUMA case', 'value': 'Failed', 'note': 'Boot warning; functional subcases passed.'},
            {'label': 'Correctness matrix', 'value': 'Incomplete', 'note': 'No timing or equivalence result.'},
        ]
        next(section for section in spec['sections'] if section['id'] == 'results')['lead'] = (
            'Per-run successes are retained alongside the failed NUMA case. The warning keeps the full matrix incomplete.'
        )
        evidence = next(section for section in spec['sections'] if section['id'] == 'evidence')
        evidence['blocks'][0]['takeaway'] = 'Revalidated build coverage; no new R3 build'
        evidence['blocks'] += [
            {'type': 'table', 'takeaway': 'Original guest results remain authoritative',
             'columns': ['Run', 'Topology', 'Passed gates / total', 'Integration', 'Failed gates'],
             'rows': [[a['run_id'], a['topology_id'],
                       str(a['gate_count'] - len(a['failed_gates'])) + ' / ' + str(a['gate_count']),
                       str(a['integration_pass']).lower(), ', '.join(a['failed_gates']) or 'none']
                      for a in obs['attempts']]},
            {'type': 'table', 'takeaway': 'The NUMA warning remains a failing outcome',
             'columns': ['Signal', 'Observed content'],
             'rows': [['Boot warning', failure['warning']],
                      ['Warning location', failure['location']],
                      ['Trusted topology arguments', json.dumps(failure['topology_arguments'])],
                      ['Passing NUMA subcases', ', '.join(failure['subcases_passed'])],
                      ['Requested / actual node placement', json.dumps(failure['placement_observations'])],
                      ['Overall integration', 'false; both kernel-warning gates failed']]},
            {'type': 'table', 'takeaway': 'Existing exact-source builds were reused',
             'columns': ['Build', 'Source commit', 'Final configuration SHA-256', 'Manifest SHA-256', 'New R3 cost'],
             'rows': [[item['build'], item['source_commit'], item['final_config_sha256'], item['manifest_sha256'], 0]
                      for item in obs['reused_builds']]},
            {'type': 'table', 'takeaway': 'Costs through the R3 closeout',
             'columns': ['Contract', 'Counted guests', 'Counted builds'],
             'rows': [[label, resources[key]['guests'], resources[key]['builds']]
                      for key, label in [('original_C1', 'Original C1'), ('R2', 'R2'), ('R3', 'R3'), ('cumulative_C1', 'C1 through R3')]]},
            {'type': 'table', 'takeaway': 'Pinned private-runtime identities',
             'columns': ['Artifact', 'SHA-256'],
             'rows': [[a['run_id'] + suffix, a[key]] for a in obs['attempts']
                      for suffix, key in [(' result', 'result_sha256'), (' serial', 'serial_sha256'),
                                          (' result hash sidecar', 'hash_sidecar_sha256'), (' start sidecar', 'started_sha256')]] +
                     [['Runtime archive', obs['runtime_archive']['sha256']],
                      ['Public observations', story['observations_sha256']]]},
        ]
        return spec

    try:
        delivery.extract, delivery.make_spec = source_summary, report_spec
        receipt = delivery.render(root, campaign)
    finally:
        delivery.extract, delivery.make_spec = extract, make_spec
        script.write_bytes(original_script)

    page = (report / 'explainer.html').read_text()
    links, markdown_links = [], []
    for related in story['related_reports']:
        if not related['url'].startswith('https://ericzhang-zxh.github.io/Swap-Next/'):
            raise ValueError('unexpected related campaign URL')
        links.append('<a href="' + html.escape(related['url'], quote=True) + '">' + html.escape(related['title']) + '</a>')
        markdown_links.append('[' + related['title'] + '](' + related['url'] + ')')
    related_html = '<p class="related">Earlier frozen contracts: ' + ' · '.join(links) + '. One unchanged kernel hypothesis.</p>'
    page = page.replace('<section id="context">', related_html + '<section id="context">')
    for item in story['patches']:
        source = item['source']
        label = html.escape(source)
        if story.get('source_commit'):
            href = 'https://github.com/ericzhang-zxh/Swap-Next/blob/' + story['source_commit'] + '/' + source
            label = '<a href="' + html.escape(href, quote=True) + '">' + label + '</a>'
        citation = '<p class="patch-source">Source: ' + label + '<br>SHA-256: <code>' + summary['sources'][source] + '</code></p>'
        target = '<p class="chart-title">' + html.escape(item['takeaway']) + '</p>'
        if page.count(target) != 1:
            raise ValueError('expected one rendered card per core patch excerpt')
        page = page.replace(target, target + citation)
    page = page.replace('</style>', '.patch-source{font-size:12px;overflow-wrap:anywhere}'
                        '.patch-source a{color:var(--ink-2)}pre.diff{max-width:100%}</style>')
    dated_name = campaign + '-' + story['date']
    dated = report / dated_name
    dated.mkdir(exist_ok=True)
    (dated / 'explainer.html').write_text(page)
    (report / 'explainer.html').unlink()
    (report / 'explainer.json').replace(dated / 'explainer.json')
    markdown = (report / 'REPORT.md').read_text()
    related_md = 'Earlier frozen contracts: ' + ' · '.join(markdown_links) + '. One unchanged kernel hypothesis.'
    markdown = markdown.replace('\n## ', '\n' + related_md + '\n\n## ', 1)
    start = markdown.index('## Limitations\n')
    lines = ['<details>', '<summary>Per-run evidence and cumulative costs</summary>', '',
             '| Run | Passed gates / total | Original integration |', '| --- | --- | --- |']
    for a in obs['attempts']:
        lines.append('| ' + a['run_id'] + ' | ' + str(a['gate_count'] - len(a['failed_gates'])) + ' / ' + str(a['gate_count']) + ' | ' + str(a['integration_pass']).lower() + ' |')
    lines += ['', 'Retained NUMA warning: `' + failure['warning'] + '`', '',
              '| Contract | Counted guests | Counted builds |', '| --- | --- | --- |']
    for key, label in [('original_C1', 'Original C1'), ('R2', 'R2'), ('R3', 'R3'), ('cumulative_C1', 'C1 through R3')]:
        lines.append('| ' + label + ' | ' + str(resources[key]['guests']) + ' | ' + str(resources[key]['builds']) + ' |')
    lines += ['', '[Public observations and hashes](observations.json)', '', '</details>', '']
    markdown = markdown[:start] + '\n'.join(lines) + (
        '\n## Limitations\n\n'
        'The two per-run passes cover their named cases. The retained NUMA failure and remaining '
        'matrix rows keep full candidate correctness incomplete. No calibration, speed or equivalence '
        'result exists. A future topology correction has no outcome in this report.\n\n'
        'Raw results, serial logs, sidecars and the pre-correction runtime archive remain retained '
        'outside this public report. Their hashes, reused builds, failed warning gates and frozen '
        'budget costs are bound in observations.json and the native closeout summary.\n\n'
        '[Interactive explanation](' + dated_name + '/explainer.html)\n'
    )
    (report / 'REPORT.md').write_text(markdown)
    receipt['artifacts'] = {
        name: delivery.digest_bytes(((dated if name in {'explainer.html', 'explainer.json'} else report) / name).read_bytes())
        for name in delivery.OUTPUTS
    }
    delivery.write(report / 'delivery.json', receipt)
    print(json.dumps({'state': receipt['state'], 'evidence_sha256': summary['evidence_sha256'],
                      'html_sha256': receipt['artifacts']['explainer.html'],
                      'dated_explainer': (dated / 'explainer.html').relative_to(root).as_posix()}, indent=2))


if __name__ == '__main__':
    main()
