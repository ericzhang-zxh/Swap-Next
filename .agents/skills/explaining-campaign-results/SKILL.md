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

## Reader contract

Write for a technically curious reader encountering the project for the first
time. They have not read the conversation, board, earlier reports or source.
The default reading path must stand alone:

- Explain the user-visible goal, the current system and why the experiment was
  worth trying before relying on project-specific names. Introduce a component
  by its role, then its name; define necessary terms and acronyms at first use.
- Use descriptive stage names in prose, diagrams, captions and navigation.
  Internal campaign/round/ticket IDs, raw gate names, commit hashes and execution
  metadata belong in closed evidence or provenance details. A glossary is a
  supplement, not a prerequisite for understanding the overview.
- Separate what was implemented, what functional checks established, what
  performance measurements established, and what remains planned. A status such
  as `inconclusive` must identify the unresolved question and its concrete cause.
  Use `verdict.label` for a plain-language badge while preserving the native
  `verdict.status`; use `card_metadata` for readable homepage context.
- State the main benefit, cost, uncertainty and next decision in ordinary
  language. Explain mechanisms without assuming that a shorter code path is a
  measured speedup. Keep the failure and its consequence visible even when its
  diagnostic code lives in the evidence details.
- Review the initial page with all evidence closed. A new reader must be able
  to answer: What problem matters? What changed? What was actually tested?
  What happened? Why is any conclusion unresolved? What happens next?
  Rewrite any answer that requires an internal label or an earlier report.

## The page, in order

1. **Verdict.** Start with the plain-language finding and decision, including
   whether to continue and the main benefit and cost. Preserve the native
   accepted / rejected / inconclusive / needs-review status in the data, and
   explain its scope visibly; it cannot replace the finding. Prefer
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
   what helps explain this experiment. State whether candidates are independent
   or stacked as an evolutionary chain.
4. **Results and explanation.** Use charts for the decisive comparisons and
   diagrams for the mechanism. Keep failures, uncertainty and important coverage
   limits visible. Label causal interpretations as inference unless demonstrated.
5. **Next.** Show the next hypothesis, the cost it addresses and the observation
   that would falsify it, using a short flow or diagram.
6. **Core kernel patches.** Immediately after `Next` (and before the collapsed
   audit evidence), attach the main code hunks of each candidate patch using
   `diff` blocks (`story["patches"]` in `evolve/delivery.py`). Each block states
   a one-line takeaway, cites its pinned `campaigns/<c>/patches/<cand>.patch`
   source, and shows the key kernel implementation diff in both `explainer.html`
   and `REPORT.md`, inside a closed technical-details disclosure. Its summary
   states what the code implements without requiring code literacy.
   End with expandable evidence: measurement protocol, full
   samples, counters, and audit tables.

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

## Multi-experiment chains and core patch code

- **Unify chained experiments into a single report:** When multiple experiments
  or rounds form a sequential, compounding evolutionary chain (e.g.
  `baseline -> M1 -> M2 -> M3` where each stage builds atop or directly
  continues the prior candidate), merge them into **one unified campaign report**
  rather than publishing separate per-stage cards on the site index.
  - Consolidate the chain's candidate records (`candidates/*.json` and
    `candidates/<cand>/`), patches (`patches/*.patch`), `archive/population.json`
    lineage (`parent_candidate`, `parent_commit`, `generation`), evaluation
    ledger rows (`ledger/ledger.json`), and cumulative budget (`ledger/budget.json`)
    into the final chain campaign directory.
  - Remove standalone report outputs (`explainer.html`, `explainer.json`,
    `REPORT.md`, `summary.json`, `story.json`, `delivery.json`,
    `generate_report.py`, `visual-verification.json`) from the intermediate
    stage directories so `scripts/build_site.py` emits only the single unified
    card on the homepage.
  - **Preserve review integrity:** Never delete `report/independent-review.md`,
    `reviews/*.json`, `candidates/**`, or `patches/*.patch` from earlier stage
    directories, because `evolve/reviews.py` verifies their SHA-256 hashes
    across the entire repository.
- **Always attach core patch diffs at the end:** Populate `story["patches"]` in
  `report/story.json` with the core kernel implementation hunks for every
  candidate in the campaign or chain:
  ```json
  "patches_title": "Core kernel patches",
  "patches_lead": "Key kernel hunks across the candidate commit chain.",
  "patches": [
    {
      "takeaway": "Milestone 1 (<short-sha>): ...",
      "source": "campaigns/<campaign>/patches/<candidate>.patch",
      "patch": "--- a/mm/xswap.c\n+++ b/mm/xswap.c\n@@ ... @@\n+..."
    }
  ]
  ```
  `evolve/delivery.py` validates that every `source` is a pinned `.patch` in
  `summary["sources"]` and renders syntax-highlighted `<pre class="diff">` cards
  in `explainer.html` plus fenced ```` ```diff ```` sections in `REPORT.md`.

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
   Apply the Reader contract to the title, badge, diagrams and homepage card,
   not only the prose. Capture fresh, unique per-campaign Visual QA screenshots
   (desktop light/dark, mobile light/dark); never copy screenshot files or hashes from prior campaigns.
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
   - Card Bottom Metadata Bar: Supply `card_metadata` with useful plain-language
     context for new reports. Keep harness/model, internal line, baseline hash
     and exact resource counts in the report's closed provenance details.
     The renderer retains this legacy fallback for older reports:
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
{"title": "...", "subtitle": "<plain-language purpose of this experiment>",
 "card_metadata": "<plain-language scope and environment>",
 "verdict": {"status": "rejected", "label": "<specific outcome>", "headline": "...", "tiles": [{"label": "", "value": "", "note": ""}]},
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
| Unexplained C1/R5-style IDs or acronyms in the overview | Name the stage by its purpose; define necessary terms where first used |
| A bare "inconclusive" badge | Say which conclusion is unresolved, why, and which results are already established |
| Starting with context before the verdict | Lead with the decision, then explain context and motivation |
| Showing exact data or tables by default | Keep visuals visible and exact data in closed details |
| A paragraph explaining a chart | Use a short caption or a cause-chain diagram; move detailed lookup into closed evidence |
| A checklist that lists only passing gates | List every policy gate, including missing ones |
