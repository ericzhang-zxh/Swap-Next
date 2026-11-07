# Two-Level RCU Radix Chunks & Interior Hole Reclamation (xswap-radix-hole-reclaim-v1)

**needs-review** — Milestone 3 evaluation: 2-level RCU radix chunks with 56-byte zero-overhead descriptors and asynchronous hole reclamation pass all 17 integration gates and achieve zero metadata regression.

## Replacing monolithic flat swap cluster allocation

Upstream mm/swapfile.c statically allocates a flat cluster array at swapon time. Large swapfiles pin megabytes of kernel memory even when mostly empty, and interior holes cannot be reclaimed.

Milestone 3 replaces monolithic cluster arrays with a dynamically expanded 2-level RCU radix directory, allocating chunks of 64 clusters on demand and reclaiming interior holes via asynchronous kfree_rcu().

Evidence: campaigns/xswap-radix-hole-reclaim-2026-11-06/research.json, campaigns/xswap-radix-hole-reclaim-2026-11-06/patches/xswap-radix-hole-reclaim-v1.patch

## Two-level RCU radix chunk directory and 56-byte layout

si->cluster_dir maps chunk IDs to 64-cluster leaves. Chunk 0 is permanent to protect swap headers. 4096-byte alignment enables O(1) lockless derivation via PAGE_MASK without adding pointer overhead to struct swap_cluster_info.

Evidence: campaigns/xswap-radix-hole-reclaim-2026-11-06/research.json, campaigns/xswap-radix-hole-reclaim-2026-11-06/protocol.json

## Lock-free interior hole isolation and asynchronous RCU reclamation

When all 64 clusters in a chunk become free, the chunk is unlinked under si->lock via rcu_assign_pointer() and reclaimed asynchronously via kfree_rcu(), preventing swap path stalls and lock inversion.

Evidence: campaigns/xswap-radix-hole-reclaim-2026-11-06/patches/xswap-radix-hole-reclaim-v1.patch, campaigns/xswap-radix-hole-reclaim-2026-11-06/reviews/xswap-radix-hole-reclaim-independent-v1.json

## Verified kernel implementation and exact correctness verification

Modified 7 kernel paths with 942 lines changed. Passed controller check with 0 checkpatch errors, 17/17 QEMU TCG integration gates, and zero plain-mode metadata regression (0.1109 bytes/slot).

Evidence: campaigns/xswap-radix-hole-reclaim-2026-11-06/patches/xswap-radix-hole-reclaim-v1.patch, campaigns/xswap-radix-hole-reclaim-2026-11-06/candidates/xswap-radix-hole-reclaim-v1/value.json

## Architectural verdict: Milestone 3 2-level RCU radix chunks & hole reclamation verified

Candidate xswap-radix-hole-reclaim-v1 proves that dynamic 2-level RCU radix directories eliminate monolithic metadata preallocation without incurring memory regression or swapin latency overhead, concluding the campaign.

Milestone 3 delivers verified 2-level RCU radix chunk directory and interior hole reclamation with 56-byte descriptors, 17/17 correctness gates passing, verified dynamic growth and shrink signals, and zero metadata regression, completing the xswap milestone series.

Evidence: campaigns/xswap-radix-hole-reclaim-2026-11-06/ledger/ledger.json, campaigns/xswap-radix-hole-reclaim-2026-11-06/ledger/budget.json

## Outcomes

| Evaluation | Candidate | Tier | Result |
| --- | --- | --- | --- |
| 8eda31b19eff4af5a704c5c73578a1b2 |  | probe | CALIBRATED |
| e0f075ffbf2a4614a3a2be191781f5d6 | xswap-radix-hole-reclaim-v1 | probe | PROBE_PASS |
| 2e0d35e724f449d79888a19659a9ffaa |  | fast | CALIBRATED |
| 0f361c6c5428419d9d04479921fab02a | xswap-radix-hole-reclaim-v1 | fast | FAST_PASS |

## Limitations

Screen evidence; candidate promotion remains human-controlled.
Raw evidence missing on this machine: 0.
Upstream comparison rows: 0.
Full outcomes, failed guards and complexity decisions are in summary.json.

[Interactive explanation](explainer.html)
