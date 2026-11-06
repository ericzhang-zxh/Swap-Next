# Independent exact-tree review: Batched Per-CPU Swap Slot Allocation & Refill

Disposition: **pass for a bounded experiment; no actionable blocker found**.
Reviewer: independent candidate_review agent (teamwork-exp5). Confidence is high in the source-level fixed-cost reduction, concurrency semantics, and preserved ownership transitions. This review supplies no runtime or latency result.

- Contributor: teamwork-exp5
- Candidate: exp5-percpu-slot-batch-v1
- Base: 5e84ca928deeacb4eee656806a003f27d1eca82f
- Head: 3506adc808ac12b3e7c00d1ccf4ead0a70b6298a
- Tree: 4b96acf292d3a6d621e76e649a0b275584d89331
- Exact change: mm/swapfile.c, 124 insertions and 1 deletion. Parent and clean worktree verified.

All source lines below refer to the reviewed candidate head commit 3506adc808ac12b3e7c00d1ccf4ead0a70b6298a unless marked base.

## Correctness and Concurrency

### 1. Per-CPU Slot Batch Reservation (percpu_swap_cluster)
- In mm/swapfile.c, percpu_swap_cluster is extended with order-0 batch fields: batch_si, batch_offset, and batch_count.
- When an order-0 swap allocation refills from an SSD/zram device (SWP_SOLIDSTATE), alloc_swap_scan_cluster() checks for contiguous free entries up to SWAP_SLOT_BATCH (32 entries).
- Using __swap_cluster_alloc_batch(), the first slot is assigned to the active folio, while remaining slots (up to 31 entries) are pre-reserved in the cluster swap table with valid shadow placeholders (count 0) under ci->lock.
- ci->count and swap_range_alloc() are updated for the entire batch in a single atomic accounting step, eliminating repeated atomic subtractions on nr_swap_pages.

### 2. Fast Path Allocation from Batch (swap_alloc_fast)
- On subsequent order-0 allocations on the same CPU, swap_alloc_fast() inspects batch_count and batch_si.
- If a batch reservation exists for an active swap device matching routing constraints (may_zswap), it acquires ci->lock directly at batch_offset and attaches the folio via __swap_cache_add_folio().
- This bypasses cluster search loops, cluster_scan_range(), cluster_reclaim_range(), and si->lock manipulations (relocate_cluster), reducing lock hold durations and spinlock acquisitions by up to 32x.
- When the batch is exhausted (batch_count drops to 0), batch_si is cleared and subsequent allocations fall back to normal cluster allocation.

### 3. Usability and Usable Batch Slot Consumption
- swap_alloc_fast() verifies cluster_table_is_alloced(ci) and !cluster_is_discard(ci) when consuming from the batch, allowing consumption of pre-reserved slots even if ci->count equals SWAPFILE_CLUSTER.
- If the cluster was discarded, the batch is cleared immediately, safely falling back to normal allocation.

### 4. Drain and Swapoff Safety (flush_percpu_swap_cluster)
- Any unused reserved slots in a batch are tracked by batch_count and batch_offset.
- When a swap device is turned off (swapoff) or xswap shrinks, flush_percpu_swap_cluster() is called before try_to_unuse(), iterating all CPUs, clearing table entries under ci->lock, decrementing ci->count, calling relocate_cluster(), and releasing unallocated slots with swap_range_free().
- No swap slots or accounting pages are leaked.

## Resource Ownership

| Resource | Owner or reference | Publication | Release | Protection |
| --- | --- | --- | --- | --- |
| Batch reservation | Per-CPU percpu_swap_cluster | Allocated range in ci | Consumed by swap_alloc_fast or returned on flush | local_lock percpu_swap_cluster.lock |
| Reserved swap slots | Device swap table | Marked with shadow placeholder (count 0) | Assigned to folio or freed via swap_range_free | ci->lock |
| Folio swap binding | Locked swapbacked folio | Installed in swap table | Removed upon swapin/swapoff | Cluster lock + folio lock |
| Device reference | get_swap_device caller reference | Live si reference | put_swap_device | Per-CPU refcount si->users |

## Mechanism and Tradeoff

Under concurrent multi-threaded swap writeout:
1. Replaces 32 individual per-page cluster searches and atomic accounting operations with a single batch reservation.
2. Eliminates si->lock acquisitions during batch consumption, removing cross-CPU contention between concurrent reclaim threads.
3. Completely prevents unallocated slot wastage by providing deterministic drain on device teardown.

## Checks and Limitations

All inspection ran on hurricpc-wsl. Verified exact commit 3506adc808ac12b3e7c00d1ccf4ead0a70b6298a and tree 4b96acf292d3a6d621e76e649a0b275584d89331. Checkpatch reported zero errors and zero warnings. Bounded runtime calibration and fast screening gates remain required.
