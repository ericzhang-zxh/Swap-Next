#!/usr/bin/env python3
"""English build of the rev7 campaign explainer (summary + round 1-3 pages).

Single reproducible generator, per .agents/skills/explaining-campaign-results/SKILL.md:
  1. extraction: derives explainer.json / round1.json / round2.json / round3.json / summary.json from
     evidence at bundle commit 729be1c (git show, read-only) plus the read-only run directory;
  2. build: the repo's unmodified build_page.py (copied from 729be1c, sha256 a7156c25...);
  3. post-processing in this generator (SKILL step 3): A/A guard + no-change reference lines on strip
     charts, a three-level "scene" block (SKILL L49-67), audit sections wrapped in closed <details>,
     nav cross-links, a visible-text check (<= MAX_PAGE_WORDS outside closed details and SVG), and
     a host-path / external-link check;
  4. summary.html is a byte copy of explainer.html.
Derived from ../v2/gen_v2.py + ../v2/render_zh.py without the Chinese layer. Run:
  PYTHONDONTWRITEBYTECODE=1 python3 gen_v2_en.py
"""
import sys
sys.dont_write_bytecode = True
import html, re, sys, json, subprocess
from html.parser import HTMLParser
sys.path.insert(0, __import__("os").path.dirname(__file__))
import build_page as bp

CJK = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]")

def _words(value):
    cjk = len(CJK.findall(value))
    rest = CJK.sub(" ", value)
    return len(rest.split()) + (cjk + 1) // 2

def strip(block, budget):
    """bp.strip (vendored, unchanged logic) plus optional dashed reference lines in "refs"."""
    esc, fmt, PAD_L, PAD_T, PAD_B, W, PAD_R = bp.esc, bp.fmt, bp.PAD_L, bp.PAD_T, bp.PAD_B, bp.W, bp.PAD_R
    if block.get("refs"):
        PAD_T += 14  # room for reference-line labels above the rows
    names = block.get("series", [])[:bp.SERIES] or [""]
    groups = block["groups"]
    refs = block.get("refs") or []
    values = [p["value"] for p in block["points"]] + [r["value"] for r in refs]
    lo, hi = min(0, min(values)), max(values) * 1.05
    row_h = 34
    height = PAD_T + row_h * len(groups) + PAD_B
    y0 = PAD_T + row_h * len(groups)
    x = lambda v: PAD_L + (v - lo) / (hi - lo) * (W - PAD_L - PAD_R)
    out = bp.x_axis(lo, hi, x, y0, height, block.get("x_label", ""))
    offsets = {n: (i - (len(names) - 1) / 2) * 9 for i, n in enumerate(names)}
    for gi, g in enumerate(groups):
        cy = PAD_T + row_h * gi + row_h / 2
        out.append(f'<text x="{PAD_L - 10}" y="{cy + 4:.1f}" text-anchor="end">{esc(g)}</text>')
    for r in refs:
        rx = x(r["value"])
        col = "var(--muted)" if r.get("tone") == "muted" else "var(--critical)"
        dash = "" if r.get("tone") == "muted" else ' stroke-dasharray="5 4"'
        anchor = "start" if r.get("tone") == "muted" else "end"
        dx = 4 if anchor == "start" else -4
        out.append(f'<line x1="{rx:.1f}" x2="{rx:.1f}" y1="{PAD_T}" y2="{y0}" stroke="{col}"{dash} stroke-width="1.5"/>'
                   f'<text x="{rx + dx:.1f}" y="{PAD_T - 3}" text-anchor="{anchor}" style="fill:{col};font-size:11px">'
                   f'{esc(r["label"])} {fmt(r["value"]) if r["value"] >= 10 else r["value"]}</text>')
    rows = []
    buckets = {}
    for p in block["points"]:
        s_ = p.get("series", names[0])
        key = (p["group"], s_, round(x(p["value"]) / 6))
        buckets.setdefault(key, []).append(p)
        rows.append([p["group"], s_, f'{p["value"]:.3f}' if p["value"] < 10 else fmt(p["value"]), p.get("tip", "")])
    row_xs = {}
    for (group, s_, _), pts in buckets.items():
        row_xs.setdefault((group, s_), []).append(x(pts[0]["value"]))
    for (group, s_, _), pts in buckets.items():
        i = bp.series_index(names, s_) if s_ else 1
        cx = x(pts[0]["value"])
        near = [v for v in row_xs[(group, s_)] if v != cx and abs(v - cx) < 32]
        cy = PAD_T + row_h * groups.index(group) + row_h / 2 + offsets.get(s_, 0)
        vals = sorted({(f'{p["value"]:.3f}' if p["value"] < 10 else fmt(p["value"])) for p in pts})
        tip = f"{group} · {s_} · {len(pts)} run(s)" + "".join(f" · {p.get('tip', '')}" for p in pts[:4])
        out.append(f'<g class="hit" tabindex="0" data-v="{esc(" / ".join(vals))}" data-l="{esc(tip)}">'
                   f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="12" fill="transparent"/>'
                   f'<circle class="mark" cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="var(--series-{i})" '
                   f'stroke="var(--surface-1)" stroke-width="2"/></g>')
        if len(pts) > 1:
            if not any(v > cx for v in near):
                pos = f'x="{cx + 9:.1f}" y="{cy + 4:.1f}"'
            elif not any(v < cx for v in near):
                pos = f'x="{cx - 9:.1f}" y="{cy + 4:.1f}" text-anchor="end"'
            else:
                pos = f'x="{cx:.1f}" y="{cy - 9:.1f}" text-anchor="middle"'
            out.append(f'<text {pos}>×{len(pts)}</text>')
    svg = f'<svg viewBox="0 0 {W} {height}" role="img" aria-label="{esc(block["takeaway"])}">{"".join(out)}</svg>'
    return bp.chart_card(block, budget, bp.legend(names) + svg,
                         bp.details(["Group", "Series", "Value", "Note"], rows, (2,)))
bp.strip = strip
bp.BLOCKS["strip"] = strip


# ---------------- scene block (three zoom levels, SKILL L49-67) ----------------
BUNDLE, BUNDLE_REV = "/workspace/Swap-Next-bundle", "729be1c"
PRECEDENT = "campaigns/xswap-swapin-2026-10-23/report/explainer.html"
def _story_css():
    src = subprocess.run(["git", "-C", BUNDLE, "show", f"{BUNDLE_REV}:{PRECEDENT}"], check=True,
                         capture_output=True, text=True).stdout
    return re.findall(r"<style>(.*?)</style>", src, re.S)[1]

EXTRA_CSS = """
details table,details pre.diff{display:block;max-width:100%;overflow-x:auto}
.card{min-width:0;overflow-wrap:anywhere}
.scene .pages{flex-wrap:wrap}
.zone-tag{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.05em;padding:1px 7px;border-radius:999px;margin-right:6px;border:1px solid currentColor}
.zone-tag.data{color:var(--ram)}.zone-tag.meta{color:var(--warm)}.zone-tag.ctl{color:var(--change)}
.scene .faded{opacity:.45}
"""

def _p(budget, text, where="scene"):
    return budget.text(text, where)

