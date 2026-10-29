#!/usr/bin/env python3
"""Box-local generator for the round-1 DRAFT section. Reads evidence read-only; writes only round1.html.
Every rendered number goes through N()/T() with a data-src citing file + key. Missing values render as visible TODOs."""
import json, re, html, math, datetime, zoneinfo, pathlib
OUT = pathlib.Path(__file__).with_name("round1.html")
REPO = pathlib.Path("/workspace/Swap-Next-main")
CAMP = "campaigns/xswap-tcg-kbench-rev7-2026-10-29"
REV6 = "campaigns/xswap-tcg-kbench-2026-10-29"
RUNDIR = pathlib.Path("/workspace/runs/grok-cloud-tcg-rev7-20261029")
ARCH = pathlib.Path("/workspace/archive-20261029")
REVIEW = pathlib.Path("/workspace/reviews/c1-v2-c1-xs-sync-ra-round1.md")
STYLE_SRC = REPO / "campaigns/xswap-swapin-2026-10-23/report/explainer.html"
TZ = zoneinfo.ZoneInfo("America/Los_Angeles")
GH = "https://github.com/ericzhang-zxh/Swap-Next/blob/"
AB, WF, VT = ("ab800d776925269deafaffbfb2df61ffd34a1220", "9c1468ac2d5a4a8ef1a59de7003f434f17d5a9b5",
              "87dc7357eb798a161a0d299f73629d8c3ce85a44")
# Public citation aliases (no host paths in rendered text): rundir: = executor run dir, archive: = cleanup archive, review: = Swap Review file
def J(rel): return json.loads((REPO / rel).read_text())
def RJ(name): return json.loads((RUNDIR / name).read_text())
e = html.escape
TODOS = []
def N(v, src, fmt="{}"):
    if v is None:
        TODOS.append(src); return f'<span class="todo" data-src="{e(src)}">TODO(missing: {e(src)})</span>'
    return f'<span class="n" data-src="{e(src)}">{e(fmt.format(v))}</span>'
def T(unix, src):
    if unix is None: return N(None, src)
    return N(datetime.datetime.fromtimestamp(unix, TZ).strftime("%H:%M:%S"), src, "{} PDT")
def TODO(what): TODOS.append(what); return f'<span class="todo">TODO: {e(what)}</span>'
def link(path_at, label=None, commit=AB):
    return f'<a href="{GH}{commit}/{e(path_at)}">{e(label or path_at)}@{commit[:8]}</a>'

ledger = J(f"{CAMP}/ledger/ledger.json")
budget = J(f"{CAMP}/ledger/budget.json")
camp = J(f"{CAMP}/campaign.json")
rev6camp = J(f"{REV6}/campaign.json"); rev6budget = J(f"{REV6}/ledger/budget.json"); rev6ledger = J(f"{REV6}/ledger/ledger.json")
rc = J(f"{REV6}/runs/rescore/469ee19c-rev7-ab800d77-receipt.json")
probe = J(f"{CAMP}/ledger/calibration-probe.json"); fast = J(f"{CAMP}/ledger/calibration-fast.json")
EV = f"{CAMP}/runs/evaluations"
c1p = J(f"{EV}/3a554e3b19bd41bda52e877d37166e94/report.json"); c1f = J(f"{EV}/68de12e0b0c9471bb497a9f0dc844a3f/report.json")
ev16 = J(f"{EV}/16fe9d242ebb4609a14a13fc119ace56/report.json"); ev0c = J(f"{EV}/0c2cd749d6594a7b9c6c3576b97b3d25/report.json")
evb0 = J(f"{EV}/b0dcd6f7e55342dda3a4cf58ebdc65ef/report.json")
v1, v2 = RJ("void-receipt.json"), RJ("void-receipt-2.json")
corr = J(f"{CAMP}/runs/guests/c1-v2-c1-xs-sync-ra-correctness-1/result.json")
corrlog = RJ("c1-correctness.log")
policy = J(f"{CAMP}/policy.json")
import subprocess
def git(*a): return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True).stdout
rev6proto = J(f"{REV6}/protocol.json"); rev7proto = J(f"{CAMP}/protocol.json")
ev_old = git("show", "ab800d77~1:benchmark/swap-standard/evidence.py").splitlines()
ev_new = git("show", "ab800d77:benchmark/swap-standard/evidence.py").splitlines()
old_num_line = next((i+1 for i, l in enumerate(ev_old) if "-d.get('MemAvailable'" in l), None)
new_num_line = next((i+1 for i, l in enumerate(ev_new) if l.startswith("ATTRIBUTABLE_FIELDS")), None)
new_fields = re.findall(r'"(\w+)"', ev_new[new_num_line-1]) if new_num_line else None
main9b = git("ls-tree", "-r", "--name-only", "9b4e3fe").splitlines()
main_tip = git("rev-parse", "origin/main").strip()
main_tip_tree = git("ls-tree", "-r", "--name-only", "origin/main").splitlines()
legacy_hits_9b = [f for f in main9b if "xswap-tcg-r3-2026-10-24" in f or "protocol-tcg-revision3" in f]
legacy_hits_tip = [f for f in main_tip_tree if "xswap-tcg-r3-2026-10-24" in f or "protocol-tcg-revision3" in f]
unmerged = {c: subprocess.run(["git", "-C", str(REPO), "merge-base", "--is-ancestor", c, "origin/main"]).returncode != 0 for c in ("ab800d77", "9c1468ac", "87dc7357")}
DM = pathlib.Path(__file__).with_name("dmesg-balloon-excerpt.txt").read_text().splitlines()
dm_raw = [l for l in DM if re.match(r"\d+:\[", l)]; dm_t = [l for l in DM if l.startswith("[Thu")]
dm_total = next((int(l.rsplit(" ", 1)[1]) for l in DM if l.startswith("# total")), None)
summary_txt = (RUNDIR / "c1-fast-summary.txt").read_text()
archlog = (ARCH / "LOG.txt").read_text().splitlines()
_full_archlog = archlog
_cut = next(i for i, l in enumerate(archlog) if l.endswith("DONE run3")) + 3  # pre-rev7 cleanup only; later lines belong to other work
archlog = archlog[:_cut]
late_arch = [l for l in _full_archlog[_cut:] if l[:4] == "2026"]
removed = [l.split("\t") for l in (ARCH / "removed.tsv").read_text().splitlines() if l.strip()]
_r1_archives = "\n".join(archlog)
removed = [r for r in removed if r[2] in _r1_archives]  # round-1 era rows only; later rows (c1b/c2/c1c/c1 worktree) are reported in summary.html
res_dir = REPO / CAMP / "ledger/guest-reservations"
reservations = sorted(p.stem for p in res_dir.glob("*.json"))

P_FAST = f"{EV}/68de12e0b0c9471bb497a9f0dc844a3f/report.json"
P_PROBE = f"{EV}/3a554e3b19bd41bda52e877d37166e94/report.json"
P_CALP = f"{CAMP}/ledger/calibration-probe.json"; P_CALF = f"{CAMP}/ledger/calibration-fast.json"
P_RC = f"{REV6}/runs/rescore/469ee19c-rev7-ab800d77-receipt.json"

# ---------- derived counts (all from files) ----------
def count_prefix(pfx): return sum(1 for r in reservations if r.startswith(pfx))
groups = [("86fc2f67 probe calibration", "86fc2f67", "probe"), ("16fe9d24 fast calibration (BLOCKED, voided)", "16fe9d24", "fast"),
          ("0c2cd749 fast calibration (INCOMPLETE, voided)", "0c2cd749", "fast"), ("e8b7a7e3 fast calibration", "e8b7a7e3", "fast"),
          ("c1 correctness proof", "c1-v2-c1-xs-sync-ra-correctness", "fast"), ("3a554e3b c1 probe", "3a554e3b", "probe"),
          ("68de12e0 c1 fast", "68de12e0", "fast")]
gcounts = {g[1]: count_prefix(g[1]) for g in groups}
res_total = len(reservations)
fast_res = sum(gcounts[g[1]] for g in groups if g[2] == "fast"); probe_res = sum(gcounts[g[1]] for g in groups if g[2] == "probe")
fast_cap, probe_cap = camp["budget"]["guest_attempts"], camp["budget"]["probe_guest_attempts"]
rev7_total = budget["guests"] + budget["probe_guests"]
rev6_total = rev6budget["guests"] + rev6budget["probe_guests"]
fast_invalid = [r for r in fast["runs"] if not r["run_valid"]]

