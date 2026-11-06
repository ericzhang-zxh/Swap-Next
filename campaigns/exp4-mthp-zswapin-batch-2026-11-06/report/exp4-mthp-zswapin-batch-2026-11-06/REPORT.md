# Batched High-Order mTHP Swap-in for Zswap

**needs-review** — Screening benchmark: assembling contiguous compressed zswap slots into high-order folios yields -4.7% sequential and -5.8% p99 latency reduction on zswap, but geomean effect (-2.3%) remains within the calibrated noise floor.

## Eliminating repeated order-0 page faults in zswap mTHP swapin

Linux disables mTHP swap-in when zswap is enabled, forcing 16 or 64 independent order-0 faults with repeated page table allocations and PTL acquisitions.

Hypothesis 4 enables high-order folios (orders 2 and 4) when contiguous slots reside in zswap, assembling compressed slots into one folio under a single set_ptes hold.

Evidence: campaigns/exp4-mthp-zswapin-batch-2026-11-06/research.json, campaigns/exp4-mthp-zswapin-batch-2026-11-06/patches/exp4-mthp-zswapin-batch-v1.patch

## Where the fault overhead appears

Under standard order-0 swapin, each subpage triggers a distinct fault, PTE lookup, and spinlock acquisition. Batched swap-in amortizes these costs under a single lock hold.

Evidence: campaigns/exp4-mthp-zswapin-batch-2026-11-06/research.json, campaigns/exp4-mthp-zswapin-batch-2026-11-06/protocol.json

## The affected path: thp_swapin_suitable_orders and zswap_load

In mm/memory.c, thp_swapin_suitable_orders permits orders <= 4 when zswap_all_present() is true; in mm/zswap.c, zswap_load decompresses each slot directly into folio subpages.

Evidence: campaigns/exp4-mthp-zswapin-batch-2026-11-06/patches/exp4-mthp-zswapin-batch-v1.patch, campaigns/exp4-mthp-zswapin-batch-2026-11-06/reviews/exp4-independent-v1.json

## Kernel modifications in mm/memory.c and mm/zswap.c

Updated zswap_decompress to accept subpage offset via folio_page, implemented zswap_all_present with tree read locking, and mapped high-order folios via swapin_sync.

Evidence: campaigns/exp4-mthp-zswapin-batch-2026-11-06/patches/exp4-mthp-zswapin-batch-v1.patch, campaigns/exp4-mthp-zswapin-batch-2026-11-06/candidates/exp4-mthp-zswapin-batch-v1/value.json

## Architectural decision: exploratory screening completed

Candidate passed all 17 correctness gates, probe calibration, and fast screening. Latency dropped -4.7% sequential on zram-64k, but geomean (-2.3%) stayed within noise.

Batched high-order swapin confirms viability for zswap folios, but without asynchronous prefetch (Exp 3), decompression latency stays on the critical fault path.

Evidence: campaigns/exp4-mthp-zswapin-batch-2026-11-06/ledger/ledger.json, campaigns/exp4-mthp-zswapin-batch-2026-11-06/ledger/budget.json

## Outcomes

| Evaluation | Candidate | Tier | Result |
| --- | --- | --- | --- |
| d8e5c310f51541038a77849ae5319295 |  | probe | CALIBRATED |
| c4ef584656a547ba8d68afe1871308fd | exp4-mthp-zswapin-batch-v1 | probe | PROBE_PASS |
| cda6e4e074d64676a019ac14dc4597dd |  | fast | CALIBRATED |
| 3106cb5ec7ec4853a9601f3ac5f37169 | exp4-mthp-zswapin-batch-v1 | fast | FAST_PASS |

## Limitations

Screen evidence; candidate promotion remains human-controlled.
Raw evidence missing on this machine: 0.
Upstream comparison rows: 0.
Full outcomes, failed guards and complexity decisions are in summary.json.

[Interactive explanation](explainer.html)
