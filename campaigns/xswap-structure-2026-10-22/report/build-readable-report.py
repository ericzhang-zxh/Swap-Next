#!/usr/bin/env python3
"""Rebuild the visual overview while retaining the original evidence spec."""
import copy
import json
import pathlib
import re
import subprocess

p = pathlib.Path(__file__).resolve().parent
root = p.parents[1]
evidence = p / "evidence-spec.json"
if not evidence.exists():
    evidence.write_bytes((p / "explainer.json").read_bytes())
old = json.loads(evidence.read_text())
by_id = {s["id"]: s for s in old["sections"]}

def flow(title, labels):
    return {"type": "flow", "takeaway": title,
            "nodes": [{"id": str(i), "label": label, "col": i, "row": 0,
                       "tone": "focus" if i == 1 else "default"} for i, label in enumerate(labels)],
            "edges": [{"from": str(i), "to": str(i + 1)} for i in range(len(labels) - 1)]}

def note(text):
    return {"type": "note", "text": text}

primary = copy.deepcopy(by_id["data"]["blocks"][0])
primary["takeaway"] = "Tail-cache reclaim removes the high-retention regime in this workload"
primary["note"] = "Each dot is one boot: A baseline, B candidate. Fewer mapped clusters is better; this measures descriptors, not total RAM."
secondary = copy.deepcopy(by_id["data"]["blocks"][1])
secondary["takeaway"] = "High retention can return after another pressure cycle"
secondary["note"] = "Mapped clusters; lower is better. Second pressure is diagnostic."
sections = [
    {"id": "context", "title": "Why change metadata reclamation?", "blocks": [
        flow("Before: memory pressure leaves metadata behind", ["Application uses RAM", "Swap mappings grow", "Tail stays mapped"]),
        note("Xswap tracks pages with cluster descriptors. Shrink releases only a contiguous free tail. High cache-only slots can pin it. Hypothesis: better placement or blocker reclamation releases metadata.")
    ]},
    {"id": "system", "title": "Where these changes fit", "blocks": [
        {"type": "flow", "takeaway": "Allocation and metadata retirement surround the existing storage path", "nodes": [
            {"id": "app", "label": "Application pages", "sub": "Need RAM and safe reads", "col": 0, "row": 0},
            {"id": "alloc", "label": "Virtual slot allocator", "sub": "Low-first selection", "col": 1, "row": 0, "tone": "focus"},
            {"id": "store", "label": "Disk or zswap", "sub": "Existing page storage", "col": 2, "row": 0},
            {"id": "cache", "label": "Swap cache / PTEs", "sub": "Keep slots live", "col": 2, "row": 1},
            {"id": "shrink", "label": "Metadata shrink", "sub": "Tail-cache clears blockers", "col": 1, "row": 1, "tone": "focus"},
            {"id": "ram", "label": "Descriptor RAM", "sub": "Returned after safe retirement", "col": 0, "row": 1}],
         "edges": [{"from": "app", "to": "alloc"}, {"from": "alloc", "to": "store"}, {"from": "store", "to": "cache"}, {"from": "cache", "to": "shrink"}, {"from": "shrink", "to": "ram"}]},
        note("Application and backend roles stay unchanged. Metadata savings leave RAM for useful work, but are small here. Low-first adds lock work; tail-cache risks later swap-out I/O and more frequent retirement.")
    ]},
    {"id": "mechanisms", "title": "Zoom in: two independent mechanisms", "blocks": [
        flow("Low-first: select a lower slot without moving live pages", ["Before: list order", "After: scan lowest", "Existing isolation"]),
        flow("Tail-cache: clear blockers before the existing tail shrink", ["Before: blocker stops", "Reclaim cache-only", "Revalidate and shrink"]),
        note("Candidates are independent. Tail-cache v2 includes the verified assertion fix. Internal helper retries prevent a strict runtime bound.")
    ]},
    {"id": "results", "title": "What changed in the measurements", "blocks": [primary, secondary,
        note("Low-first is inconclusive. Repeated pressure can leave new blockers after the last trigger. A source-level descriptor retirement race blocks promotion.")
    ]},
    {"id": "next", "title": "Repair lifetime safety before pursuing the mechanism", "blocks": [
        flow("Next steps depend on passing the preceding safety check", ["Repair reader lifetime", "Retest tail-cache", "Measure interior holes"]),
        note("Require baseline race reproduction and repair success. Retest with delayed retry; high retention would weaken the finding. Sanitizers, failure injection, confirmation and holdout remain missing. Warning failures are retained.")
    ]}
]
for section in old["sections"]:
    audit = copy.deepcopy(section)
    audit["id"] = "audit-" + audit["id"]
    sections.append(audit)
spec = {"title": "Can xswap release metadata after memory pressure?",
        "subtitle": "Structural campaign — allocation, tail reclamation and the lifetime blocker",
        "verdict": {"status": old["verdict"]["status"], "headline": "Promising reclamation, little RAM saved; a lifetime race blocks promotion",
                    "tiles": [{"label": "Tail-cache reclaim", "value": "Promising", "note": "High retention disappears in the primary workload."},
                              {"label": "Low-first allocation", "value": "Inconclusive", "note": "High retention remains; selection adds lock work."},
                              {"label": "Decision", "value": "Repair first", "note": "Source-level lifetime race; no promotion."}]},
        "sections": sections}
(p / "explainer.json").write_text(json.dumps(spec, indent=2) + "\n")
subprocess.run(["python3", str(root / ".agents/skills/explaining-campaign-results/scripts/build_page.py"), str(p / "explainer.json"), str(p / "explainer.html")], check=True)
h = (p / "explainer.html").read_text()
h = re.sub(r"<a href=\"#audit-[^\"]+\">.*?</a>", "", h)
h = re.sub(r"(<section id=\"audit-[^\"]+\">)(.*?)(</section>)", lambda m: "<details class=\"audit\"><summary>" + re.search(r"<h2>(.*?)</h2>", m[2]).group(1) + "</summary>" + m[0] + "</details>", h, flags=re.S)
h = h.replace("<details class=\"audit\">", "<h2 id=\"audit\">Evidence, when you need it</h2><p>Original samples, exact patches, protocol and all gates are retained. Expand to inspect.</p><details class=\"audit\">", 1)
h = re.sub(r"(<svg\b.*?</svg>)", lambda m: chr(60) + "div class=\"visual-scroll\">" + m[0] + "</div>", h, flags=re.S)
h = h.replace("</style>", "details.audit{margin:12px 0;border:1px solid var(--grid);border-radius:10px;padding:14px 18px;background:var(--surface-1)}details.audit>summary{font-weight:600;cursor:pointer}details.audit section{margin-top:20px}details.audit pre{overflow:auto}nav{flex-wrap:wrap}.visual-scroll{overflow-x:auto}.visual-scroll svg{min-width:640px}</style>")
h = h.replace("<summary>Table view</summary>", "<summary>Show exact measurements</summary>")
(p / "explainer.html").write_text(h)
