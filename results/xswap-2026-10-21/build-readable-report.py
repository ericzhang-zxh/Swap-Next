#!/usr/bin/env python3
"""Rebuild the visual review from the preserved campaign evidence spec."""
import copy
import html
import importlib.util
import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
original = json.loads((HERE / "evidence-spec.json").read_text())
module_spec = importlib.util.spec_from_file_location(
    "report_renderer", ROOT / ".agents/skills/explaining-campaign-results/scripts/build_page.py")
renderer = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(renderer)


def flow(title, labels):
    return {"type": "flow", "takeaway": title,
            "nodes": [{"id": str(i), "label": label, "col": i, "row": 0,
                       "tone": "focus" if i == 1 else "default"}
                      for i, label in enumerate(labels)],
            "edges": [{"from": str(i), "to": str(i + 1)}
                      for i in range(len(labels) - 1)]}


def note(text):
    return {"type": "note", "text": text}


def evidence_chart(index, title):
    block = copy.deepcopy(next(s for s in original["sections"] if s["id"] == "data")["blocks"][index])
    block["takeaway"] = title
    return block


sections = [
    {"id": "context", "title": "Why tune metadata growth and shrink?", "blocks": [
        flow("Swap preserves application data while releasing application RAM",
             ["Memory pressure", "Move pages to swap", "Restore on demand"]),
        note("Xswap tracks virtual swap slots in mapped metadata. The experiment aimed to release unused metadata RAM after pressure, without increasing slow application reads. These are comparisons between xswap variants on the same baseline.")
    ]},
    {"id": "system", "title": "Where the change fits in the system", "blocks": [
        {"type": "flow", "takeaway": "The policy changes metadata capacity around the swap-slot lifecycle",
         "nodes": [
             {"id": "app", "label": "Application memory", "col": 0, "row": 0},
             {"id": "reclaim", "label": "Kernel reclaim", "col": 1, "row": 0},
             {"id": "slots", "label": "Xswap slots", "sub": "Allocate and free", "col": 2, "row": 0},
             {"id": "backend", "label": "Zswap or disk", "sub": "Store page contents", "col": 2, "row": 2},
             {"id": "policy", "label": "Metadata policy", "sub": "Changed constants", "col": 1, "row": 1, "tone": "focus"},
             {"id": "ram", "label": "Metadata RAM", "sub": "Map or unmap", "col": 0, "row": 1}],
         "edges": [{"from": "app", "to": "reclaim"}, {"from": "reclaim", "to": "slots"},
                   {"from": "slots", "to": "backend"}, {"from": "slots", "to": "policy"},
                   {"from": "policy", "to": "ram"}]},
        note("Application behavior and storage backends stay unchanged. Smaller retained mappings could free RAM, but more frequent shrinking adds unmap and synchronization work; larger growth batches may cause allocation bursts. The experiment measures metadata retention and guards read latency.")
    ]},
    {"id": "changes", "title": "Zoom in: the three candidate policies", "blocks": [
        flow("Before: grow under pressure; shrink only a free tail",
             ["Slots fill or free", "Check thresholds", "Map or unmap tail"]),
        flow("Shrink-min: allow a smaller reclaim batch",
             ["Free tail", "Lower batch minimum", "Try shrinking sooner"]),
        flow("Grow-cap: permit a larger batch per growth episode",
             ["Capacity needed", "Raise growth cap", "Try fewer episodes"]),
        flow("Grow-target: keep less headroom with the larger cap",
             ["Capacity needed", "Higher usage target", "Try retaining less"]),
        note("Each candidate starts from the same reference; they are independent alternatives. Grow-target includes the larger cap in its own patch. Locks, lifetime rules and the requirement for a contiguous free tail remain unchanged.")
    ]},
    {"id": "results", "title": "The comparison is dominated by the baseline split", "blocks": [
        evidence_chart(0, "Identical kernels already split into low and high retention"),
        note("Each dot is a boot; A/A uses the identical kernel on both sides. Lower mapped-cluster retention is better. Changing constants produced no detectable improvement beyond the baseline variability."),
        evidence_chart(2, "Retained mappings stop changing after the pressure phase"),
        flow("A surviving high slot can block reclaim below it",
             ["Pressure ends", "High slot survives", "Free tail stays short"]),
        note("High confidence: tail-only shrink limits reclamation. Cache-only slots are a plausible source of the surviving high slots, but that cause is untested. Growth counters respond to the knobs without a detectable retention or latency benefit.")
    ]},
    {"id": "next", "title": "Next: repair measurement, then test the structure", "blocks": [
        flow("Distinguish a pinned tail from genuinely occupied metadata",
             ["Measure high slots", "Re-pressure diagnostic", "Test structural change"]),
        note("Test interior unmapping or low-first allocation only after the metric is stable. Failure to reduce retained mappings or the high-state rate would falsify the respective hypotheses. Cache-only reclaim depends on confirming cache pinning."),
        note("Coverage: completed boots passed guest checks; one setup failure was repaired. A/A stability failed. Independent confirmation, holdout, failure injection, concurrency sanitizers and broader workload coverage remain missing. No candidate was promoted.")
    ]}
]
spec = {"title": "Can policy tuning reduce xswap metadata RAM?",
        "subtitle": "Historical campaign: 2026-10-21 · xswap Phase I/II baseline",
        "verdict": {"status": original["verdict"]["status"],
                    "headline": "Reject these candidates; fix the measurement before continuing",
                    "tiles": [
                        {"label": "Retained metadata", "value": "No detectable gain", "note": "Baseline variability dominates comparisons."},
                        {"label": "Mechanism", "value": "Tail stays pinned", "note": "Constant tuning leaves the structural limit in place."},
                        {"label": "Decision", "value": "Nothing promoted", "note": "Guest checks pass; acceptance coverage is incomplete."}]},
        "sections": sections}