def scene(block, budget):
    """block: {"takeaway", "level": 1|2|3, ...}. Text fields are budgeted like any other prose."""
    t = lambda k: _p(budget, block.get(k, ""))
    lv = block["level"]
    head = (f'<div class="eyebrow">{bp.esc(block["eyebrow"])}</div><p class="chart-title" style="font-size:18px">{t("takeaway")}</p>'
            + (f'<p class="intro">{t("intro")}</p>' if block.get("intro") else ""))
    sch = f'<span class="schematic">{bp.esc(block.get("schematic", ""))}</span>'
    if lv == 1:
        z = block["zones"]
        body = (f'<div class="scene"><div class="scene-top"><span class="scene-label">{t("label")}</span>{sch}</div>'
                f'<div class="app-strip"><div class="app-icon" aria-hidden="true">▤</div><div><strong>{t("app")}</strong><small>{t("app_sub")}</small></div></div>'
                f'<div class="journey"><span>{t("down")}</span><span>{t("up")}</span></div>'
                f'<div class="memory-shelf"><div class="shelf-title"><strong>{t("ram")}</strong><small>{t("ram_sub")}</small></div><div class="ram-zones">'
                + "".join(f'<div class="ram-zone"><span class="zone-label">{_p(budget, zz["label"])}</span><div class="pages">'
                          + "".join(f'<span class="page-block {zz.get("kind", "")}">{bp.esc(p)}</span>' for p in zz["pages"])
                          + f'</div><p class="zone-caption">{_p(budget, zz["caption"])}</p></div>' for zz in z)
                + f'</div></div><div class="journey"><span>{t("down2")}</span><span>{t("up2")}</span></div>'
                f'<div class="disk-shelf"><div><strong>{t("disk")}</strong><p class="zone-caption">{t("disk_sub")}</p></div><div class="pages">'
                + "".join(f'<span class="page-block disk-page">{bp.esc(p)}</span>' for p in block["disk_pages"]) + '</div></div></div>')
    elif lv == 2:
        body = (f'<div class="scene"><div class="scene-top"><span class="scene-label">{t("label")}</span>{sch}</div>'
                f'<div class="request-path"><div class="request"><strong>{t("fault")}</strong><small>{t("fault_sub")}</small></div>'
                f'<span class="big-arrow" aria-hidden="true">→</span><div class="cache-outline"><span class="zone-label"><span class="zone-tag data">{bp.esc(block["tag_data"])}</span>{t("cache")}</span>'
                f'<div class="pages"><span class="page-block empty">A?</span><span class="page-block">X</span></div><p class="zone-caption">{t("cache_sub")}</p></div></div>'
                f'<p class="fork-caption">{t("miss")}</p>'
                f'<p class="zone-caption"><span class="zone-tag meta">{bp.esc(block["tag_meta"])}</span>{t("meta")}</p>'
                f'<div class="policy-box"><span class="change-pin">{bp.esc(block["pin"])}</span><div><strong><span class="zone-tag ctl">{bp.esc(block["tag_ctl"])}</span>{t("policy")}</strong><p>{t("policy_sub")}</p></div></div>'
                f'<div class="backend-pair">' + "".join(f'<div class="backend-card {b["cls"]}"><span class="schematic">{_p(budget, b["kicker"])}</span><strong>{_p(budget, b["title"])}</strong><p>{_p(budget, b["text"])}</p></div>' for b in block["backends"])
                + f'</div><p class="zone-caption faded">{t("unchanged")}</p></div>')
    else:
        cands = block["candidates"]
        cfg = json.dumps({c["key"]: {"label": c["label"], "disk": c["disk"], "zram": c["zram"]} for c in cands}, ensure_ascii=False)
        txt = json.dumps(block["strings"], ensure_ascii=False)
        for v in block["strings"].values():
            _p(budget, v)  # step-through strings are painted by script; budget them all (conservative)
        btn = "".join(f'<button type="button" data-cand="{c["key"]}" aria-pressed="{"true" if i == 1 else "false"}">{bp.esc(c["label"])}</button>' for i, c in enumerate(cands))
        bks = "".join(f'<button type="button" data-bk="{k}" aria-pressed="{"true" if i == 0 else "false"}">{bp.esc(l)}</button>' for i, (k, l) in enumerate(block["backends"]))
        body = (f'<div class="scene" id="s3"><div class="scene-top"><span class="scene-label">{t("label")}</span>{sch}</div>'
                f'<div class="demo-controls" role="group">{btn}</div><div class="demo-controls" role="group">{bks}</div>'
                f'<div class="step-caption" id="s3-caption" aria-live="polite"></div>'
                f'<div class="demo-grid"><div class="demo-card"><span class="eyebrow">{bp.esc(block["before"])}</span><div class="demo-pages" id="s3-before"></div><div class="demo-status" id="s3-bstat"></div></div>'
                f'<div class="demo-card after"><span class="eyebrow" id="s3-alabel"></span><div class="demo-pages" id="s3-after"></div><div class="demo-status" id="s3-astat"></div></div></div>'
                f'<div class="demo-footer"><div class="step-dots" aria-hidden="true"><span class="step-dot"></span><span class="step-dot"></span><span class="step-dot"></span><span class="step-dot"></span></div>'
                f'<div><button type="button" id="s3-reset">{bp.esc(block["strings"]["reset"])}</button> <button type="button" id="s3-next"></button></div></div>'
                f'<div class="tradeoff">{t("tradeoff")}</div><noscript><p>{t("static")}</p></noscript></div>'
                f'<script>(()=>{{const C={cfg},S={txt};let step=1,cand=Object.keys(C)[1],bk="disk";const $=i=>document.getElementById(i),P=["A","B","C"];'
                'const bl=(n,cur)=>P.map((p,i)=>`<span class="page-block ${i>=n?"empty ":""}${cur===i?"current":""}">${p}</span>`).join("");'
                'function r(){const ra=C[cand][bk],op=S[bk];$("s3-before").innerHTML=bl(step,step-1);$("s3-after").innerHTML=bl(ra&&step?3:step,step-1);'
                '$("s3-alabel").textContent=S.after+" · "+C[cand].label;$("s3-caption").textContent=step?S.req+P[step-1]:S.start;'
                '$("s3-bstat").innerHTML=step?"<strong>"+S.wait+op+"</strong>":S.none;'
                '$("s3-astat").innerHTML=!step?S.none:(!ra?"<strong>"+S.wait+op+"</strong>"+S.same:(step===1?"<strong>"+S.all3+"</strong>"+S[bk+"_cost"]:"<strong>"+S.hit+"</strong>"));'
                '$("s3-next").disabled=step===3;$("s3-next").textContent=step===3?S.done:S.next+P[step]+" →";'
                'document.querySelectorAll("#s3 .step-dot").forEach((x,i)=>x.classList.toggle("active",i===step));'
                'document.querySelectorAll("[data-cand]").forEach(x=>x.setAttribute("aria-pressed",x.dataset.cand===cand));'
                'document.querySelectorAll("[data-bk]").forEach(x=>x.setAttribute("aria-pressed",x.dataset.bk===bk));}'
                '$("s3-next").onclick=()=>{step=Math.min(3,step+1);r()};$("s3-reset").onclick=()=>{step=0;r()};'
                'document.querySelectorAll("[data-cand]").forEach(x=>x.onclick=()=>{cand=x.dataset.cand;r()});'
                'document.querySelectorAll("[data-bk]").forEach(x=>x.onclick=()=>{bk=x.dataset.bk;r()});r()})();</script>')
    return f'<div class="story">{head}{body}</div>'
bp.BLOCKS["scene"] = scene

# ---------------- visible-text check ----------------
class _Vis(HTMLParser):
    VOID = {"br", "img", "meta", "link", "input", "hr", "circle", "line", "rect", "path", "source"}
    def __init__(self):
        super().__init__(); self.stack = []; self.prose = 0; self.svg = 0; self.hidden = 0
    def handle_starttag(self, tag, attrs):
        if tag in self.VOID: return
        a = dict(attrs)
        self.stack.append((tag, "open" in a))
    def handle_startendtag(self, tag, attrs): pass
    def handle_endtag(self, tag):
        if tag in self.VOID: return
        while self.stack:
            t, _ = self.stack.pop()
            if t == tag: break
    def handle_data(self, d):
        tags = [t for t, _ in self.stack]
        if any(t in ("script", "style", "noscript", "title") for t in tags): return
        # inside a closed <details> but not in its <summary>: hidden on load
        for i, (t, op) in enumerate(self.stack):
            if t == "details" and not op and "summary" not in tags[i + 1:]:
                return
        n = _words(d)
        if "svg" in tags: self.svg += n
        else: self.prose += n

def visible_words(page):
    v = _Vis(); v.feed(page); return v.prose, v.svg

SCRIPT_RESERVE = 40


# ======================= evidence extraction =======================
import math, datetime, zoneinfo, statistics, pathlib, hashlib, shutil
REPO = "/workspace/Swap-Next-bundle"
REV = "729be1c"
CAMP = "campaigns/xswap-tcg-kbench-rev7-2026-10-29"
HERE = pathlib.Path(__file__).parent
TZ = zoneinfo.ZoneInfo("America/Los_Angeles")

def show(path):
    return subprocess.run(["git", "-C", REPO, "show", f"{REV}:{path}"], check=True,
                          capture_output=True, text=True).stdout
def J(path): return json.loads(show(path))
def ls(path):
    return subprocess.run(["git", "-C", REPO, "ls-tree", "--name-only", f"{REV}:{path}"], check=True,
                          capture_output=True, text=True).stdout.split()
def t(unix): return datetime.datetime.fromtimestamp(unix, TZ).strftime("%H:%M")

FULLREV = subprocess.run(["git", "-C", REPO, "rev-parse", REV], capture_output=True, text=True).stdout.strip()
LINK = f"github.com/ericzhang-zxh/Swap-Next/tree/{FULLREV[:12]}/{CAMP}"
def git(*a, ok=False):
    p = subprocess.run(["git", "-C", REPO, *a], capture_output=True, text=True)
    return p.returncode if ok else p.stdout.strip()
# Is the evidence commit on any remote branch? (pinned links only resolve after the bundle branch is pushed)
PUSHED = bool(git("branch", "-r", "--contains", FULLREV))
# Code provenance: tool commits named in the round-1 audit; checked against origin/main here, not copied.
TOOL_COMMITS = ["ab800d77", "9c1468ac", "87dc7357"]
MAIN = git("rev-parse", "--short=8", "origin/main")
UNMERGED = [c for c in TOOL_COMMITS if git("merge-base", "--is-ancestor", c, "origin/main", ok=True) == 1]
AGENTS = show("AGENTS.md").splitlines()
CAP_LINE = next(i + 1 for i, x in enumerate(AGENTS) if "Default campaign budget cap" in x)
CAP_AGENTS = int(re.search(r"(\d+) guest attempts", AGENTS[CAP_LINE - 1]).group(1))
# Run directory (read-only): the c1 disk base range written in LOG.md, and the cap history in GUEST-ACCOUNTING.md.
RUNDIR = pathlib.Path("/workspace/runs/grok-cloud-tcg-rev7-20261029")
LOG = (RUNDIR / "LOG.md").read_text().splitlines()
LOG27 = re.search(r"mean (\d+)-(\d+) us", LOG[26]).groups()
GA = (RUNDIR / "GUEST-ACCOUNTING.md").read_text().splitlines()
GA_LINE = next(i + 1 for i, x in enumerate(GA) if "cap " in x and "->" in x and "global" in x)
CAPS = [int(x) for x in re.search(r"cap (\d+) -> (\d+) -> (\d+)", GA[GA_LINE - 1]).groups()]
ARCH_LINE = next(i + 1 for i, x in enumerate(LOG) if "c1 worktree" in x and "c1 closed" in x)

L = J(f"{CAMP}/ledger/ledger.json")
row = {r["id"][:8]: r for r in L}
proto = J(f"{CAMP}/protocol.json")
policy = J(f"{CAMP}/policy.json")
budget = J(f"{CAMP}/ledger/budget.json")
calf = J(f"{CAMP}/ledger/calibration-fast.json")
calp = J(f"{CAMP}/ledger/calibration-probe.json")
cand = {c: J(f"{CAMP}/candidates/{c}.json") for c in ("v2-c1-xs-sync-ra", "v2-c1c-xs-ra-safe")}
patch = {c: show(f"{CAMP}/patches/{c}.patch") for c in cand}
resv = ls(f"{CAMP}/ledger/guest-reservations")

AA, C1P, C1F, C1CP, C1CF = row["e8b7a7e3"], row["3a554e3b"], row["68de12e0"], row["bc73887e"], row["66a07143"]
noise_log = calf["analysis"]["noise_log"]
METRICS = list(noise_log)
def guard(m): return math.exp(-noise_log[m])
def zh(m):
    case, stat = m.split(".", 1)
    b = "disk" if case == "swapin-disk" else "zram"
    k = "seq" if "seq" in stat else "rand"
    q = "mean" if "mean" in stat else "p99"
    return f"{b} {k} {q}"
def ratios(r, m):
    return [p["a"][m] / p["b"][m] for p in r["pairs"] if m in p["a"] and m in p["b"]]
def f1(x): return f"{x:.1f}"
advisory = set(m for m in METRICS if any(m.endswith(s) for s in proto["advisory_metric_suffixes"]))

