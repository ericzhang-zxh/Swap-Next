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
3. **What changed, in the larger system.** Start with a high-level system map:
   show the user/application goal, relevant components or layers, and the request
   or data path. Highlight where the change sits, its upstream/downstream
   dependencies, and which surrounding components stay unchanged. Explain why
   changing this location could affect the end-to-end outcome and where cost or
   work may move elsewhere in the system. Then zoom into before/after or branching
   flow diagrams for each candidate's actual mechanism and expected tradeoff.
   Use plain component roles before code symbols; keep the overview scoped to
   what helps explain this experiment. Put exact patches in collapsed evidence.
   State whether candidates are independent or stacked.
4. **Results and explanation.** Use charts for the decisive comparisons and
   diagrams for the mechanism. Keep failures, uncertainty and important coverage
   limits visible. Label causal interpretations as inference unless demonstrated.
5. **Next.** Show the next hypothesis, the cost it addresses and the observation
   that would falsify it, using a short flow or diagram. End with expandable
   evidence: measurement protocol, full samples, counters, patches and checks.

## Default visual standard

Use the owner-approved [swap-in review](../../../campaigns/xswap-swapin-2026-10-23/report/explainer.html)
as the presentation reference. Its reproducible generator and `system-story.html`
are in the same campaign directory. Adapt the visual vocabulary to the experiment;
do not reuse its findings or impose memory-page imagery on unrelated systems.

After the verdict, tell the story through three explicit zoom levels:

1. **Whole system:** orient the reader with concrete components, locations and
   objects. For memory work, show application, physical RAM, compressed contents
   inside RAM and disk. Establish the user-visible goal and cost.
2. **Relevant subsystem:** keep colors and identities consistent, fade unrelated
   components, and highlight exactly where the change sits. Distinguish data,
   metadata and control policy; show upstream/downstream relationships.
3. **Concrete change:** use the same objects in a before/after scene. Show what
   moves, becomes available, blocks progress or consumes work. Explain both the
   benefit and where the cost moves.

Prefer a few large, purposeful scenes over many small box-and-arrow diagrams.
Do not merely put prose inside boxes. Use spatial grouping, page/object tiles,
consistent colors and explicitly labeled actions to make the mechanism apparent.
Use a step-through interaction when sequence helps: show a meaningful comparison
on initial load, offer next/reset controls, and preserve a useful static explanation.
Mark illustrative counts, sizes and timing as schematic; real measurements remain
separate evidence. On phones, reflow scenes rather than shrinking the whole picture.

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
   Include an explicit `date` field (`YYYY-MM-DD`).
   Use the page order above and separate overview sections from audit material.
3. Build with `python3 scripts/build_page.py explainer.json explainer.html`.
   Chart tables are already collapsed. Where the renderer lacks audit-section
   disclosure, add reproducible post-processing in the campaign generator to
   wrap those sections in closed `<details>`; retain verdict-first ordering.
   A text-budget error means shorten the overview or move detail into evidence.
4. Render light and dark themes and a narrow mobile viewport. Check readable
   labels, no overlap or whole-page overflow, visible charts, no visible numeric
   tables on initial load, and working evidence expand/collapse controls.
   Capture fresh, unique per-campaign Visual QA screenshots (desktop light/dark,
   mobile light/dark); never copy screenshot files or hashes from prior campaigns.
5. **Async Publication Decoupling**: Once a campaign is closed with `close-campaign`,
   decouple report rendering, Visual QA, and publication so a dedicated report
   worker runs publication asynchronously on main while subsequent machine
   executions start immediately without blocking.
6. **Dated Entry & Layout**: Place published explainer pages under a dated directory
   (e.g. `campaigns/<c>/report/<c>-YYYY-MM-DD/explainer.html` and `explainer.json`)
   and remove any undated root duplicate so `build_site.py` outputs a clean, single
   entry.
7. **Standardized Card Metadata & Layout**: Run `scripts/build_site.py campaigns/ _site/`.
   - Card Top-Right Badge: Display resolved `YYYY-MM-DD` date (via multi-tier fallback: explicit `date` in `explainer.json`, `YYYY-MM-DD` in directory name, timestamps in `campaign.json`, `delivery.json`, or subtitle).
   - Card Bottom Metadata Bar: Unified, self-explanatory format across all homepage cards:
     `<harness> (<model>) · line: <line> · base <short-sha> · <N> candidate · <G> guests / <B> build`
     * Harness/model mapping: `agy (gemini4argon)` for exp1 through exp5, `codex (gpt-6-astra)` for codex-r01/r02, `grok-bot / claudecode (opus5.5)` for rev7 kbench, and `claudecode (opus5.5)` for historical 2026-10-21..2026-10-24.
     * `line: <line>`: from campaign line record (e.g. `line: demand`, `line: exp2-stride-gated-ra`).
     * `base <short-sha>`: 8-char short commit (e.g. `base 5e84ca92`).
     * `<N> candidate · <G> guests / <B> build`: execution scale and budget from candidate records and ledger budget.
   - Forbid Hostnames & Jargon: NEVER show hostnames (e.g. `hurricpc`) or internal protocol revision jargon (`rev7`/`rev6`) on the homepage cards. Translate host machine references to clean environments (`QEMU TCG` or `KVM`); protocol details remain inside the report page's expandable evidence section.
   - Campaign Deduplication: Deduplicate by campaign folder so each campaign produces at most one card on the homepage, prioritizing dated explainers and serving both dated and canonical URLs with HTTP 200.
8. **Live Verification**: Commit report artifacts to `main`, push to `origin/main`,
   and verify both `<site>/<campaign>/` (200 OK and expected content) and `<site>/`
   (ensuring the newest campaign is ordered at the very top of the index) before
   declaring publication complete.

## Spec reference

```json
{"title": "...", "subtitle": "<harness> (<model>) · line: <line> · base <short-sha> · <N> candidate · <G> guests / <B> build",
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