# Render the concise overview and original audit separately with the unchanged
# renderer; both retain its prose limits. Exact original data is never rewritten.
page, budget = renderer.build(spec)
assert not budget.errors, budget.errors
assert budget.words <= renderer.MAX_PAGE_WORDS
spec["sections"] += [dict(copy.deepcopy(s), id="audit-" + s["id"]) for s in original["sections"]]
(HERE / "explainer.json").write_text(json.dumps(spec, indent=2) + "\n")
audit_page, audit_budget = renderer.build(original)
assert not audit_budget.errors, audit_budget.errors
fragments = re.findall(r"<section id=\"[^\"]+\">.*?</section>", audit_page, re.S)
assert len(fragments) == len(original["sections"])
audit = "<h2 id=\"audit\">Evidence, when you need it</h2><p>Original samples, protocol, patches, checks and next-step hypotheses.</p>"
# Preserve the original numerical verdict summary inside a closed disclosure too.
audit += '<details class="audit"><summary>Original verdict and exact summary</summary>'
audit += "<p>" + html.escape(original["verdict"]["headline"]) + "</p>"
audit += renderer.table_view(["Metric", "Value", "Note"], [[t["label"], t["value"], t["note"]] for t in original["verdict"]["tiles"]]) + "</details>"
for fragment in fragments:
    fragment = fragment.replace("<section id=\"", "<section id=\"audit-", 1)
    title = re.search(r"<h2>(.*?)</h2>", fragment).group(1)
    audit += "<details class=\"audit\"><summary>" + title + "</summary>" + fragment + "</details>"
page = page.replace("</main>", audit + "</main>")
assert audit in page
page = re.sub(r"(<svg\b.*?</svg>)", lambda m: '<div class="visual-scroll">' + m[0] + '</div>', page, flags=re.S)
page = page.replace("<summary>Table view</summary>", "<summary>Show exact measurements</summary>")
page = page.replace("</style>", """
details.audit{margin:12px 0;border:1px solid var(--grid);border-radius:10px;padding:14px;background:var(--surface-1);overflow-x:auto}
details.audit>summary{font-weight:600;cursor:pointer}details.audit section{margin-top:20px}
.visual-scroll{overflow-x:auto}.visual-scroll svg{min-width:640px}nav,.legend{flex-wrap:wrap}
.card{min-width:0}details{overflow-x:auto}@media(max-width:600px){.visual-scroll{padding-bottom:8px}}
</style>""")
(HERE / "explainer.html").write_text(page)
print(f"Built overview ({budget.words} words); retained {len(fragments)} original audit sections.")
