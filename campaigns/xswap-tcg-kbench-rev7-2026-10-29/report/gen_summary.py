#!/usr/bin/env python3
"""Box-local generator for the end-of-mandate SUMMARY (summary.html). Reads evidence read-only; writes only summary.html.
Every rendered number goes through N()/T() with a data-src naming file + key/line. Missing values render as visible TODOs.
Statements that come only from the coordinator are labelled "per coordinator, 2026-10-29"."""
import json, re, html, math, datetime, zoneinfo, pathlib, subprocess, os
HERE = pathlib.Path(__file__).parent
OUT = HERE / "summary.html"
REPO = pathlib.Path("/workspace/Swap-Next-main")
CAMP = "campaigns/xswap-tcg-kbench-rev7-2026-10-29"
REV6 = "campaigns/xswap-tcg-kbench-2026-10-29"
RUNDIR = pathlib.Path("/workspace/runs/grok-cloud-tcg-rev7-20261029")
ARCH = pathlib.Path("/workspace/archive-20261029")
REVIEW2 = pathlib.Path("/workspace/reviews/c1c-v2-c1c-xs-ra-safe-round2.md")
STYLE_SRC = REPO / "campaigns/xswap-swapin-2026-10-23/report/explainer.html"
TZ = zoneinfo.ZoneInfo("America/Los_Angeles")
GH = "https://github.com/ericzhang-zxh/Swap-Next/blob/"
AB, WF, VT = ("ab800d776925269deafaffbfb2df61ffd34a1220", "9c1468ac2d5a4a8ef1a59de7003f434f17d5a9b5",
              "87dc7357eb798a161a0d299f73629d8c3ce85a44")
PC = "per coordinator, 2026-10-29"
e = html.escape
TODOS = []
def N(v, src, fmt="{}"):
    if v is None:
        TODOS.append(src); return f'<span class="todo" data-src="{e(src)}">TODO(missing: {e(src)})</span>'
    return f'<span class="n" data-src="{e(src)}">{e(fmt.format(v))}</span>'
def ts(unix): return datetime.datetime.fromtimestamp(unix, TZ).strftime("%H:%M:%S")
def T(unix, src): return N(None, src) if unix is None else N(ts(unix), src, "{} PDT")
def TODO(what): TODOS.append(what); return f'<span class="todo">TODO: {e(what)}</span>'
def link(path_at, label=None, commit=AB): return f'<a href="{GH}{commit}/{e(path_at)}">{e(label or path_at)}@{commit[:8]}</a>'
def J(rel): return json.loads((REPO / rel).read_text())
def git(*a): return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True).stdout
def mtime(p): return os.stat(p).st_mtime
def find_line(lines, needle, start=0):
    for i, l in enumerate(lines[start:], start):
        if needle in l: return i + 1
    return None

# ---------------- evidence ----------------
EV = f"{CAMP}/runs/evaluations"
P68 = f"{EV}/68de12e0b0c9471bb497a9f0dc844a3f/report.json"; P66 = f"{EV}/66a07143990c419d9c78404c466fc1ba/report.json"
PBC = f"{EV}/bc73887e02b54db2a57243b964b38d54/report.json"; PCALF = f"{CAMP}/ledger/calibration-fast.json"
PC1C = f"{CAMP}/candidates/v2-c1c-xs-ra-safe.json"; PC1 = f"{CAMP}/candidates/v2-c1-xs-sync-ra.json"
PCOR = f"{CAMP}/runs/guests/c1c-v2-c1c-xs-ra-safe-correctness-1/result.json"
PRES_COR = f"{CAMP}/ledger/guest-reservations/c1c-v2-c1c-xs-ra-safe-correctness-1.json"
r68, r66, rbc, calf = J(P68), J(P66), J(PBC), J(PCALF)
c1c, c1 = J(PC1C), J(PC1)
cor = J(PCOR); res_cor = J(PRES_COR)
ledger = J(f"{CAMP}/ledger/ledger.json"); budget = J(f"{CAMP}/ledger/budget.json"); camp = J(f"{CAMP}/campaign.json")
rev6budget = J(f"{REV6}/ledger/budget.json"); policy = J(f"{CAMP}/policy.json"); proto = J(f"{CAMP}/protocol.json")
events = [json.loads(l) for l in (REPO / CAMP / "ledger/events.jsonl").read_text().splitlines() if l.strip()]
ev_close = next(x for x in events if x["event"] == "candidate_closed")
ev_c1c = next(x for x in events if x["event"] == "candidate_created" and x["payload"]["id"] == "v2-c1c-xs-ra-safe")
idx66 = next(i for i, r in enumerate(ledger) if r["id"] == r66["id"]); idxbc = next(i for i, r in enumerate(ledger) if r["id"] == rbc["id"])
row66 = ledger[idx66]
import hashlib
sha = lambda p: hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
c1c_sha = sha(REPO / PC1C); ledger_sha = sha(REPO / CAMP / "ledger/ledger.json")
stop_txt = (REPO / CAMP / "STOP").read_text().strip(); stop_m = mtime(REPO / CAMP / "STOP")
LOG = (RUNDIR / "LOG.md").read_text().splitlines()
watch = (RUNDIR / "c1c-rerun-watch.log").read_text().splitlines()
void3 = json.loads((RUNDIR / "void-3.err").read_text()); void3b = json.loads((RUNDIR / "void-3b.err").read_text())
void3_m = mtime(RUNDIR / "void-3.err")
GA = (RUNDIR / "GUEST-ACCOUNTING.md").read_text().splitlines()
RV = REVIEW2.read_text().splitlines()
corstart = (RUNDIR / "c1c-correctness.start").read_text().strip()
started_json_m = mtime(REPO / CAMP / "runs/guests/c1c-v2-c1c-xs-ra-safe-correctness-1/started.json")
c1c_m = mtime(REPO / PC1C)
ledger_m = mtime(REPO / CAMP / "ledger/ledger.json")
dfcap = (HERE / "df-i-capture.txt").read_text().splitlines()
archlog = (ARCH / "LOG.txt").read_text().splitlines()
removed = [l.split("\t") for l in (ARCH / "removed.tsv").read_text().splitlines() if l.strip()]
sums = (ARCH / "SHA256SUMS").read_text().splitlines()
vt_wf = git("show", f"{WF}:evolve/control/void_calibration.py").splitlines()
vt_vt = git("show", f"{VT}:evolve/control/void_calibration.py").splitlines()
vt_wf_l = find_line(vt_wf, "not a calibration attempt"); vt_vt_l = find_line(vt_vt, "not a calibration attempt")
unmerged = {c: subprocess.run(["git", "-C", str(REPO), "merge-base", "--is-ancestor", c, "origin/main"]).returncode != 0 for c in ("ab800d77", "9c1468ac", "87dc7357")}
main_tip = git("rev-parse", "--short=7", "origin/main").strip()
authors = {c: git("log", "-1", "--format=%an", c).strip() for c in ("ab800d77", "9c1468ac", "87dc7357")}
reservations = sorted(p.stem for p in (REPO / CAMP / "ledger/guest-reservations").glob("*.json"))
guestdirs = sorted(p.name for p in (REPO / CAMP / "runs/guests").iterdir())
# protocol_hash (controller.py L68-73 at 9c1468ac): sha256 over name+bytes of campaign policy.json, analysis.py, controller.py
ph = hashlib.sha256()
for p in sorted([(REPO / CAMP / "policy.json").resolve(), (REPO / "evolve/control/analysis.py").resolve(), (REPO / "evolve/control/controller.py").resolve()]):
    ph.update(p.name.encode()); ph.update(p.read_bytes())
