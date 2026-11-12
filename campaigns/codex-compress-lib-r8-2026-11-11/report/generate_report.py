#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build the follow-up report from the closed campaign and public observations."""
from hashlib import sha256
import html
import json
from pathlib import Path
import re
import runpy
import subprocess
import sys
import time

report = Path(__file__).resolve().parent
root = report.parents[2]
campaign = report.parent.name
sys.path[:0] = [str(root / name) for name in ("evolve", "evolve/control", "campaigns")]
import delivery
from render_compression_closeout import CSS, SCENES

SCENES = {**SCENES, "changes": '<section id="changes"><h2>3. The repair: keep the measuring tool resident</h2>\n<p class="lead">The kernel reports successful decompression for the whole measuring process. A page used by the tool can produce an event in the same window as the application data it meant to measure.</p>\n<div class="scene"><div class="scene-grid">\n<div class="scene-box"><p class="scene-label">Before</p><h3>Two kinds of pages can fault</h3><div class="pages"><div class="page-object compressed">A</div><div class="page-object compressed">T</div></div><p>The target page A and a page used by the timing tool T can both be reclaimed. The trace identifies the process and leaves the page addresses unknown.</p></div>\n<div class="scene-box focus"><p class="scene-label">After</p><h3>Target pages stay eligible for swap</h3><div class="pages"><div class="page-object compressed">A</div><div class="page-object">T</div></div><p>The test keeps the tool\'s mappings resident, unlocks the target range, and checks both conditions before and after measuring.</p></div>\n</div><p class="scene-cost">The timed load and the requirement for exactly one successful decoder return per page remain the same. The isolation checks happen outside the timed load.</p></div></section>'}


def sha(path):
    return sha256(path.read_bytes()).hexdigest()


summary = delivery.extract(root, campaign)
story = delivery.read(report / "story.json")
obs_path = report / "observations.json"
obs = delivery.read(obs_path)
if (summary["status"] != "closed" or obs["native_evidence_sha256"] != summary["evidence_sha256"]
        or story["observations_sha256"] != sha(obs_path)):
    raise ValueError("report does not match the closed campaign evidence")

spec = delivery.make_spec(summary, story)
spec.update(subtitle=story["subtitle"], card_metadata=story["card_metadata"])
spec["verdict"].update(label=story["verdict_label"], tiles=story["verdict_tiles"])
sections = {section["id"]: section for section in spec["sections"]}
spec["sections"] = [sections[key] for key in
                    ("context", "system", "subsystem", "changes", "results", "next", "patches", "evidence")]
sections["results"].update(title="What the run established", lead=story["results_lead"],
                           blocks=[{"type": "note", "text": story["results_detail"]}])
if "chart" in story:
    sections["results"]["blocks"].append(story["chart"])
sections["evidence"]["blocks"].insert(0, {
    "type": "table", "takeaway": "Diagnostic and resource evidence",
    "columns": ["Observation", "Value"], "rows": obs["audit_rows"],
})
sections["evidence"]["blocks"].insert(1, {
    "type": "table", "takeaway": "Counted follow-up attempts",
    "columns": ["Run", "Purpose", "Valid environment", "Passed workload"],
    "rows": [[row["id"], row["purpose"], row["run_valid"], row["integration_pass"]]
             for row in obs["attempts"]],
})
builder = runpy.run_path(str(root / ".agents/skills/explaining-campaign-results/scripts/build_page.py"))
page, budget = builder["build"](spec)
if budget.errors:
    raise ValueError("; ".join(budget.errors))
for key, scene in SCENES.items():
    page, count = re.subn(r'<section id="' + key + r'">.*?</section>',
                          lambda _: scene, page, count=1, flags=re.S)
    if count != 1:
        raise ValueError("missing scene " + key)
page = page.replace("</style>", CSS + ".audit{overflow:auto}.audit table{min-width:600px}"
                    "@media(max-width:600px){main{padding:20px 12px}.card{padding:14px}"
                    ".verdict{flex-wrap:wrap}.card:has(svg){overflow-x:auto}}</style>")
