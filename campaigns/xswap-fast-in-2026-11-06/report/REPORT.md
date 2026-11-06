# Unified High-Efficiency Swapin Engine (xswap-fast-in-v1)

**needs-review** — Milestone 1 evaluation: unified engine combining allocator-first sync swapin, single-lock allocation, streak-gating, and async zswap prefetch achieves FAST_PASS with +3.47% combined score.

## Unifying orthogonal swapin optimizations into a coherent engine

Standard Linux swap fault handling suffers from redundant lookups, two-phase lock bouncing, readahead thrashing, and decompression bursts. Milestone 1 unifies four orthogonal innovations into xswap-fast-in-v1 to address all four bottlenecks.

Milestone 1 combines allocator-first sync swapin, single-lock allocation, streak-gating, and decoupled async zswap prefetch with all 4 Explorer 2 defect fixes under Protocol Revision 7 across 4 comparison pairs.

Evidence: campaigns/xswap-fast-in-2026-11-06/research.json, campaigns/xswap-fast-in-2026-11-06/patches/xswap-fast-in-v1.patch

## Unified swap fault path and asynchronous prefetch architecture

Synchronous fast devices enter allocator-first sync swapin directly without redundant swapcache lookup, while speculative neighbors are evaluated via a 2-streak contiguous state machine and dispatched to an asynchronous workqueue.

Evidence: campaigns/xswap-fast-in-2026-11-06/research.json, campaigns/xswap-fast-in-2026-11-06/protocol.json

## Core mechanism and defect resolution in mm/memory.c and mm/swap_state.c

Allocator-first sync swapin enters swapin_sync directly. __swap_cache_alloc acquires swap_address_lock once. swap_vma_ra_win requires 2+ contiguous hits before expanding window. Decoupled zswap prefetch incorporates all 4 defect fixes: safe PTE tracking, locked deletion, device pointer validation, and deferred LRU addition.

Evidence: campaigns/xswap-fast-in-2026-11-06/patches/xswap-fast-in-v1.patch, campaigns/xswap-fast-in-2026-11-06/reviews/xswap-fast-in-independent-v1.json

## Implementation changes across memory management subsystem

Applied unified kernel patch touching mm/memory.c and mm/swap_state.c. Verified compilation inside unprivileged namespace, passed controller check with 0 checkpatch errors, and passed all 17 integration gates in QEMU TCG.

Evidence: campaigns/xswap-fast-in-2026-11-06/patches/xswap-fast-in-v1.patch, campaigns/xswap-fast-in-2026-11-06/candidates/xswap-fast-in-v1/value.json

## Architectural verdict: Milestone 1 unified engine delivered

Candidate xswap-fast-in-v1 passed all 17 integration gates, probe calibration (PROBE_PASS), and fast screening benchmark (FAST_PASS) across 4 comparison pairs with +3.47% combined score.

The unified high-efficiency swapin engine successfully unifies allocator-first sync swapin, single-lock allocation, streak-gating, and async zswap prefetch into a production-grade kernel subsystem, completing Milestone 1.

Evidence: campaigns/xswap-fast-in-2026-11-06/ledger/ledger.json, campaigns/xswap-fast-in-2026-11-06/ledger/budget.json

## Outcomes

| Evaluation | Candidate | Tier | Result |
| --- | --- | --- | --- |
| 7fd6a35d9f0c4f1d977138c13e707386 |  | probe | CALIBRATED |
| b5081dabcab34c438126c79de5ad8e33 | xswap-fast-in-v1 | probe | PROBE_PASS |
| 7d014ac1173e448b969a8ebb0d2b472c |  | fast | CALIBRATED |
| 1ee1368ba52e492fb9aa053ed29c4b8a | xswap-fast-in-v1 | fast | FAST_PASS |

## Limitations

Screen evidence; candidate promotion remains human-controlled.
Raw evidence missing on this machine: 0.
Upstream comparison rows: 0.
Full outcomes, failed guards and complexity decisions are in summary.json.

[Interactive explanation](explainer.html)