proto_hash = ph.hexdigest()

def serial_hits(run_id, pat="unstable due to frequency skew"):
    p = REPO / CAMP / "runs/guests" / run_id / "serial.log"
    return [(i + 1, l.strip()) for i, l in enumerate(p.read_text(errors="replace").splitlines()) if pat in l]

# ---------------- derived ----------------
gates = policy["required_gates"]
c1c_static = J(f"{CAMP}/candidates/v2-c1c-xs-ra-safe/static.json")
gstat = {"checkpatch": ("PASS", f"{CAMP}/candidates/v2-c1c-xs-ra-safe/static.json checkpatch.exit_code={c1c_static['checkpatch']['exit_code']}"),
         "gcc_swap_on": ("BUILT", "benchmark/kernel/builds/std-b69e47c9118b/result.json (build manifest; not re-verified here)"),
         "guest_boot_identity": ("PASS", f"{PCOR} gates.boot={cor['gates']['boot']}, gates.cmdline_identity={cor['gates']['cmdline_identity']}")}
for g in ("data_roundtrip", "fork_cow", "concurrent_fault", "swapoff_live_pages", "no_new_kernel_warnings"):
    gstat[g] = ("PASS (disk only)", f"{PCOR} gates.{g}={cor['gates'].get(g)}")
notrun = [g for g in gates if g not in gstat]
ngates_true = sum(1 for v in cor["gates"].values() if v is True)
fast_runs = r66["runs"]
pass_runs = [r for r in fast_runs if r["status"] == "PASS"]
inv_runs = [r for r in fast_runs if r["status"] == "INVALID"]
start_runs = [r for r in fast_runs if r["status"] == "STARTED"]
slots_p01 = len(proto["tiers"]["fast"]["cases"]) * 2 * 2          # pairs 0-1 x cases x arms
slots_plan = len(proto["tiers"]["fast"]["cases"]) * 2 * proto["tiers"]["fast"]["comparison_pairs"]
cmp_pairs = proto["tiers"]["fast"]["comparison_pairs"]
noise_log = calf["analysis"]["noise_log"]; adv = set(calf["analysis"]["advisory_metrics"])
metrics = list(r68["analysis"]["metrics"].keys())
def guard(k): return math.exp(-noise_log[k])
def short(k): return k.replace("swapin-", "").replace(".swapin_", " ").replace("_ns", "")
c1c_ratios = {k: [p["a"][k] / p["b"][k] for p in r66["pairs"] if k in p["a"] and k in p["b"]] for k in metrics}
c1c_pairidx = {k: [i for i, p in enumerate(r66["pairs"]) if k in p["a"] and k in p["b"]] for k in metrics}
rev7_total = budget["guests"] + budget["probe_guests"]; rev6_total = rev6budget["guests"] + rev6budget["probe_guests"]
fast_cap, probe_cap = camp["budget"]["guest_attempts"], camp["budget"]["probe_guest_attempts"]
MANDATE = 120  # per coordinator (whole run); campaign.json/protocol total_ceiling is the per-campaign 120
def cp(pfx): return sum(1 for r in reservations if r.startswith(pfx))
def cd(pfx): return sum(1 for d in guestdirs if d.startswith(pfx))
r2_groups = [("c1c correctness (run.py)", "c1c-v2-c1c-xs-ra-safe-correctness", "fast"), ("bc73887e c1c probe", "bc73887e", "probe"), ("66a07143 c1c fast", "66a07143", "fast")]
r2_used = sum(cp(p) for _, p, _ in r2_groups)
l_r1end = find_line(LOG, "global 90/120"); l_close = find_line(LOG, "PRE-REGISTRATION RECORD"); l_fast = find_line(LOG, "c1c fast: RAM gate OK")
l_void = find_line(LOG, "not a calibration attempt"); l_stopkeep = find_line(LOG, "END-OF-MANDATE STOP"); l_ga = find_line(LOG, "wrote GUEST-ACCOUNTING.md")
l_wt = find_line(LOG, "c1 worktree (created by me"); l_probe = find_line(LOG, "c1c probe: loop.py")
ga_global = find_line(GA, "**global**"); ga_total = find_line(GA, "**rev7 total**"); ga_66 = find_line(GA, "66a07143990c419d9c78404c466fc1ba")
ga_glob_val = re.search(r"\*\*(\d+) / (\d+)\*\* \((\d+) remaining\)", GA[ga_global - 1]).groups() if ga_global else (None, None, None)
ga_tot_val = re.search(r"\*\*(\d+)\*\* \| (\d+)", GA[ga_total - 1]).groups() if ga_total else (None, None)
r1end_val = re.search(r"global (\d+)/120", LOG[l_r1end - 1]).group(1) if l_r1end else None
rv = lambda needle: f"review2: line {find_line(RV, needle)}"
rv_verdict = find_line(RV, "## Verdict:")