def fmt_ratio(x): return f"{x:.3f}"
CSS = re.search(r"<style>(.*?)</style>", STYLE_SRC.read_text(), re.S).group(1)
EXTRA = """.todo{background:var(--warning);color:#1f1b16;padding:0 4px;border-radius:4px;font-weight:600}
.notrun{border:2px solid var(--critical);border-radius:12px;padding:14px 18px;margin:16px 0;background:color-mix(in srgb,var(--critical) 8%,var(--surface-1))}
.notrun h3{margin:0 0 6px;color:var(--critical)}.draft{border:2px dashed var(--serious);padding:8px 12px;border-radius:8px;margin:0 0 12px;font-size:13px}
.st-pass{color:var(--good);font-weight:600}.st-fail{color:var(--critical);font-weight:600}.st-warn{color:var(--serious);font-weight:600}
.flowrow{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0}.box{border:1px solid var(--ring);border-radius:8px;padding:6px 10px;background:var(--page);font-size:13px}
.box.focus{background:var(--focus);border-color:var(--series-1)}.box.muted{opacity:.55}.arrow{color:var(--muted)}
code{font-size:12.5px}td,th{vertical-align:top}"""

def section(id_, title, lead, body, src=''):
    return f'<section id="{id_}"><h2 data-src="{e(src)}">{e(title)}</h2><p class="lead">{lead}</p>{body}</section>'
def details(summary, body, cls=""): return f'<details class="{cls}"><summary>{e(summary)}</summary>{body}</details>'
def table(cols, rows, numeric=()):
    h = "".join(f'<th class="{"num" if i in numeric else ""}">{e(c)}</th>' for i, c in enumerate(cols))
    b = "".join("<tr>" + "".join(f'<td class="{"num" if i in numeric else ""}">{c}</td>' for i, c in enumerate(r)) + "</tr>" for r in rows)
    return f"<table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>"

# ---------- strip chart of c1 pair ratios (log scale) ----------
def strip_svg():
    m = c1f["analysis"]["metrics"]; names = list(m.keys())
    W, rowh, left, right = 760, 30, 250, 20; H = rowh * len(names) + 50
    lo, hi = math.log(0.4), math.log(3.6)
    X = lambda v: left + (math.log(v) - lo) / (hi - lo) * (W - left - right)
    s = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="c1 per-pair base/candidate ratios">']
    for t in (0.5, 0.75, 1, 1.5, 2, 3):
        s.append(f'<line x1="{X(t):.1f}" x2="{X(t):.1f}" y1="10" y2="{H-30}" stroke="var(--{"axis" if t==1 else "grid"})" stroke-width="{2 if t==1 else 1}"/>'
                 f'<text x="{X(t):.1f}" y="{H-14}" text-anchor="middle">{t}</text>')
    s.append(f'<text class="axis-label" x="{left}" y="{H-1}">base/candidate latency ratio (log scale; &gt;1 = candidate faster; 1 = no change)</text>')
    for i, k in enumerate(names):
        y = 22 + i * rowh; v = m[k]; adv = v.get("advisory"); gp = v["guard_pass"]
        lab = k.replace("swapin-", "").replace("_ns", "") + (" (advisory)" if adv else "")
        col = "var(--critical)" if not gp else ("var(--series-2)" if adv else "var(--series-1)")
        s.append(f'<text x="{left-8}" y="{y+4}" text-anchor="end">{e(lab)}</text>')
        for j, r in enumerate(v["pair_ratios"]):
            s.append(f'<g class="hit" tabindex="0" data-v="{r:.3f}" data-l="{e(k)} pair {j} ({c1f["pairs"][j]["order"]}); src {P_FAST} analysis.metrics[{e(k)}].pair_ratios[{j}]">'
                     f'<circle class="mark" cx="{X(r):.1f}" cy="{y}" r="5" fill="{col}" fill-opacity=".8"/></g>')
        md = v["median_ratio"]
        s.append(f'<line x1="{X(md):.1f}" x2="{X(md):.1f}" y1="{y-9}" y2="{y+9}" stroke="var(--ink)" stroke-width="2"><title>median {md:.3f}</title></line>')
    s.append("</svg>"); return "".join(s)

def noise_svg():
    nr = fast["analysis"]["noise_relative"]; ceil = fast["analysis"]["noise_ceiling"]; floor = fast["analysis"]["noise_floor"]
    W, rowh, left = 760, 26, 250; H = rowh * len(nr) + 44; X = lambda v: left + v / 0.3 * (W - left - 20)
    s = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="A/A noise envelope">']
    for t in (0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3):
        s.append(f'<line x1="{X(t):.1f}" x2="{X(t):.1f}" y1="6" y2="{H-30}" stroke="var(--grid)"/><text x="{X(t):.1f}" y="{H-14}" text-anchor="middle">{t:g}</text>')
    s.append(f'<line x1="{X(ceil):.1f}" x2="{X(ceil):.1f}" y1="6" y2="{H-30}" stroke="var(--critical)" stroke-dasharray="4 3"><title>noise_ceiling {ceil}</title></line>')
    s.append(f'<line x1="{X(floor):.1f}" x2="{X(floor):.1f}" y1="6" y2="{H-30}" stroke="var(--muted)" stroke-dasharray="2 3"><title>noise_floor {floor}</title></line>')
    for i, (k, v) in enumerate(nr.items()):
        y = 18 + i * rowh
        s.append(f'<text x="{left-8}" y="{y+4}" text-anchor="end">{e(k.replace("swapin-","").replace("_ns",""))}</text>')
        s.append(f'<g class="hit" tabindex="0" data-v="{v:.4f}" data-l="p90 noise_relative; src {P_CALF} analysis.noise_relative[{e(k)}]"><rect class="mark" x="{left}" y="{y-7}" width="{X(v)-left:.1f}" height="14" rx="3" fill="var(--series-1)" fill-opacity=".75"/></g>')
    s.append(f'<text class="axis-label" x="{left}" y="{H-1}">p90 relative A/A noise (dashed red = ceiling {ceil}, dotted = floor {floor})</text></svg>')
    return "".join(s)

# ---------- build ----------
A = c1f["analysis"]; M = A["metrics"]
k_dseq, k_zseq = "swapin-disk.swapin_seq.mean_ns", "swapin-zram-64k.swapin_seq.mean_ns"
k_zp99 = "swapin-zram-64k.swapin_seq.p99_ns"
m_sum = {}
for line in summary_txt.splitlines():
    mm = re.match(r"(\S+) (swapin_\w+) base.*mean rel change ([+-][\d.]+%) 95% t-CI \(log ratio, n=4\) \[([^\]]+)\]", line)
    if mm: m_sum[f"{mm.group(1)}.{mm.group(2)}"] = (mm.group(3), mm.group(4))
H = []
H.append('<div class="draft"><b>DRAFT — box-local, not published, not committed.</b> Round-1 section for the campaign report. '
         'Hover any number: <code>data-src</code> names the evidence file and key. Prefixes: <code>campaigns/…</code> = Swap-Next checkout (repo-relative); '
         '<code>rundir:</code> = executor run directory; <code>archive:</code> = cleanup archive; <code>review:</code> = Swap Review file; <code>drafts:</code> = captured excerpts saved next to this draft. '
         'Untracked evidence has no pinned commit yet: ' + TODO("pin evidence links to the bundle commit once the final PR exists") + '</div>')

# Verdict
gates = policy["required_gates"]
status_of = {"checkpatch": ("PASS", "candidates/v2-c1-xs-sync-ra/static.json checkpatch.exit_code=0"),
             "gcc_swap_on": ("BUILT (reused)", "correctness.build_manifest benchmark/kernel/builds/std-31eb4618eae8/result.json (not re-verified here)"),
             "guest_boot_identity": ("PASS", f"rundir:c1-correctness.log gates.boot={corrlog['gates']['boot']}, gates.cmdline_identity={corrlog['gates']['cmdline_identity']}")}