def strip_block(m, rows, takeaway, note=None):
    pts = []
    for label, r in rows:
        for i, v in enumerate(ratios(r, m)):
            pts.append({"group": label, "series": "pair ratio", "value": round(v, 4),
                        "tip": f"pair {i} · base/cand"})
    return {"type": "strip", "takeaway": takeaway, "x_label": f"{zh(m)}: base/cand (>1 = candidate faster)",
            "groups": [g for g, _ in rows], "series": ["pair ratio"], "points": pts,
            "refs": [{"value": 1.0, "label": "no change", "tone": "muted"}, {"value": round(guard(m), 3), "label": "A/A guard"}],
            **({"note": note} if note else {})}

NPAIRS = proto["tiers"]["fast"]["comparison_pairs"]
AA_ROW = (f"A/A · {len(AA['pairs'])} pairs", AA)
C1_ROW = (f"c1 · {len(C1F['pairs'])} pairs", C1F)
C1C_ROW = ("c1c · incomplete", C1CF)

# ---------- gates ----------
gates = policy["required_gates"]
corr_gates = C1CF["correctness"]["gates"]
static_c1c = J(f"{CAMP}/candidates/v2-c1c-xs-ra-safe/static.json")
# long form (source) goes into the collapsed audit table; the visible checklist uses the short form
have = {"checkpatch": f"static.json checkpatch exit {static_c1c['checkpatch']['exit_code']}",
        "guest_boot_identity": "correctness gates.boot / cmdline_identity = true",
        "gcc_swap_on": "built (build manifest referenced, not re-verified)"}
short = {"checkpatch": f"exit {static_c1c['checkpatch']['exit_code']}", "guest_boot_identity": "identity matches",
         "gcc_swap_on": "built, not re-verified"}
for g in ("data_roundtrip", "fork_cow", "concurrent_fault", "swapoff_live_pages", "no_new_kernel_warnings"):
    have[g] = f"correctness gates.{g} = {corr_gates[g]} (disk backend only)"
    assert corr_gates[g] is True, g
    short[g] = "disk only"
notrun = [g for g in gates if g not in have]

# ---------- budget ----------
def count(prefix): return sum(1 for f in resv if f.startswith(prefix))
groups = [("rev6 probe cal", proto["metadata_rescore"]["predecessor_probe_spent"]),
          ("rev7 probe cal", count("86fc2f67")),
          ("fast cal (voided)", count("16fe9d24") + count("0c2cd749")),
          ("fast cal A/A", count("e8b7a7e3")),
          ("round 1 c1", count("c1-") + count("3a554e3b") + count("68de12e0")),
          ("round 2 c1c", count("c1c-") + count("bc73887e") + count("66a07143"))]
rev7_total = len(resv)
assert rev7_total == budget["guests"] + budget["probe_guests"], (rev7_total, budget)
run_total = rev7_total + groups[0][1]

# ---------- round-2 runs ----------
r2runs = C1CF["runs"]
def runlabel(r):
    p, case, arm = r["pair"], r["case"].replace("swapin-", ""), r["arm"]
    return f"pair {p} · {'disk' if case=='disk' else 'zram'} · {'base' if arm=='a' else 'cand'}"

def probe_vals(r, case, key):
    v = r["probe_signals"][case][f"swapin_vmstat_delta.{key}"]
    return v[0]
def cal_median(case, key):
    return calp["analysis"]["bands"][case][f"swapin_vmstat_delta.{key}"]["median"]

# ---------- derived facts used in prose ----------
def npairs(r, case): return sum(1 for p in r["pairs"] if any(k.startswith(case) for k in p["a"]))
C1C_DISK, C1C_ZRAM = npairs(C1CF, "swapin-disk"), npairs(C1CF, "swapin-zram")
seq_all = ratios(C1F, METRICS[0]) + ratios(C1CF, METRICS[0])
SEQ_RANGE = f"{min(seq_all):.1f}–{max(seq_all):.1f}"
def below(r, m): return sum(1 for x in ratios(r, m) if x < guard(m))
ZP = METRICS[5]
KILL = float(re.search(r"seq\.p99 ratio \(baseline/candidate\) < ([0-9.]+)", cand["v2-c1c-xs-ra-safe"]["hypothesis"]).group(1))
assert abs(KILL - round(guard(ZP), 3)) < 1e-9, (KILL, guard(ZP))
CG = C1CF["correctness"]["gates"]
CORR = f"{sum(1 for v in CG.values() if v is True)}/{len(CG)}"
cres = pathlib.Path("/workspace/Swap-Next-main") / C1CF["correctness"]["result"]
assert hashlib.sha256(cres.read_bytes()).hexdigest() == C1CF["correctness"]["result_sha256"], "correctness result.json changed"
CORR_RA = json.loads(cres.read_text())["metrics"]["correctness_vmstat_delta"]["swap_ra"]
nr = calf["analysis"]["noise_relative"]
NOISE_X = statistics.mean(nr[m] for m in METRICS if "zram" in m) / statistics.mean(nr[m] for m in METRICS if "disk" in m)
base_dm = [p["a"][METRICS[0]] / 1000 for p in C1F["pairs"]]  # ns -> µs
BASE_RANGE = f"{min(base_dm):.1f}–{max(base_dm):.1f}"
fast_cal = [r for r in L if r["action"] == "calibrate" and r.get("tier") == "fast"]
voided = {r["attempt_id"][:8] for r in L if r["action"] == "void-calibration"}
started_r = [r for r in C1CF["runs"] if r["status"] == "STARTED"]
inval_r = [r for r in C1CF["runs"] if r["status"] == "INVALID"]
APPROVED = not proto["approval"].startswith("Proposed")
summary = {
    "campaign": "xswap-tcg-kbench-rev7-2026-10-29", "source_commit": FULLREV, "protocol_revision": proto["protocol_revision"],
    "guest": proto["guest"], "accelerator": proto["accelerator"]["qemu"],
    "evaluations": {k: {"status": r["status"], "candidate": r.get("candidate"),
                        "ratios": {m: [round(x, 4) for x in ratios(r, m)] for m in METRICS} if r.get("pairs") else None}
                    for k, r in row.items() if r.get("action") in ("evaluate", "calibrate")},
    "aa_guard": {m: round(guard(m), 4) for m in METRICS},
    "required_gates": {g: ("evidence" if g in have else "NOT RUN") for g in gates},
    "guests": {"rev7_reservations": rev7_total, "budget_json": budget, "run_wide_incl_rev6": run_total,
               "groups": dict(groups)},
    "derived": {"seq_mean_ratio_range": SEQ_RANGE, "c1_zram_seq_p99_below_guard": below(C1F, ZP), "kill": KILL,
                "c1c_pairs": {"disk": C1C_DISK, "zram": C1C_ZRAM, "planned": NPAIRS}, "correctness": CORR,
                "correctness_swap_ra": CORR_RA, "noise_zram_over_disk": round(NOISE_X, 3), "c1_disk_base_us": BASE_RANGE,
                "log_md_l27_us": "-".join(LOG27), "cap_history": CAPS, "agents_md_cap": [CAP_LINE, CAP_AGENTS],
                "unmerged_vs_main": {"main": MAIN, "unmerged": UNMERGED}, "evidence_commit_pushed": PUSHED},
    "scope": f"rounds 1-2 only; ledger has {len(L)} rows",
}
(HERE / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))

# ================= main explainer =================
dm, dp, zm, zp = METRICS[0], METRICS[1], METRICS[4], METRICS[5]
c1_med = C1F["analysis"]["metrics"]
probe_cases = ["swapin-disk", "swapin-zram-64k"]

exact_rows = []
for m in METRICS:
    c1v = c1_med[m]
    exact_rows.append([zh(m) + (" (advisory)" if m in advisory else ""), f"{guard(m):.3f}",
                       " / ".join(f"{x:.3f}" for x in c1v["pair_ratios"]), f"{c1v['median_ratio']:.3f}",
                       "yes" if c1v["guard_pass"] else "no",
                       " / ".join(f"{x:.3f}" for x in ratios(C1CF, m)) or "no data", str(len(ratios(C1CF, m)))])


# ======================= round 3 evidence (read-only) =======================
# Sources outside the bundle (run directory, linux-base, the c1d proposal file) are cited on the page
# by file name and line only; host paths never reach the HTML.
LINUX = "/workspace/linux-base"
PROPOSAL = pathlib.Path("/workspace/swap-next-proposals-v3/c1d-xs-ra-cap4.md")
def lgit(*a): return subprocess.run(["git", "-C", LINUX, *a], check=True, capture_output=True, text=True).stdout.strip()
def LG(pat):
    i = next(i for i, x in enumerate(LOG) if re.search(pat, x)); return i + 1, LOG[i]