# ---------------- page helpers ----------------
CSS = re.search(r"<style>(.*?)</style>", STYLE_SRC.read_text(), re.S).group(1)
JS = re.findall(r"<script>(.*?)</script>", STYLE_SRC.read_text(), re.S)[-1]
EXTRA = """.todo{background:var(--warning);color:#1f1b16;padding:0 4px;border-radius:4px;font-weight:600}
.notrun{border:2px solid var(--critical);border-radius:12px;padding:14px 18px;margin:16px 0;background:color-mix(in srgb,var(--critical) 8%,var(--surface-1))}
.notrun h3{margin:0 0 6px;color:var(--critical)}.draft{border:2px dashed var(--serious);padding:8px 12px;border-radius:8px;margin:0 0 12px;font-size:13px}
.prov{border:3px solid var(--serious);border-radius:12px;padding:12px 18px;margin:0 0 16px;background:color-mix(in srgb,var(--serious) 10%,var(--surface-1))}
.prov h3{margin:0 0 6px;color:var(--serious)}
.st-pass{color:var(--good);font-weight:600}.st-fail{color:var(--critical);font-weight:600}.st-warn{color:var(--serious);font-weight:600}
.inc{background:repeating-linear-gradient(45deg,transparent 0 6px,color-mix(in srgb,var(--warning) 22%,transparent) 6px 12px)}
.flowrow{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0}.box{border:1px solid var(--ring);border-radius:8px;padding:6px 10px;background:var(--page);font-size:13px}
.box.focus{background:var(--focus);border-color:var(--series-1)}.box.muted{opacity:.55}.arrow{color:var(--muted)}
code{font-size:12.5px}td,th{vertical-align:top}"""
def section(id_, title, lead, body, src=''):
    return f'<section id="{id_}"><h2 data-src="{e(src)}">{title}</h2><p class="lead">{lead}</p>{body}</section>'
def details(summary, body): return f'<details><summary>{e(summary)}</summary>{body}</details>'
def table(cols, rows, numeric=(), rowcls=None):
    h = "".join(f'<th class="{"num" if i in numeric else ""}">{e(c)}</th>' for i, c in enumerate(cols))
    b = "".join("<tr>" + "".join((f'<td class="{"num" if i in numeric else ""} {(rowcls[j][i] if rowcls and rowcls[j] and i < len(rowcls[j]) else "")}">{c}</td>') for i, c in enumerate(r)) + "</tr>" for j, r in enumerate(rows))
    return f"<table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table>"
def fr(x): return f"{x:.3f}"

H = []
# ---------------- banner ----------------
H.append('<div class="draft"><b>DRAFT — box-local, not published, not committed.</b> End-of-mandate summary for the campaign report; the coordinator commits it in the bundle PR. '
         'Hover any number: <code>data-src</code> names the evidence file and key. Prefixes: <code>campaigns/…</code> = Swap-Next checkout (repo-relative); <code>rundir:</code> = executor run directory; '
         '<code>archive:</code> = cleanup archive; <code>review2:</code> = round-2 Swap Review file; <code>drafts:</code> = files saved next to this draft. '
         'Untracked evidence has no pinned commit yet: ' + TODO("pin evidence links to the bundle commit once the final PR exists") + '</div>')
H.append(f'<div class="prov"><h3>Provenance: every result here comes from unmerged code</h3><p>'
         f'rev7 protocol <b>ab800d77</b> (PR #8, open), workflow checkout <b>9c1468ac</b> and void tool <b>87dc7357</b> (branch with no PR). '
         f'Not ancestors of origin/main {N(main_tip, "git rev-parse --short origin/main")}: ab800d77 {N(unmerged["ab800d77"], "git merge-base --is-ancestor ab800d77 origin/main (nonzero = unmerged)")}, '
         f'9c1468ac {N(unmerged["9c1468ac"], "git merge-base --is-ancestor 9c1468ac origin/main")}, 87dc7357 {N(unmerged["87dc7357"], "git merge-base --is-ancestor 87dc7357 origin/main")}. '
         f'One fingerprint on all {N(len(ledger), CAMP+"/ledger/ledger.json len")} ledger rows: <code>{N(sorted({r["fingerprint"] for r in ledger})[0][:8] if len({r["fingerprint"] for r in ledger}) == 1 else None, CAMP+"/ledger/ledger.json [*].fingerprint (one distinct value)")}</code>. '
         f'<b>rev7 approval is pending Hurric\'s review of the bundle PR</b> ({PC}; review2 §(d) also records no owner approval). Until then every verdict below is provisional.</p></div>')

# ---------------- verdict ----------------
k_dseq, k_dp99, k_drm, k_zp99 = "swapin-disk.swapin_seq.mean_ns", "swapin-disk.swapin_seq.p99_ns", "swapin-disk.swapin_rand.mean_ns", "swapin-zram-64k.swapin_seq.p99_ns"
tiles = [("Mandate outcome", "No candidate accepted", "rounds 1 and 2 ran; round 3 not run (budget, " + PC + ")"),
         ("Round 1 · c1", N(r68["status"], P68 + " status"), "screen only; review NEEDS-MORE-EVIDENCE; closed as superseded"),
         ("Round 2 · c1c fast", N(r66["status"], P66 + " status"), "INCOMPLETE: no median decision possible"),
         ("c1c disk seq.mean", " / ".join(N(fr(v), f"derived: {P66} pairs[{i}].a/b[{k_dseq}]", "{}×") for v, i in zip(c1c_ratios[k_dseq], c1c_pairidx[k_dseq])), "per pair (two pairs); TCG-only effect"),
         ("c1c disk seq.p99", " / ".join(N(fr(v), f"derived: {P66} pairs[{i}].a/b[{k_dp99}]", "{}×") for v, i in zip(c1c_ratios[k_dp99], c1c_pairidx[k_dp99])), "RED FLAG (advisory): below guard in both pairs"),
         ("Guests", N(f"{rev6_total + rev7_total} / {MANDATE}", f"derived: {REV6}/ledger/budget.json + {CAMP}/ledger/budget.json; cap {PC}"), "run-wide mandate cap"),
         ("Formal gates", N(f"{len(notrun)} of {len(gates)}", CAMP + "/policy.json required_gates minus gates with evidence", "{} NOT RUN"), "carried forward from round 1")]
tile_html = "".join(f'<div class="tile"><div class="label">{e(a)}</div><div class="value" style="font-size:20px">{b}</div><div class="note">{e(c)}</div></div>' for a, b, c in tiles)
H.append(f'<div class="card"><div class="verdict"><span class="badge"><i class="dot" style="background:var(--warning)"></i>Needs more evidence</span>'
         f'<span>End of mandate: two readahead candidates screened; neither accepted; the safer one (c1c) has an unfinished fast tier</span></div><div class="tiles">{tile_html}</div>'
         f'<p class="lead" style="margin-top:12px">c1 cleared the round-1 non-regression screen but its zram tail regressed and a SIGBUS question stayed open, so it was closed as superseded by c1c. '
         f'c1c passed correctness ({N(f"{ngates_true}/{len(cor["gates"])}", PCOR+" gates (count true / total)")}) and its probe ({N(rbc["status"], PBC+" status")}), then the fast run stopped after '
         f'{N(len(pass_runs), P66+" runs[status=PASS] count")} of {N(slots_p01, "derived: protocol.json tiers.fast.cases (2) × 2 arms × pairs 0–1")} arm-slots in pairs 0–1 '
         f'({N(slots_plan, "derived: protocol.json tiers.fast 2 cases × 2 arms × comparison_pairs 4")} planned), because the candidate zram arm failed twice on a host clock problem. '
         f'The protocol decides on the median of {N(cmp_pairs, CAMP+"/protocol.json tiers.fast.comparison_pairs")} pairs, so there is no fast decision: no FAST_PASS, no REGRESSION ({rv("## Verdict:")}). '
         f'Round 1 detail: <a href="round1.html">round1.html</a>.</p></div>')

