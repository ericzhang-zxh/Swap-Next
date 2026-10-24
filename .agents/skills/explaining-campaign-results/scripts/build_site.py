#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Collect every results/<campaign>/explainer.html into a static site.

    python3 build_site.py results/ _site/

Each page becomes _site/<campaign>/index.html. _site/index.html lists the
campaigns, newest first, with the verdict read from explainer.json.
"""
import html
import json
import pathlib
import re
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from build_page import CSS, STATUS  # noqa: E402


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    results, site = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    site.mkdir(parents=True, exist_ok=True)
    rows = []
    def campaign_date(page):
        match = re.search(r"\d{4}-\d{2}-\d{2}", page.parent.name)
        return (match.group(0) if match else "", page.parent.name)

    for page in sorted(results.glob("*/explainer.html"), key=campaign_date, reverse=True):
        name = page.parent.name
        (site / name).mkdir(exist_ok=True)
        shutil.copyfile(page, site / name / "index.html")
        spec_path = page.with_suffix(".json")
        spec = json.loads(spec_path.read_text()) if spec_path.exists() else {}
        verdict = spec.get("verdict", {})
        var, icon, label = STATUS.get(verdict.get("status"), ("--muted", "·", "Report"))
        rows.append(
            f'<a class="card" href="{html.escape(name)}/" style="display:block;color:inherit;text-decoration:none">'
            f'<span class="badge"><i class="dot" style="background:var({var})"></i>{icon} {label}</span>'
            f'<p class="chart-title" style="margin:10px 0 2px">{html.escape(spec.get("title", name))}</p>'
            f'<p class="lead" style="margin:0">{html.escape(verdict.get("headline", ""))}</p>'
            f'<p class="lead" style="margin:4px 0 0;font-size:13px">{html.escape(spec.get("subtitle", ""))}</p></a>')
    index = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
             f'<meta name="viewport" content="width=device-width,initial-scale=1">'
             f'<title>Swap Next experiments</title><style>{CSS}</style></head>'
             f'<body><div class="viz-root"><main><header><h1>Swap Next experiments</h1>'
             f'<p>One review page per campaign, newest first.</p></header>'
             f'{"".join(rows) or "<p>No campaign pages yet.</p>"}</main></div></body></html>')
    (site / "index.html").write_text(index, encoding="utf-8")
    print(f"site: {len(rows)} campaign page(s) in {site}")


if __name__ == "__main__":
    main()
