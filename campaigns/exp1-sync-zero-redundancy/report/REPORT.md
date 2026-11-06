# Zero-Redundancy Synchronous Swap-in Path

**needs-review** — Exploratory screen: allocator-first loop and single-lock allocation pass all 17 correctness gates with 1.44% disk latency gain, within noise.

## Eliminating redundant operations on synchronous cold swap-in

Synchronous swapin repeats a cache lookup after callers miss, and __swap_cache_alloc acquires ci->lock twice for order-0 faults. Candidate exp1-sync-zero-redundancy-v1 removes both redundant operations.

Hypothesis 1 combines allocator-first reordering in swapin_sync() with single-lock order-0 allocation in __swap_cache_alloc(). Evaluated under Protocol Revision 7 with attributable metadata accounting.

Evidence: campaigns/exp1-sync-zero-redundancy/research.json, campaigns/exp1-sync-zero-redundancy/patches/exp1-sync-zero-redundancy-v1.patch

## System architecture of synchronous swap-in

Faulting tasks traverse swap cache lookup, folio allocation, swap cache entry publication, and backing storage read.

Evidence: campaigns/exp1-sync-zero-redundancy/research.json, campaigns/exp1-sync-zero-redundancy/protocol.json

## Swap cache allocation and publication path

Baseline performs unpinned lock and lookup, memory allocation, and authoritative locked validation. Candidate removes preliminary locking for order-0 demand faults.

Evidence: campaigns/exp1-sync-zero-redundancy/patches/exp1-sync-zero-redundancy-v1.patch, campaigns/exp1-sync-zero-redundancy/reviews/exp1-independent-v1.json

## Allocator-first reordering and single-lock order-0 allocation

Reordered swapin_sync calls __swap_cache_alloc_folio first, handling -EEXIST via cache lookup fallback. Preliminary cluster lock check omitted for order-0 demand faults.

Evidence: campaigns/exp1-sync-zero-redundancy/patches/exp1-sync-zero-redundancy-v1.patch, campaigns/exp1-sync-zero-redundancy/candidates/exp1-sync-zero-redundancy-v1/value.json

## Next steps: profile-bound architectural decision

Fast screening benchmark demonstrated full correctness across all 17 gates and a modest 1.44% sequential disk swapin latency gain. Because gain is below the 5% min_useful_effect policy threshold and within noise, candidate is retained as an exploratory screen.

The candidate proves that single-lock allocation and allocator-first loops are functionally correct and lockdep-safe. Exploration may focus on batched or asynchronous prefetch mechanisms.

Evidence: campaigns/exp1-sync-zero-redundancy/ledger/ledger.json, campaigns/exp1-sync-zero-redundancy/ledger/budget.json

## Outcomes

| Evaluation | Candidate | Tier | Result |
| --- | --- | --- | --- |
| 95feb9df0d48499485e365c4b5a521d1 |  | probe | CALIBRATED |
| 14a8d2d9099a47e2b506c581eaa12502 | exp1-sync-zero-redundancy-v1 | probe | PROBE_PASS |
| eba499eeed3542e992d9d8f276d407de |  | fast | CALIBRATED |
| 5f58033b1bba401ca43655fc5fd516ec | exp1-sync-zero-redundancy-v1 | fast | FAST_PASS |

## Limitations

Screen evidence; candidate promotion remains human-controlled.
Raw evidence missing on this machine: 0.
Upstream comparison rows: 0.
Full outcomes, failed guards and complexity decisions are in summary.json.

[Interactive explanation](explainer.html)