H.append(f'<div class="notrun"><h3>Formal gates NOT RUN: {N(len(notrun), CAMP+"/policy.json required_gates minus gates with evidence")} of {N(len(gates), CAMP+"/policy.json len(required_gates)")} — for both c1 and c1c</h3>'
         f'<p>{", ".join("<b>"+e(g)+"</b>" for g in notrun)}. c1c\'s correctness ran once, on the disk backend, with zswpout {N(cor["metrics"]["correctness_vmstat_delta"]["zswpout"], PCOR+" metrics.correctness_vmstat_delta.zswpout")} (the zswap-mixed async path is not exercised; the candidate record itself says “zswap-mixed async-backend test NOT RUN”, {PC1C} hypothesis). '
         f'The build is not instrumented, so a clean serial-log grep is not a lockdep or KASAN result ({rv("--no-instrumentation")}). '
         f'<b>import-state: SKIPPED on this box, still open</b> (carried forward; reason {PC}; see round1.html §10).</p></div>')

# ---------------- system -> subsystem -> change ----------------
H.append(section("system", "Where c1c sits: system → subsystem → change", "Schematic, not measured. Wording from the candidate record and the review.",
  '<div class="card"><div class="flowrow"><span class="box">Linux memory management</span><span class="arrow">→</span><span class="box">swap-in path (page fault on a swapped-out page)</span><span class="arrow">→</span>'
  '<span class="box focus">mm/swap_state.c readahead for xswap slots</span></div>'
  f'<ul><li><b>System.</b> When a process touches memory that was swapped out, the kernel reads it back (“swap-in”). Readahead also reads neighbouring slots, betting they will be needed next.</li>'
  f'<li><b>Subsystem.</b> xswap is the project\'s swap layer; baseline {N(c1c["baseline_commit"][:8], PC1C+" baseline_commit")} skips readahead for xswap slots.</li>'
  f'<li><b>c1 (round 1).</b> Turned readahead on for xswap faults on every backend. Disk got faster, but zram (a synchronous, in-memory backend) got a heavier tail.</li>'
  f'<li><b>c1c (round 2).</b> Same idea, plus a safety gate: readahead only when the physical backend is asynchronous and writable, with a recheck under the cluster lock after the page enters the swap cache that drops the speculative page before any read ({PC1C} hypothesis). '
  f'One file changed (<code>{e(", ".join(c1c_static["changed_paths"]))}</code>), {N(c1c_static["changed_lines"], CAMP+"/candidates/v2-c1c-xs-ra-safe/static.json changed_lines")} changed lines, {N(c1c_static["status"], CAMP+"/candidates/v2-c1c-xs-ra-safe/static.json status")}; '
  f'commit {N(r66["candidate_commit"][:8], P66+" candidate_commit")}, parent = baseline {N(r66["parent_comparison"]["parent_commit"][:8], P66+" parent_comparison.parent_commit")}.</li>'
  f'<li><b>Expected trade.</b> Disk sequential swap-in faster; zram back on the baseline path (readahead ≈ 0, tail ≈ unchanged). Pre-registered KILL: median zram seq.p99 ratio below {N("0.834", PC1C+" hypothesis (KILL clause)")}.</li></ul></div>'))

# ---------------- round 2 timeline ----------------
inv1 = next((l for l in watch if "invalid=1" in l), ""); inv2 = next((l for l in watch if "invalid=2" in l), "")
tl = [
 ["c1 closed (superseded)", T(ev_close["time_unix"], CAMP+"/ledger/events.jsonl candidate_closed.time_unix"), "controller close; reason below"],
 ["c1c created; pre-registration record written", T(ev_c1c["time_unix"], CAMP+"/ledger/events.jsonl candidate_created[v2-c1c].time_unix"), f'record sha256 {N(c1c_sha[:8], "sha256sum "+PC1C)}…, file mtime {T(c1c_m, "stat mtime "+PC1C)}; logged at {N(LOG[l_close-1][13:21] if l_close else None, f"rundir:LOG.md line {l_close} timestamp")} PDT'],
 ["First c1c guest reserved (correctness)", T(res_cor["reserved_unix"], PRES_COR+" reserved_unix"), f'rundir:c1c-correctness.start = {N(corstart[11:19], "rundir:c1c-correctness.start")} PDT; QEMU started.json mtime {T(started_json_m, "stat mtime "+CAMP+"/runs/guests/c1c-…-correctness-1/started.json")}'],
 ["Probe bc73887e", f'{T(rbc["started"], PBC+" started")}–{T(rbc["finished"], PBC+" finished")}', N(rbc["status"], PBC+" status")],
 ["Fast 66a07143", f'{T(r66["started"], P66+" started")}–{T(r66["finished"], P66+" finished")}', N(r66["reason"], P66+" reason")],
 ["1st INVALID (pair 1 zram-64k-b)", N(inv1[11:19] or None, "rundir:c1c-rerun-watch.log invalid=1 line", "{} PDT"), "clocksource_fallback"],
 ["2nd INVALID (r1) → STOP written", N(inv2[11:19] or None, "rundir:c1c-rerun-watch.log invalid=2 line", "{} PDT"), f'STOP mtime {T(stop_m, "stat mtime "+CAMP+"/STOP")}'],
 ["Void attempts (both refused)", T(void3_m, "stat mtime rundir:void-3.err"), f'{N(void3["status"], "rundir:void-3.err status")} / {N(void3b["status"], "rundir:void-3b.err status")}'],
 ["Round-2 review written", T(mtime(REVIEW2), "stat mtime review2"), "NEEDS-MORE-EVIDENCE"],
]
H.append(section("round2", "Round 2 · c1c: correct, mechanism confirmed, fast tier stopped incomplete", "Record hashed before the first guest; correctness and probe passed; the fast run hit the round's one-rerun stop.",
  '<div class="card">' + table(["step", "time", "evidence"], tl) +
  f'<p><b>Order check.</b> The pre-registration record was written at {T(c1c_m, "stat mtime "+PC1C)} and has not changed since (sha256 still {N(c1c_sha[:8], "sha256sum "+PC1C)}…). The first c1c guest was reserved at {T(res_cor["reserved_unix"], PRES_COR+" reserved_unix")}. '
  f'So the hypothesis and KILL rule were fixed before any c1c guest. The record is untracked in git ({rv("candidates/` is untracked")}): hashed and logged, not committed.</p></div>'
  + '<div class="card"><p class="chart-title">Correctness (disk backend, run.py)</p>'
  f'<p>integration_pass {N(cor["integration_pass"], PCOR+" integration_pass")}, run_valid {N(cor["run_valid"], PCOR+" run_valid")}, gates true {N(ngates_true, PCOR+" gates (count true)")} of {N(len(cor["gates"]), PCOR+" gates (count)")}. '
  f'Readahead did run, a little: swap_ra {N(cor["metrics"]["correctness_vmstat_delta"]["swap_ra"], PCOR+" metrics.correctness_vmstat_delta.swap_ra")}, swap_ra_hit {N(cor["metrics"]["correctness_vmstat_delta"]["swap_ra_hit"], PCOR+" metrics.correctness_vmstat_delta.swap_ra_hit")}, '
  f'pswpin {N(cor["metrics"]["correctness_vmstat_delta"]["pswpin"], PCOR+" metrics.correctness_vmstat_delta.pswpin")}, pgmajfault {N(cor["metrics"]["correctness_vmstat_delta"]["pgmajfault"], PCOR+" metrics.correctness_vmstat_delta.pgmajfault")}. '
  f'Nothing shows the recheck\'s <i>drop</i> path ran; no counter records it ({rv("swap_ra 12 as evidence")}).</p></div>'
  + '<div class="card"><p class="chart-title">Probe bc73887e: mechanism on disk, safety gate holds on zram</p>'
  + table(["case", "swap_ra", "swap_ra_hit", "pgmajfault", "pswpin", "wall s"],
          [[e(c)] + [N(rbc["analysis"]["probe_signals"][c][f"swapin_vmstat_delta.{k}"][0], PBC+f" analysis.probe_signals[{c}][swapin_vmstat_delta.{k}][0]") for k in ("swap_ra", "swap_ra_hit", "pgmajfault", "pswpin")]
           + [N(round(next(r["wall_seconds"] for r in rbc["runs"] if r["case"] == c), 2), PBC+f" runs[case={c}].wall_seconds")] for c in ("swapin-disk", "swapin-zram-64k")], (1, 2, 3, 4, 5))
  + f'<p>metadata-brd {N(round(rbc["analysis"]["probe_signals"]["metadata-brd"]["metadata_delta_bytes_per_capacity_slot"][0], 6), PBC+" analysis.probe_signals[metadata-brd].metadata_delta_bytes_per_capacity_slot[0]")} B/slot. No pre-registered falsifier fired ({rv("Probe falsifiers")}).</p></div>'))