for g in ("data_roundtrip", "fork_cow", "concurrent_fault", "swapoff_live_pages", "no_new_kernel_warnings"):
    status_of[g] = ("PASS (disk only)", f"runs/guests/c1-v2-c1-xs-sync-ra-correctness-1/result.json gates.{g}={corrlog['gates'].get(g)}")
notrun = [g for g in gates if g not in status_of]
tiles = [("Swap Review", "NEEDS-MORE-EVIDENCE", "fail-closed; review: verdict line"),
         ("c1 fast screen", N(c1f["status"], P_FAST + " status"), "non-regression screen, not an acceptance"),
         ("Disk sequential", N(M[k_dseq]["median_ratio"], P_FAST + f" analysis.metrics[{k_dseq}].median_ratio", "{:.3f}×"), "TCG-only effect; no KVM arm"),
         ("zram sequential", N(M[k_zseq]["median_ratio"], P_FAST + f" analysis.metrics[{k_zseq}].median_ratio", "{:.3f}×"), "unresolved: one pair a loss"),
         ("zram seq p99", N(M[k_zp99]["median_ratio"], P_FAST + f" analysis.metrics[{k_zp99}].median_ratio", "{:.3f}×"), "guard_pass false (advisory) — a regression"),
         ("Formal gates", N(f"{len(notrun)} of {len(gates)}", CAMP+"/policy.json required_gates minus gates with evidence", "{} NOT RUN"), "policy.json required_gates")]
tile_html = "".join(f'<div class="tile"><div class="label">{e(a)}</div><div class="value" style="font-size:20px">{b}</div><div class="note">{e(c)}</div></div>' for a, b, c in tiles)
H.append(f'<div class="card"><div class="verdict"><span class="badge"><i class="dot" style="background:var(--warning)"></i>Needs more evidence</span>'
         f'<span>Round 1: c1 passes the screen; not accepted, not a parent yet</span></div><div class="tiles">{tile_html}</div>'
         f'<p class="lead" style="margin-top:12px">Workflow: performance_accepted {N(A["performance_accepted"], P_FAST+" analysis.performance_accepted")}, '
         f'auto_promote {N(A["auto_promote"], P_FAST+" analysis.auto_promote")}, eligible_for_slow {N(A["eligible_for_slow"], P_FAST+" analysis.eligible_for_slow")}. '
         f'rev7 has no slow tier, so there is no next tier to accept into (review: Verdict). Process caveat: rev7 is an unmerged proposal (PR #8, open) and the void tool branch has no PR; '
         f'until the owner confirms rev7, every rev7 verdict is diagnostic only (review: Process).</p></div>')

# NOT RUN banner (gates)

H.append(f'<div class="notrun"><h3>Formal gates NOT RUN: {N(len(notrun), CAMP+"/policy.json required_gates minus gates with evidence")} of {N(len(gates), CAMP+"/policy.json len(required_gates)")}</h3>'
         f'<p>{", ".join("<b>"+e(g)+"</b>" for g in notrun)}. No sparse, KASAN, KCSAN, lockdep, fault-injection, memcg-limit, large-folio, swap-off or zswap-on build evidence exists for c1. '
         f'The protocol correctness gates ran once, on the disk backend only, with zswpout {N(corr["metrics"]["vmstat_delta"]["zswpout"], CAMP+"/runs/guests/c1-v2-c1-xs-sync-ra-correctness-1/result.json metrics.vmstat_delta.zswpout")} (zswap-mixed path not exercised). No acceptance claim is possible.</p></div>')

prov = (f'<div class="card"><p class="chart-title">Code provenance — all three commits unmerged; one fingerprint throughout</p><ul>'
  f'<li><b>ab800d77</b> (rev7 protocol, PR #8 open): rev6 close, rev7 open, probe calibration 86fc2f67 and fast attempt 16fe9d24 (rundir:LOG.md lines 1–9), plus the 469ee19c re-score receipt.</li>'
  f'<li><b>9c1468ac</b> (void branch, no PR): checked out at 11:20 PDT (rundir:LOG.md line 11); everything after — void a7930c57, attempt 0c2cd749, fast calibration e8b7a7e3, c1 correctness, probe 3a554e3b, fast 68de12e0.</li>'
  f'<li><b>87dc7357</b> (same branch): only void_calibration.py, extracted to run void 820fdc14 with the 9c1468ac checkout on PYTHONPATH (rundir:LOG.md lines 15–16; extracted file sha256 6980e69a… = git blob).</li>'
  f'<li>Fingerprint <code>{N(ledger[0]["fingerprint"][:8], CAMP+"/ledger/ledger.json [*].fingerprint (one distinct value)")}</code> on all {N(len(ledger), CAMP+"/ledger/ledger.json len")} ledger rows; the void tool is outside it.</li>'
  f'<li>Unmerged into origin/main: ab800d77 {N(unmerged["ab800d77"], "git merge-base --is-ancestor ab800d77 origin/main (nonzero)")}, 9c1468ac {N(unmerged["9c1468ac"], "git merge-base …")}, 87dc7357 {N(unmerged["87dc7357"], "git merge-base …")}.</li></ul></div>')
H.append(prov)

# System -> subsystem -> change
H.append(section("system", "Where c1 sits: system → subsystem → change", "Schematic, not measured. Hypothesis wording from the candidate record; the cost shift is the reviewer's inference.",
  '<div class="card"><p class="chart-title">1 · Whole system — an application touches a page that was swapped out</p><div class="flowrow"><span class="box">application access</span><span class="arrow">→</span><span class="box">page fault</span><span class="arrow">→</span><span class="box focus">swap-in path (mm/swap_state.c)</span><span class="arrow">→</span><span class="box">backend: disk (async I/O) or zram-64k (synchronous decompress)</span></div>'
  '<p class="chart-title">2 · Subsystem — swap-in readahead</p><div class="flowrow"><span class="box">fault on xswap slot</span><span class="arrow">→</span><span class="box muted">before: xswap skipped readahead at device level; one page per fault</span></div>'
  '<div class="flowrow"><span class="box">fault on xswap slot</span><span class="arrow">→</span><span class="box focus">after c1: order-0, non-shmem, page_cluster&gt;0, adjacent to the VMA\'s last fault → readahead path</span><span class="arrow">→</span><span class="box focus">per-entry filter <code>xswap_readahead_wanted</code> picks neighbours</span></div>'
  '<p class="chart-title">3 · Change — what moves</p><p>Benefit: neighbours are already in the swap cache, so later sequential faults become cache hits (counter <code>swap_ra</code> rises from a baseline band near zero; see the probe in section 5). '
  'Cost (inference, review: Design observations): on a synchronous backend (zram) the faulting task decompresses the whole window before returning — consistent with a lower mean and a higher p99. '
  'Also: speculative neighbour reads now reach slots that previously saw only demand faults (open SIGBUS assumption, review: Unresolved assumption 1). c1 is a single candidate whose parent is the baseline (not stacked).</p>'
  + details("Candidate record (exact)", f'<p>Candidate <code>v2-c1-xs-sync-ra</code>, commit <code>{N(c1f["candidate_commit"][:12], P_FAST+" candidate_commit")}</code>, parent <code>{N(c1f["parent_comparison"]["parent_commit"][:12], P_FAST+" parent_comparison.parent_commit")}</code>, '
            f'changed paths {N(", ".join(c1f["controller_check"]["changed_paths"]), P_FAST+" controller_check.changed_paths")}, changed lines {N(c1f["controller_check"]["changed_lines"], P_FAST+" controller_check.changed_lines")}, '
            f'mechanism <code>{N(c1f["mechanism"], P_FAST+" mechanism")}</code>. Patch: <code>{CAMP}/patches/v2-c1-xs-sync-ra.patch</code>. Lineage (review): H6/H7 line — not cited in the candidate record.</p>') + '</div>'))

