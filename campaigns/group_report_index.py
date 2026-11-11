#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Group related report cards while retaining every immutable report route."""
import html
import json
from pathlib import Path
import re
import sys

NAME = re.compile(r'[a-z][a-z0-9-]{0,47}')
CARD = re.compile(r'<a class="card" href="([^"<>]+)"[^>]*>.*?</a>', re.S)


def group_index(campaigns, site):
    campaigns, site = Path(campaigns), Path(site)
    manifest = json.loads((campaigns / 'report-groups.json').read_text())
    if manifest.get('schema_version') != 1:
        raise ValueError('unsupported report-group schema')
    index = site / 'index.html'
    page = index.read_text()
    cards = list(CARD.finditer(page))
    seen, replacements = set(), []
    for group in manifest['groups']:
        members, representative = group['members'], group['representative']
        if (not isinstance(members, list) or len(set(members)) != len(members)
                or representative not in members or not group.get('title')
                or any(not NAME.fullmatch(name) or name in seen for name in members)):
            raise ValueError('invalid or overlapping report group')
        seen.update(members)
        matched = {}
        for member in members:
            record = json.loads((campaigns / member / 'campaign.json').read_text())
            if record.get('status') != 'closed' or not (site / member / 'index.html').is_file():
                raise ValueError('group member lacks a closed report route: ' + member)
            matches = [m for m in cards if m.group(1) == member + '/' or
                       re.fullmatch(re.escape(member) + r'-\d{4}-\d{2}-\d{2}/', m.group(1))]
            if len(matches) != 1:
                raise ValueError('expected exactly one source card for ' + member)
            matched[member] = matches[0]
        for member, match in matched.items():
            if member != representative:
                replacements.append((match.start(), match.end(), ''))
        match = matched[representative]
        links = ''.join('<li><a href="' + html.escape(member, quote=True) + '/">' +
                        html.escape(member) + '</a></li>' for member in members if member != representative)
        appendix = ('<details style="margin:0 0 24px;padding:0 18px"><summary>' +
                    html.escape(group['title']) + ': retained contract evidence</summary><ul>' +
                    links + '</ul></details>')
        replacements.append((match.start(), match.end(), match.group(0) + appendix))
    for start, end, replacement in sorted(replacements, reverse=True):
        page = page[:start] + replacement + page[end:]
    page = page.replace('One review page per campaign, newest first.',
                        'One review card per campaign or experiment family, newest first.')
    for member in seen:
        if 'href="' + member + '/' not in page and not any(
                href.startswith(member + '-') for href in CARD.findall(page)):
            raise ValueError('grouping removed report discoverability: ' + member)
    index.write_text(page)
    print(json.dumps({'grouped_families': len(manifest['groups']), 'retained_routes': len(seen),
                      'index_cards': len(CARD.findall(page))}))


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('usage: group_report_index.py CAMPAIGNS SITE')
    group_index(sys.argv[1], sys.argv[2])