for key, label in (("patches", "Shared compression library source"),
                   ("evidence", "Exact observations and evidence")):
    page, count = re.subn(r'<section id="' + key + r'">.*?</section>',
                          lambda match: '<details class="audit"><summary>' + label + '</summary>'
                          + match.group(0) + '</details>', page, count=1, flags=re.S)
    if count != 1:
        raise ValueError("missing disclosure " + key)
page = page.replace("</script>", """document.querySelectorAll('nav a').forEach(link => link.addEventListener('click', () => {
  const section = document.getElementById(link.hash.slice(1));
  const disclosure = section && section.closest('details');
  if (disclosure) disclosure.open = true;
}));</script>""")
source_base = "https://github.com/ericzhang-zxh/Swap-Next/blob/" + story["source_commit"] + "/"
sources = {ref for section in story["sections"] for ref in section["evidence"]}
sources.update((str(obs_path.relative_to(root)),
                f"campaigns/{campaign}/candidates/c1-shared-store-r8/correctness.json"))
sources = sorted(sources)
for ref in sources:
    archived = subprocess.check_output(["git", "-C", str(root), "show", story["source_commit"] + ":" + ref])
    if sha256(archived).hexdigest() != sha(root / ref):
        raise ValueError("report source differs from its pinned bytes: " + ref)
links = "".join('<li><a href="' + html.escape(source_base + ref, quote=True) + '">'
                + html.escape(ref) + '</a></li>' for ref in sources)
links += '<li><a href="../codex-compress-lib-r7-2026-11-11/">Previous family report</a></li>'
page = page.replace("</main>", '<details class="audit"><summary>Pinned sources and previous report</summary><ul>'
                    + links + "</ul></details></main>")
dated = report / (campaign + "-" + story["date"])
dated.mkdir(exist_ok=True)
(dated / "explainer.html").write_text(page)
delivery.write(dated / "explainer.json", spec)
delivery.write(report / "summary.json", summary)

lines = ["# " + story["title"], "", "**" + story["verdict_label"] + ".** " + story["headline"],
         "", "## Results", "", story["results_lead"], "", story["results_detail"], ""]
for section in story["sections"]:
    lines.extend(["## " + section["title"], "", section["lead"], ""])
    for block in section["blocks"]:
        if block["type"] == "note":
            lines.extend([block["text"], ""])
lines.extend(["<details>", "<summary>Shared compression library source</summary>", ""])
for patch in story["patches"]:
    lines.extend([patch["takeaway"], "", "[Pinned patch](" + source_base + patch["source"] + ")", "",
                  "```diff", patch["patch"].rstrip(), "```", ""])
lines.extend(["</details>", "", "<details>", "<summary>Exact evidence</summary>", "",
              "[Public observations](observations.json) · [Native summary](summary.json)", "",
              *[f"- [{ref}]({source_base}{ref})" for ref in sources], "", "</details>", "",
              "[Interactive report](" + dated.name + "/explainer.html)", ""])
(report / "REPORT.md").write_text("\n".join(lines))

artifacts = {name: sha((dated if name.startswith("explainer.") else report) / name)
             for name in delivery.OUTPUTS}
receipt_path = report / "delivery.json"
previous = delivery.read(receipt_path) if receipt_path.exists() else {}
story_hash = sha(report / "story.json")
if (previous.get("artifacts"), previous.get("evidence_sha256"), previous.get("story_sha256")) != (
        artifacts, summary["evidence_sha256"], story_hash):
    delivery.write(receipt_path, {
        "schema_version": 1, "campaign": campaign, "state": "generated", "artifacts": artifacts,
        "evidence_sha256": summary["evidence_sha256"], "story_sha256": story_hash,
        "history": previous.get("history", []) + [{"state": "generated", "time": time.time()}],
    })
print(json.dumps({"campaign": campaign, "html_sha256": artifacts["explainer.html"]}))