# fast run detail
frows = []
for r in fast_runs:
    cls = {"PASS": "st-pass", "INVALID": "st-fail"}.get(r["status"], "st-warn")
    frows.append([f'<code>{e(r["id"][33:])}</code>', f'<span class="{cls}">{N(r["status"], P66+f" runs[id=…{r["id"][33:]}].status")}</span>',
                  N(r.get("invalid_reason") or "—", P66+f" runs[id=…{r['id'][33:]}].invalid_reason"),
                  N(round(r["wall_seconds"], 2) if r.get("wall_seconds") is not None else "never booted", P66+f" runs[id=…{r['id'][33:]}].wall_seconds")])
sh = []
for rid in ["66a07143990c419d9c78404c466fc1ba-1-swapin-zram-64k-b", "66a07143990c419d9c78404c466fc1ba-1-swapin-zram-64k-b-r1",
            "e8b7a7e377eb40ab88f875c83b2dfc69-0-swapin-zram-64k-a", "e8b7a7e377eb40ab88f875c83b2dfc69-2-swapin-disk-a"]:
    hits = serial_hits(rid)
    sh.append([f'<code>{e(rid[:8])}…{e(rid[32:])}</code>', ("candidate fast" if rid.startswith("66a0") else "A/A calibration"),
               (N(f'line {hits[0][0]}: {hits[0][1]}', f"{CAMP}/runs/guests/{rid}/serial.log line {hits[0][0]}") if hits else N(None, f"{CAMP}/runs/guests/{rid}/serial.log grep 'unstable due to frequency skew'"))])
H.append(section("fast", "Round 2 · fast run 66a07143: BLOCKED by the round's rerun stop", f"Status {N(r66['status'], P66+' status')}; executor and review call it INCOMPLETE. Pair 1 has no zram data.",
  '<div class="card">' + table(["run", "status", "invalid reason", "wall s"], frows, (3,)) +
  f'<p>The candidate zram arm in pair 1 failed twice with <code>clocksource_fallback</code>. The guest kernel stopped trusting its TSC clock. The same message appears in two A/A calibration runs, which ran baseline code on both arms, so it is a host/TCG problem, not something c1c caused ({rv("zram-64k-b in pair 1")}). '
  f'The third attempt (r2) was reserved and counted but never booted. The coordinator\'s round-2 rule allowed {N(1, "rundir:c1c-rerun-watch.log start line max_invalid=1")} rerun in total, stricter than the protocol\'s reruns_per_arm {N(proto["validity"]["reruns_per_arm"], CAMP+"/protocol.json validity.reruns_per_arm")}, so the watcher wrote STOP: “{e(stop_txt.split(":")[0])}” ({CAMP}/STOP).</p>'
  + details("Serial-log evidence of TSC frequency skew", table(["guest", "kind", "serial.log"], sh)) + '</div>'
  + '<div class="card"><p class="chart-title">Why 66a07143 was not voided</p>'
  f'<p>Both void tools refuse any ledger row whose action is not <code>calibrate</code>: 9c1468ac void_calibration.py line {N(vt_wf_l, "git show 9c1468ac:evolve/control/void_calibration.py grep \'not a calibration attempt\'")} and 87dc7357 line {N(vt_vt_l, "git show 87dc7357:evolve/control/void_calibration.py grep …")}. '
  f'Both attempts returned {N(void3["error"], "rundir:void-3.err error")} / {N(void3b["error"], "rundir:void-3b.err error")}. '
  f'Row {N(idx66, CAMP+"/ledger/ledger.json index of id 66a07143…")} is unmodified: action {N(row66["action"], CAMP+f"/ledger/ledger.json [{idx66}].action")}, no void receipt key ({N("void_receipt" in row66, CAMP+f"/ledger/ledger.json [{idx66}] has key void_receipt")}), identical to report.json ({N(row66 == r66, "derived: ledger row == "+P66)}); '
  f'ledger.json sha256 {N(ledger_sha[:8], "sha256sum "+CAMP+"/ledger/ledger.json")}… matches the executor\'s “unchanged” note (rundir:LOG.md line {l_void}), and its mtime {T(ledger_m, "stat mtime "+CAMP+"/ledger/ledger.json")} is before the void attempts. '
  f'A re-run of the same tree is also blocked by the duplicate-tree rule ({rv("Re-evaluating the same tree")}). Completing c1c needs a reviewed evaluation-void rule or a new protocol revision.</p></div>'))