# 1 rev6 closure + rescore
rev6v = [x["metadata_delta_bytes_per_capacity_slot"] for x in rev6ledger[0]["probe_signals"]["metadata-brd"]]
mb = rc["outputs"]["metadata_band"]
body = (f'<div class="card"><p>rev6 campaign <code>xswap-tcg-kbench-2026-10-29</code>: status {N(rev6camp["status"], REV6+"/campaign.json status")}, closed {N(rev6camp["closed"], REV6+"/campaign.json closed")}. '
        f'Its only ledger row, probe calibration 469ee19c, was {N(rev6ledger[0]["status"], REV6+"/ledger/ledger.json [0].status")} '
        f'({N("; ".join(rev6ledger[0]["analysis"]["reasons"]), REV6+"/ledger/ledger.json [0].analysis.reasons")}); metadata-brd values '
        f'{", ".join(N(v, REV6+f"/ledger/ledger.json [0].probe_signals.metadata-brd[{i}].metadata_delta_bytes_per_capacity_slot", "{:.5f}") for i, v in enumerate(rev6v))} bytes/slot. '
        f'rev6 spent {N(rev6budget["probe_guests"], REV6+"/ledger/budget.json probe_guests")} probe and {N(rev6budget["guests"], REV6+"/ledger/budget.json guests")} fast guests. '
        f'Close reason (per coordinator, 2026-10-29; the close command itself recorded only a placeholder, rundir:LOG.md line 1): rev6\'s metadata-brd numerator was −ΔMemAvailable '
        f'(evidence.py L{N(old_num_line, "git ab800d77~1:benchmark/swap-standard/evidence.py (used_kib = -MemAvailable)")} before ab800d77), which made the probe calibration NOISY. '
        f'rev7 (PR #8, commit ab800d77) scores Δ({N("+".join(new_fields) if new_fields else None, "git ab800d77:benchmark/swap-standard/evidence.py ATTRIBUTABLE_FIELDS")}) per capacity slot '
        f'(protocol numerator {N(rev7proto["cases"]["metadata-brd"]["metadata_accounting"]["numerator"], CAMP+"/protocol.json cases.metadata-brd.metadata_accounting.numerator")}), keeping the same band '
        f'{N(rev6proto["probe_band"]["metadata_spread_fraction"], REV6+"/protocol.json probe_band.metadata_spread_fraction")} → {N(rev7proto["probe_band"]["metadata_spread_fraction"], CAMP+"/protocol.json probe_band.metadata_spread_fraction")} '
        f'and ceiling {N(rev6proto["noise_ceiling"], REV6+"/protocol.json noise_ceiling")} → {N(rev7proto["noise_ceiling"], CAMP+"/protocol.json noise_ceiling")}. '
        f'A rev7 re-score could not be adopted into rev6, so rev6 was closed and rev7 opened with a fresh probe calibration.</p>'
        f'<div class="callout"><p><b>Rescore receipt — evidence only, not a decision.</b> Guest-free re-score of the same {N(len(rc["inputs"]), P_RC+" len(inputs)")} rev6 results with the rev7 metadata numerator '
        f'(rev7 commit <code>{N(rc["rev7_commit"][:8], P_RC+" rev7_commit")}</code>): verdict {N(rc["verdict"], P_RC+" verdict")}, band '
        f'{N(mb["low"], P_RC+" outputs.metadata_band.low", "{:.6f}")}–{N(mb["high"], P_RC+" outputs.metadata_band.high", "{:.6f}")} (median {N(mb["median"], P_RC+" outputs.metadata_band.median", "{:.6f}")}, n={N(mb["n"], P_RC+" outputs.metadata_band.n")}). '
        f'Same inputs under rev6 rules: {N(rc["rev6_recheck_same_inputs"]["status"], P_RC+" rev6_recheck_same_inputs.status")}. New guests: {N(rc["guests"], P_RC+" guests")}; ledger_modified {N(rc["ledger_modified"], P_RC+" ledger_modified")}; '
        f'performance_accepted {N(rc["full_calibration"]["performance_accepted"], P_RC+" full_calibration.performance_accepted")}. '
        f'Adoption: {N(rc["workflow_adoption"].split(".")[0], P_RC+" workflow_adoption")} — the ledger has no re-score/adopt action, so rev7 ran its own probe calibration (next section).</p></div></div>')
H.append(section("rev6", "1 · rev6 closed; the rev7 re-score is a receipt, not a calibration", "The rev6 probe calibration was noisy on metadata; rev7 changed the metadata numerator.", body))

# 2 probe calibration
pb = probe["analysis"]["bands"]
rows = []
for c, b in pb.items():
    for mname, v in b.items():
        src = P_CALP + f" analysis.bands[{c}][{mname}]"
        rows.append([e(c), f"<code>{e(mname)}</code>", N(v["low"], src+".low", "{:g}"), N(v["high"], src+".high", "{:g}"), N(v["median"], src+".median", "{:g}")])
walls = [N(r["wall_seconds"], P_CALP+f" runs[{i}].wall_seconds", "{:.1f} s") for i, r in enumerate(probe["runs"])]
md = pb["metadata-brd"]["metadata_delta_bytes_per_capacity_slot"]
H.append(section("probe-cal", "2 · Probe calibration 86fc2f67: calibrated, metadata now stable", "Three baseline runs per probe case set the counter bands that candidate probes are checked against.",
  f'<div class="card"><p>Eval <code>{N(probe["id"][:8], P_CALP+" id")}</code> status {N(probe["status"], P_CALP+" status")} (reasons: {N(len(probe["analysis"]["reasons"]), P_CALP+" len(analysis.reasons)")}), '
  f'{N(len(probe["runs"]), P_CALP+" len(runs)")} guests, all {N(sum(r["status"]=="PASS" and r["run_valid"] for r in probe["runs"]), P_CALP+" runs[].status==PASS && run_valid")} PASS and valid. '
  f'Wall {T(probe["started"], P_CALP+" started")} → {T(probe["finished"], P_CALP+" finished")} ({N(probe["finished"]-probe["started"], P_CALP+" finished-started", "{:.0f} s")}). '
  f'metadata-brd band {N(md["low"], P_CALP+" analysis.bands.metadata-brd.*.low", "{:.6f}")}–{N(md["high"], P_CALP+" analysis.bands.metadata-brd.*.high", "{:.6f}")}, median {N(md["median"], P_CALP+" analysis.bands.metadata-brd.*.median", "{:.6f}")} '
  f'(min {N(md["minimum"], P_CALP+" …minimum", "{:.6f}")}, max {N(md["maximum"], P_CALP+" …maximum", "{:.6f}")}). Protocol revision {N(probe["protocol_revision"], P_CALP+" protocol_revision")}, fingerprint <code>{N(probe["fingerprint"][:8], P_CALP+" fingerprint")}</code>, '
  f'run at commit ab800d77 (before 9c1468ac existed; rundir:LOG.md line 3–4).</p>'
  + details("All probe bands (exact)", table(["case", "counter", "low", "high", "median"], rows, (2, 3, 4)))
  + details("Per-guest walls", "<p>" + ", ".join(walls) + "</p>") + '</div>'))

# 3 fast calibration
nr, nl = fast["analysis"]["noise_relative"], fast["analysis"]["noise_log"]
nrows = [[f"<code>{e(k)}</code>", N(nr[k], P_CALF+f" analysis.noise_relative[{k}]", "{:.4f}"), N(nl[k], P_CALF+f" analysis.noise_log[{k}]", "{:.4f}"),
          ("advisory" if k in fast["analysis"]["advisory_metrics"] else ("primary" if k in fast["analysis"]["primary"] else "guard"))] for k in nr]
inv_rows = [[e(r["id"].split("-", 1)[1]), N(r["status"], P_CALF+f" runs[id={r['id']}].status"), N(r["invalid_reason"], P_CALF+f" runs[id={r['id']}].invalid_reason"),
             N(r["clocksource_invalid"], P_CALF+f" runs[id={r['id']}].clocksource_invalid"), N(r["wall_seconds"], P_CALF+f" runs[id={r['id']}].wall_seconds", "{:.1f} s")] for r in fast_invalid]
