# Batched Per-CPU Swap Slot Allocation & Refill

**needs-review** — Screening benchmark: reserving swap slots in per-CPU batches reduces cluster spinlock contention, delivering -1.4% sequential mean on disk and -2.5% on zram, with overall -2.8% geomean within calibrated noise floor (+/-6.2%).

## Eliminating per-slot spinlock contention in swap allocation

In mm/swapfile.c, cluster_alloc_swap_entry and swap_alloc_fast acquire spinlocks (ci->lock and si->lock) for every single page allocation, causing high contention under concurrent writeouts.

Hypothesis 5 amortizes spinlock acquisition and atomic cluster accounting across a per-CPU reservation batch (up to 32 entries) in percpu_swap_cluster, releasing any unallocated slots cleanly on swapoff.

Evidence: campaigns/exp5-percpu-slot-batch-2026-11-06/research.json, campaigns/exp5-percpu-slot-batch-2026-11-06/patches/exp5-percpu-slot-batch-v1.patch

## Where the cluster locking cost appears

Under standard allocation, every order-0 folio must acquire ci->lock, update cluster usage counters, and check cluster flags. Batched refill amortizes these costs across 32 slots.

Evidence: campaigns/exp5-percpu-slot-batch-2026-11-06/research.json, campaigns/exp5-percpu-slot-batch-2026-11-06/protocol.json

## The affected path: percpu_swap_cluster and cluster allocation

In mm/swapfile.c, percpu_swap_cluster tracks the per-CPU reserved batch. When empty, __swap_cluster_alloc_batch acquires ci->lock once and claims up to 32 slots, resetting unallocated slots on flush.

Evidence: campaigns/exp5-percpu-slot-batch-2026-11-06/patches/exp5-percpu-slot-batch-v1.patch, campaigns/exp5-percpu-slot-batch-2026-11-06/reviews/exp5-independent-v1.json

## Kernel modifications in mm/swapfile.c

Added batch_start and batch_nr tracking to percpu_swap_cluster, implemented __swap_cluster_alloc_batch with count-0 placeholders, and extended flush_percpu_swap_cluster to release unused slots.

Evidence: campaigns/exp5-percpu-slot-batch-2026-11-06/patches/exp5-percpu-slot-batch-v1.patch, campaigns/exp5-percpu-slot-batch-2026-11-06/candidates/exp5-percpu-slot-batch-v1/value.json

## Architectural decision: exploratory screening completed

Candidate passed all 17 correctness gates, probe calibration, and fast screening. Latency decreased -1.4% sequential mean on disk and -2.5% on zram, but net gain (-2.8%) remained within noise floor (+/-6.2%).

Batched swap slot reservation proves functionally sound and passes rigorous correctness gates including full swapoff unuse. However, spinlock overhead in swap allocation is not the primary bottleneck under current test scale, so candidate is cleanly retired on value policy.

Evidence: campaigns/exp5-percpu-slot-batch-2026-11-06/ledger/ledger.json, campaigns/exp5-percpu-slot-batch-2026-11-06/ledger/budget.json

## Outcomes

| Evaluation | Candidate | Tier | Result |
| --- | --- | --- | --- |
| 53d2ec001df740d6a69c8acb56be5300 |  | probe | INTERRUPTED |
| ec136964679248bc965322d74feff523 |  | probe | CALIBRATED |
| cc219436ae3c47ef8a839c94eb1b5129 | exp5-percpu-slot-batch-v1 | probe | PROBE_PASS |
| 56f58217338d4b0dbaa356b6422b0ec5 |  | fast | CALIBRATED |
| 7b7755e6dd1d45ee89dbe0e8c4d4bef9 | exp5-percpu-slot-batch-v1 | fast | FAST_PASS |

## Limitations

Screen evidence; candidate promotion remains human-controlled.
Raw evidence missing on this machine: 0.
Upstream comparison rows: 0.
Full outcomes, failed guards and complexity decisions are in summary.json.

[Interactive explanation](explainer.html)