# ---------------- comparison table ----------------
crow, ccls = [], []
review_calls = {k_dseq: "noise-free gain", k_dp99: "RED FLAG (advisory)", k_drm: "WATCH", "swapin-disk.swapin_rand.p99_ns": "noise",
                "swapin-zram-64k.swapin_seq.mean_ns": "noise", k_zp99: "KILL not evaluable", "swapin-zram-64k.swapin_rand.mean_ns": "noise", "swapin-zram-64k.swapin_rand.p99_ns": "noise"}
for k in metrics:
    m = r68["analysis"]["metrics"][k]; g = guard(k); nr = m["noise_relative"]
    v1 = ("outside guard" if not m["guard_pass"] else ("gain beyond noise" if m["median_ratio"] >= 1 + nr else "within noise"))
    rs = c1c_ratios[k]; n = len(rs)
    if n:
        below = sum(1 for x in rs if x < g); above = sum(1 for x in rs if x >= 1 + nr)
        v2 = (f"below guard in {below}/{n}" if below else (f"gain in {above}/{n}" if above == n else "inside noise"))
    cell_c1c = " / ".join(N(fr(x), f"derived: {P66} pairs[{i}].a[{k}]/b[{k}]") for x, i in zip(rs, c1c_pairidx[k]))
    crow.append([f'<code>{e(short(k))}</code>' + (" <small>(advisory)</small>" if k in adv else ""),
                 N(fr(g), f"derived: exp(-{PCALF} analysis.noise_log[{k}])"),
                 N(fr(m["median_ratio"]), P68+f" analysis.metrics[{k}].median_ratio"),
                 f'<span class="{"st-pass" if m["guard_pass"] else "st-fail"}">{e(v1)}</span> <small>guard_pass {N(m["guard_pass"], P68+f" analysis.metrics[{k}].guard_pass")}</small>',
                 cell_c1c, N(n, f"derived: {P66} pairs containing {k}"),
                 f'<b>INCOMPLETE</b> ({N(n, f"derived: {P66} pairs containing {k}")} of {N(cmp_pairs, CAMP+"/protocol.json tiers.fast.comparison_pairs")} pairs) · ' + N(v2, f"derived: {P66} pair ratios vs guard exp(-noise_log) and 1+noise_relative ({P68} analysis.metrics[{k}].noise_relative)"),
                 f'<span data-src="review2: Red-flag calls table">{e(review_calls[k])}</span>'])
    ccls.append(["", "", "", "", "inc", "inc", "inc", ""])
H.append(section("compare", "Both rounds against baseline 5e84ca92, per metric", "Ratio = baseline ÷ candidate latency, so above 1 means the candidate is faster. Guard = lower edge of the A/A noise envelope from calibration e8b7a7e3. Hatched cells are incomplete: they are partial pairs, not a protocol decision.",
  '<div class="card">' + table(["metric", "guard", "c1 68de12e0 median (n=4)", "c1 verdict", "c1c 66a07143 pair ratios", "n", "c1c status", "review2 call"], crow, (1, 2, 4, 5), ccls) +
  f'<p>Read across: c1c keeps most of c1\'s disk sequential gain and removes c1\'s zram tail loss (zram seq.p99 {N(fr(c1c_ratios[k_zp99][0]), f"derived: {P66} pairs[0] {k_zp99}")} in its one pair against c1\'s {N(fr(r68["analysis"]["metrics"][k_zp99]["median_ratio"]), P68+f" analysis.metrics[{k_zp99}].median_ratio")}). '
  f'But it adds a disk tail cost: disk seq.p99 is below its guard in both pairs. That metric is advisory in rev7, so it could never cause a REGRESSION, but it is a real cost unless more pairs refute it. Disk rand.mean is a scored metric and sits just above its guard; two more pairs could turn it into a REGRESSION ({rv("**Disk rand.mean.**")}).</p></div>'))

# ---------------- review ----------------
def rv_block(tag):
    s = find_line(RV, f"**({tag})"); 
    if not s: return None, None
    nxt = [find_line(RV, f"**({t})") for t in "abcd" if t > tag] + [find_line(RV, "## Limitations")]
    end = min(x for x in nxt if x and x > s)
    return s, [l for l in RV[s-1:end-1] if l.strip()]
steps = []
for tag, title in [("a", "Formal gates on hurricpc-wsl"), ("b", "Harness and protocol proposals"), ("c", "Funding"), ("d", "Process")]:
    s, lines = rv_block(tag)
    items = [re.sub(r"^\s*(\d+\.|-)\s*", "", l).replace("**", "") for l in (lines or [])[1:] if re.match(r"^\s*(\d+\.|-)\s", l)]
    steps.append(f'<li data-src="review2: line {s}"><b>({tag}) {e(title)}</b> — owner proposal, not applied.<ul>' + "".join(f"<li>{e(i)}</li>" for i in items) + "</ul></li>")
H.append(section("review", "Round-2 Swap Review: NEEDS-MORE-EVIDENCE", f'Fail-closed, read-only review ({N(rv_verdict, "review2: line of ## Verdict")} in review2). No REJECT trigger; one advisory red flag; one watch item.',
  '<div class="card"><p>Parent judgement: c1c is a clean, correctness-passing, mechanism-confirmed candidate with an unproven performance profile. Do not promote it, open a slow tier, or call the result “passed”. '
  'Do not use a void to make this evaluation look complete. Preserve all run rows, guest directories and report.json unmodified; any void must be an appended record (review2: Integrity notes).</p></div>'
  + '<div class="card"><p class="chart-title">Next steps (a)–(d): owner proposals from review2, none applied</p><ul>' + "".join(steps) + '</ul></div>'))