assert len(fast_invalid)==3 and len(fast["runs"])==43
H.append(section("fast-cal", f"3 · Fast calibration e8b7a7e3: {len(fast['runs'])} guests, calibrated after {len(fast_invalid)} validity reruns", "Ten baseline A/A pairs set the noise envelope that candidate ratios must clear.",
  f'<div class="card"><p>Eval <code>{N(fast["id"][:8], P_CALF+" id")}</code> {N(fast["status"], P_CALF+" status")}: {N(len(fast["runs"]), P_CALF+" len(runs)")} guests = '
  f'{N(fast["analysis"]["pair_count"], P_CALF+" analysis.pair_count")} pairs × 4 + {N(len(fast_invalid), P_CALF+" count(runs[].run_valid==false)")} reruns. '
  f'Wall {T(fast["started"], P_CALF+" started")} → {T(fast["finished"], P_CALF+" finished")} ({N((fast["finished"]-fast["started"])/60, P_CALF+" finished-started", "{:.0f} min")}). '
  f'Envelope {N(fast["analysis"]["envelope"], P_CALF+" analysis.envelope")}, ceiling {N(fast["analysis"]["noise_ceiling"], P_CALF+" analysis.noise_ceiling")}, floor {N(fast["analysis"]["noise_floor"], P_CALF+" analysis.noise_floor")}, rejected metrics {N(len(fast["analysis"]["rejected_metrics"]), P_CALF+" len(analysis.rejected_metrics)")}.</p>'
  f'<p class="chart-title">zram is about {N(nr[k_zseq]/nr[k_dseq], 'derived: '+P_CALF+' noise_relative[zram seq.mean]/noise_relative[disk seq.mean]', '{:.1f}')}× noisier than disk on the primary sequential metric</p>'
  f'<div class="visual-scroll">{noise_svg()}</div>'
  f'<p>The three invalid attempts are retained in the row. The run log attributes them to two box stalls (~{N('11:58–12:00', 'rundir:LOG.md line 19')} and ~{N('12:14–12:19', 'rundir:LOG.md line 20')} PDT) — that attribution is the executor\'s inference from monitor gaps (rundir:LOG.md lines 19–20), the workflow records only the reasons below.</p>'
  + f'<div class="callout"><p><b>Ledger is authoritative; run log flagged.</b> rundir:LOG.md line 21 calls 2-swapin-disk-a-r1 “run_valid but workflow INVALID”; the ledger has run_valid {N([r for r in fast["runs"] if r["id"].endswith("2-swapin-disk-a-r1")][0]["run_valid"], P_CALF+" runs[id=…2-swapin-disk-a-r1].run_valid")}.</p></div>'
  + details("Invalid attempts (retained)", table(["run", "status", "invalid_reason", "clocksource_invalid", "wall"], inv_rows, (4,)))
  + details("Noise envelope (exact)", table(["metric", "noise_relative (p90)", "noise_log", "role"], nrows, (1, 2))) + '</div>'))

# 4 incidents
H.append(section("incidents", "4 · Two incidents, two voided fast-calibration attempts", "Both voids discard attempts that carried no scorable data; both were before c1 existed.",
  f'<div class="card"><p class="chart-title">Watchdog false-STOP → void <code>{N(v1["id"][:8], "rundir:void-receipt.json id")}</code></p>'
  f'<p>Attempt <code>{N(v1["attempt_id"][:8], "rundir:void-receipt.json attempt_id")}</code> ended {N(v1["attempt_status"], "rundir:void-receipt.json attempt_status")} (“{N(v1["attempt_reason"], "rundir:void-receipt.json attempt_reason")}”) after '
  f'{N(len(v1["guests"]), "rundir:void-receipt.json len(guests)")} guests, all {N(sum(g["status"]=="PASS" and g["run_valid"] for g in v1["guests"]), "rundir:void-receipt.json guests[].status==PASS&&run_valid")} PASS and valid. '
  f'Receipt reason: “{N(v1["reason"], "rundir:void-receipt.json reason")}” The executor\'s watchdog read an empty cmdline of an exiting QEMU and touched the campaign STOP (rundir:watchdog.log, {N('10:46:34', 'rundir:watchdog.log line 20')} PDT); the STOP was renamed, not deleted, to <code>STOP.watchdog-falsepositive-20261029T1046</code>. '
  f'A rerun under the same fingerprint was then refused by the frozen retry gate (eval <code>{N(evb0["id"][:8], EV+"/b0dcd6f7…/report.json id")}</code> {N(evb0["status"], EV+"/b0dcd6f7…/report.json status")}: “{N(evb0["reason"], EV+"/b0dcd6f7…/report.json reason")}”). '
  f'Void recorded {T(v1["recorded"], "rundir:void-receipt.json recorded")} by the tool at {link("evolve/control/void_calibration.py", "void_calibration.py", WF)}.</p>'
  f'<p class="chart-title">Host-RAM refusal (“RAM balloon”) → void <code>{N(v2["id"][:8], "rundir:void-receipt-2.json id")}</code></p>'
  f'<p>Attempt <code>{N(v2["attempt_id"][:8], "rundir:void-receipt-2.json attempt_id")}</code> {N(v2["attempt_status"], "rundir:void-receipt-2.json attempt_status")} (“{N(v2["attempt_reason"], "rundir:void-receipt-2.json attempt_reason")}”): '
  f'{N(len(v2["guests"]), "rundir:void-receipt-2.json len(guests)")} guest reserved, preflight message “{N(v2["preflight"][0]["message"], "rundir:void-receipt-2.json preflight[0].message")}”, guest_directory {N(v2["preflight"][0]["guest_directory"], "rundir:void-receipt-2.json preflight[0].guest_directory")} — no QEMU started. '
  f'Cause: <b>likely virtio_balloon</b> — the box kernel log shows “virtio_balloon virtio0: Out of puff!” at {N(dm_t[0][12:20] if dm_t else None, "drafts:dmesg-balloon-excerpt.txt (dmesg -T, line "+(dm_raw[0].split(":")[0] if dm_raw else "?")+")")} and {N(dm_t[1][12:20] if len(dm_t)>1 else None, "drafts:dmesg-balloon-excerpt.txt (dmesg -T)")} PDT, about a minute before the refusal, '
  f'and {N(len([l for l in dm_t if " 11:43:" in l]), "drafts:dmesg-balloon-excerpt.txt count(11:43)")} more around 11:43 PDT ({N(dm_total, "drafts:dmesg-balloon-excerpt.txt total")} such lines since box boot, so it is a recurring box condition, not a one-off). dmesg -T wall times are approximate. '
  f'The receipt words it more strongly than this evidence supports: “{N(v2["reason"], "rundir:void-receipt-2.json reason")}” '
  f'Void recorded {T(v2["recorded"], "rundir:void-receipt-2.json recorded")} with the tool extracted from {link("evolve/control/void_calibration.py", "void_calibration.py", VT)} while the workflow checkout stayed at 9c1468ac (mixed code; the void tool is outside the fingerprint).</p>'
  f'<div class="callout"><p><b>What a void does (from code).</b> The tool sets <code>execution_started=False</code> and <code>void_receipt</code> on the original row and appends the receipt (void_calibration.py L185–188 @9c1468ac). '
  f'In the ledger the two original rows now read execution_started {N(ledger[1]["execution_started"], CAMP+"/ledger/ledger.json [1].execution_started")} / {N(ledger[4]["execution_started"], CAMP+"/ledger/ledger.json [4].execution_started")}; '
  f'the receipts preserve the original value {N(v1["execution_started"], "rundir:void-receipt.json execution_started")} / {N(v2["execution_started"], "rundir:void-receipt-2.json execution_started")}. '
  f'Voided guests still count against the budget (section 7). The review flags the tool as unreviewed core code written after the failures it voids (no PR for its branch).</p></div></div>'))

# 5 c1
cr = corrlog; mrows = []
for k, v in M.items():
    src = P_FAST + f" analysis.metrics[{k}]"
    gp = v["guard_pass"]
    ms = m_sum.get(k.replace("swapin-disk.", "swapin-disk ").replace("swapin-zram-64k.", "swapin-zram-64k ").replace(" ", ".")) if False else None
    mrows.append([f"<code>{e(k)}</code>", N(v["median_ratio"], src+".median_ratio", "{:.3f}"), N(v["geomean_ratio"], src+".geomean_ratio", "{:.3f}"),
                  " / ".join(N(r, src+f".pair_ratios[{i}]", "{:.3f}") for i, r in enumerate(v["pair_ratios"])),
                  N(v["noise_relative"], src+".noise_relative", "{:.4f}"),
                  f'<span class="{"st-pass" if gp else "st-fail"}">{N(gp, src+".guard_pass")}</span>' + (" (advisory)" if v.get("advisory") else "")])
