#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Collect every campaigns/<c>/report/[<sub>/]explainer.html into a static site.

    python3 build_site.py campaigns/ _site/

A report at campaigns/<c>/report/explainer.html becomes _site/<c>/index.html;
a nested report at campaigns/<c>/report/<sub>/explainer.html becomes
_site/<sub>/index.html. Two sources that publish the same name are an error.
_site/index.html lists the campaigns, newest first, with the verdict read from
explainer.json.
"""
import datetime
import html
import json
import pathlib
import re
import shutil
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from build_page import CSS, STATUS  # noqa: E402


def published_name(page):
    # campaigns/<c>/report/explainer.html -> <c>; nested report -> its own directory.
    if page.parent.name == "report":
        return page.parent.parent.name
    return page.parent.name


def parse_date_value(val):
    if not val:
        return ""
    if isinstance(val, (int, float)):
        try:
            return datetime.datetime.fromtimestamp(val, datetime.timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            return ""
    if isinstance(val, str):
        m = re.search(r"\d{4}-\d{2}-\d{2}", val)
        if m:
            return m.group(0)
    return ""


def resolve_campaign_date(page, spec=None, camp_dir=None):
    """Resolve campaign date (YYYY-MM-DD) in order of priority:
    (a) explicit date field in explainer.json, or YYYY-MM-DD in published_name
    (b) campaign.json (closed_at / closed / opened_at / opened / created_at timestamp or ISO string)
    (c) delivery.json (history timestamp), or regex on subtitle / title
    """
    name = published_name(page)
    # (a)
    if spec:
        d = parse_date_value(spec.get("date"))
        if d:
            return d
    m = re.search(r"\d{4}-\d{2}-\d{2}", name)
    if m:
        return m.group(0)

    # (b)
    if camp_dir:
        camp_json = camp_dir / "campaign.json"
        if camp_json.exists():
            try:
                cdata = json.loads(camp_json.read_text(encoding="utf-8"))
                for key in ("closed_at", "closed", "opened_at", "opened", "created_at", "timestamp"):
                    d = parse_date_value(cdata.get(key))
                    if d:
                        return d
            except Exception:
                pass

    # (c)
    search_dirs = [page.parent]
    if camp_dir:
        search_dirs.append(camp_dir / "report")
    for dpath in search_dirs:
        deliv_file = dpath / "delivery.json"
        if deliv_file.exists():
            try:
                ddata = json.loads(deliv_file.read_text(encoding="utf-8"))
                hist = ddata.get("history", [])
                times = [h.get("time") for h in hist if isinstance(h, dict) and isinstance(h.get("time"), (int, float))]
                if times:
                    d = parse_date_value(max(times))
                    if d:
                        return d
                for key in ("timestamp", "delivered_at", "created_at"):
                    d = parse_date_value(ddata.get(key))
                    if d:
                        return d
            except Exception:
                pass

    if spec:
        m = re.search(r"\d{4}-\d{2}-\d{2}", spec.get("subtitle", ""))
        if m:
            return m.group(0)
        m = re.search(r"\d{4}-\d{2}-\d{2}", spec.get("title", ""))
        if m:
            return m.group(0)

    return ""


def get_sort_key(page, spec, camp_dir):
    date_str = resolve_campaign_date(page, spec, camp_dir)
    # Tie breaker timestamp
    ts = 0.0
    if camp_dir:
        search_dirs = [page.parent, camp_dir / "report"]
        for dpath in search_dirs:
            deliv_file = dpath / "delivery.json"
            if deliv_file.exists():
                try:
                    ddata = json.loads(deliv_file.read_text(encoding="utf-8"))
                    times = [h.get("time") for h in ddata.get("history", []) if isinstance(h, dict) and isinstance(h.get("time"), (int, float))]
                    if times:
                        ts = max(times)
                        break
                except Exception:
                    pass
    return (date_str, ts, published_name(page))


def build_site(campaigns, site):
    raw_pages = list(campaigns.glob("*/report/**/explainer.html"))
    page_items = []
    sources = {}

    for page in raw_pages:
        name = published_name(page)
        if name in sources:
            raise SystemExit(f"duplicate published name {name!r}: {sources[name]} and {page}")
        sources[name] = page

        spec_path = page.with_suffix(".json")
        spec = json.loads(spec_path.read_text(encoding="utf-8")) if spec_path.exists() else {}
        camp_dir = next((p for p in page.parents if (p / "campaign.json").exists()), None)
        date_str = resolve_campaign_date(page, spec, camp_dir)
        sort_key = get_sort_key(page, spec, camp_dir)
        page_items.append({
            "page": page,
            "name": name,
            "spec": spec,
            "date": date_str,
            "sort_key": sort_key,
        })

    # Sort newest first
    page_items.sort(key=lambda item: item["sort_key"], reverse=True)

    site.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in page_items:
        page = item["page"]
        name = item["name"]
        spec = item["spec"]
        date_str = item["date"]

        (site / name).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(page, site / name / "index.html")

        verdict = spec.get("verdict", {})
        var, icon, label = STATUS.get(verdict.get("status"), ("--muted", "·", "Report"))
        date_html = (f'<span style="font-size:13px;color:var(--muted);font-weight:600">'
                     f'{html.escape(date_str)}</span>') if date_str else ""

        rows.append(
            f'<a class="card" href="{html.escape(name)}/" style="display:block;color:inherit;text-decoration:none">'
            f'<div style="display:flex;justify-content:space-between;align-items:center">'
            f'<span class="badge"><i class="dot" style="background:var({var})"></i>{icon} {label}</span>'
            f'{date_html}</div>'
            f'<p class="chart-title" style="margin:10px 0 2px">{html.escape(spec.get("title", name))}</p>'
            f'<p class="lead" style="margin:0">{html.escape(verdict.get("headline", ""))}</p>'
            f'<p class="lead" style="margin:4px 0 0;font-size:13px">{html.escape(spec.get("subtitle", ""))}</p></a>')

    index = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
             f'<meta name="viewport" content="width=device-width,initial-scale=1">'
             f'<title>Swap Next experiments</title><style>{CSS}</style></head>'
             f'<body><div class="viz-root"><main><header><h1>Swap Next experiments</h1>'
             f'<p>One review page per campaign, newest first.</p></header>'
             f'{" ".join(rows) or "<p>No campaign pages yet.</p>"}</main></div></body></html>')
    (site / "index.html").write_text(index, encoding="utf-8")
    print(f"site: {len(rows)} campaign page(s) in {site}")


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    campaigns, site = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
    build_site(campaigns, site)


if __name__ == "__main__":
    main()
