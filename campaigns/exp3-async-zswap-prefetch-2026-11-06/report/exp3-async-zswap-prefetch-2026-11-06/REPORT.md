# Asynchronous Decoupled Zswap Speculative Prefetch

**needs-review** — Screening benchmark: asynchronous background zswap prefetch unblocks the faulting thread with -5.0% random p99 latency reduction and +1.48% geomean gain.

## Eliminating synchronous decompression latency bursts in speculative swapin

Standard swap readahead speculatively decompresses multiple neighboring slots synchronously during page faults, stalling the faulting thread. Candidate exp3-async-zswap-prefetch-v1 decouples speculative zswap readahead into a background workqueue, unblocking the faulting thread immediately.

Hypothesis 3 synchronously loads only the demanded order-0 folio via swap_cache_read_folio_sync, while speculative neighboring swap slots are batched and dispatched to a dedicated background workqueue (zswap_prefetch_wq). Evaluated under Protocol Revision 7 with attributable metadata accounting.

Evidence: campaigns/exp3-async-zswap-prefetch-2026-11-06/research.json, campaigns/exp3-async-zswap-prefetch-2026-11-06/patches/exp3-async-zswap-prefetch-v1.patch

## Zswap readahead path and background prefetch queue

Page fault handlers trigger swap readahead. Decoupled prefetch separates the synchronous critical demand path from speculative background decompression.

Evidence: campaigns/exp3-async-zswap-prefetch-2026-11-06/research.json, campaigns/exp3-async-zswap-prefetch-2026-11-06/protocol.json

## Decoupled dispatch in swap_vma_readahead and swap_cluster_readahead

Demanded slot synchronously loaded via swap_cache_read_folio_sync; speculative slots batched into struct zswap_prefetch_batch and queued to zswap_prefetch_wq.

Evidence: campaigns/exp3-async-zswap-prefetch-2026-11-06/patches/exp3-async-zswap-prefetch-v1.patch, campaigns/exp3-async-zswap-prefetch-2026-11-06/reviews/exp3-independent-v1.json

## Modifications in mm/swap_state.c

Added zswap_prefetch_batch, zswap_prefetch_work_fn, zswap_prefetch_wq; modified swap_vma_readahead and swap_cluster_readahead to synchronously return the demanded folio and asynchronously prefetch speculative slots.

Evidence: campaigns/exp3-async-zswap-prefetch-2026-11-06/patches/exp3-async-zswap-prefetch-v1.patch, campaigns/exp3-async-zswap-prefetch-2026-11-06/candidates/exp3-async-zswap-prefetch-v1/value.json

## Architectural decision: exploratory screening completed

Candidate passed all 17 correctness gates, probe calibration, and fast screening benchmark (+1.48% gain, -5.0% random p99 latency). Benign complexity vs benefit ratio designated research disposition as rejected while preserving candidate as frontier-eligible.

Asynchronous prefetch proves the decoupled loading concept, reducing random swapin tail latency. Future work could pair this mechanism with adaptive stride gating to avoid queueing unused speculative slots.

Evidence: campaigns/exp3-async-zswap-prefetch-2026-11-06/ledger/ledger.json, campaigns/exp3-async-zswap-prefetch-2026-11-06/ledger/budget.json

## Outcomes

| Evaluation | Candidate | Tier | Result |
| --- | --- | --- | --- |
| ed772865e8a54c329732012874b42bce |  | probe | CALIBRATED |
| ffcfccb9ebfa4de087cb7c081e765985 | exp3-async-zswap-prefetch-v1 | probe | PROBE_PASS |
| 66164a8732e447bdb80d8475465b7397 |  | fast | CALIBRATED |
| ca3305446765481fa10086865d11dcf8 | exp3-async-zswap-prefetch-v1 | fast | FAST_PASS |

## Limitations

Screen evidence; candidate promotion remains human-controlled.
Raw evidence missing on this machine: 0.
Upstream comparison rows: 0.
Full outcomes, failed guards and complexity decisions are in summary.json.

[Interactive explanation](explainer.html)