ps = c1p["analysis"]["probe_signals"]
def sig(case, k): return N(ps[case][k][0], P_PROBE+f" analysis.probe_signals[{case}][{k}][0]")
def band(case, k):
    b = probe["analysis"]["bands"][case][k]; s = P_CALP+f" analysis.bands[{case}][{k}]"
    return f'{N(b["low"], s+".low", "{:g}")}..{N(b["high"], s+".high", "{:g}")}'
prow = []
for case in ("swapin-disk", "swapin-zram-64k"):
    for k in ("swapin_vmstat_delta.swap_ra", "swapin_vmstat_delta.swap_ra_hit", "swapin_vmstat_delta.pgmajfault", "swapin_vmstat_delta.pswpin", "xswap.clusters_mapped"):
        prow.append([e(case), f"<code>{e(k)}</code>", sig(case, k), band(case, k)])
prow.append(["metadata-brd", "<code>metadata_delta_bytes_per_capacity_slot</code>", sig("metadata-brd", "metadata_delta_bytes_per_capacity_slot"), band("metadata-brd", "metadata_delta_bytes_per_capacity_slot")])
pairs_rows = []
for i, p in enumerate(c1f["pairs"]):
    pairs_rows.append([N(i, P_FAST+f" pairs[{i}]"), N(p["order"], P_FAST+f" pairs[{i}].order")] +
                      [N(p[s][k]/1000, P_FAST+f" pairs[{i}].{s}[{k}] /1000", "{:.1f}") for k in (k_dseq, k_zseq) for s in ("a", "b")])
sum_rows = []
for line in summary_txt.splitlines():
    mm = re.match(r"(\S+) (swapin_\w+) base.*median delta (-?\d+) mean rel change ([+-][\d.]+%) 95% t-CI \(log ratio, n=4\) \[([^\]]+)\]", line)
    if mm: sum_rows.append([e(mm.group(1)), e(mm.group(2)), N(mm.group(3), "rundir:c1-fast-summary.txt line '"+mm.group(1)+" "+mm.group(2)+"' median delta", "{} ns"),
                            N(mm.group(4), "rundir:c1-fast-summary.txt mean rel change"), N(mm.group(5), "rundir:c1-fast-summary.txt 95% t-CI")])
c1_inv = [r for r in c1f["runs"] if not r["run_valid"]]
H.append(section("c1", "5 · Candidate c1: correct on disk, faster on disk under TCG, unresolved on zram, worse zram p99", "Correctness proof → exact-commit probe → AB/BA fast screen against baseline 5e84ca92.",
  f'<div class="card"><p class="chart-title">Correctness proof: {N(cr["integration_pass"] and "CORRECTNESS_PASS", P_FAST+" correctness.status")} — one guest, disk backend</p>'
  f'<p>Run <code>c1-v2-c1-xs-sync-ra-correctness-1</code>: integration_pass {N(cr["integration_pass"], "rundir:c1-correctness.log integration_pass")}, run_valid {N(cr["run_valid"], "rundir:c1-correctness.log run_valid")}, '
  f'{N(sum(cr["gates"].values()), "rundir:c1-correctness.log count(gates==true)")}/{N(len(cr["gates"]), "rundir:c1-correctness.log len(gates)")} gates true, accelerator {N(cr["accelerator"], "rundir:c1-correctness.log accelerator")}, wall {N(cr["wall_seconds"], "rundir:c1-correctness.log wall_seconds", "{:.1f} s")}. '
  f'Readahead fired in the proof (swap_ra {N(corr["metrics"]["vmstat_delta"]["swap_ra"], CAMP+"/runs/guests/c1-v2-c1-xs-sync-ra-correctness-1/result.json metrics.vmstat_delta.swap_ra")}, swap_ra_hit {N(corr["metrics"]["vmstat_delta"]["swap_ra_hit"], CAMP+"/runs/guests/c1-…/result.json metrics.vmstat_delta.swap_ra_hit")}), '
  f'but zswpout {N(corr["metrics"]["vmstat_delta"]["zswpout"], CAMP+"/runs/guests/c1-…/result.json metrics.vmstat_delta.zswpout")}: the zswap-mixed path was not exercised.</p>'
  f'<p class="chart-title">Probe 3a554e3b: {N(c1p["status"], P_PROBE+" status")} — the declared mechanism fired</p>'
  f'<p>On zram-64k, swap_ra {sig("swapin-zram-64k","swapin_vmstat_delta.swap_ra")} against a baseline band of {band("swapin-zram-64k","swapin_vmstat_delta.swap_ra")}; pgmajfault {sig("swapin-zram-64k","swapin_vmstat_delta.pgmajfault")} against {band("swapin-zram-64k","swapin_vmstat_delta.pgmajfault")}. Disk fires too; metadata stays in band.</p>'
  + details("Probe signals vs calibrated bands (exact)", table(["case", "counter", "c1 probe", "baseline band"], prow, (2,))) +
  f'<p class="chart-title">Fast screen 68de12e0: {N(c1f["status"], P_FAST+" status")} by the median rule — every pair ratio, every metric</p>'
  f'<div class="visual-scroll">{strip_svg()}</div>'
  f'<p>Decision rule {N(A["decision"], P_FAST+" analysis.decision")}, {N(A["pair_count"], P_FAST+" analysis.pair_count")} pairs (protocol fast comparison_pairs; policy min_pairs is {N(policy["measurement"]["min_pairs"], CAMP+"/policy.json measurement.min_pairs")}), overall median ratio {N(A["overall_median_ratio"], P_FAST+" analysis.overall_median_ratio", "{:.3f}")}, '
  f'needs_review {N(A["needs_review"], P_FAST+" analysis.needs_review")}. Disk sequential mean is {N(M[k_dseq]["median_ratio"], P_FAST+f" analysis.metrics[{k_dseq}].median_ratio", "{:.3f}")}× (noise {N(M[k_dseq]["noise_relative"], P_FAST+f" …[{k_dseq}].noise_relative", "{:.4f}")}) — a TCG screen effect only, no KVM arm. '
  f'zram sequential mean is {N(M[k_zseq]["median_ratio"], P_FAST+f" analysis.metrics[{k_zseq}].median_ratio", "{:.3f}")}× with pair 1 at {N(M[k_zseq]["pair_ratios"][1], P_FAST+f" …[{k_zseq}].pair_ratios[1]", "{:.3f}")} (a loss) and noise {N(M[k_zseq]["noise_relative"], P_FAST+f" …[{k_zseq}].noise_relative", "{:.4f}")}: neutral-to-positive, unresolved. '
  f'zram sequential p99 median {N(M[k_zp99]["median_ratio"], P_FAST+f" analysis.metrics[{k_zp99}].median_ratio", "{:.3f}")}, guard_pass {N(M[k_zp99]["guard_pass"], P_FAST+f" …[{k_zp99}].guard_pass")} — advisory by pre-registration (protocol at ab800d77), but a real regression to report next to the win.</p>'
  f'<div class="callout"><p><b>Ledger is authoritative; run log flagged.</b> rundir:LOG.md line 27 gives the disk baseline as 227–249 µs; the ledger pairs give {N(min(p["a"][k_dseq] for p in c1f["pairs"])/1000, P_FAST+" min(pairs[].a[disk seq.mean])/1000", "{:.1f}")}–{N(max(p["a"][k_dseq] for p in c1f["pairs"])/1000, P_FAST+" max(pairs[].a[disk seq.mean])/1000", "{:.1f}")} µs.</p></div>'
  f'<p>One invalid fast attempt retained: {", ".join(N(r["id"].split("-",1)[1]+" "+r["invalid_reason"]+f' {r["wall_seconds"]:.1f} s', P_FAST+f" runs[id={r['id']}]") for r in c1_inv)}; rerun -r1 PASS.</p>'
  + details("All metric ratios (exact)", table(["metric", "median", "geomean", "pair ratios", "A/A noise", "guard"], mrows, (1, 2, 4)))
  + details("Primary-metric raw pair values (µs; a = baseline, b = candidate)", table(["pair", "order", "disk seq a", "disk seq b", "zram seq a", "zram seq b"], pairs_rows, (2, 3, 4, 5)))
  + details("Executor's descriptive stats (rundir:c1-fast-summary.txt; not a workflow output)", table(["case", "metric", "median delta", "mean rel. change", "95% t-CI (n=4)"], sum_rows, (2, 3)))
  + '</div>'))

