---
name: explaining-campaign-results
description: Use when a campaign, experiment round or candidate evaluation has finished and its results need to be explained to a reviewer, or when asked for an HTML page, visual report or review page about what changed and what the measurements showed.
---

# Explaining campaign results

## Overview

Generate a self-contained HTML page for human review in five minutes. Put the
verdict first, then explain why the experiment existed before showing its
implementation and results. Prefer diagrams and charts to tables. Use short
captions to connect the pictures; keep exact measurements and audit material
available on demand.

## The page, in order

1. **Verdict.** Start with accepted / rejected / inconclusive / needs-review,
   whether to continue, and the main benefit and cost in plain language. Prefer
   qualitative summary tiles; exact effect sizes belong in expandable details.
2. **Context and motivation.** Show the original path, the cost or problem being
   addressed, and why the proposed mechanism might help. Assume the reader has
   not followed the campaign conversation. Distinguish the hypothesis from the
   measured finding.
3. **What changed.** Use before/after or branching flow diagrams to show each
   candidate's actual change and its expected tradeoff. Put exact patches in
   collapsed evidence. State whether candidates are independent or stacked.
4. **Results and explanation.** Use charts for the decisive comparisons and
   diagrams for the mechanism. Keep failures, uncertainty and important coverage
   limits visible. Label causal interpretations as inference unless demonstrated.
5. **Next.** Show the next hypothesis, the cost it addresses and the observation
   that would falsify it, using a short flow or diagram. End with expandable
   evidence: measurement protocol, full samples, counters, patches and checks.

## Visual and disclosure rules

- Pictures carry the explanation. Prefer `flow` for paths and cause chains,
  `strip` for paired samples and `lines`/`bars` for comparisons. Use tables for
  exact lookup inside closed `<details>`, not as the default reading experience.
- Keep chart axes, units, baseline and direction of improvement visible so the
  picture is interpretable. Exact per-run values, percentages, thresholds and
  full numeric tables are hidden by default and revealed on demand. Do not hide
  the existence of a failed gate, a material regression or missing coverage.
- Use takeaway titles that state the finding in plain language. Derive every
  number from the evidence; do not require a number in each title.
- Keep data tables and audit sections closed on initial load on desktop and
  mobile. Never replace a mobile chart with an automatically expanded table.
  Reflow diagrams where practical, otherwise allow local horizontal scrolling
  with legible labels and no whole-page overflow.
- Preserve all required evidence behind disclosure controls and pinned links.
  Collapsing evidence must not remove failed attempts or change the verdict.

## Steps

1. Read the campaign report, machine-readable summary, protocol and patches.
2. Write an extraction script that derives `explainer.json` from that evidence.
   Use the page order above and separate overview sections from audit material.
3. Build with `python3 scripts/build_page.py explainer.json explainer.html`.
   Chart tables are already collapsed. Where the renderer lacks audit-section
   disclosure, add reproducible post-processing in the campaign generator to
   wrap those sections in closed `<details>`; retain verdict-first ordering.
   A text-budget error means shorten the overview or move detail into evidence.
4. Render light and dark themes and a narrow mobile viewport. Check readable
   labels, no overlap or whole-page overflow, visible charts, no visible numeric
   tables on initial load, and working evidence expand/collapse controls.
5. Save the source spec, generator and HTML next to the report. Follow AGENTS.md
   for report-only publication independently of candidate promotion. Build the
   Pages index with `scripts/build_site.py`, verify the deployment for that
   commit and the live page and index before claiming publication complete.
   Pages collects `results/<campaign>/explainer.html` from main and serves it at
   `https://ericzhang-zxh.github.io/Swap-Next/<campaign>/`.

## Spec reference

```json
{"title": "...", "subtitle": "baseline · date · boots",
 "verdict": {"status": "rejected", "headline": "...", "tiles": [{"label": "", "value": "", "note": ""}]},
 "sections": [{"id": "data", "title": "What the data shows", "lead": "one sentence",
   "blocks": [{"type": "strip", "takeaway": "...", "x_label": "", "groups": [], "series": [],
               "points": [{"group": "", "series": "", "value": 0, "tip": ""}]}]}]}
```

| Block | Required fields | Use for |
|---|---|---|
| `flow` | `nodes[{id,label,sub?,col,row,tone?}]`, `edges[{from,to,label?}]` | pipelines, code paths, cause chains; tones `default focus bad good muted` |
| `strip` | `groups`, `series` (≤3), `points` | per-run distributions, regimes, A/A spread |
| `lines` | `x` (phases), `series`, `lines[{series,label,values}]` | a counter's trajectory across phases |
| `bars` | `categories`, `series`, `values{series:[...]}` | mechanism counters per candidate |
| `diff` | `patch` | the exact candidate change |
| `checklist` | `items[{status,label,evidence}]` | gates and reviewer questions |
| `table` | `columns`, `rows`, `numeric?` | anything a reader looks up rather than compares |
| `note` | `text` | one callout per section, at most |

Every chart block takes `takeaway` (rendered as its title) and an optional
`note`. Charts get hover tooltips and a table view automatically.

## Common mistakes

| Mistake | Fix |
|---|---|
| Plotting means of two runs | Plot every run as a dot, with the baseline/A/A group in the same chart |
| A neutral chart title ("Mapped clusters") | State the finding in plain language; keep exact figures expandable |
| Four or more series on one chart | Split into small multiples; the builder colors three |
| Typing numbers into the spec by hand | Generate the spec from the summary with a script |
| Starting with context before the verdict | Lead with the decision, then explain context and motivation |
| Showing exact data or tables by default | Keep visuals visible and exact data in closed details |
| A paragraph explaining a chart | Use a short caption or a cause-chain diagram; move detailed lookup into closed evidence |
| A checklist that lists only passing gates | List every policy gate, including missing ones |
