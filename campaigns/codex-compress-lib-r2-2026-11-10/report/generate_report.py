#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Render the native evidence-bound report and package its dated explainer.

An isolated authoring checkout may read the closed campaign from --evidence-root.
Only this checkout's report directory is written; private runtime files are never
copied. On integrated main, no argument is needed.
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
    extract = delivery.extract
    make_spec = delivery.make_spec
    summary = extract(evidence_root, campaign)
    story = delivery.read(report / 'story.json')
    delivery.validate_story(story, summary)
    observations_path = report / 'observations.json'
    if delivery.digest_bytes(observations_path.read_bytes()) != story['observations_sha256']:
        raise ValueError('public observations changed without an explanation update')
    observations = delivery.read(observations_path)
    if observations['native_evidence_sha256'] != summary['evidence_sha256']:
        raise ValueError('public observations belong to different closed evidence')
    stops = [item for item in summary['execution_closeout']['decisions'] if item['kind'] == 'stop']
    bound = stops[-1]['input_hashes']
    for attempt in observations['attempts']:
        if bound.get(attempt['result_source']) != attempt['result_sha256']:
            raise ValueError('raw result hash is not pinned by the closed session')
        serial_source = str(Path(attempt['result_source']).with_name('serial.log'))
        if bound.get(serial_source) != attempt['serial_sha256']:
            raise ValueError('serial log hash is not pinned by the closed session')
    replay = observations['diagnostic_replay']
    if summary['sources'].get(replay['source']) != replay['sha256']:
        raise ValueError('diagnostic interpretation is not bound to the closed record')
    builds = [row for row in summary['evaluations'] if row.get('action') == 'build-coverage']
    if len(builds) != 1 or builds[0]['build_manifest_sha256'] != observations['configured_build']['manifest_sha256']:
        raise ValueError('configured build observations differ from the retained ledger')
    if observations['resources']['cumulative_C1'] != {
            key: observations['resources']['original_C1'][key] + observations['resources']['R2'][key]
            for key in ('guests', 'builds')}:
        raise ValueError('logical-phase resource accounting does not reconcile')
    if summary['status'] != 'closed' or summary['verdict'] != 'inconclusive':
        raise ValueError('this closeout explanation requires the closed inconclusive contract')
    if any(row.get('action') in {'evaluate', 'calibrate'} for row in summary['evaluations']):
        raise ValueError('new runtime measurements require a new explanation')

    def source_summary(requested_root, requested_campaign):
        if Path(requested_root).resolve() != root or requested_campaign != campaign:
            raise ValueError('report extraction escaped the assigned campaign')
        return summary

    def report_spec(observed, explanation):
        spec = make_spec(observed, explanation)
        spec['verdict']['tiles'] = [
            {'label': 'Debug build', 'value': 'Verified',
             'note': 'Required memory checker enabled.'},
            {'label': 'Candidate guest', 'value': 'Recorded',
             'note': 'Raw success records; parsing failed.'},
            {'label': 'Correctness matrix', 'value': 'Incomplete',
             'note': 'No performance or equivalence result.'},
        ]
        next(section for section in spec['sections'] if section['id'] == 'results')['lead'] = (
            'High confidence in the observed parser defects. Raw debug observations remain distinct from validated complete coverage.'
        )
        evidence = next(section for section in spec['sections'] if section['id'] == 'evidence')
        evidence['blocks'][0]['takeaway'] = 'Recorded build ledger'
        attempts = observations['attempts']
        raw = observations['debug_raw_observations']
        resources = observations['resources']
        evidence['blocks'] += [
            {'type': 'table', 'takeaway': 'Original guest outcomes remain unchanged',
             'columns': ['Run', 'Role', 'Exit', 'Run valid', 'Integration pass', 'Raw result SHA-256'],
             'rows': [[a['run_id'], a['role'], a['exit_code'], str(a['run_valid']).lower(),
                       str(a['integration_pass']).lower(), a['result_sha256']] for a in attempts]},
            {'type': 'table', 'takeaway': 'Retained debug signals are raw observations',
             'columns': ['Signal', 'Observed content', 'Validation boundary'],
             'rows': [['Subcases reporting PASS', ', '.join(raw['subcases_reporting_PASS']), 'Original parsing failed'],
                      ['Named KUnit cases reporting ok', ', '.join(raw['kunit_cases_reporting_ok']), 'Full matrix remains incomplete'],
                      ['Standard KUnit summary', raw['kunit_summary'], 'Zero-skip framing caused a diagnostic replay rejection'],
                      ['Kernel diagnostic scan', 'No diagnostic found in retained log', 'Raw observation only'],
                      ['Original parser error', attempts[1]['parse_error'], 'Saved integration_pass remains false']]},
            {'type': 'table', 'takeaway': 'Costs accumulate within one C1 phase',
             'columns': ['Contract', 'Counted guests', 'Counted builds'],
             'rows': [[label, resources[key]['guests'], resources[key]['builds']]
                      for key, label in [('original_C1', 'Original C1'), ('R2', 'R2'), ('cumulative_C1', 'C1 cumulative')]]},
            {'type': 'table', 'takeaway': 'Retained runtime identities',
             'columns': ['Artifact', 'SHA-256'],
             'rows': [['Candidate serial log', attempts[1]['serial_sha256']],
                      ['Candidate raw result', attempts[1]['result_sha256']],
                      ['Pre-fix runtime archive', observations['runtime_archive']['sha256']],
                      ['Debug final configuration', observations['configured_build']['final_config_sha256']],
                      ['Public observation summary', story['observations_sha256']]]},
        ]
        return spec

    try:
        delivery.extract = source_summary
        delivery.make_spec = report_spec
        receipt = delivery.render(root, campaign)
    finally:
        delivery.extract = extract
        delivery.make_spec = make_spec
        # Native delivery emits its generic wrapper; keep this dated wrapper.
        script.write_bytes(original_script)

    page = (report / 'explainer.html').read_text()
    related = story['related_reports'][0]
    if not related['url'].startswith('https://ericzhang-zxh.github.io/Swap-Next/'):
        raise ValueError('unexpected related campaign URL')
    related_html = ('<p class="related">Continuation of <a href="' +
                    html.escape(related['url'], quote=True) + '">' +
                    html.escape(related['title']) + '</a> on the same kernel source.</p>')
    page = page.replace('<section id="context">', related_html + '<section id="context">')
    for item in story['patches']:
        source = item['source']
        label = html.escape(source)
        commit = story.get('source_commit')
        if commit:
            href = 'https://github.com/ericzhang-zxh/Swap-Next/blob/' + commit + '/' + source
            label = '<a href="' + html.escape(href, quote=True) + '">' + label + '</a>'
        citation = ('<p class="patch-source">Source: ' + label + '<br>SHA-256: <code>' +
                    summary['sources'][source] + '</code></p>')
        target = '<p class="chart-title">' + html.escape(item['takeaway']) + '</p>'
        if page.count(target) != 1:
            raise ValueError('expected one rendered card per core patch excerpt')
        page = page.replace(target, target + citation)
    page = page.replace('</style>', '.patch-source{font-size:12px;overflow-wrap:anywhere}'
                        '.patch-source a{color:var(--ink-2)}'
                        'pre.diff{max-width:100%}</style>')

    dated_name = campaign + '-' + story['date']
    dated = report / dated_name
    dated.mkdir(exist_ok=True)
    (dated / 'explainer.html').write_text(page)
    (report / 'explainer.html').unlink()
    (report / 'explainer.json').replace(dated / 'explainer.json')
    markdown = (report / 'REPORT.md').read_text()
    related_md = 'Continuation of [' + related['title'] + '](' + related['url'] + ') on the same kernel source.'
    markdown = markdown.replace('\n## ', '\n' + related_md + '\n\n## ', 1)
    markdown = markdown.replace('[Interactive explanation](explainer.html)',
                                '[Interactive explanation](' + dated_name + '/explainer.html)')
    start = markdown.index('## Limitations\n')
    evidence_lines = ['<details>', '<summary>Retained guest observations and cumulative costs</summary>', '',
                      '| Run | Original integration | Raw observation |', '| --- | --- | --- |']
    for attempt in observations['attempts']:
        detail = 'Fresh baseline passed' if attempt['role'] == 'baseline' else 'Debug log completed; parsing rejected'
        evidence_lines.append('| ' + attempt['run_id'] + ' | ' + str(attempt['integration_pass']).lower() + ' | ' + detail + ' |')
    evidence_lines += ['', '| Contract | Counted guests | Counted builds |', '| --- | --- | --- |']
    for key, label in [('original_C1', 'Original C1'), ('R2', 'R2'), ('cumulative_C1', 'C1 cumulative')]:
        item = observations['resources'][key]
        evidence_lines.append('| ' + label + ' | ' + str(item['guests']) + ' | ' + str(item['builds']) + ' |')
    evidence_lines += ['', '[Public observations and hashes](observations.json)', '', '</details>', '']
    markdown = markdown[:start] + '\n'.join(evidence_lines) + (
        '\n## Limitations\n\n'
        'R2 records raw candidate debug output from the unchanged kernel. The saved integration '
        'result remains failed and the complete required correctness matrix is unfinished. '
        'Diagnostic replay identifies parser defects; it replaces no failed observation. '
        'No calibrated speed or equivalence result exists.\n\n'
        'Raw runtime bytes and the pre-fix runtime archive remain retained outside this public report. '
        'The closeout record pins the original hashes; observations.json summarizes the raw signals '
        'and cumulative costs. Fresh counted correctness evidence is required under any correction.\n\n'
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
