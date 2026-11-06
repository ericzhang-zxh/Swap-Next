#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Collect every campaigns/<c>/report/[<sub>/]explainer.html into a static site.

    python3 build_site.py campaigns/ _site/

A report at campaigns/<c>/report/explainer.html becomes _site/<c>/index.html;
a nested report at campaigns/<c>/report/<sub>/explainer.html becomes
_site/<sub>/index.html. Deduplicates by campaign folder so a campaign never generates
duplicate cards on the homepage.
_site/index.html lists the campaigns, newest first, with a standardized metadata bar.
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


def resolve_harness_model(name, spec=None, camp_dir=None):
    if spec:
        h = spec.get("harness")
        m = spec.get("model")
        if h and m:
            return f"{h} ({m})"
    n = name.lower()
    if camp_dir:
        n = f"{n} {camp_dir.name.lower()}"
    if re.search(r"\bexp[1-5]\b", n) or n.startswith("exp") or "exp1" in n or "exp2" in n or "exp3" in n or "exp4" in n or "exp5" in n:
        return "agy (gemini4argon)"
    if "codex-r01" in n or "codex-r02" in n or "codex" in n:
        return "codex (gpt-6-astra)"
    if "tcg-kbench" in n or "rev7" in n:
        return "grok-bot / claudecode (opus5.5)"
    if any(d in n for d in ("2026-10-21", "2026-10-22", "2026-10-23", "2026-10-24")) or "xswap" in n or "swap-standard" in n:
        return "claudecode (opus5.5)"
    return "agy (gemini4argon)"


def resolve_line(page, spec=None, camp_dir=None):
    if spec and spec.get("line"):
        return spec["line"]
    if camp_dir:
        camp_json = camp_dir / "campaign.json"
        if camp_json.exists():
            try:
                cdata = json.loads(camp_json.read_text(encoding="utf-8"))
                if cdata.get("line"):
                    return cdata["line"]
            except Exception:
                pass
        sum_json = camp_dir / "report" / "summary.json"
        if sum_json.exists():
            try:
                sdata = json.loads(sum_json.read_text(encoding="utf-8"))
                if sdata.get("line"):
                    return sdata["line"]
            except Exception:
                pass
    if spec and spec.get("subtitle"):
        parts = [p.strip() for p in spec["subtitle"].split("·")]
        for p in parts:
            if p.startswith("line:"):
                return p.replace("line:", "").strip()
        if parts:
            first = parts[0]
            if not re.search(r"^\d{4}-\d{2}-\d{2}$", first) and not re.search(r"^[0-9a-f]{8,}$", first) and "(" not in first:
                return first
    name = published_name(page)
    clean_name = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", name)
    return clean_name


def resolve_base_sha(page, spec=None, camp_dir=None):
    if spec and spec.get("baseline_commit"):
        return spec["baseline_commit"][:8]
    if camp_dir:
        prot_json = camp_dir / "protocol.json"
        if prot_json.exists():
            try:
                pdata = json.loads(prot_json.read_text(encoding="utf-8"))
                if pdata.get("baseline_commit"):
                    return pdata["baseline_commit"][:8]
            except Exception:
                pass
        sum_json = camp_dir / "report" / "summary.json"
        if sum_json.exists():
            try:
                sdata = json.loads(sum_json.read_text(encoding="utf-8"))
                if sdata.get("baseline_commit"):
                    return sdata["baseline_commit"][:8]
            except Exception:
                pass
    if spec and spec.get("subtitle"):
        m = re.search(r"\b([0-9a-f]{7,40})\b", spec["subtitle"])
        if m:
            return m.group(1)[:8]
    return "5e84ca92"


def resolve_scale_and_budget(page, spec=None, camp_dir=None):
    candidates_count = 0
    guests = 0
    builds = 0

    if camp_dir:
        cands_dir = camp_dir / "candidates"
        if cands_dir.is_dir():
            candidates_count = len(list(cands_dir.glob("*.json")))

        b_file = camp_dir / "ledger" / "budget.json"
        if b_file.exists():
            try:
                bdata = json.loads(b_file.read_text(encoding="utf-8"))
                guests = bdata.get("guests", 0) + bdata.get("probe_guests", 0)
                builds = bdata.get("builds", 0)
            except Exception:
                pass
        else:
            sum_json = camp_dir / "report" / "summary.json"
            if sum_json.exists():
                try:
                    sdata = json.loads(sum_json.read_text(encoding="utf-8"))
                    if not candidates_count and "candidates" in sdata:
                        candidates_count = len(sdata["candidates"])
                    bdata = sdata.get("budget", {})
                    guests = bdata.get("guests", 0) + bdata.get("probe_guests", 0)
                    builds = bdata.get("builds", 0)
                    if not guests and "evaluations" in sdata:
                        guests = len(sdata["evaluations"])
                except Exception:
                    pass

    if spec:
        if "candidates_count" in spec:
            candidates_count = spec["candidates_count"]
        if "guests" in spec:
            guests = spec["guests"]
        if "builds" in spec:
            builds = spec["builds"]

    cand_label = f"{candidates_count} candidate" if candidates_count == 1 else f"{candidates_count} candidates"
    build_label = f"{builds} build" if builds == 1 else f"{builds} builds"
    return f"{cand_label} · {guests} guests / {build_label}"