# ---------------- guest accounting ----------------
grows = []
for lbl, pfx, pool in [("rev6 probe (rev6 budget)", None, "probe")] + [
        ("86fc2f67 probe calibration", "86fc2f67", "probe"), ("16fe9d24 fast calibration (voided)", "16fe9d24", "fast"),
        ("0c2cd749 fast calibration (voided)", "0c2cd749", "fast"), ("e8b7a7e3 fast calibration", "e8b7a7e3", "fast"),
        ("c1 correctness", "c1-v2-c1-xs-sync-ra-correctness", "fast"), ("3a554e3b c1 probe", "3a554e3b", "probe"), ("68de12e0 c1 fast", "68de12e0", "fast")] + r2_groups:
    if pfx is None:
        grows.append([e(lbl), "probe", N(rev6_total, REV6+"/ledger/budget.json guests+probe_guests"), "—", "before rev7"]); continue
    rnd = "round 2" if (pfx.startswith("c1c") or pfx in ("bc73887e", "66a07143")) else ("round 1" if pfx.startswith("c1-") or pfx in ("3a554e3b", "68de12e0") else "calibration")
    grows.append([e(lbl), pool, N(cp(pfx), f"{CAMP}/ledger/guest-reservations/{pfx}*.json count"), N(cd(pfx), f"{CAMP}/runs/guests/{pfx}* dir count"), rnd])
H.append(section("budget", f"Guest accounting: {N(rev6_total + rev7_total, 'derived: rev6 + rev7 budget.json')} of {N(MANDATE, PC)} used; round 2 used {N(r2_used, 'derived: reservations c1c-correctness + bc73887e + 66a07143')}",
  "Recounted from reservation manifests and checked against budget.json, the executor's GUEST-ACCOUNTING.md and the round-1 view. Counted guests include the two that never booted.",
  '<div class="card"><div class="tiles">'
  f'<div class="tile"><div class="label">Run-wide mandate (whole run)</div><div class="value" style="font-size:20px">{N(rev6_total + rev7_total, "derived")} / {N(MANDATE, PC)}</div><div class="note">left {N(MANDATE - rev6_total - rev7_total, "derived: 120 − 103")}; the 120 run-wide figure is {PC} only</div></div>'
  f'<div class="tile"><div class="label">rev7 per-campaign</div><div class="value" style="font-size:20px">{N(rev7_total, CAMP+"/ledger/budget.json guests+probe_guests")} / {N(fast_cap + probe_cap, CAMP+"/campaign.json budget")}</div><div class="note">fast {N(budget["guests"], CAMP+"/ledger/budget.json guests")}/{N(fast_cap, CAMP+"/campaign.json budget.guest_attempts")}, probe {N(budget["probe_guests"], CAMP+"/ledger/budget.json probe_guests")}/{N(probe_cap, CAMP+"/campaign.json budget.probe_guest_attempts")}</div></div>'
  f'<div class="tile"><div class="label">After round 1 → after round 2</div><div class="value" style="font-size:20px">{N(r1end_val, f"rundir:LOG.md line {l_r1end} global …/120")} → {N(rev6_total + rev7_total, "derived")}</div><div class="note">+{N(rev6_total + rev7_total - int(r1end_val) if r1end_val else None, "derived: 103 − 90")} = round-2 reservations {N(r2_used, "derived")}</div></div></div>'
  f'<p><b>Reconciliation.</b> Reservation files {N(len(reservations), CAMP+"/ledger/guest-reservations/*.json count")} = budget.json {N(budget["guests"], CAMP+"/ledger/budget.json guests")} + {N(budget["probe_guests"], CAMP+"/ledger/budget.json probe_guests")}. '
  f'GUEST-ACCOUNTING.md says rev7 {N(ga_tot_val[0], f"rundir:GUEST-ACCOUNTING.md line {ga_total}")} counted / {N(ga_tot_val[1], f"rundir:GUEST-ACCOUNTING.md line {ga_total}")} booted and global {N(ga_glob_val[0], f"rundir:GUEST-ACCOUNTING.md line {ga_global}")}/{N(ga_glob_val[1], f"rundir:GUEST-ACCOUNTING.md line {ga_global}")} with {N(ga_glob_val[2], f"rundir:GUEST-ACCOUNTING.md line {ga_global}")} remaining: all match. '
  f'Guest directories {N(len(guestdirs), CAMP+"/runs/guests/* count")} = booted; the two counted-not-booted guests are 0c2cd749 (refused before QEMU) and 66a07143 r2 (reserved as STOP landed). '
  f'Round 2 planned {N(proto["planned_guest_counts"]["one_round"], CAMP+"/protocol.json planned_guest_counts.one_round")} + {N(1, "reserve " + PC + " (round-1 plan: one_round + 1)")} reserve and used {N(r2_used, "derived")}. '
  f'At the stop, the per-campaign pools still had fast {N(fast_cap - budget["guests"], "derived: 96 − 79")} and probe {N(probe_cap - budget["probe_guests"], "derived: 24 − 15")}. The binding limit was the coordinator\'s one-rerun rule for round 2, not a pool. '
  f'Ending the mandate with {N(MANDATE - rev6_total - rev7_total, "derived")} guests unspent, and not running round 3, are coordinator decisions ({PC}; rundir:LOG.md line {l_void}).</p>'
  + details("Reservation groups (exact)", table(["group", "pool", "counted", "guest dirs", "phase"], grows, (2, 3))) + '</div>'))

# ---------------- cleanup ----------------
dfs = [(i, archlog[i + 1]) for i, l in enumerate(archlog) if l.startswith("Filesystem")]
oks = [(i, l) for i, l in enumerate(archlog) if " OK removed " in l]
late = [(i, l) for i, l in oks if l[11:16] >= "13:00"]
lrows = [[N(l[11:19], f"archive:LOG.txt line {i+1}", "{} PDT"), f'<code>{e(re.sub(r"/workspace/|/tmp/", "<box>/", l.split(" OK removed ")[1].split(" (")[0]))}</code>',
          N(re.search(r"entries=(\d+)", l).group(1) if re.search(r"entries=(\d+)", l) else None, f"archive:LOG.txt line {i+1} entries")] for i, l in late]