# 6 review
asks = ["Close assumption 1 (speculative read of an unbacked xswap slot → possible SIGBUS): trace store/refusal/writeback/shrink states, or re-check under ci->lock / drop the folio.",
        "Propose (not run) a zswap-mixed xswap correctness run with forced writeback (zswpout>0, zswpwb>0) plus swapoff under load.",
        "Address the zram p99 cost shift: backend-dependent window (SWP_SYNCHRONOUS_IO → smaller or async neighbours); pre-register median p99 ratio ≥ 0.90 as kill criterion.",
        "Make swapoff behaviour explicit (try_to_unuse path) and apply the zswap-target rule in VMA mode.",
        "Run the formal-acceptance gates before any acceptance claim (owner-gated, hurricpc-wsl): sparse, gcc_swap_off/zswap_on, lockdep, KASAN, KCSAN, fault injection, memcg limits, large-folio.",
        "Correct lineage (H6/H7) and expectations in reports; state the disk effect as TCG-only.",
        "Process: get owner approval for rev7; open a PR for the void tooling (9c1468ac/87dc7357) before more rev7 verdicts are recorded."]
H.append(section("review", "6 · Swap Review: NEEDS-MORE-EVIDENCE (fail-closed)", "The screen stands under the frozen rules; it is not a basis for acceptance, and there is no next tier to accept into.",
  '<div class="card"><ul>' + "".join(f"<li>{e(a)}</li>" for a in asks) + '</ul>'
  '<p>Parent judgement (review): not a sound round-2 parent yet; acceptable in the exploratory population as a neutral-to-positive screen; upgrade only if the SIGBUS assumption is closed and the zswap-mixed test passes. '
  'Conflict to resolve by the owner: AGENTS.md says every candidate\'s parent is the campaign baseline, the controller accepts an exact parent commit.</p>'
  f'<div class="callout"><p><b>Protocol proposal (not self-applied).</b> The workflow wrote needs_review {N(A["needs_review"], P_FAST+" analysis.needs_review")} for a FAST_PASS whose human verdict is NEEDS-MORE-EVIDENCE. '
  f'Proposal for a later protocol revision: a FAST_PASS with any advisory guard_pass false, a primary metric whose pair ratios straddle 1, or fewer pairs than policy min_pairs sets needs_review true. Nothing in rev7 was changed; round 1 stands as recorded.</p></div></div>'))

# 7 budget
brow = [[e(lbl), e(pool), N(gcounts[p], f"{CAMP}/ledger/guest-reservations/{p}*.json count")] for lbl, p, pool in groups]
MANDATE = 120  # per coordinator, 2026-10-29 (whole 3-round run); AGENTS.md only defines a per-campaign default cap of 120
mand_left = MANDATE - rev6_total - rev7_total
round_need = rev7proto["planned_guest_counts"]["one_round"] + 1
H.append(section("budget", f"7 · Budget: the run-wide cap binds — {mand_left} guests left, enough for one more round (c1c)", "Two views: the mandate cap for the whole run, and rev7's own per-campaign cap. The smaller one binds.",
  f'<div class="card"><div class="tiles">'
  f'<div class="tile"><div class="label">Mandate cap, whole 3-round run</div><div class="value" style="font-size:20px">{N(rev6_total+rev7_total, "derived: rev6 budget.json + rev7 budget.json")} / {N(MANDATE, "per coordinator, 2026-10-29")}</div><div class="note">rev6 {N(rev6_total, REV6+"/ledger/budget.json")} + rev7 {N(rev7_total, CAMP+"/ledger/budget.json")}; left {N(mand_left, "derived: 120-90")}</div></div>'
  f'<div class="tile"><div class="label">rev7 per-campaign cap</div><div class="value" style="font-size:20px">{N(rev7_total, CAMP+"/ledger/budget.json guests+probe_guests")} / {N(fast_cap+probe_cap, CAMP+"/campaign.json budget")}</div><div class="note">fast left {N(fast_cap-budget["guests"], "derived: 96-69")}, probe left {N(probe_cap-budget["probe_guests"], "derived: 24-12")}</div></div>'
  f'<div class="tile"><div class="label">Next round c1c needs</div><div class="value" style="font-size:20px">{N(round_need, "derived: "+CAMP+"/protocol.json planned_guest_counts.one_round + 1 reserve")}</div><div class="note">probe 3 + fast 16 + correctness 1, +1 reserve; fits both caps once</div></div></div>'
  f'<p>Binding limit: the mandate cap ({N(mand_left, "derived")} left) is smaller than rev7\'s remaining {N(fast_cap+probe_cap-rev7_total, "derived: 120-81")}, so only one more round fits (c1c, per coordinator). The 120 run-wide mandate comes from the coordinator; AGENTS.md defines 120 only as a per-campaign default.</p></div>'
  + '<p class="lead" style="margin-top:12px">Recount from guest-reservation manifests, checked against budget.json; overrun vs plan kept as found (voided guests count).</p>' +
  f'<div class="card"><p>rev7 ledger budget: fast {N(budget["guests"], CAMP+"/ledger/budget.json guests")} of {N(fast_cap, CAMP+"/campaign.json budget.guest_attempts")}, probe {N(budget["probe_guests"], CAMP+"/ledger/budget.json probe_guests")} of {N(probe_cap, CAMP+"/campaign.json budget.probe_guest_attempts")}, '
  f'total {N(rev7_total, "derived: budget.json guests+probe_guests")} of {N(fast_cap+probe_cap, "derived: campaign.json guest_attempts+probe_guest_attempts")}. '
  f'Reservation manifests: {N(res_total, CAMP+"/ledger/guest-reservations/*.json count")} (fast {N(fast_res, "derived: reservation groups, fast pool")}, probe {N(probe_res, "derived: reservation groups, probe pool")}) — matches. Guest directories: {N(len(list((REPO/CAMP/"runs/guests").iterdir())), CAMP+"/runs/guests/* count")} (the RAM-refused reservation never created one). '
  f'Remaining: fast {N(fast_cap-budget["guests"], "derived: 96-69")}, probe {N(probe_cap-budget["probe_guests"], "derived: 24-12")}. Round 1 used {N(gcounts["c1-v2-c1-xs-sync-ra-correctness"]+gcounts["3a554e3b"]+gcounts["68de12e0"], "derived: reservations c1-correctness+3a554e3b+68de12e0")} guests (correctness {N(gcounts["c1-v2-c1-xs-sync-ra-correctness"], "reservations")} + probe {N(gcounts["3a554e3b"], "reservations")} + fast {N(gcounts["68de12e0"], "reservations")}); the plan assumed {N(20, 'rundir:status-after-void2.json limits note')} per round and {N(fast['analysis']['pair_count']*4, 'derived: '+P_CALF+' analysis.pair_count × 4')} for fast calibration, which actually took '
  f'{N(gcounts["16fe9d24"]+gcounts["0c2cd749"]+gcounts["e8b7a7e3"], "derived: reservations 16fe9d24+0c2cd749+e8b7a7e3")} including voided attempts. With fast {N(fast_cap-budget["guests"], "derived")} left, the rev7 pool alone would fit one more full round ({N(gcounts["68de12e0"], "derived: round-1 fast reservations 68de12e0")} fast) but not two.</p>'
  f'<p>The run log\'s “global {N('90/120', 'rundir:LOG.md line 27')}” is the mandate view above (rev6 + rev7 against the run-wide cap, per coordinator).</p>'
  + details("Reservation groups (exact)", table(["group", "pool", "guests"], brow, (2,))) + '</div>'))

