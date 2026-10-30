#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Render a campaign explainer spec (JSON) into one self-contained HTML page.

    python3 build_page.py spec.json out.html

The page has no external resources: inline CSS, inline SVG, a few lines of
inline JS for tooltips and the theme toggle. Every chart also gets a table
view. Prose longer than the budget is reported on stderr and fails the build.
"""
import html
import json
import math
import sys

MAX_TEXT_WORDS = 40      # any single text field
MAX_PAGE_WORDS = 700     # all prose on the page, excluding tables and diffs
# Violet / teal / brick: validated all-pairs (CVD, normal-vision, contrast) on
# #fbf8f3 (light) and #1c1a17 (dark) with the dataviz palette validator.
SERIES = 3

W, PAD_L, PAD_R, PAD_T, PAD_B = 760, 150, 24, 16, 40

CSS = """
.viz-root{color-scheme:light;--page:#f4f0e8;--surface-1:#fbf8f3;--ink:#1f1b16;--ink-2:#5b5348;
--muted:#8c8274;--grid:#e8e1d4;--axis:#cfc6b6;--ring:rgba(31,27,22,.10);
--series-1:#6a4fd1;--series-2:#00978c;--series-3:#d0572b;
--good:#0ca30c;--warning:#fab219;--serious:#ec835a;--critical:#d03b3b;
--add:#e1f1ec;--del:#f8e3da;--focus:#e6e0fa}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])) .viz-root{color-scheme:dark;
--page:#12110f;--surface-1:#1c1a17;--ink:#f2ede4;--ink-2:#c9c0b2;--muted:#8c8274;--grid:#2d2a25;--axis:#3d3932;
--ring:rgba(255,250,240,.10);--series-1:#8a76ee;--series-2:#14a596;--series-3:#d9693a;
--add:#15302c;--del:#3b231a;--focus:#2e2754}}
:root[data-theme="dark"] .viz-root{color-scheme:dark;--page:#12110f;--surface-1:#1c1a17;--ink:#f2ede4;
--ink-2:#c9c0b2;--muted:#8c8274;--grid:#2d2a25;--axis:#3d3932;--ring:rgba(255,250,240,.10);--series-1:#8a76ee;
--series-2:#14a596;--series-3:#d9693a;--add:#15302c;--del:#3b231a;--focus:#2e2754}
*{box-sizing:border-box}
body{margin:0}
.viz-root{background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;min-height:100vh}
main{max-width:860px;margin:0 auto;padding:32px 20px 64px}
header h1{font-size:26px;margin:0 0 4px}
header p{color:var(--ink-2);margin:0}
nav{display:flex;flex-wrap:wrap;gap:8px 16px;margin:16px 0 0;font-size:13px}
nav a{color:var(--ink-2)}
.toggle{float:right;font:inherit;font-size:13px;background:var(--surface-1);color:var(--ink-2);
border:1px solid var(--ring);border-radius:6px;padding:4px 10px;cursor:pointer}
.card{background:var(--surface-1);border:1px solid var(--ring);border-radius:12px;padding:20px;margin:16px 0}
section>h2{font-size:19px;margin:36px 0 4px}
.lead{color:var(--ink-2);margin:0 0 8px}
.chart-title{font-weight:600;margin:0 0 8px}
.verdict{display:flex;gap:12px;align-items:center;font-size:20px;font-weight:600}
.badge{display:inline-flex;white-space:nowrap;flex-shrink:0;align-items:center;gap:6px;font-size:13px;font-weight:600;
padding:3px 10px;border-radius:999px;border:1px solid var(--ring);color:var(--ink)}
.dot{width:10px;height:10px;border-radius:50%;display:inline-block}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-top:16px}
.tile .label{color:var(--ink-2);font-size:13px}
.tile .value{font-size:28px;font-weight:600}
.tile .note{color:var(--muted);font-size:12px}
.legend{display:flex;gap:16px;font-size:13px;color:var(--ink-2);margin:0 0 6px}
.legend span{display:inline-flex;align-items:center;gap:6px}
svg{display:block;width:100%;height:auto;overflow:visible}
svg text{fill:var(--ink-2);font:12px system-ui,-apple-system,"Segoe UI",sans-serif}
svg .axis-label{fill:var(--muted)}
.hit{cursor:default}
.hit:hover>.mark,.hit:focus>.mark{stroke:var(--ink);stroke-width:2}
.hit:focus{outline:none}
details{margin-top:10px;font-size:13px;color:var(--ink-2)}
summary{cursor:pointer}
table{border-collapse:collapse;width:100%;font-size:13px;margin-top:6px}
th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--grid)}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.check{list-style:none;padding:0;margin:0}
.check li{display:grid;grid-template-columns:110px 1fr;gap:12px;padding:8px 0;border-bottom:1px solid var(--grid)}
.check .ev{color:var(--muted);font-size:12px}
pre.diff{font:12px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace;overflow-x:auto;margin:0;
border-radius:8px;border:1px solid var(--ring)}
pre.diff span{display:block;padding:0 10px;white-space:pre}
pre.diff .a{background:var(--add)}pre.diff .d{background:var(--del)}pre.diff .h{color:var(--muted)}
.callout{border-left:3px solid var(--series-1);padding:10px 14px;background:var(--surface-1);
border-radius:0 8px 8px 0;margin:12px 0}
.tip{position:fixed;pointer-events:none;background:var(--surface-1);color:var(--ink);border:1px solid var(--ring);
border-radius:8px;padding:6px 10px;font-size:12px;box-shadow:0 4px 16px rgba(0,0,0,.12);display:none;max-width:280px}
.tip b{display:block;font-size:14px}
"""

JS = """
(function(){var t=document.createElement('div');t.className='tip';document.querySelector('.viz-root').appendChild(t);
function show(e,el){t.textContent='';var b=document.createElement('b');b.textContent=el.dataset.v;t.appendChild(b);
var s=document.createElement('span');s.textContent=el.dataset.l;t.appendChild(s);t.style.display='block';
var r=el.getBoundingClientRect(),x=e&&e.clientX?e.clientX:r.left+r.width/2,y=e&&e.clientY?e.clientY:r.top;
t.style.left=Math.min(x+12,innerWidth-t.offsetWidth-8)+'px';t.style.top=Math.max(8,y-t.offsetHeight-12)+'px'}
document.querySelectorAll('.hit').forEach(function(el){el.addEventListener('pointermove',function(e){show(e,el)});
el.addEventListener('focus',function(){show(null,el)});['pointerleave','blur'].forEach(function(k){
el.addEventListener(k,function(){t.style.display='none'})})});
var btn=document.querySelector('.toggle');btn.addEventListener('click',function(){var d=document.documentElement;
var dark=d.dataset.theme?d.dataset.theme==='dark':matchMedia('(prefers-color-scheme: dark)').matches;
d.dataset.theme=dark?'light':'dark'})})();
"""

STATUS = {  # role -> (css var, icon, label)
    "accepted": ("--good", "✓", "Accepted"),
    "rejected": ("--critical", "✕", "Rejected"),
    "inconclusive": ("--warning", "?", "Inconclusive"),
    "needs-review": ("--serious", "!", "Needs review"),
    "pass": ("--good", "✓", "Pass"),
    "fail": ("--critical", "✕", "Fail"),
    "missing": ("--serious", "–", "Missing"),
    "warn": ("--warning", "!", "Check"),
}

TONES = {"default": ("--surface-1", "--axis"), "focus": ("--focus", "--series-1"),
         "bad": ("--del", "--critical"), "good": ("--add", "--good"), "muted": ("--page", "--grid")}


class Budget:
    def __init__(self):
        self.words = 0
        self.errors = []

    def text(self, value, where):
        value = value or ""
        n = len(value.split())
        self.words += n
        if n > MAX_TEXT_WORDS:
            self.errors.append(f"{where}: {n} words (max {MAX_TEXT_WORDS}); split it or move it to a table")
        return html.escape(value)


def esc(value):
    return html.escape(str(value))


def fmt(v):
    if isinstance(v, float) and not v.is_integer():
        return f"{v:,.1f}"
    return f"{int(v):,}"


def ticks(lo, hi, n=5):
    span = hi - lo or 1
    step = 10 ** math.floor(math.log10(span / n))
    for m in (1, 2, 5, 10):
        if span / (step * m) <= n:
            step *= m
            break
    start = math.floor(lo / step) * step
    out, v = [], start
    while v <= hi + step * 1e-9:
        out.append(round(v, 10))
        v += step
    return out


def series_index(spec_series, name):
    if name not in spec_series:
        raise ValueError("unknown series: " + name)
    return spec_series.index(name) + 1


def legend(names, shape="dot"):
    if len(names) < 2:
        return ""
    items = []
    for i, name in enumerate(names, 1):
        mark = (f'<i class="dot" style="background:var(--series-{i})"></i>' if shape == "dot" else
                f'<i style="width:14px;height:2px;background:var(--series-{i});display:inline-block"></i>')
        items.append(f"<span>{mark}{esc(name)}</span>")
    return f'<div class="legend">{"".join(items)}</div>'


def table_view(columns, rows, numeric=()):
    head = "".join(f'<th class="{"num" if i in numeric else ""}">{esc(c)}</th>' for i, c in enumerate(columns))
    body = "".join("<tr>" + "".join(f'<td class="{"num" if i in numeric else ""}">{esc(c)}</td>'
                                    for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def details(columns, rows, numeric=()):
    return f"<details><summary>Table view</summary>{table_view(columns, rows, numeric)}</details>"


def x_axis(lo, hi, x, y0, height, label):
    out = []
    for t in ticks(lo, hi):
        if lo <= t <= hi:
            px = x(t)
            out.append(f'<line x1="{px:.1f}" x2="{px:.1f}" y1="{PAD_T}" y2="{y0}" stroke="var(--grid)"/>'
                       f'<text x="{px:.1f}" y="{y0 + 16}" text-anchor="middle">{fmt(t)}</text>')
    out.append(f'<line x1="{PAD_L}" x2="{W - PAD_R}" y1="{y0}" y2="{y0}" stroke="var(--axis)"/>')
    out.append(f'<text class="axis-label" x="{W - PAD_R}" y="{height - 4}" text-anchor="end">{esc(label)}</text>')
    return out


def strip(block, budget):
    """One row per group, one dot per observation: shows regimes and spread."""
    names = block.get("series", [])[:SERIES] or [""]
    groups = block["groups"]
    values = [p["value"] for p in block["points"]]
    lo, hi = min(0, min(values)), max(values) * 1.05
    row_h = 34
    height = PAD_T + row_h * len(groups) + PAD_B
    y0 = PAD_T + row_h * len(groups)
    x = lambda v: PAD_L + (v - lo) / (hi - lo) * (W - PAD_L - PAD_R)
    out = x_axis(lo, hi, x, y0, height, block.get("x_label", ""))
    offsets = {n: (i - (len(names) - 1) / 2) * 9 for i, n in enumerate(names)}
    for gi, g in enumerate(groups):
        cy = PAD_T + row_h * gi + row_h / 2
        out.append(f'<text x="{PAD_L - 10}" y="{cy + 4:.1f}" text-anchor="end">{esc(g)}</text>')
    rows = []
    # Identical values in one row would hide each other: draw one dot and label the count.
    buckets = {}
    for p in block["points"]:
        s = p.get("series", names[0])
        key = (p["group"], s, round(x(p["value"]) / 6))
        buckets.setdefault(key, []).append(p)
        rows.append([p["group"], s, fmt(p["value"]), p.get("tip", "")])
    row_xs = {}
    for (group, s, _), pts in buckets.items():
        row_xs.setdefault((group, s), []).append(x(pts[0]["value"]))
    for (group, s, _), pts in buckets.items():
        i = series_index(names, s) if s else 1
        cx = x(pts[0]["value"])
        near = [v for v in row_xs[(group, s)] if v != cx and abs(v - cx) < 32]
        cy = PAD_T + row_h * groups.index(group) + row_h / 2 + offsets.get(s, 0)
        values = sorted({fmt(p["value"]) for p in pts})
        tip = f"{group} · {s} · {len(pts)} run(s)" + "".join(f" · {p.get('tip', '')}" for p in pts[:4])
        out.append(f'<g class="hit" tabindex="0" data-v="{esc(" / ".join(values))}" data-l="{esc(tip)}">'
                   f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="12" fill="transparent"/>'
                   f'<circle class="mark" cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="var(--series-{i})" '
                   f'stroke="var(--surface-1)" stroke-width="2"/></g>')
        if len(pts) > 1:  # count label right of the dot, else left, else above
            if not any(v > cx for v in near):
                pos = f'x="{cx + 9:.1f}" y="{cy + 4:.1f}"'
            elif not any(v < cx for v in near):
                pos = f'x="{cx - 9:.1f}" y="{cy + 4:.1f}" text-anchor="end"'
            else:
                pos = f'x="{cx:.1f}" y="{cy - 9:.1f}" text-anchor="middle"'
            out.append(f'<text {pos}>×{len(pts)}</text>')
    svg = f'<svg viewBox="0 0 {W} {height}" role="img" aria-label="{esc(block["takeaway"])}">{"".join(out)}</svg>'
    return chart_card(block, budget, legend(names) + svg, details(["Group", "Series", "Value", "Note"], rows, (2,)))


def lines(block, budget):
    """Ordered phases on x, one line per observation, colored by series."""
    names = block.get("series", [])[:SERIES] or [""]
    xs = block["x"]
    allv = [v for ln in block["lines"] for v in ln["values"]]
    lo, hi = min(0, min(allv)), max(allv) * 1.08
    height = 280
    y0 = height - PAD_B
    left = 60
    xp = lambda i: left + i * (W - left - PAD_R) / max(1, len(xs) - 1)
    yp = lambda v: y0 - (v - lo) / (hi - lo) * (y0 - PAD_T)
    out = []
    for t in ticks(lo, hi):
        if lo <= t <= hi:
            out.append(f'<line x1="{left}" x2="{W - PAD_R}" y1="{yp(t):.1f}" y2="{yp(t):.1f}" stroke="var(--grid)"/>'
                       f'<text x="{left - 8}" y="{yp(t) + 4:.1f}" text-anchor="end">{fmt(t)}</text>')
    for i, name in enumerate(xs):
        out.append(f'<text x="{xp(i):.1f}" y="{y0 + 18}" text-anchor="middle">{esc(name)}</text>')
    out.append(f'<line x1="{left}" x2="{W - PAD_R}" y1="{y0}" y2="{y0}" stroke="var(--axis)"/>')
    out.append(f'<text class="axis-label" x="{left}" y="{PAD_T - 4}">{esc(block.get("y_label", ""))}</text>')
    rows = []
    # Later series first, so the first series is drawn on top and never buried.
    for ln in sorted(block["lines"], key=lambda ln: -names.index(ln.get("series", names[0]))):
        s = ln.get("series", names[0])
        i = series_index(names, s) if s else 1
        pts = " ".join(f"{xp(k):.1f},{yp(v):.1f}" for k, v in enumerate(ln["values"]))
        out.append(f'<polyline points="{pts}" fill="none" stroke="var(--series-{i})" stroke-width="2" '
                   f'stroke-opacity=".7" stroke-linejoin="round" stroke-linecap="round"/>')
        for k, v in enumerate(ln["values"]):
            out.append(f'<g class="hit" tabindex="-1" data-v="{esc(fmt(v))}" data-l="{esc(ln["label"])} · {esc(xs[k])}">'
                       f'<circle cx="{xp(k):.1f}" cy="{yp(v):.1f}" r="12" fill="transparent"/>'
                       f'<circle class="mark" cx="{xp(k):.1f}" cy="{yp(v):.1f}" r="4" fill="var(--series-{i})" '
                       f'stroke="var(--surface-1)" stroke-width="2"/></g>')
        rows.append([ln["label"], s] + [fmt(v) for v in ln["values"]])
    svg = f'<svg viewBox="0 0 {W} {height}" role="img" aria-label="{esc(block["takeaway"])}">{"".join(out)}</svg>'
    cols = ["Line", "Series"] + xs
    return chart_card(block, budget, legend(names, "line") + svg,
                      details(cols, rows, tuple(range(2, len(cols)))))


def bars(block, budget):
    """Grouped columns: categories on x, one column per series."""
    names = block["series"][:SERIES]
    cats = block["categories"]
    allv = [v for s in names for v in block["values"][s]]
    hi = max(allv) * 1.12 or 1
    height = 260
    y0 = height - PAD_B
    left = 60
    band = (W - left - PAD_R) / len(cats)
    bw = min(24, band * 0.7 / len(names))
    yp = lambda v: y0 - v / hi * (y0 - PAD_T)
    out = []
    for t in ticks(0, hi):
        if t <= hi:
            out.append(f'<line x1="{left}" x2="{W - PAD_R}" y1="{yp(t):.1f}" y2="{yp(t):.1f}" stroke="var(--grid)"/>'
                       f'<text x="{left - 8}" y="{yp(t) + 4:.1f}" text-anchor="end">{fmt(t)}</text>')
    rows = []
    for ci, c in enumerate(cats):
        cx = left + band * ci + band / 2
        out.append(f'<text x="{cx:.1f}" y="{y0 + 18}" text-anchor="middle">{esc(c)}</text>')
        start = cx - (bw + 2) * len(names) / 2
        for si, s in enumerate(names, 1):
            v = block["values"][s][ci]
            bx, top = start + (bw + 2) * (si - 1), yp(v)
            h = y0 - top
            r = min(4, h)
            path = (f"M{bx:.1f},{y0} V{top + r:.1f} Q{bx:.1f},{top:.1f} {bx + r:.1f},{top:.1f} "
                    f"H{bx + bw - r:.1f} Q{bx + bw:.1f},{top:.1f} {bx + bw:.1f},{top + r:.1f} V{y0} Z")
            out.append(f'<g class="hit" tabindex="0" data-v="{esc(fmt(v))}" data-l="{esc(c)} · {esc(s)}">'
                       f'<rect x="{bx - 2:.1f}" y="{PAD_T}" width="{bw + 4:.1f}" height="{y0 - PAD_T}" fill="transparent"/>'
                       f'<path class="mark" d="{path}" fill="var(--series-{si})"/></g>')
        rows.append([c] + [fmt(block["values"][s][ci]) for s in names])
    out.append(f'<line x1="{left}" x2="{W - PAD_R}" y1="{y0}" y2="{y0}" stroke="var(--axis)"/>')
    out.append(f'<text class="axis-label" x="{left}" y="{PAD_T - 4}">{esc(block.get("y_label", ""))}</text>')
    svg = f'<svg viewBox="0 0 {W} {height}" role="img" aria-label="{esc(block["takeaway"])}">{"".join(out)}</svg>'
    return chart_card(block, budget, legend(names) + svg,
                      details(["Category"] + names, rows, tuple(range(1, len(names) + 1))))


def flow(block, budget):
    """Boxes on a (col,row) grid joined by arrows; tone marks where the story is."""
    nodes = {n["id"]: n for n in block["nodes"]}
    cols = max(n["col"] for n in nodes.values()) + 1
    nrows = max(n["row"] for n in nodes.values()) + 1
    bw, bh, gap_x, gap_y = 150, 58, 0, 26
    gap_x = (W - 20 - cols * bw) / max(1, cols - 1) if cols > 1 else 0
    height = nrows * bh + (nrows - 1) * gap_y + 20
    pos = lambda n: (10 + n["col"] * (bw + gap_x), 10 + n["row"] * (bh + gap_y))
    out = ['<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
           'orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="var(--muted)"/></marker></defs>']
    for e in block.get("edges", []):
        a, b = nodes[e["from"]], nodes[e["to"]]
        (ax, ay), (bx, by) = pos(a), pos(b)
        if a["row"] == b["row"]:
            x1, y1, x2, y2 = ax + bw, ay + bh / 2, bx, by + bh / 2
            if bx < ax:
                x1, x2 = ax, bx + bw
            d = f"M{x1:.1f},{y1:.1f} H{x2:.1f}"
        elif a["col"] == b["col"]:
            x1, y1 = ax + bw / 2, ay + (bh if by > ay else 0)
            x2, y2 = bx + bw / 2, by + (0 if by > ay else bh)
            d = f"M{x1:.1f},{y1:.1f} V{y2:.1f}"
        else:  # elbow: down out of the source, then across into the target's side
            x1, y1 = ax + bw / 2, ay + (bh if by > ay else 0)
            x2, y2 = (bx if bx > ax else bx + bw), by + bh / 2
            d = f"M{x1:.1f},{y1:.1f} V{y2:.1f} H{x2:.1f}"
        out.append(f'<path d="{d}" fill="none" stroke="var(--muted)" stroke-width="1.5" marker-end="url(#arr)"/>')
        if e.get("label"):
            out.append(f'<text x="{(x1 + x2) / 2:.1f}" y="{(y1 + y2) / 2 - 6:.1f}" text-anchor="middle" '
                       f'class="axis-label">{budget.text(e["label"], "edge label")}</text>')
    for n in nodes.values():
        x, y = pos(n)
        fill, stroke = TONES[n.get("tone", "default")]
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw}" height="{bh}" rx="10" fill="var({fill})" '
                   f'stroke="var({stroke})" stroke-width="1.5"/>')
        label = budget.text(n["label"], "flow node")
        out.append(f'<text x="{x + bw / 2:.1f}" y="{y + (24 if n.get("sub") else 33):.1f}" text-anchor="middle" '
                   f'style="fill:var(--ink);font-weight:600">{label}</text>')
        if n.get("sub"):
            out.append(f'<text x="{x + bw / 2:.1f}" y="{y + 42:.1f}" text-anchor="middle">'
                       f'{budget.text(n["sub"], "flow node")}</text>')
    svg = f'<svg viewBox="0 0 {W} {height}" role="img" aria-label="{esc(block["takeaway"])}">{"".join(out)}</svg>'
    return chart_card(block, budget, svg, "")


def chart_card(block, budget, body, table):
    title = budget.text(block["takeaway"], "takeaway")
    note = f'<p class="lead">{budget.text(block["note"], "note")}</p>' if block.get("note") else ""
    return f'<div class="card"><p class="chart-title">{title}</p>{body}{note}{table}</div>'


def badge(status):
    var, icon, label = STATUS[status]
    return f'<span class="badge"><i class="dot" style="background:var({var})"></i>{icon} {label}</span>'


def checklist(block, budget):
    items = "".join(f'<li><div>{badge(i["status"])}</div><div>{budget.text(i["label"], "check item")}'
                    f'<div class="ev">{esc(i.get("evidence", ""))}</div></div></li>' for i in block["items"])
    return f'<div class="card"><p class="chart-title">{budget.text(block["takeaway"], "takeaway")}</p>' \
           f'<ul class="check">{items}</ul></div>'


def diff(block, budget):
    spans = []
    for line in block["patch"].splitlines():
        cls = "a" if line.startswith("+") and not line.startswith("+++") else \
              "d" if line.startswith("-") and not line.startswith("---") else \
              "h" if line.startswith(("@@", "diff", "index", "---", "+++")) else ""
        spans.append(f'<span class="{cls}">{esc(line) or " "}</span>')
    return f'<div class="card"><p class="chart-title">{budget.text(block["takeaway"], "takeaway")}</p>' \
           f'<pre class="diff">{"".join(spans)}</pre></div>'


def table(block, budget):
    return f'<div class="card"><p class="chart-title">{budget.text(block["takeaway"], "takeaway")}</p>' \
           f'{table_view(block["columns"], block["rows"], tuple(block.get("numeric", [])))}</div>'


def note(block, budget):
    return f'<div class="callout">{budget.text(block["text"], "note")}</div>'


BLOCKS = {"strip": strip, "lines": lines, "bars": bars, "flow": flow,
          "checklist": checklist, "diff": diff, "table": table, "note": note}


def build(spec):
    budget = Budget()
    v = spec["verdict"]
    tiles = "".join(f'<div class="tile"><div class="label">{budget.text(t["label"], "tile")}</div>'
                    f'<div class="value">{esc(t["value"])}</div>'
                    f'<div class="note">{budget.text(t.get("note", ""), "tile")}</div></div>'
                    for t in v.get("tiles", [])[:4])
    parts = [f'<div class="card"><div class="verdict">{badge(v["status"])}'
             f'<span>{budget.text(v["headline"], "headline")}</span></div><div class="tiles">{tiles}</div></div>']
    toc = []
    for s in spec["sections"]:
        toc.append(f'<a href="#{esc(s["id"])}">{esc(s["title"])}</a>')
        lead = f'<p class="lead">{budget.text(s["lead"], "section lead")}</p>' if s.get("lead") else ""
        blocks = "".join(BLOCKS[b["type"]](b, budget) for b in s["blocks"])
        parts.append(f'<section id="{esc(s["id"])}"><h2>{esc(s["title"])}</h2>{lead}{blocks}</section>')
    if budget.words > MAX_PAGE_WORDS:
        budget.errors.append(f"page prose: {budget.words} words (max {MAX_PAGE_WORDS})")
    page = (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(spec["title"])}</title><style>{CSS}</style></head>'
            f'<body><div class="viz-root"><main><header><button class="toggle" type="button">Theme</button>'
            f'<h1>{esc(spec["title"])}</h1><p>{esc(spec.get("subtitle", ""))}</p>'
            f'<nav>{"".join(toc)}</nav></header>{"".join(parts)}</main></div><script>{JS}</script></body></html>')
    return page, budget


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    spec = json.loads(open(sys.argv[1], encoding="utf-8").read())
    page, budget = build(spec)
    for err in budget.errors:
        print("TEXT BUDGET: " + err, file=sys.stderr)
    if budget.errors:
        raise SystemExit(1)
    if "http://" in page.split("<body")[0] or "https://" in page.split("<body")[0]:
        raise SystemExit("external resource in <head>")
    open(sys.argv[2], "w", encoding="utf-8").write(page)
    print(f"wrote {sys.argv[2]}: {budget.words} prose words")


if __name__ == "__main__":
    main()
