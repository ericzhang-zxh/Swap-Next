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
            {'label': 'Candidate source', 'value': 'Compiled',
             'note': 'Required debug configuration failed.'},
            {'label': 'Candidate runtime', 'value': 'Not run',
             'note': 'No correctness or performance result.'},
            {'label': 'Next decision', 'value': 'Correct setup',
             'note': 'Same source; remaining phase budget.'},
        ]
        next(section for section in spec['sections'] if section['id'] == 'results')['lead'] = (
            'High confidence in the recorded stopping cause; candidate behavior and costs remain unknown.'
        )
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
    markdown = markdown.replace('[Interactive explanation](explainer.html)',
                                '[Interactive explanation](' + dated_name + '/explainer.html)')
    start = markdown.index('## Limitations\n')
    markdown = markdown[:start] + (
        '## Limitations\n\n'
        'Evidence is limited to source review, baseline checks and candidate compilation. '
        'Required candidate configuration failed before runtime. No candidate correctness, '
        'KUnit, sanitizer, calibration, speed or equivalence result exists.\n\n'
        'Raw runtime evidence remains retained outside this public report. The original '
        'closeout record pins its observed artifact hashes; summary.json preserves the '
        'failed build, audited infrastructure retry, budget and closed outcome.\n\n'
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
