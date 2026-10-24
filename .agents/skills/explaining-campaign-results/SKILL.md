---
name: explaining-campaign-results
description: Use when a campaign, experiment round or candidate evaluation has finished and its results need to be explained to a reviewer, or when asked for an HTML page, visual report or review page about what changed and what the measurements showed.
---

# Explaining campaign results

## Overview

The output is a single self-contained HTML page that a reviewer can check
in five minutes. Pictures carry the argument: every claim has one chart or
diagram, and the chart title states the claim. Prose is limited to one-line
captions. `scripts/build_page.py` renders a JSON spec and enforces the text
budget.

## The page, in order

| # | Section | Form | Content |
|---|---|---|---|
| 1 | Verdict | status badge + headline + ≤4 tiles | accepted / rejected / inconclusive / needs-review; boots run, gates passed, effect size |
| 2 | What changed | `flow` + one `diff` per candidate | where the change sits in the code path; the exact patch |
| 3 | How it was measured | `flow` | baseline → build → guest phases → metrics, with the scored phase highlighted |
| 4 | What the data shows | `strip`, `lines`, `bars` | one dot per run, always including A/A or baseline runs; counters across phases; mechanism counters |
| 5 | Why | `flow` | the cause chain behind the result, `bad`/`good` tones on the decisive step |
| 6 | Review checklist | `checklist` | every gate as pass / fail / missing, with an evidence path; open questions as `warn` |
| 7 | Next | `flow` or `table` | ranked next hypotheses, each with its falsifier |

## Steps

1. Read the campaign report, its machine-readable summary, the protocol and
   the candidate patches.
2. Write a throwaway extraction script that turns the summary into
   `spec.json`. Every number on the page comes from that script.
3. Write each takeaway as a claim with a number, for example "Disk retains
   219 clusters whenever a shrink ran (9/9 boots)".
4. Build the page: `python3 scripts/build_page.py spec.json explainer.html`.
   A text-budget error means the content belongs in a chart or a table.
5. Render the page in both themes with a headless browser, take
   screenshots, and fix label collisions, overflow and empty charts.
6. Save `explainer.json` and `explainer.html` next to the campaign report,
   and follow AGENTS.md to publish report artifacts in a separate main commit,
   keeping experimental code on its branch. Verify the deployment and live page
   before linking it as published. A push to `main` publishes
   every `results/<campaign>/explainer.html` to
   `https://ericzhang-zxh.github.io/Swap-Next/<campaign>/` through
   `.github/workflows/pages.yml` (`scripts/build_site.py` builds the index).

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
| A neutral chart title ("Mapped clusters") | Make the title state the finding |
| Four or more series on one chart | Split into small multiples; the builder colors three |
| Typing numbers into the spec by hand | Generate the spec from the summary with a script |
| A paragraph explaining a chart | Shorten it to one caption, or turn it into a `table` |
| A checklist that lists only passing gates | List every policy gate, including missing ones |