# 8 cleanup
dfs = [(i, archlog[i+1]) for i, l in enumerate(archlog) if l.startswith("Filesystem")]
oks = [l for l in archlog if " OK removed " in l]
rrows = [[f"<code>{e(re.sub(r'^(/workspace/|/tmp/)', '<box>/', r[0]))}</code>", N(r[1], f"archive:removed.tsv line {i+1} col2"), e(r[2]), N(r[3], f"archive:removed.tsv line {i+1} col4")] for i, r in enumerate(removed)]
dfrows = [[N(archlog[i-1][:19], f"archive:LOG.txt line {i}"), N(l.split()[3], f"archive:LOG.txt line {i+2} IFree"), N(l.split()[4], f"archive:LOG.txt line {i+2} IUse%")] for i, l in dfs]
H.append(section("cleanup", f"8 · Cleanup before the run: {len(oks)} trees archived then removed; inodes {dfs[0][1].split()[4]} → {dfs[-1][1].split()[4]}", f"Done {archlog[0][11:16]}–{[l for l in archlog if l[:4]=='2026'][-1][11:16]} PDT (archive:LOG.txt), before rev7 opened; nothing in a campaign directory was touched.",
  f'<div class="card"><p>The cleanup log records {N(len(oks), "archive:LOG.txt count(\'OK removed\')")} removals, each after archiving to a verified tar.zst; the final <code>df -i</code> reads IFree {N(dfs[-1][1].split()[3], f"archive:LOG.txt line {dfs[-1][0]+2}")} / IUse {N(dfs[-1][1].split()[4], f"archive:LOG.txt line {dfs[-1][0]+2}")}. '
  f'<code>removed.tsv</code> lists only {N(len(removed), "archive:removed.tsv line count")} of them (two of the batches); the first batch, the two build <code>source/</code> trees and the run-3 batch are only in LOG.txt. '
  f'All {N(len((ARCH/"SHA256SUMS").read_text().splitlines()), "archive:SHA256SUMS line count")} archives in SHA256SUMS verify (re-checked read-only during this audit). Cleanup is box hygiene only and does not touch rev7 evidence. ' + (f'After round 1, LOG.txt gained {N(len(late_arch), "archive:LOG.txt lines after DONE run3")} further entr(y/ies) starting {N(late_arch[0][11:19], "archive:LOG.txt line "+str(_cut+1))} PDT (archiving the aborted c1b build and later round-2 cleanup; outside round 1, reported in summary.html §Cleanup).' if late_arch else '') + '</p>'
  + details("removed.tsv (exact)", table(["original path (box)", "entries", "archive", "size"], rrows, (1, 3)))
  + details("df -i after each batch (archive:LOG.txt)", table(["after", "IFree", "IUse%"], dfrows, (1, 2))) + '</div>'))

# 9 gates checklist
grows = []
for g in gates:
    st, ev = status_of.get(g, ("NOT RUN", "no evidence in campaign or run dir"))
    cls = "st-pass" if st.startswith("PASS") or st.startswith("BUILT") else "st-fail"
    grows.append([f"<code>{e(g)}</code>", f'<span class="{cls}">{e(st)}</span>', f'<span data-src="{e(CAMP+"/policy.json required_gates")}">{e(ev)}</span>'])
H.append(section("gates", f"9 · Formal gates: {len(notrun)} of {len(gates)} NOT RUN", "Listed in policy order, including every missing gate.",
  '<div class="card">' + table(["gate", "status", "evidence"], grows) + '</div>'))

# 10 import-state
H.append(section("import-state", "10 · Open item: import-state SKIPPED on this box", "AGENTS.md: each additional machine explicitly runs migrate.py import-state; the shared layout marker alone does not mean its state was imported.",
  '<div class="card"><p>No per-machine import receipt exists for this box (the private <code>swap-next-migration/&lt;machine&gt;.json</code> under the git common dir is absent), and <code>campaigns/MOVED.json</code> has no imports list. '
  '<b>Status: SKIPPED, still open.</b> Reason (per coordinator, 2026-10-29): <code>migrate.py import-state</code> needs campaign records for <code>xswap-tcg-r3-2026-10-24</code> / <code>protocol-tcg-revision3</code>, and the old evidence was declared void by the owner (owner statement at 01:32 PT relayed by the coordinator; not verified from a file). '
  f'Checked: commit 9b4e3fe has {N(len(legacy_hits_9b), "git ls-tree -r 9b4e3fe | grep xswap-tcg-r3-2026-10-24|protocol-tcg-revision3")} matching paths, and current origin/main {N(main_tip[:7], "git rev-parse origin/main")} has {N(len(legacy_hits_tip), "git ls-tree -r origin/main | grep …")}. No receipt was written. '
  'The archived rev3 evidence index agrees that the old evidence was never imported (“import attempted, impossible”).</p></div>'))

# 11 models
H.append(section("models", "11 · Models per step", "Filled in after round 2: see <a href=\"summary.html#models\">summary.html §Models</a> (cloud-agent models per coordinator; teammate models not separately logged).", ""))

# audit
aud = (f'<p><b>archive/ in the rev7 campaign directory was created by the workflow.</b> <code>evolve/population.py</code> at 9c1468ac sets <code>self.archive = directory / "archive"</code> (L185–186), writes briefs to <code>archive/briefs/</code> (L510) and the OpenEvolve view to <code>archive/database/</code> (L266–268); '
       f'standard_workflow.py builds <code>Population(CAMPAIGN, …)</code> (L765) and calls <code>next_brief</code> (L848). File times match: brief {N('12:57:30', 'stat mtime '+CAMP+'/archive/briefs/brief-000001-450a25c6d11d.json')} PDT = <code>loop.py next</code> output (rundir:c1-next.out mtime); <code>population.json</code> {N('13:21:18.39', 'stat mtime '+CAMP+'/archive/population.json')} vs fast row finished {T(c1f["finished"], P_FAST+" finished")} (FAST_PASS admits a candidate). '
       f'The void tool at 9c1468ac and 87dc7357 contains no “archive” string; the box cleanup ended {N([l for l in archlog if l[:4]=='2026'][-1][11:19], 'archive:LOG.txt line '+str(_cut-2)+' (DONE run3)')}, before rev7 opened, and never names a campaign path. It is untracked because .gitignore ignores <code>campaigns/*/runs/</code> but not <code>archive/</code>; <b>archive/population.json is owned evidence</b> (population.py L5–6: it “owns evidence and sampling sequence”; archive/database is a rebuildable view) and will be committed with the campaign records (per coordinator, 2026-10-29).</p>'
       f'<p>Pinned code: {link("evolve/population.py", None, WF)}, {link("evolve/standard_workflow.py", None, WF)}, {link("evolve/control/void_calibration.py", None, WF)}, {link("evolve/control/void_calibration.py", None, VT)}, '
       f'{link(CAMP+"/protocol.json", None, AB)}, {link(CAMP+"/policy.json", None, AB)}.</p>'
       f'<p>Ledger: {N(len(ledger), CAMP+"/ledger/ledger.json len")} rows, single fingerprint <code>{N(ledger[0]["fingerprint"][:8], CAMP+"/ledger/ledger.json [*].fingerprint (one distinct value)")}</code>. Void receipts in the ledger equal the run-dir copies byte-for-byte after JSON parse.</p>')
H.append(f'<details class="audit"><summary>Audit and provenance (closed by default)</summary>{aud}</details>')

nav = "".join(f'<a href="#{i}">{e(t)}</a>' for i, t in [("rev6", "rev6 / rescore"), ("probe-cal", "Probe cal"), ("fast-cal", "Fast cal"), ("incidents", "Incidents"), ("c1", "c1"), ("review", "Review"), ("budget", "Budget"), ("cleanup", "Cleanup"), ("gates", "Gates"), ("import-state", "import-state"), ("models", "Models")])
JS = re.findall(r"<script>(.*?)</script>", STYLE_SRC.read_text(), re.S)[-1]
page = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>DRAFT · Round 1 · xswap-tcg-kbench-rev7-2026-10-29</title><style>{CSS}{EXTRA}</style></head><body><div class="viz-root"><main>'
        f'<header><button class="toggle" type="button">Theme</button><h1>Round 1: c1 passes the TCG screen but needs more evidence</h1>'
        f'<p>xswap-tcg-kbench-rev7-2026-10-29 · baseline 5e84ca92 · QEMU TCG · {N(rev7_total, "derived: budget.json")} guests · 2026-10-29</p><nav>{nav}</nav></header>'
        + "".join(H) + f'</main></div><script>{JS}</script></body></html>')
OUT.write_text(page)
print("wrote", OUT, len(page), "bytes; TODOs:", len(TODOS)); [print(" -", t) for t in TODOS]