def hm(s): return re.search(r"2026-10-29 (\d\d:\d\d):\d\d PDT", s).group(1)
R3, R3SRC = {}, {}
GO_L, s = LG(r"ROUND 3 GO received")
m = re.search(r"Hurric's decision: (\d+), then updated to (\d+) \((\d+) used, (\d+) remain; keep (\d+) in reserve -> ceiling (\d+)\)", s)
R3.update(cap1=int(m[1]), cap2=int(m[2]), used=int(m[3]), remain=int(m[4]), ceiling=int(m[6]), go_logged=hm(s))
m = re.search(r"fast (\d+)/(\d+), probe (\d+)/(\d+)", s)
R3.update(fast_used=int(m[1]), fast_pool=int(m[2]), probe_used=int(m[3]), probe_pool=int(m[4]))
R3["go"] = "~" + re.search(r"~(\d\d:\d\d) PDT", GA[GA_LINE - 1]).group(1)
BLK_L, s = LG(r"HARD BLOCKERS")
assert "standard_workflow.py:597-606" in s and "66a07143" in s and "58d43c94" in s
m = re.search(r"only (\d+) rerun", s) or re.search(r"(\d+) rerun", s)
R3["rerun_l47"] = int(m[1]) if m else None
ERR_L, s = LG(r"action-review service errors")
R3["errs"] = re.findall(r"(\d\d:\d\d)", s.split("retries at", 1)[1].split("PDT", 1)[0])
R3["err_first"] = R3["errs"][0]
GATE_L, s = LG(r"round c1d \(")
m = re.search(r"round c1d \((\w+), tree (\w+), parent (\w+)\)", s)
log_c1d = m.groups()
m = re.search(r"fast (\d+) \+ correctness (\d+) \+ fast eval (\d+) = (\d+)/(\d+) = ZERO reruns", s)
R3.update(b_fast=int(m[1]), b_corr=int(m[2]), b_eval=int(m[3]), b_tot=int(m[4]), b_pool=int(m[5]))
m = re.search(r"available (\d+) MiB < (\d+)", s); R3.update(ram_first=int(m[1]), gate=int(m[2]), gate_time=hm(s))
m = re.search(r"global (\d+)/(\d+)", s); R3.update(glob_used=int(m[1]), glob_cap=int(m[2]))
WAIT_L, s = LG(r"Started ram-wait\.sh")
m = re.search(r"RAM (\d+) MiB < (\d+)", s); R3.update(ram_l50=int(m[1]), wait_time=hm(s))
R3["deadline"] = re.search(r"deadline (\d\d:\d\d) PDT", s).group(1)
assert int(m[2]) == R3["gate"]
# checks against other files
assert R3["b_fast"] == budget["guests"] == R3["fast_used"], "fast pool count"
assert R3["b_pool"] == R3["fast_pool"] == proto["budget"]["guest_attempts"], "fast pool size"
assert R3["b_eval"] == NPAIRS * 2 * 2, "fast eval = pairs x 2 cases x 2 arms"
assert R3["b_tot"] == R3["b_fast"] + R3["b_corr"] + R3["b_eval"] and R3["b_tot"] <= R3["b_pool"]
R3["spare"] = R3["b_pool"] - R3["b_tot"]
corr_resv = J(f"{CAMP}/ledger/guest-reservations/c1c-v2-c1c-xs-ra-safe-correctness-1.json")
assert corr_resv["pool"] == "fast", "correctness reservations draw from the fast pool"
assert R3["used"] == R3["glob_used"] == run_total and R3["glob_cap"] == R3["cap2"] == CAPS[-1]
live = pathlib.Path("/workspace/Swap-Next-main") / CAMP
LIVE_BUDGET = json.loads((live / "ledger/budget.json").read_text())
LIVE_LEDGER = json.loads((live / "ledger/ledger.json").read_text())
assert LIVE_BUDGET["guests"] == budget["guests"] and len(LIVE_LEDGER) == len(L), "round 3 spent nothing"
assert not [f for f in ls(f"{CAMP}/candidates") if "c1d" in f]
assert not [f for f in (live / "candidates").iterdir() if "c1d" in f.name]
GA_R3_L = next(i + 1 for i, x in enumerate(GA) if "NOT started; 0 guests" in x)
# RAM readings while waiting for the gate (ram-monitor.log), plus the two values in LOG.md
RM = (RUNDIR / "ram-monitor.log").read_text().splitlines()
RAM = []
for i, x in enumerate(RM):
    m = re.search(r"2026-10-29 (\d\d:\d\d):\d\d PDT (?:c1d RAM gate wait available=(\d+)MiB need (\d+)|waiting, available (\d+) MiB)", x)
    if m:
        RAM.append((m[1], int(m[2] or m[4]), f"ram-monitor.log L{i + 1}"))
        if m[3]: assert int(m[3]) == R3["gate"]
RAM_LINES = (int(RAM[0][2].split("L")[1]), int(RAM[-1][2].split("L")[1]))
RAM = [(R3["gate_time"], R3["ram_first"], f"LOG.md L{GATE_L}")] + RAM + [(R3["wait_time"], R3["ram_l50"], f"LOG.md L{WAIT_L}")]
RAM.sort()
R3["ram_min"], R3["ram_max"] = min(v for _, v, _ in RAM), max(v for _, v, _ in RAM)
R3["ram_last"] = RAM[-1]
assert R3["ram_max"] < R3["gate"]
WAIT_SH = (RUNDIR / "ram-wait.sh").read_text()
assert f"MemAvailable >= {R3['gate']} MiB" in WAIT_SH and f'-ge {R3["gate"]} ]' in WAIT_SH
# the gate in code: run.py at the pinned tool commit (guest MiB + 1024 under TCG)
RUNPY = subprocess.run(["git", "-C", REPO, "show", "9c1468ac:benchmark/swap-standard/run.py"], check=True, capture_output=True, text=True).stdout.splitlines()
RUNPY_L = next(i + 1 for i, x in enumerate(RUNPY) if "need_kib = (guest_mib + 1024) * 1024 if tcg" in x)
assert "MiB available host RAM" in RUNPY[RUNPY_L + 1]
CODE_GATE = proto["guest"]["mem_mib"] + 1024
# duplicate guard and void tool, at the tool commits
SW = subprocess.run(["git", "-C", REPO, "show", "9c1468ac:evolve/standard_workflow.py"], check=True, capture_output=True, text=True).stdout.splitlines()
assert "duplicate candidate content tier attempt" in SW[600] and "same_tree = " in SW[597] and "duplicate candidate tier attempt" in SW[605]
for c, a in (("9c1468ac", 107), ("87dc7357", 165)):
    v = subprocess.run(["git", "-C", REPO, "show", f"{c}:evolve/control/void_calibration.py"], check=True, capture_output=True, text=True).stdout.splitlines()
    assert 'row.get("action") != "calibrate"' in v[a - 1] and "not a calibration attempt" in v[a], c
VOID_L, s = LG(r"Void of fast eval 66a07143")
assert '"REFUSED"' in s and "not a calibration attempt" in s
R3["void_time"] = hm(s)
assert C1CF["execution_started"] is True or C1CF.get("execution_started") in (True, None)
# c1d commit (linux-base) and the proposal file
C1D = lgit("rev-parse", "v3-c1d-xs-ra-cap4-base")
R3.update(c1d=C1D, c1d_tree=lgit("rev-parse", C1D + "^{tree}"), c1d_parent=lgit("rev-parse", C1D + "^"),
          c1d_time=lgit("show", "-s", "--format=%ci", C1D)[11:16])
assert [R3["c1d"][:8], R3["c1d_tree"][:8], R3["c1d_parent"][:8]] == list(log_c1d)
PROP = PROPOSAL.read_text().splitlines()
PROP_MTIME = datetime.datetime.fromtimestamp(PROPOSAL.stat().st_mtime, TZ).strftime("%H:%M")
PCOMMIT_L = next(i + 1 for i, x in enumerate(PROP) if x.startswith("| Commit |"))
PSTACK = re.search(r"`([0-9a-f]{40})`", PROP[PCOMMIT_L - 1]).group(1)
assert lgit("rev-parse", PSTACK + "^{tree}") == R3["c1d_tree"]
R3["stack"], R3["stack_parent"] = PSTACK, lgit("rev-parse", PSTACK + "^")
PSTATUS_L = next(i + 1 for i, x in enumerate(PROP) if x.startswith("| Status |"))
k0 = next(i for i, x in enumerate(PROP) if x.startswith("## Pre-registered KILL"))
k1 = next(i for i, x in enumerate(PROP) if x.startswith("Other falsifiers"))
KILLS = [(i + 1, re.sub(r"\*\*", "", PROP[i][2:])) for i in range(k0, k1) if PROP[i].startswith("- ")]
assert len(KILLS) == 4
FALS = [(i + 1, re.sub(r"[*`]", "", PROP[i][2:])) for i in range(k1, len(PROP)) if PROP[i].startswith("- ") and i < k1 + 9]
CAP_ORDER_L = next(i + 1 for i, x in enumerate(PROP) if "XSWAP_RA_ORDER" in x)
C1D_DIFF = lgit("show", "--format=", PSTACK)
PC = "per coordinator, 2026-10-29"
R3_DISC_ROWS = [
 ["round 3", f"RAM gate: the wait threshold {R3['gate']} MiB comes from the run log and ram-wait.sh; run.py's own gate is guest {proto['guest']['mem_mib']} + 1024 = {CODE_GATE} MiB. The source of the extra {R3['gate'] - CODE_GATE} MiB is not recorded. All readings are below both",
  f"LOG.md L{GATE_L}; ram-wait.sh L1; run.py L{RUNPY_L}-{RUNPY_L + 2} @9c1468ac"],
 ["round 3", f"reruns: LOG.md L{BLK_L} and GUEST-ACCOUNTING say {R3['rerun_l47']} rerun fits; LOG.md L{GATE_L} adds the fast-pool correctness reservation and gets {R3['spare']}. This page uses {R3['spare']}",
  f"LOG.md L{BLK_L}, L{GATE_L}; c1c correctness reservation pool=fast"],
 ["round 3", f"'about 2.5–3 GiB available' ({PC}); logged readings are {R3['ram_min']}–{R3['ram_max']} MiB, last {R3['ram_last'][1]} MiB at {R3['ram_last'][0]} PDT",
  f"LOG.md L{GATE_L}, L{WAIT_L}; ram-monitor.log L{RAM_LINES[0]}-{RAM_LINES[1]}"],
 ["round 3", f"'c1d pre-registered' ({PC}): the kill list exists only in a proposal file outside the bundle (status: proposal); there is no candidates/ record and no ledger row",
  f"c1d proposal L{PSTATUS_L}, L{k0 + 1}; candidates/ and ledger at {REV}"],
 ["round 3", f"commit: the proposal names {PSTACK[:8]} (parent c1c {R3['stack_parent'][:8]}); the GO used {R3['c1d'][:8]} (parent {R3['c1d_parent'][:8]}). Both have tree {R3['c1d_tree'][:8]}, so the code is the same",
  f"c1d proposal L{PCOMMIT_L}; LOG.md L{GATE_L}; git rev-parse"],
 ["round 3", f"stuck since {R3['err_first']}: LOG.md L{ERR_L} (main agent) lists retries at {', '.join(R3['errs'])} PDT rejected by action-review service errors; the errors themselves are not in a file",
  f"LOG.md L{ERR_L}"],
 ["round 3", "round-3 sources (run log, guest accounting, RAM log, proposal) are not in the bundle commit, so they cannot be linked", "this page"]]

# ======================= English page specs =======================
def mech_strip(cands, takeaway, note=None):
    """Every calibration run and every probe run as its own dot (SKILL L135), per counter."""
    keys = [("swapin-disk", "swap_ra", "disk readahead"), ("swapin-zram-64k", "swap_ra", "zram readahead"),
            ("swapin-disk", "pgmajfault", "disk major faults"), ("swapin-zram-64k", "pgmajfault", "zram major faults")]
    pts = []
    for case, k, g in keys:
        for r in calp["runs"]:
            if r["case"] == case and r["status"] == "PASS":
                pts.append({"group": g, "series": "baseline calibration (each run)", "value": r["metrics"]["vmstat_delta"][k], "tip": f"calibration run {r['index']}"})
        for lab, row_ in cands:
            pts.append({"group": g, "series": lab, "value": probe_vals(row_, case, k), "tip": "1 probe run"})
    return {"type": "strip", "takeaway": takeaway, "x_label": "counter delta (events)", "groups": [g for *_, g in keys],
            "series": ["baseline calibration (each run)"] + [l for l, _ in cands], "points": pts, **({"note": note} if note else {})}

