# Research-loop implementation and verification

Status: implemented and fixture-verified on 2026-11-03.
Scope: owner-approved stages 1-4 of the [audit and redesign](../specs/2026-11-02-research-loop-audit-and-redesign.md), including the requested independent contributor blind test and shared reference reuse. The real pilot in stage 5 remains separately authorized.

## Result

A contributor invokes `closed-loop-evolve` and drives `evolve/loop.py start` or
`resume` through durable actions. The active agent supplies research judgment,
code changes, review and explanation. Trusted commands reconcile artifacts,
execute allowed measurements, record decisions and verify delivery. The driver
does not invoke a model or run an unattended research service by itself.

| Change | Result and evidence |
| --- | --- |
| Exact-tree review dispositions | A veto blocks execution, baseline use, population selection, stale briefs, descendants and reusable references. Only an applicable explicit resolution clears a finding. See `evolve/reviews.py` and `evolve/control/tests/test_review_dispositions.py`. |
| Durable contributor entry | Start, Resume, Next, Execute, Decide and Value use stable evidence-bound actions, persisted launch receipts and counted-attempt reconciliation. Failed delivery actions can retry without replaying measurements. See `evolve/session-schema.md` and `evolve/test_session.py`. |
| Research agendas and profiles | Lines retain questions, ideas, original anchors, alternatives, practical-value thresholds and cumulative cost. Capabilities and edit scope are frozen before execution; an unsupported profile stops before measurement. See `evolve/research-schema.md` and `evolve/profiles/`. |
| Practical value | Exact-evidence decisions distinguish worthwhile confirmation, simplification, exploratory learning and rejection. Rejected or invalid decisions remove parent eligibility; exploratory learning cannot advance a baseline. Numerical advancement gates still apply. See `evolve/test_population_value.py`. |
| Mechanism coverage | Approved structural evidence binds the claim, falsifier, exact tree and review, permitting count-neutral changes while retaining correctness and metadata guards. See `evolve/test_mechanisms.py` and `benchmark/swap-standard/test_probe.py`. |
| Upstream alternatives | Pinned common-base B/P/C and optional composition contrasts use the existing runner, reservations, validity and statistics. Incompatible arms retain an explicit coverage gap. See `evolve/comparison-schema.md` and `evolve/test_comparison_runtime.py`. |
| Report delivery | Evidence extraction, authored explanation, rendering, visual inspection, publication and independent live verification have separate durable states. STOP and experiment closure still allow delivery. See `evolve/delivery.py` and `evolve/test_delivery.py`. |

The repository and installed `closed-loop-evolve` entry instructions now point
to the same driver. Existing scientific campaign inputs and Linux/OpenEvolve
submodule pins are unchanged.

## Reuse contract

The shared, ignored `benchmark/reference-cache/` indexes original evidence.
Its supported kinds are upstream source, build, review, correctness,
calibration and performance. Lookup verifies retained bytes, exact scientific
identity, native proof, coverage and current review disposition.

Automatic runtime integration covers native probe/fast A/A and complete
upstream B/P contrasts. The session planner consults those same runtime rules,
so a reusable result costs zero new guest attempts. Upstream source, build,
review and correctness references have verified registration/lookup APIs;
contributors reconcile their required coverage through the documented cache
contract. This release does not add a universal automatic scheduler for every
artifact kind.

- Identity includes source, configuration, guest image, measurement protocol,
  evaluator/harness and environment. Cosmetic campaign/output names and total
  budget ceilings do not force repetition.
- Reuse preserves original timestamps and expiry, counted reservations and
  raw samples. A new reference is not an independent observation.
- An intact upstream B/P contrast can be reused within its original reference
  window. A new candidate still requires its own B/C evidence. Old control
  samples are never paired with new treatment samples.
- Changed inputs, missing raw evidence, expired windows, incomplete coverage or
  a current review veto require new evidence or historical-only reporting.
- Retired upstream worktrees need not be recreated: exact retained Git objects
  and exports remain subject to the controller's read-only scope check.

See [reference-cache-schema](../../../evolve/reference-cache-schema.md).

## Independent contributor blind test

A fresh-context subagent received the contributor entry documents and an
isolated remote snapshot, without expected steps or a list of known defects.
It used synthetic runtime adapters and exercised the public session interface.

Two defects were reproduced, repaired and rechecked:

1. The planner originally charged full guest cost for reusable A/A. In the
   repaired reproduction it schedules 8 guests with 10 remaining and recognizes
   reusable calibration, agreeing with the runtime plan.
2. Failed live verification originally stranded delivery. Resume now creates a
   new durable delivery action, retaining the failed receipt and unchanged
   measurement/budget bytes. A separate render-failure reproduction also passes.

Generated comparison commands were additionally checked through the actual
wrapper and argparse dispatcher: internal comparison actions translate to
`evaluate` / `calibrate`. The check stopped before real campaign execution.
Review vetoes, stale actions, ambiguous-attempt accounting, original cache
expiry and intact upstream reuse also passed. The blind tester reported no
remaining regression within this scope.

## Verification

All checks ran on the Linux worker. The final command for each suite was
`evolve/.venv/bin/python -m unittest discover -s <suite-path> -p 'test_*.py' -q`.

| Suite path | Tests run | Result |
| --- | ---: | --- |
| `evolve` | 201 | Pass |
| `evolve/control/tests` | 158 | Pass |
| `benchmark/tests` | 12 | Pass |
| `benchmark/swap-standard` | 90 | Pass |
| `benchmark/xswap` | 18 | Pass; real provenance fixture class skipped |
| `benchmark/xswap-structure` | 29 | Pass; real provenance fixture class skipped |
| `benchmark/xswap-hole-probe` | 20 | Pass |
| `benchmark/kernel` | 0 | Real provenance fixture class skipped |
| Total | 528 | No failures; three fixture-dependent classes skipped |

The skipped classes require `SWAP_NEXT_EVIDENCE_FIXTURE`,
`XSWAP_EVIDENCE_FIXTURE` and `XSWAP_STRUCTURE_EVIDENCE_FIXTURE`, respectively.
No new real guest evidence was created to satisfy them. The installed skill
passed the skill-creator validator. `git diff --check`, local Markdown link
validation and the Pages index build also passed.

## Limitations and next acceptance step

This is framework and synthetic integration evidence. No real kernel build,
boot, calibration, performance experiment, upstream comparison or new campaign
publication was performed. The end-to-end renderer ran; screenshots and network
responses in the session fixtures were synthetic, so there is no claimed
visual or live-publication acceptance for a new report.

The next acceptance step is the separately authorized bounded pilot: one
substantive idea, a pinned relevant upstream alternative, current machine
preflight, real probe/fast evidence and the full explanatory report delivery.
No slow tier or candidate promotion follows automatically.