prune = find_line(archlog, "worktree prune")
dfrows = [[N(archlog[i - 1][:19], f"archive:LOG.txt line {i}"), N(f"{int(l.split()[3]):,}", f"archive:LOG.txt line {i+2} IFree"), N(l.split()[4], f"archive:LOG.txt line {i+2} IUse%")] for i, l in dfs]
dc = dfcap[-1].split(); dct = dfcap[1]
dfrows.append([N(dct[:19], "drafts:df-i-capture.txt line 2") + " <small>(box capture, not in LOG.txt)</small>", N(f"{int(dc[3]):,}", "drafts:df-i-capture.txt line 4 IFree"), N(dc[4], "drafts:df-i-capture.txt line 4 IUse%")])
H.append(section("cleanup", f"Box cleanup during rev7: {N(len(late), 'archive:LOG.txt count OK removed after 13:00')} trees archived, then removed", "Box hygiene only. Every removal was archived to a verified tar.zst first; no ledger, guest or evaluation file was touched.",
  '<div class="card">' + table(["removed at", "path", "entries"], lrows, (2,)) +
  (f'<p>The c1 worktree\'s git admin directory was archived, then pruned (archive:LOG.txt line {prune}); branch agents/v2-c1-xs-sync-ra was kept.</p>' if prune else "") +
  f'<p>All {N(len(sums), "archive:SHA256SUMS line count")} archives in SHA256SUMS verify (re-checked read-only during this audit); removed.tsv has {N(len(removed), "archive:removed.tsv line count")} rows. '
  f'The c1 close reason says its “worktree … kept as evidence” ({PC1} reason). The worktree was later archived and removed (rundir:LOG.md line {l_wt}), so it now survives only as a verified archive. See Discrepancies.</p>'
  + table(["df -i after", "IFree", "IUse%"], dfrows, (1, 2)) +
  f'<p>The latest <code>df -i</code> inside archive:LOG.txt is {N(f"{int(dfs[-1][1].split()[3]):,}", f"archive:LOG.txt line {dfs[-1][0]+2} IFree")} free. The ≈1.19M figure ({PC}) matches only a live box reading taken for this report (drafts:df-i-capture.txt); LOG.txt has no later <code>df -i</code>.</p></div>'))

# ---------------- models ----------------
mrows = [["Cloud agent: rev7 protocol (PR #8)", "<code>bc-9fa8e17e</code>", f"grok-4.7 <small>({PC})</small>", f'commit author “{N(authors["ab800d77"], "git log -1 --format=%an ab800d77")}”; model not recorded in git'],
         ["Cloud agent: void tool", "<code>bc-33e85066</code>", f"grok-4.7 <small>({PC})</small>", f'commit author “{N(authors["87dc7357"], "git log -1 --format=%an 87dc7357")}”; model not recorded in git'],
         ["Hypothesis teammate", "—", "default (not separately logged)", ""],
         ["Experiment teammate (executor)", "—", "default (not separately logged)", f'rundir:LOG.md lines say only “model: Grok Bot” (e.g. line {l_fast})'],
         ["Review teammate", "—", "default (not separately logged)", ""],
         ["Report teammate (this page)", "—", "default (not separately logged)", ""],
         ["Coordinator", "—", "default (not separately logged)", ""]]
H.append(section("models", "Models per step", f"No quota was exhausted, so no fallback model was used ({PC}). Not verifiable from repository files.", '<div class="card">' + table(["step", "agent id", "model", "evidence"], mrows) + '</div>'))

# ---------------- end of mandate ----------------
H.append(section("end", "End of mandate: what stands, what is open", "Two rounds ran; the third was not run for budget reasons (" + PC + ").",
  '<div class="card"><ul>'
  f'<li><b>c1</b>: {N(r68["status"], P68+" status")} as a non-regression screen; review NEEDS-MORE-EVIDENCE; status {N(c1["status"], PC1+" status")}. Close reason (verbatim, {PC1} <code>reason</code>; same text in ledger/events.jsonl candidate_closed): “{e(re.sub(r" \(/workspace/[^)]*\)", " (round-1 review file)", c1["reason"]))}”</li>'
  f'<li><b>c1c</b>: status {N(c1c["status"], PC1C+" status")} (left active for owner review, rundir:LOG.md line {l_stopkeep}); fast {N(r66["status"], P66+" status")}, INCOMPLETE; review NEEDS-MORE-EVIDENCE.</li>'
  f'<li><b>STOP</b> file left in place as the end-of-mandate stop (rundir:LOG.md line {l_stopkeep}).</li>'
  f'<li><b>Open for Hurric</b>: approve or reject rev7 (PR #8) and review the void tool (no PR); decide on review2 steps (a)–(d); run the formal gates; resolve import-state (SKIPPED); fund a rev8 completion run and a KVM arm, or stop.</li>'
  '<li><b>Not claimed</b>: no acceptance, no promotion, no KVM result, no lockdep/KASAN result, no zswap-mixed result.</li></ul></div>'))

# ---------------- audit ----------------
aud = (f'<p>Pre-registration record sha256 <code>{N(c1c_sha[:16], "sha256sum "+PC1C)}…</code>. Its <code>protocol_sha256</code> {N(c1c["protocol_sha256"][:8], PC1C+" protocol_sha256")} is the controller\'s protocol_hash (campaign policy.json + analysis.py + controller.py, controller.py L68–73), recomputed here as {N(proto_hash[:8], "derived: protocol_hash() over current files")}. It is not the protocol.json file hash, so it is not a mismatch.</p>'
       f'<p>Fingerprint {N(r66["fingerprint"][:8], P66+" fingerprint")}, candidate_tree {N(r66["candidate_tree"][:8], P66+" candidate_tree")}, probe_id {N(r66["probe_id"][:8], P66+" probe_id")}, mechanism <code>{N(r66["mechanism"], P66+" mechanism")}</code>.</p>'
       f'<p>Pinned code: {link("evolve/control/void_calibration.py", None, WF)}, {link("evolve/control/void_calibration.py", None, VT)}, {link("evolve/standard_workflow.py", None, WF)}, {link(CAMP+"/protocol.json", None, AB)}, {link(CAMP+"/policy.json", None, AB)}.</p>')
H.append(f'<details class="audit"><summary>Audit and provenance (closed by default)</summary>{aud}</details>')

nav = "".join(f'<a href="{h}">{e(t)}</a>' for h, t in [("round1.html", "Round 1 ↗"), ("#system", "System"), ("#round2", "Round 2"), ("#fast", "Fast run"), ("#compare", "Comparison"), ("#review", "Review"), ("#budget", "Budget"), ("#cleanup", "Cleanup"), ("#models", "Models"), ("#end", "End of mandate")])
page = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>DRAFT · Summary · xswap-tcg-kbench-rev7-2026-10-29</title><style>{CSS}{EXTRA}</style></head><body><div class="viz-root"><main>'
        f'<header><button class="toggle" type="button">Theme</button><h1>Summary: no readahead candidate accepted; c1c needs a completed fast tier</h1>'
        f'<p>xswap-tcg-kbench-rev7-2026-10-29 · baseline 5e84ca92 · QEMU TCG · rounds 1–2 of {N(proto["planned_guest_counts"]["three_rounds"] // proto["planned_guest_counts"]["one_round"], "derived: protocol.json planned_guest_counts.three_rounds / one_round")} · {N(rev6_total + rev7_total, "derived: rev6 + rev7 budget.json")} guests · 2026-10-29</p><nav>{nav}</nav></header>'
        + "".join(H) + f'</main></div><script>{JS}</script></body></html>')
OUT.write_text(page)
print("wrote", OUT, len(page), "bytes; TODOs:", len(TODOS)); [print(" -", t) for t in TODOS]