def resolve_metadata_bar(page, spec=None, camp_dir=None):
    """Render unified bottom bar:
    <harness> (<model>) · line: <line> · base <short-sha> · <N> candidate · <G> guests / <B> build
    Never show hostnames like hurricpc or protocol jargon like rev7.
    """
    name = published_name(page)
    harness_model = resolve_harness_model(name, spec, camp_dir)
    line = resolve_line(page, spec, camp_dir)
    line = re.sub(r"\bhurricpc(-wsl)?\b", "QEMU TCG", line, flags=re.I)
    base = resolve_base_sha(page, spec, camp_dir)
    scale_budget = resolve_scale_and_budget(page, spec, camp_dir)
    meta = f"{harness_model} · line: {line} · base {base} · {scale_budget}"
    meta = re.sub(r"\bhurricpc(-wsl)?\b", "QEMU TCG", meta, flags=re.I)
    meta = re.sub(r"\b(rev\s*[0-9]+|protocol\s+rev\s*[0-9]+)\b", "", meta, flags=re.I)
    meta = re.sub(r"\s+·\s+·\s+", " · ", meta)
    return meta


def build_site(campaigns, site):
    raw_pages = list(campaigns.glob("*/report/**/explainer.html"))

    # Group by campaign folder so a campaign never generates duplicate cards on the homepage.
    campaign_groups = {}
    for page in raw_pages:
        camp_dir = next((p for p in page.parents if p.parent == campaigns), None)
        camp_key = camp_dir if camp_dir else page.parent
        campaign_groups.setdefault(camp_key, []).append(page)

    page_items = []
    sources = {}

    for camp_dir, pages in campaign_groups.items():
        candidates = []
        for page in pages:
            name = published_name(page)
            spec_path = page.with_suffix(".json")
            spec = json.loads(spec_path.read_text(encoding="utf-8")) if spec_path.exists() else {}
            date_str = resolve_campaign_date(page, spec, camp_dir)
            sort_key = get_sort_key(page, spec, camp_dir)
            is_nested = (page.parent.name != "report")
            candidates.append({
                "page": page,
                "name": name,
                "spec": spec,
                "date": date_str,
                "sort_key": sort_key,
                "is_nested": is_nested,
                "camp_dir": camp_dir,
            })

        # Sort candidates within this campaign: prefer nested (dated) over root, then newest sort_key
        candidates.sort(key=lambda c: (c["is_nested"], c["sort_key"]), reverse=True)
        chosen = candidates[0]

        name = chosen["name"]
        if name in sources:
            raise SystemExit(f"duplicate published name {name!r}: {sources[name]} and {chosen['page']}")
        sources[name] = chosen["page"]
        page_items.append(chosen)

    # Sort all campaigns newest first
    page_items.sort(key=lambda item: item["sort_key"], reverse=True)

    site.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in page_items:
        page = item["page"]
        name = item["name"]
        spec = item["spec"]
        date_str = item["date"]
        camp_dir = item["camp_dir"]

        (site / name).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(page, site / name / "index.html")
        if camp_dir and camp_dir.name != name:
            (site / camp_dir.name).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(page, site / camp_dir.name / "index.html")
        undated_alias = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", name)
        if undated_alias != name and not (site / undated_alias / "index.html").exists():
            (site / undated_alias).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(page, site / undated_alias / "index.html")

        verdict = spec.get("verdict", {})
        var, icon, label = STATUS.get(verdict.get("status"), ("--muted", "·", "Report"))
        date_html = (f'<span style="font-size:13px;color:var(--muted);font-weight:600">'
                     f'{html.escape(date_str)}</span>') if date_str else ""
        meta_bar = resolve_metadata_bar(page, spec, camp_dir)

        rows.append(
            f'<a class="card" href="{html.escape(name)}/" style="display:block;color:inherit;text-decoration:none">'
            f'<div style="display:flex;justify-content:space-between;align-items:center">'
            f'<span class="badge"><i class="dot" style="background:var({var})"></i>{icon} {label}</span>'
            f'{date_html}</div>'
            f'<p class="chart-title" style="margin:10px 0 2px">{html.escape(spec.get("title", name))}</p>'
            f'<p class="lead" style="margin:0">{html.escape(verdict.get("headline", ""))}</p>'
            f'<p class="lead" style="margin:4px 0 0;font-size:13px;color:var(--muted)">{html.escape(meta_bar)}</p></a>')

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
