#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Render the native closed-R4 report with public observations and dated output.

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
        raise ValueError('the report requires the closed inconclusive R4 contract')
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
    clock = obs['clock_validity']
    if summary['sources'].get(clock['record_source']) != clock['record_sha256']:
        raise ValueError('clock observations differ from the closed evidence')
    if [item['integration_pass'] for item in obs['attempts']] != [True, True]:
        raise ValueError('retained functional outcomes changed')
    if [item['run_valid'] for item in obs['attempts']] != [True, False]:
        raise ValueError('retained validity outcomes changed')
    if any(item['failed_gates'] for item in obs['attempts']):
        raise ValueError('the R4 explanation requires the original passing functional gates')
    if obs['attempts'][1]['invalid_reasons'] != ['clocksource_fallback']:
        raise ValueError('the explanation no longer matches the validity failure')
    builds = [row for row in summary['evaluations'] if row.get('action') == 'build-coverage']
    if not builds or any(not row.get('build_reused') or row.get('build_reserved') for row in builds):
        raise ValueError('R4 build reuse changed')
    manifests = {item['manifest_sha256'] for item in obs['reused_builds']}
    if manifests != {row['build_manifest_sha256'] for row in builds}:
        raise ValueError('reused build identities differ from the ledger')
    resources = obs['resources']
    totals = {key: sum(resources[contract][key] for contract in ['original_C1', 'R2', 'R3', 'R4'])
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
            {'label': 'NUMA functional gates', 'value': 'Passed', 'note': 'All checks and warning gates passed.'},
            {'label': 'NUMA run validity', 'value': 'Failed', 'note': 'Boot clocksource fallback recorded.'},
            {'label': 'Correctness matrix', 'value': 'Incomplete', 'note': 'No calibration or performance result.'},
        ]
        next(section for section in spec['sections'] if section['id'] == 'results')['lead'] = (
            'The saved functional pass and validity failure are both authoritative. No full candidate correctness result follows from this invalid run.'
        )
        evidence = next(section for section in spec['sections'] if section['id'] == 'evidence')
        evidence['blocks'][0]['takeaway'] = 'Revalidated build coverage; no new R4 build'
        candidate = obs['attempts'][1]
        evidence['blocks'] += [
            {'type': 'table', 'takeaway': 'Functional pass and run validity stay separate',
             'columns': ['Run', 'Functional gates', 'integration_pass', 'run_valid', 'Invalid reasons'],
             'rows': [[a['run_id'], str(a['gate_count'] - len(a['failed_gates'])) + ' / ' + str(a['gate_count']),
                       str(a['integration_pass']).lower(), str(a['run_valid']).lower(),
                       ', '.join(a['invalid_reasons']) or 'none'] for a in obs['attempts']]},
            {'type': 'table', 'takeaway': 'Retained boot-clock events precede hotplug',
             'columns': ['Serial line', 'Exact recorded event'],
             'rows': [[event['serial_line'], event['message']] for event in clock['events']]},
            {'type': 'table', 'takeaway': 'Exit and subcase-reset observations have a bounded scope',
             'columns': ['Record', 'Exit / reset', 'Recorded cleanup fields'],
             'rows': [[a['run_id'], 'exit=' + str(a['exit_code']) + ', qemu_exit=' + str(a['gates']['qemu_exit']).lower(),
                       'stop_reason=' + str(a['stop_reason'])] for a in obs['attempts']] +
                     [[name, 'status=' + item['status'] + ', reset=' + str(item['reset']).lower(),
                       json.dumps(item['reset_observations'], sort_keys=True) if item['reset_observations'] else
                       'No reset counters emitted; untouched=' + str(item['untouched']).lower()]
                      for name, item in candidate['subcases'].items()]},
            {'type': 'table', 'takeaway': 'Existing exact-source builds were reused',
             'columns': ['Build', 'Source commit', 'Final configuration SHA-256', 'Manifest SHA-256', 'New R4 cost'],
             'rows': [[item['build'], item['source_commit'], item['final_config_sha256'], item['manifest_sha256'], 0]
                      for item in obs['reused_builds']]},
            {'type': 'table', 'takeaway': 'Costs through the R4 closeout',
             'columns': ['Contract', 'Counted guests', 'Counted builds'],
             'rows': [[label, resources[key]['guests'], resources[key]['builds']]
                      for key, label in [('original_C1', 'Original C1'), ('R2', 'R2'), ('R3', 'R3'), ('R4', 'R4'), ('cumulative_C1', 'C1 through R4')]]},
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
    lines = ['<details>', '<summary>Functional outcomes, validity and cumulative costs</summary>', '',
             '| Run | Functional gates | integration_pass | run_valid |', '| --- | --- | --- | --- |']
    for a in obs['attempts']:
        lines.append('| ' + a['run_id'] + ' | ' + str(a['gate_count'] - len(a['failed_gates'])) + ' / ' + str(a['gate_count']) +
                     ' | ' + str(a['integration_pass']).lower() + ' | ' + str(a['run_valid']).lower() + ' |')
    lines += ['', 'NUMA invalid reason: `clocksource_fallback`.', '',
              '| Serial line | Recorded boot event |', '| --- | --- |']
    lines += ['| ' + str(event['serial_line']) + ' | ' + event['message'] + ' |' for event in clock['events']]
    lines += ['', '| Contract | Counted guests | Counted builds |', '| --- | --- | --- |']
    for key, label in [('original_C1', 'Original C1'), ('R2', 'R2'), ('R3', 'R3'), ('R4', 'R4'), ('cumulative_C1', 'C1 through R4')]:
        lines.append('| ' + label + ' | ' + str(resources[key]['guests']) + ' | ' + str(resources[key]['builds']) + ' |')
    lines += ['', '[Public observations and hashes](observations.json)', '', '</details>', '']
    markdown = markdown[:start] + '\n'.join(lines) + (
        '\n## Limitations\n\n'
        'The NUMA run supplies warning-free functional evidence with integration_pass=true. '
        'Its saved run_valid=false prevents valid matrix coverage. R4 ran only baseline common '
        'and candidate NUMA; no candidate debug or other matrix case ran. No calibration, speed '
        'or equivalence result exists. Any future environment correction is unmeasured here.\n\n'
        'Normal exit and the named subcase reset fields are recorded observations, not a broader '
        'teardown audit. Raw results, serial logs, sidecars, reused build provenance and the '
        'pre-change runtime archive remain retained outside this public report. Their hashes '
        'and all four frozen budget costs are bound in observations.json.\n\n'
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
