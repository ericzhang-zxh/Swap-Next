# Independent Exact-Tree Review: xswap-radix-hole-reclaim-v1

- Campaign: xswap-radix-hole-reclaim-2026-11-06
- Candidate Commit: 2c1ddb537fd926482ab4845bd7d5be116b4523ac
- Baseline Commit: 5e84ca928deeacb4eee656806a003f27d1eca82f
- Disposition: PASS (0 blockers)

## Findings Summary
1. 2-Level RCU Radix Directory: In mm/swapfile.c and mm/swap.h, the flat contiguous VM_SPARSE descriptor array is replaced with a 2-level pointer array si->cluster_dir indexed by chunk_idx = offset / (SWAPFILE_CLUSTER * 64). Each leaf chunk holds 64 struct swap_cluster_info descriptors. Lockless lookup via swap_cluster_lookup_rcu() uses rcu_dereference() protected under rcu_read_lock(), avoiding global lock acquisition and guaranteeing O(1) concurrent reader throughput.
2. Zero-Overhead 56-Byte Descriptors and Page-Aligned Radix Chunk Lookup: In mm/swap.h, struct swap_cluster_info is strictly preserved at 56 bytes by eliminating descriptor-level backpointers. Leaf chunks struct swap_cluster_chunk (3648 bytes) are allocated via kmem_cache_create with 4096-byte PAGE_SIZE alignment. For any constituent cluster descriptor ci, (struct swap_cluster_chunk *)((unsigned long)ci & PAGE_MASK) deterministically derives the enclosing chunk via a single bitwise AND with zero memory dereferences and zero plain-mode memory overhead.
3. Lockless Atomic Draining: In mm/swapfile.c:__free_cluster(), atomic_dec_and_test(&chunk->live_clusters) safely tracks chunk occupancy without acquiring si->xswap_lock. When a chunk live cluster count drops to zero, test_and_set_bit() atomically flags the chunk in si->empty_chunks_bm and schedules the deferred asynchronous reclaim worker xswap_shrink_work.
4. Safe Lock Ordering and Permanent Chunk Guard: In xswap_reclaim_interior_holes(), Chunk 0 is guarded by XSWAP_CHUNK_PERMANENT to preserve the swap header and bad page table permanently. Reclaim acquires si->xswap_lock and spin_lock(&si->lock), then attempts spin_trylock() on each constituent cluster lock. If contention or concurrent reallocation is detected, reclaim aborts gracefully with zero lock inversion.
5. Asynchronous kfree_rcu() Reclamation: Unlinked chunks are detached with rcu_assign_pointer(si->cluster_dir[chunk_idx], NULL) and deferred to kfree_rcu(chunk, rcu). This completely eliminates synchronous synchronize_rcu() latency penalties and latency spikes, allowing interior hole reclamation to execute concurrently with heavy swap I/O.