SUB_PROV = (f"protocol rev{proto['protocol_revision']}{'' if APPROVED else ' (not approved)'} · tool code "
            f"{'unmerged' if UNMERGED else 'merged'} · guest {proto['guest']['vcpus']} vCPU / {proto['guest']['mem_mib']} MiB / swap {proto['guest']['swap_gib']} GiB · QEMU TCG")
LINKS_MAIN = [{"href": "round1.html", "label": "Round 1"}, {"href": "round2.html", "label": "Round 2"}, {"href": "round3.html", "label": "Round 3 (not run)"}]
LINKS_ROUND = [{"href": "summary.html", "label": "← Summary"}]
PC = "per coordinator, 2026-10-29"

spec = {
 "title": "xswap swap-in readahead: rounds 1–3",
 "subtitle": f"{SUB_PROV} · draft 2026-10-29",
 "links": LINKS_MAIN,
 "verdict": {"status": "needs-review",
   "headline": "No candidate accepted: c1 worsened zram tails, clock faults cut c1c short, and round 3 (c1d) did not run. Continuing needs a protocol fix; Hurric decides.",
   "tiles": [
     {"label": "c1 (round 1)", "value": "closed", "note": "zram tail worse"},
     {"label": "c1c (round 2)", "value": "incomplete", "note": f"disk {C1C_DISK}, zram {C1C_ZRAM} of {NPAIRS} pairs"},
     {"label": "c1d (round 3)", "value": "NOT RUN", "note": "0 guests spent"},
     {"label": "Required gates", "value": f"{len(notrun)}/{len(gates)} not run", "note": "no lockdep, KASAN"}]},
 "sections": [
  {"id": "context", "title": "Why", "lead": "Touching a swapped-out page stalls until the kernel reads it back.",
   "blocks": [
    {"type": "flow", "takeaway": "Every swap-in makes the program wait",
     "nodes": [{"id": "a", "label": "touch memory", "sub": "page swapped out", "col": 0, "row": 0},
               {"id": "b", "label": "fault", "sub": "program stalls", "col": 1, "row": 0, "tone": "bad"},
               {"id": "c", "label": "read backend", "sub": "disk or zram", "col": 2, "row": 0, "tone": "focus"},
               {"id": "d", "label": "resume", "sub": "wait = swap-in latency", "col": 3, "row": 0}],
     "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}, {"from": "c", "to": "d"}]},
    {"type": "note", "text": "Hypothesis: read neighbouring pages too (readahead) so later faults hit."}]},
  {"id": "system", "title": "Where the change sits", "lead": "Three zoom levels.",
   "blocks": [
    {"type": "scene", "level": 1, "eyebrow": "Level 1 · machine", "takeaway": "Under memory pressure cold pages go to two backends", "schematic": "schematic",
     "label": "guest kernel", "app": "program", "app_sub": "",
     "down": "↓ swap out", "up": "↑ fault in", "ram": "RAM", "ram_sub": "hot pages",
     "zones": [{"label": "hot pages", "pages": ["A", "B"], "caption": "direct access"},
               {"label": "zram", "pages": ["C"], "kind": "compressed", "caption": "sync: decompress now"}],
     "down2": "↓", "up2": "↑", "disk": "disk swap", "disk_sub": "async: wait for I/O", "disk_pages": ["D", "E", "F"]},
    {"type": "scene", "level": 2, "eyebrow": "Level 2 · swap-in path", "takeaway": "Only the readahead decision changes", "schematic": "schematic",
     "label": "fault handler", "fault": "fault A", "fault_sub": "", "tag_data": "data", "cache": "swap cache",
     "cache_sub": "hit: no backend read", "miss": "miss → readahead decision", "tag_meta": "metadata", "meta": "slot records backend (unchanged)",
     "pin": "change", "tag_ctl": "control", "policy": "readahead decision", "policy_sub": "baseline: no readahead for xswap",
     "backends": [{"cls": "async", "kicker": "async", "title": "disk", "text": "reads can queue"},
                  {"cls": "sync", "kicker": "sync", "title": "zram", "text": "decompress each page"}],
     "unchanged": "backends and swap-out unchanged"},
    {"type": "scene", "level": 3, "eyebrow": "Level 3 · the change", "takeaway": "Step through: c1 reads ahead on both, c1c on disk only", "schematic": "schematic, 3-page window",
     "label": "sequential A→B→C",
     "candidates": [{"key": "base", "label": "baseline", "disk": False, "zram": False},
                    {"key": "c1", "label": "c1", "disk": True, "zram": True},
                    {"key": "c1c", "label": "c1c", "disk": True, "zram": False}],
     "backends": [["disk", "disk"], ["zram", "zram"]], "before": "baseline",
     "strings": {"after": "changed", "req": "touch ", "start": "press next", "wait": "wait ", "disk": "disk I/O", "zram": "decompress",
                 "none": "—", "same": " as baseline", "all3": "reads 3 pages ", "disk_cost": "first wait longer",
                 "zram_cost": "decompress 3 now", "hit": "hit, no wait", "next": "next ", "done": "done", "reset": "reset"},
     "tradeoff": "Inference: readahead saves later waits but costs the first fault; zram is sync, so the cost lands in the tail.",
     "static": "c1 reads ahead on disk and zram; c1c on disk only."}]},
  {"id": "results", "title": "Results", "lead": "One dot per pair; left of the red dashed line = slower beyond noise.",
   "blocks": [
    strip_block(dm, [AA_ROW, C1_ROW, C1C_ROW], f"Disk seq mean: both candidates {SEQ_RANGE}× faster (TCG only)"),
    strip_block(zp, [AA_ROW, C1_ROW, C1C_ROW], "zram seq p99: c1 worse; c1c's single pair recovered",
                f"c1: {below(C1F, ZP)} pairs below the guard; c1c has {C1C_ZRAM} pair."),
    strip_block(dp, [AA_ROW, C1_ROW, C1C_ROW], f"Disk seq p99: both c1c pairs ({below(C1CF, dp)}) below the guard",
                "p99 is advisory; review flagged it."),
    mech_strip([("c1 probe", C1P), ("c1c probe", C1CP)], "Mechanism: c1c reads ahead on disk, not on zram", "Mechanism only, not speed.")]},
  {"id": "round2", "title": "Why round 2 stopped", "lead": "Clock faults used the one allowed rerun.",
   "blocks": [
    {"type": "strip", "takeaway": f"{len(r2runs)} attempts: all {len(inval_r)} invalid runs on one arm",
     "x_label": "wall time (s)", "groups": list(dict.fromkeys(runlabel(r) for r in r2runs if r["status"] != "STARTED")),
     "series": ["valid", "invalid (clock fallback)"],
     "points": [{"group": runlabel(r), "series": "valid" if r["status"] == "PASS" else "invalid (clock fallback)",
                 "value": round(r["wall_seconds"], 1), "tip": r["id"].split("-", 1)[1]} for r in r2runs if r["status"] != "STARTED"],
     "note": f"{len(started_r)} more reserved, never started. A/A had the same fault."},
    {"type": "flow", "takeaway": "Current tools and rules block a rerun",
     "nodes": [{"id": "i", "label": f"{len(inval_r)} invalid", "sub": "clocksource_fallback", "col": 0, "row": 0, "tone": "bad"},
               {"id": "s", "label": "STOP", "sub": "one rerun max", "col": 1, "row": 0},
               {"id": "v", "label": "void tool", "sub": "calibrations only", "col": 2, "row": 0, "tone": "bad"},
               {"id": "d", "label": "duplicate guard", "sub": "same code not re-run", "col": 3, "row": 0, "tone": "bad"},
               {"id": "n", "label": "needs rev8", "sub": "or a reviewed void rule", "col": 3, "row": 1, "tone": "focus"}],
     "edges": [{"from": "i", "to": "s"}, {"from": "s", "to": "v"}, {"from": "v", "to": "d"}, {"from": "d", "to": "n"}]}]},
  {"id": "round3", "title": "Round 3: NOT RUN", "lead": "c1d was prepared; no guest booted.",
   "blocks": [
    {"type": "flow", "takeaway": "Three blockers, in order (PDT)",
     "nodes": [{"id": "g", "label": "GO", "sub": R3["go"], "col": 0, "row": 0},
               {"id": "c", "label": "c1c re-eval", "sub": "duplicate guard", "col": 1, "row": 0, "tone": "bad"},
               {"id": "r", "label": "c1d build", "sub": "review errors " + R3["err_first"], "col": 2, "row": 0, "tone": "bad"},
               {"id": "m", "label": "RAM gate", "sub": f"waiting since {R3['gate_time']}", "col": 3, "row": 0, "tone": "bad"}],
     "edges": [{"from": "g", "to": "c"}, {"from": "c", "to": "r"}, {"from": "r", "to": "m"}]},
    {"type": "note", "text": f"Fast pool: {R3['spare']} reruns left ({R3['b_fast']}+{R3['b_corr']}+{R3['b_eval']} = {R3['b_tot']}/{R3['b_pool']})."}]},
  {"id": "gates", "title": "Gates", "lead": "All required gates; correctness ran on disk only.",
   "blocks": [
    {"type": "checklist", "takeaway": f"{len(notrun)} of {len(gates)} have no evidence (same for c1 and c1c)",
     "items": [{"status": ("warn" if g == "gcc_swap_on" else "pass") if g in have else "missing", "label": g,
                "evidence": short.get(g, "")} for g in gates]},
    {"type": "note", "text": "zswap mixed path not covered."}]},
  {"id": "budget", "title": "Budget", "lead": f"Run-wide {run_total} guests, rev7 {rev7_total}; global cap {CAPS[-1]} ({PC}).",
   "blocks": [
    {"type": "bars", "takeaway": "Fast A/A calibration used the most guests",
     "categories": [g for g, _ in groups], "series": ["guests"], "values": {"guests": [n for _, n in groups]}, "y_label": "guest attempts",
     "note": "From reservation files; round 3 used 0."}]},
  {"id": "next", "title": "Next", "lead": "Proposals: fix the protocol first.",
   "blocks": [
    {"type": "flow", "takeaway": "Path and kill conditions",
     "nodes": [{"id": "a", "label": "rev8 protocol", "sub": "clock + void rule", "col": 0, "row": 0, "tone": "focus"},
               {"id": "b", "label": "redo A/A", "col": 1, "row": 0},
               {"id": "c", "label": f"c1c or c1d, {NPAIRS} pairs", "col": 2, "row": 0},
               {"id": "d", "label": "required gates", "sub": "lockdep/KASAN", "col": 3, "row": 0},
               {"id": "k1", "label": "kill: zram p99", "sub": f"median < {KILL}", "col": 2, "row": 1, "tone": "bad"},
               {"id": "k2", "label": "flag: disk p99", "sub": "median below guard", "col": 3, "row": 1, "tone": "bad"}],
     "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}, {"from": "c", "to": "d"}, {"from": "c", "to": "k1"}, {"from": "c", "to": "k2"}]},
    {"type": "note", "text": "For Hurric: rev7 (PR #8), void tool, rev8, host RAM for c1d, KVM cross-check."}]},
  {"id": "audit-data", "title": "Exact data", "blocks": [
    {"type": "table", "takeaway": "Pair ratio = base/cand; guard = exp(−A/A noise_log)",
     "columns": ["Metric", "A/A guard", "c1 pairs", "c1 median", "c1 passes", "c1c pairs", "c1c n"], "rows": exact_rows},
    {"type": "table", "takeaway": "Gate evidence sources", "columns": ["Gate", "Evidence"], "rows": [[g, have.get(g, "not run")] for g in gates]},
    strip_block(zm, [AA_ROW, C1_ROW, C1C_ROW], "zram seq mean: c1 gain unstable, c1c within noise"),
    strip_block(METRICS[2], [AA_ROW, C1_ROW, C1C_ROW], "Disk rand mean: c1c close to the guard"),
    strip_block(METRICS[3], [AA_ROW, C1_ROW, C1C_ROW], "Disk rand p99"),
    strip_block(METRICS[6], [AA_ROW, C1_ROW, C1C_ROW], "zram rand mean"),
    strip_block(METRICS[7], [AA_ROW, C1_ROW, C1C_ROW], "zram rand p99")]},
  {"id": "audit-runs", "title": "Timeline", "blocks": [
    {"type": "table", "takeaway": f"Ledger, {len(L)} rows (PDT); round 3 added none",
     "columns": ["Eval", "Action", "Tier", "Candidate", "Status", "Start", "End", "Reason / void"],
     "rows": [[r["id"][:8], r["action"], r.get("tier", ""), r.get("candidate") or r.get("attempt_id", "")[:8] or "", r["status"],
               t(r["started"]) if r.get("started") else "", t(r["finished"]) if r.get("finished") else (t(r["recorded"]) if r.get("recorded") else ""),
               (r.get("reason") or "")[:60] + (f" · void {r['void_receipt'][:8]}" if r.get("void_receipt") else "")] for r in L]}]},
  {"id": "audit-provenance", "title": "Provenance and environment", "blocks": [
    {"type": "table", "takeaway": "Fixed facts needed to reproduce",
     "columns": ["Item", "Value", "Source"],
     "rows": [["Protocol", f"TCG kbench rev{proto['protocol_revision']} (PR #8, {'approved' if APPROVED else 'not approved'})", "protocol.json approval"],
              ["Guest", f"{proto['guest']['vcpus']} vCPU / {proto['guest']['mem_mib']} MiB RAM / {proto['guest']['swap_gib']} GiB swap", "protocol.json guest"],
              ["QEMU accelerator", " ".join(proto["accelerator"]["qemu"]), "protocol.json accelerator.qemu"],
              ["Fingerprint", L[0]["fingerprint"][:8] + f" ({len(L)} rows, {'all equal' if len({r['fingerprint'] for r in L}) == 1 else 'MISMATCH'})", "ledger.json"],
              ["c1 commit", C1F["candidate_commit"][:8], "ledger 68de12e0"],
              ["c1c commit", C1CF["candidate_commit"][:8], "ledger 66a07143"],
              ["c1d commit", f"{R3['c1d'][:8]} (tree {R3['c1d_tree'][:8]}, parent {R3['c1d_parent'][:8]}); not in ledger", "linux-base ref v3-c1d-xs-ra-cap4-base"],
              ["Evidence commit", FULLREV[:12] + ("" if PUSHED else " (not pushed yet)"), "git branch -r --contains"],
              ["Evidence links", "repo-relative, below; " + ("live" if PUSHED else "resolve once the bundle branch is pushed"), "this page"],
              ["Tool code", " / ".join(TOOL_COMMITS) + f": {len(UNMERGED)} not on main ({MAIN})", "git merge-base --is-ancestor"],
              ["Models", "cloud agents bc-9fa8e17e, bc-33e85066: grok-4.7; other roles: default model, not recorded; no quota fallback", PC + "; not verifiable in the repo"]]}]},
  {"id": "audit-limits", "title": "Limits and discrepancies", "blocks": [
    {"type": "table", "takeaway": "What is not claimed, and audit findings", "columns": ["Kind", "Content", "Source"],
     "rows": [["not claimed", "no acceptance, no promotion, no KVM, lockdep/KASAN or zswap mixed result; no round 3 result", "round2 review; run log"],
              ["finding", "c1 SIGBUS (TOCTOU) concern not closed; c1c adds a re-check under lock, but no counter shows the discard path ran", "round1 review hypothesis 1; round2 review 2b"],
              ["finding", f"run log says disk base {LOG27[0]}–{LOG27[1]} µs, ledger {BASE_RANGE} µs; ledger wins", "LOG.md L27; ledger 68de12e0 pairs[].a; audit.md item 5"],
              ["finding", "void tool rewrites the ledger row (execution_started → False); receipt keeps the original", "audit.md item 11"],
              ["finding", "cleanup record removed.tsv has fewer rows than LOG.txt deletions", "audit.md item 8"],
              ["finding", "0c2cd749 refusal cause (virtio balloon holding host RAM) is only 'likely'", "820fdc14 receipt; audit.md item 9"],
              ["finding", "c1 close reason says 'worktree kept as evidence', but it was later archived and removed", f"candidates/v2-c1-xs-sync-ra.json; LOG.md L{ARCH_LINE}"],
              ["finding", f"cap {CAPS[0]} → {CAPS[1]} → {CAPS[2]} only {PC} (Hurric's decision as relayed); AGENTS.md L{CAP_LINE} sets {CAP_AGENTS} per campaign", f"AGENTS.md L{CAP_LINE}; GUEST-ACCOUNTING.md L{GA_LINE}"]] + R3_DISC_ROWS}]},
  {"id": "audit-diff", "title": "Patches", "blocks": [
    {"type": "diff", "takeaway": f"c1c ({C1CF['candidate_commit'][:8]})", "patch": patch["v2-c1c-xs-ra-safe"]},
    {"type": "diff", "takeaway": f"c1 ({C1F['candidate_commit'][:8]})", "patch": patch["v2-c1-xs-sync-ra"]}]},
 ]}

# ================= round 1 page =================
aa_inv = [r for r in AA["runs"] if r["status"] != "PASS"]
r1 = {
 "title": "Round 1: c1 enables xswap readahead on every backend",
 "subtitle": f"eval 68de12e0 · probe 3a554e3b · calibration e8b7a7e3 · {SUB_PROV} · 2026-10-29",
 "links": LINKS_ROUND,
 "verdict": {"status": "needs-review", "headline": "c1 passed the no-regression screen, but zram tail latency got clearly worse and a SIGBUS risk is open. Closed.",
   "tiles": [{"label": "Fast tier", "value": "screen passed", "note": "not acceptance"},
             {"label": "Disk seq mean", "value": "much faster", "note": "TCG only"},
             {"label": "zram seq p99", "value": "worse", "note": f"{below(C1F, ZP)} of {len(C1F['pairs'])} pairs below guard"},
             {"label": "Review", "value": "needs evidence", "note": "NEEDS-MORE-EVIDENCE"}]},
 "sections": [
  {"id": "calib", "title": f"Noise first: {len(fast_cal)} fast A/A attempts", "lead": f"Baseline against baseline, {len(AA['pairs'])} pairs, gives each metric's noise guard.",
   "blocks": [
    {"type": "flow", "takeaway": f"{len(voided)} voided, 1 refused by the duplicate guard, attempt {len(fast_cal)} succeeded",
     "nodes": [{"id": "a", "label": fast_cal[0]["id"][:8], "sub": "watchdog false STOP", "col": 0, "row": 0, "tone": "bad"},
               {"id": "r", "label": fast_cal[1]["id"][:8], "sub": "duplicate guard", "col": 1, "row": 0, "tone": "bad"},
               {"id": "b", "label": fast_cal[2]["id"][:8], "sub": "host RAM short", "col": 2, "row": 0, "tone": "bad"},
               {"id": "c", "label": fast_cal[3]["id"][:8], "sub": "calibrated", "col": 3, "row": 0, "tone": "good"}],
     "edges": [{"from": "a", "to": "r", "label": "void" if fast_cal[0]["id"][:8] in voided else ""},
               {"from": "r", "to": "b"}, {"from": "b", "to": "c", "label": "void" if fast_cal[2]["id"][:8] in voided else ""}]},
    {"type": "bars", "takeaway": f"zram noise is about {NOISE_X:.1f}× disk noise on average",
     "categories": [zh(m) for m in METRICS], "series": ["A/A relative noise"], "y_label": "relative noise (p90)",
     "values": {"A/A relative noise": [round(calf["analysis"]["noise_relative"][m], 4) for m in METRICS]},
     "note": f"Ceiling {calf['analysis']['noise_ceiling']}; all below, so calibration is valid. {len(aa_inv)} invalid reruns (clock or wall timeout)."}]},
  {"id": "mech", "title": "Mechanism: readahead happened", "lead": "One probe run against every baseline calibration run.",
   "blocks": [mech_strip([("c1 probe", C1P)], "c1 reads ahead on disk and zram; major faults drop")]},
  {"id": "results", "title": "Results: faster mean, heavier zram tail", "lead": "One dot per pair; dashed line = A/A guard.",
   "blocks": [strip_block(m, [AA_ROW, C1_ROW], f"{zh(m)}: " + ("much faster" if c1_med[m]["median_ratio"] > 1.2 else ("below the guard" if not c1_med[m]["guard_pass"] else "within noise")))
              for m in (dm, zm, zp, dp)] + [
    {"type": "note", "text": "Inference: zram is synchronous, so the faulting thread decompresses the whole window; mean drops, p99 rises. Not measured directly."}]},
  {"id": "review", "title": "Review findings", "lead": "Code and evidence review only; nothing re-run.",
   "blocks": [{"type": "checklist", "takeaway": "Why the review said NEEDS-MORE-EVIDENCE",
     "items": [{"status": "pass", "label": f"patch identity, scope, checkpatch fine; correctness {sum(1 for v in C1F['correctness']['gates'].values() if v is True)}/{len(C1F['correctness']['gates'])} (disk only)", "evidence": "round1 review table"},
               {"status": "fail", "label": "zram seq p99 median below the guard (advisory, pre-registered)", "evidence": "68de12e0 analysis"},
               {"status": "warn", "label": "race between backend check and neighbour read may SIGBUS (unverified)", "evidence": "round1 review hypothesis 1"},
               {"status": "missing", "label": f"{len(notrun)} required gates not run; zswap mixed path untested (zswpout 0)", "evidence": "policy required_gates"},
               {"status": "warn", "label": f"{len(C1F['pairs'])} pairs, below policy minimum {policy['measurement']['min_pairs']}; no slow tier, cannot accept", "evidence": "policy measurement.min_pairs"}]}]},
  {"id": "next", "title": "Next: c1c", "lead": "Limit readahead to async backends and re-check under lock.",
   "blocks": [{"type": "flow", "takeaway": "How c1c addresses c1's two problems",
     "nodes": [{"id": "p1", "label": "zram tail", "col": 0, "row": 0, "tone": "bad"},
               {"id": "p2", "label": "SIGBUS race", "col": 0, "row": 1, "tone": "bad"},
               {"id": "f1", "label": "async-only readahead", "col": 1, "row": 0, "tone": "focus"},
               {"id": "f2", "label": "re-check under lock", "sub": "discard if stale", "col": 1, "row": 1, "tone": "focus"},
               {"id": "k", "label": "kill", "sub": f"zram p99 median < {KILL}", "col": 2, "row": 0, "tone": "bad"}],
     "edges": [{"from": "p1", "to": "f1"}, {"from": "p2", "to": "f2"}, {"from": "f1", "to": "k"}]}]},
  {"id": "audit-data", "title": "Exact data", "blocks": [
    {"type": "table", "takeaway": "c1, all 8 metrics", "columns": ["Metric", "Guard", "Pairs", "Median", "Passes"],
     "rows": [r[:5] for r in exact_rows]}] + [strip_block(m, [AA_ROW, C1_ROW], zh(m)) for m in METRICS if m not in (dm, zm, zp, dp)]},
  {"id": "audit-diff", "title": "Patch", "blocks": [{"type": "diff", "takeaway": f"c1 ({C1F['candidate_commit'][:8]})", "patch": patch["v2-c1-xs-sync-ra"]}]}]}

# ================= round 2 page =================
pre = cand["v2-c1c-xs-ra-safe"]
r2 = {
 "title": "Round 2: c1c reads ahead on async backends only",
 "subtitle": f"eval 66a07143 · probe bc73887e · commit {C1CF['candidate_commit'][:8]} · {SUB_PROV} · 2026-10-29",
 "links": LINKS_ROUND,
 "verdict": {"status": "inconclusive", "headline": f"c1c passed correctness and the mechanism probe, but the fast tier finished only disk {C1C_DISK} and zram {C1C_ZRAM} of {NPAIRS} pairs. No performance conclusion.",
   "tiles": [{"label": "Correctness", "value": CORR, "note": "disk backend only"},
             {"label": "Mechanism", "value": "as expected", "note": "disk reads ahead, zram not"},
             {"label": "Fast tier", "value": "incomplete", "note": "BLOCKED: STOP"},
             {"label": "Disk seq p99", "value": "red flag", "note": "both pairs below guard (advisory)"}]},
 "sections": [
  {"id": "prereg", "title": "Pre-registered: hypothesis and kill before any guest", "lead": "Written and hashed before the first c1c guest; unchanged since.",
   "blocks": [{"type": "flow", "takeaway": f"Order (PDT): {t(pre['created_unix'])} registered → {t(C1CP['started'])} probe → {t(C1CF['started'])} fast tier",
     "nodes": [{"id": "a", "label": "register", "sub": t(pre["created_unix"]), "col": 0, "row": 0, "tone": "focus"},
               {"id": "b", "label": "correctness", "sub": f"{CORR} pass", "col": 1, "row": 0, "tone": "good"},
               {"id": "c", "label": "probe", "sub": t(C1CP["started"]) + " pass", "col": 2, "row": 0, "tone": "good"},
               {"id": "d", "label": "fast tier", "sub": t(C1CF["finished"]) + " STOP", "col": 3, "row": 0, "tone": "bad"}],
     "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}, {"from": "c", "to": "d"}]}]},
  {"id": "mech", "title": "Mechanism: the gate works on zram", "lead": "The probe shows readahead on disk only.",
   "blocks": [mech_strip([("c1 probe", C1P), ("c1c probe", C1CP)], "c1c: zero zram readahead; major faults back to baseline",
                         f"Correctness saw only {CORR_RA} readaheads; no counter proves the discard path ran.")]},
  {"id": "results", "title": "Partial results: direction only", "lead": f"Disk {C1C_DISK} pairs, zram {C1C_ZRAM}; the protocol needs {NPAIRS} for a median.",
   "blocks": [strip_block(dm, [AA_ROW, C1_ROW, C1C_ROW], "Disk seq mean: both pairs far above noise"),
              strip_block(dp, [AA_ROW, C1_ROW, C1C_ROW], "Disk seq p99: both pairs below the guard, worse than c1"),
              strip_block(METRICS[2], [AA_ROW, C1_ROW, C1C_ROW], "Disk rand mean: near the guard; two more pairs could regress"),
              strip_block(zp, [AA_ROW, C1_ROW, C1C_ROW], "zram seq p99: the one pair recovered; kill not evaluable")]},
  {"id": "stop", "title": "Why it stopped", "lead": "Two clock faults on pair 1's candidate zram arm hit the one-rerun rule.",
   "blocks": list(next(x for x in spec["sections"] if x["id"] == "round2")["blocks"])},
  {"id": "next", "title": "Next", "lead": "Finishing needs a protocol change; Hurric decides.",
   "blocks": list(next(x for x in spec["sections"] if x["id"] == "next")["blocks"])},
  {"id": "audit-data", "title": "Exact data", "blocks": [
    {"type": "table", "takeaway": "c1c partial pair ratios (base/cand)", "columns": ["Metric", "Guard", "c1c pairs", "n"],
     "rows": [[r[0], r[1], r[5], r[6]] for r in exact_rows]},
    {"type": "table", "takeaway": "Pre-registration record (verbatim)", "columns": ["Field", "Content"],
     "rows": [["hypothesis", pre["hypothesis"]], ["mechanism", pre["mechanism"]], ["protocol_sha256", pre["protocol_sha256"][:16]]]}]},
  {"id": "audit-diff", "title": "Patch", "blocks": [{"type": "diff", "takeaway": f"c1c ({C1CF['candidate_commit'][:8]})", "patch": patch["v2-c1c-xs-ra-safe"]}]}]}

# ================= round 3 page (NOT RUN) =================
bp.STATUS["not-run"] = ("--serious", "–", "Not run")
r3 = {
 "title": "Round 3: c1d caps the readahead window at 4 pages — NOT RUN",
 "subtitle": f"c1d {R3['c1d'][:8]} · tree {R3['c1d_tree'][:8]} · base {R3['c1d_parent'][:8]} · {SUB_PROV} · 2026-10-29",
 "links": LINKS_ROUND,
 "verdict": {"status": "not-run", "headline": f"NOT RUN. c1d was prepared, but no guest booted: tooling blocks a c1c re-run, and since {R3['gate_time']} PDT host RAM has stayed below the gate. No result exists.",
   "tiles": [{"label": "Guests spent", "value": "0", "note": f"ledger still {len(L)} rows"},
             {"label": "Host RAM free", "value": f"{R3['ram_min']}–{R3['ram_max']} MiB", "note": f"gate {R3['gate']} MiB; last read {R3['ram_last'][0]} PDT"},
             {"label": "Fast reruns left", "value": str(R3["spare"]), "note": f"{R3['b_tot']}/{R3['b_pool']} committed"},
             {"label": "Global cap", "value": f"{R3['glob_used']}/{R3['glob_cap']}", "note": PC}]},
 "sections": [
  {"id": "prepared", "title": "What was prepared", "lead": "One change on top of c1c: the xswap readahead window is capped at 4 pages.",
   "blocks": [
    {"type": "flow", "takeaway": f"c1d committed {R3['c1d_time']} PDT; never built",
     "nodes": [{"id": "a", "label": "c1c", "sub": C1CF["candidate_commit"][:8], "col": 0, "row": 0},
               {"id": "b", "label": "c1d", "sub": "window ≤ 4 pages", "col": 1, "row": 0, "tone": "focus"},
               {"id": "c", "label": "build + probe", "sub": "not started", "col": 2, "row": 0, "tone": "bad"},
               {"id": "d", "label": f"fast tier, {NPAIRS} pairs", "sub": "not started", "col": 3, "row": 0, "tone": "bad"}],
     "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}, {"from": "c", "to": "d"}]},
    {"type": "checklist", "takeaway": "Kill list written before any c1d guest (none evaluated)",
     "items": [{"status": "missing", "label": txt, "evidence": f"proposal L{ln}"} for ln, txt in KILLS]}]},
  {"id": "c1c", "title": "Why c1c was not re-run first", "lead": "The coordinator's GO asked for a fresh c1c fast evaluation.",
   "blocks": [{"type": "checklist", "takeaway": "Both exits are closed by current tools",
     "items": [{"status": "fail", "label": "duplicate guard: same tree and commit already started (66a07143)", "evidence": "standard_workflow.py L597-606"},
               {"status": "fail", "label": f"void tool refuses evaluate rows; tried {R3['void_time']} PDT, exit 2", "evidence": "void_calibration.py L107-108"},
               {"status": "warn", "label": "campaign STOP still in place", "evidence": f"LOG.md L{WAIT_L}"}]}]},
  {"id": "ram", "title": "Why c1d has not run", "lead": f"Build retries at {', '.join(R3['errs'])} PDT hit action-review service errors; then the RAM gate.",
   "blocks": [
    {"type": "strip", "takeaway": f"Every reading since {R3['gate_time']} PDT is below the gate",
     "x_label": "host available RAM (MiB)", "groups": ["readings"], "series": ["reading"],
     "points": [{"group": "readings", "series": "reading", "value": v, "tip": f"{tm} PDT · {src}"} for tm, v, src in RAM],
     "refs": [{"value": R3["gate"], "label": "wait gate"}],
     "note": f"run.py itself needs {CODE_GATE} MiB; still above every reading. Wait deadline {R3['deadline']} PDT, 10-30."}]},
  {"id": "budget", "title": "Budget", "lead": f"Fast pool {R3['b_pool']} guests; global {R3['glob_used']}/{R3['glob_cap']} ({PC}).",
   "blocks": [
    {"type": "bars", "takeaway": f"c1d would leave {R3['spare']} fast reruns",
     "categories": ["used (rounds 1–2)", "c1d correctness", "c1d fast eval", "spare"], "series": ["guests"],
     "values": {"guests": [R3["b_fast"], R3["b_corr"], R3["b_eval"], R3["spare"]]}, "y_label": "fast-pool guests",
     "note": f"Fast eval = {NPAIRS} pairs × 2 backends × 2 arms. Probe pool {R3['probe_used']}/{R3['probe_pool']}."}]},
  {"id": "next", "title": "Next", "lead": "Decisions for Hurric; none taken here.",
   "blocks": [{"type": "note", "text": "Free host RAM or approve another host; one invalid run ends c1d with no rerun, so the clock fix (rev8) matters first."}]},
  {"id": "audit-facts", "title": "Verified facts", "blocks": [
    {"type": "table", "takeaway": "Each round-3 fact and where it was read (PDT)", "columns": ["Fact", "Value", "Source"],
     "rows": [["round 3 GO", f"logged {R3['go_logged']}; decision {R3['go']}", f"LOG.md L{GO_L}; GUEST-ACCOUNTING.md L{GA_LINE}"],
              ["global cap", f"{R3['cap1']} then {R3['cap2']}; {R3['used']} used, ceiling {R3['ceiling']}", f"LOG.md L{GO_L} (relayed, {PC})"],
              ["c1c re-eval blocked", "duplicate guard on 66a07143 (tree 58d43c94)", f"LOG.md L{BLK_L}; standard_workflow.py L597-606 @9c1468ac"],
              ["void refuses evaluate", f"exit 2 at {R3['void_time']}; 'not a calibration attempt'", f"LOG.md L{VOID_L}; void_calibration.py L107-108 @9c1468ac, L165-166 @87dc7357"],
              ["c1d commit", f"{R3['c1d'][:8]}, tree {R3['c1d_tree'][:8]}, parent {R3['c1d_parent'][:8]}, {R3['c1d_time']} PDT", f"LOG.md L{GATE_L}; git rev-parse"],
              ["window cap", "4 pages", f"c1d proposal L{CAP_ORDER_L}; commit subject"],
              ["proposal written", f"{PROP_MTIME} PDT (file time)", "c1d proposal"],
              ["action-review errors", ", ".join(R3["errs"]) + " PDT", f"LOG.md L{ERR_L}"],
              ["RAM gate wait", f"since {R3['gate_time']}; {R3['ram_min']}–{R3['ram_max']} MiB < {R3['gate']}", f"LOG.md L{GATE_L}, L{WAIT_L}; ram-monitor.log L{RAM_LINES[0]}-{RAM_LINES[1]}"],
              ["fast pool", f"{R3['b_fast']} + {R3['b_corr']} + {R3['b_eval']} = {R3['b_tot']}/{R3['b_pool']}, spare {R3['spare']}", f"LOG.md L{GATE_L}; budget.json; protocol.json budget; reservation pool=fast"],
              ["guests spent", f"0; ledger {len(LIVE_LEDGER)} rows, budget guests {LIVE_BUDGET['guests']}", f"GUEST-ACCOUNTING.md L{GA_R3_L}; ledger.json; budget.json (live main checkout)"]]},
    {"type": "table", "takeaway": "Other falsifiers in the proposal (verbatim)", "columns": ["Line", "Text"],
     "rows": [[f"L{ln}", txt] for ln, txt in FALS]}]},
  {"id": "audit-limits", "title": "Limits and discrepancies", "blocks": [
    {"type": "table", "takeaway": "Claims checked against files", "columns": ["Kind", "Content", "Source"], "rows": R3_DISC_ROWS}]},
  {"id": "audit-diff", "title": "Patch", "blocks": [{"type": "diff", "takeaway": f"c1d incremental on c1c ({PSTACK[:8]}, same tree as {R3['c1d'][:8]})", "patch": C1D_DIFF}]}]}

summary["round3"] = {"status": "NOT RUN", "guests": 0, "c1d": {"commit": R3["c1d"], "tree": R3["c1d_tree"], "parent": R3["c1d_parent"]},
                     "fast_pool": {k: R3[k] for k in ("b_fast", "b_corr", "b_eval", "b_tot", "b_pool", "spare")},
                     "ram_gate_mib": R3["gate"], "run_py_gate_mib": CODE_GATE, "ram_readings_mib": [v for _, v, _ in RAM],
                     "global": [R3["glob_used"], R3["glob_cap"]], "per_coordinator": ["cap 200 (Hurric's decision as relayed)", "c1d pre-registered", "models"]}
summary["scope"] = f"rounds 1-3 (round 3 not run); ledger has {len(L)} rows"

# ================= evidence links (repo-relative, from campaigns/<campaign>/report/) =================
EVID = [("protocol.json", "protocol rev7"), ("policy.json", "policy and required gates"), ("ledger/ledger.json", "ledger, all rows"),
        ("ledger/budget.json", "guest budget"), ("ledger/calibration-fast.json", "fast A/A calibration"),
        ("ledger/calibration-probe.json", "probe calibration"), ("candidates/v2-c1-xs-sync-ra.json", "c1 record"),
        ("candidates/v2-c1c-xs-ra-safe.json", "c1c record and pre-registration"), ("candidates/v2-c1c-xs-ra-safe/static.json", "c1c static checks"),
        ("patches/v2-c1-xs-sync-ra.patch", "c1 patch"), ("patches/v2-c1c-xs-ra-safe.patch", "c1c patch"),
        ("report/audit.md", "audit"), ("report/c1-v2-c1-xs-sync-ra-round1.md", "round 1 review"),
        ("report/c1c-v2-c1c-xs-ra-safe-round2.md", "round 2 review"), ("report/dmesg-balloon-excerpt.txt", "balloon excerpt")]
for p, _ in EVID:
    assert git("cat-file", "-e", f"{REV}:{CAMP}/{p}", ok=True) == 0, p
def evidence_html(extra=""):
    li = "".join(f'<li><a href="{bp.esc(("" if p.startswith("report/") else "../") + p.replace("report/", ""))}">{bp.esc(p)}</a> — {bp.esc(d)}</li>' for p, d in EVID)
    return (f'<section id="audit-evidence"><details><summary><h2 style="display:inline">Evidence files</h2>'
            f'<span class="lead"> (repo-relative; evidence commit {FULLREV[:12]}{"" if PUSHED else ", not pushed yet"})</span></summary>'
            f'<ul>{li}</ul>{extra}</details></section>')

HOSTPAT = re.compile(r"/workspace|/home|/cursor|file://")
def render(spec, out_path, extra=""):
    page, budget_ = bp.build(spec)
    for err in budget_.errors:
        print("TEXT BUDGET: " + err, file=sys.stderr)
    if budget_.errors:
        raise SystemExit(1)
    css = EXTRA_CSS + (_story_css() if '<div class="story">' in page else "")
    page = page.replace("</style></head>", css + "</style></head>", 1)
    links = "".join(f'<a href="{bp.esc(l["href"])}">{bp.esc(l["label"])}</a>' for l in spec.get("links", []))
    page = page.replace("<nav>", "<nav>" + links, 1)
    def wrap(m):
        return (f'<section id="{m.group(1)}"><details><summary><h2 style="display:inline">{m.group(2)}</h2>'
                f'<span class="lead"> (evidence)</span></summary>{m.group(3)}</details></section>')
    page = re.sub(r'<section id="(audit-[^"]+)"><h2>(.*?)</h2>(.*?)</section>', wrap, page, flags=re.S)
    page = page.replace("</main>", evidence_html(extra) + "</main>", 1)
    if re.search(r'<(link|script)[^>]+(src|href)="https?://', page):
        raise SystemExit("external resource")
    hrefs = re.findall(r'href="([^"]*)"', page)
    bad = [h for h in hrefs if re.match(r"[a-z]+:|/", h)]
    if bad or HOSTPAT.search(page):
        raise SystemExit(f"non-relative link or host path: {bad[:3]} {HOSTPAT.findall(page)[:3]}")
    prose, svgw = visible_words(page)
    limit = bp.MAX_PAGE_WORDS - (SCRIPT_RESERVE if '<div class="story">' in page else 0)
    if prose > limit:
        raise SystemExit(f"VISIBLE TEXT {out_path.name}: {prose} words outside closed details and SVG (max {limit})")
    out_path.write_text(page, encoding="utf-8")
    print(f"wrote {out_path.name}: budget {budget_.words} words; visible prose {prose} (limit {limit}); SVG labels {svgw}")

R3_EXTRA = ('<p class="lead">Round-3 sources are in the run directory and the c1d proposal file, '
            'not in the bundle commit; they are cited by file name and line above.</p>')
for name, sp in (("explainer", spec), ("round1", r1), ("round2", r2), ("round3", r3)):
    js = json.dumps(sp, ensure_ascii=False, indent=1)
    assert not HOSTPAT.search(js), name
    (HERE / f"{name}.json").write_text(js)
sj = json.dumps(summary, ensure_ascii=False, indent=1); assert not HOSTPAT.search(sj)
(HERE / "summary.json").write_text(sj)
if "--specs-only" not in sys.argv:
    for name, sp in (("explainer", spec), ("round1", r1), ("round2", r2), ("round3", r3)):
        render(sp, HERE / f"{name}.html", R3_EXTRA if name == "round3" else "")
    shutil.copyfile(HERE / "explainer.html", HERE / "summary.html")  # published name; byte-identical to explainer.html
    print("summary.html = explainer.html")
