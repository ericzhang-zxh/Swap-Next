# Demand swap-in: a smaller path, an unresolved benefit

**inconclusive** — Stop this pilot: baseline metadata noise blocked candidate timing.

## A small fixed cost was worth testing

Earlier prefetch experiments exposed random-latency regressions. This independent idea targets duplicate validation on demand allocation, while keeping the upstream algorithm as the baseline.

The candidate skips a preliminary lock-and-slot check for demand base-page allocation. Review confirms reduced source-level work; both kernels passed the required correctness route. The useful-effect threshold was frozen before measurement. No candidate latency comparison was reached.

Evidence: campaigns/codex-r01-demand-2026-11-03/research.json, campaigns/codex-r01-demand-2026-11-03/protocol.json

## The missing page must return to RAM

The application waits while a new resident page is allocated and filled from swap backing. The changed allocator sits before the data read.

Evidence: campaigns/codex-r01-demand-2026-11-03/patches/codex-r01-precheck-v1.patch, campaigns/codex-r01-demand-2026-11-03/reviews/codex-r01-independent-v1.json

## Ownership stays with the existing objects

The device owns the cluster table. Its cache slot publishes the allocated folio under the cluster lock. The retained lookup and validation remain the lifetime boundary.

Evidence: campaigns/codex-r01-demand-2026-11-03/patches/codex-r01-precheck-v1.patch, campaigns/codex-r01-demand-2026-11-03/reviews/codex-r01-independent-v1.json

## One early check is skipped; the final check remains

Only order-0 allocations with a fault context take the new branch. Large folios and speculative callers keep the preliminary check.

Evidence: campaigns/codex-r01-demand-2026-11-03/patches/codex-r01-precheck-v1.patch, campaigns/codex-r01-demand-2026-11-03/reviews/codex-r01-independent-v1.json, campaigns/codex-r01-demand-2026-11-03/candidates/codex-r01-precheck-v1.json

## Keep the baseline; diagnose measurement first

The failed baseline gate ends this pilot. No measured benefit justifies the added branch and allocation-failure validation burden. The candidate remains unmerged.

Limits: whole-guest memory variation has an unknown cause. Runtime correctness covers anonymous base-page xswap on disk. Shmem, THP, memcg limits and forced failures remain untested. No fast result, separate upstream arm, slow confirmation or promotion exists.

Evidence: campaigns/codex-r01-demand-2026-11-03/ledger/ledger.json, campaigns/codex-r01-demand-2026-11-03/ledger/session-closeout.json, campaigns/codex-r01-demand-2026-11-03/research.json

## Outcomes

| Evaluation | Candidate | Tier | Result |
| --- | --- | --- | --- |
| 99f37fe54bb4410ab3d3337138bd522d |  | probe | CALIBRATION_NOISY |

## Limitations

Screen evidence; candidate promotion remains human-controlled.
Raw evidence missing on this machine: 0.
Upstream comparison rows: 0.
Full outcomes, failed guards and complexity decisions are in summary.json.

[Interactive explanation](explainer.html)
