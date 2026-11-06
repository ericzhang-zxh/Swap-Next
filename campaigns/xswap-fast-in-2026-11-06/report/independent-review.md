# Independent Exact-Tree Review: xswap-fast-in-v1

- Campaign: xswap-fast-in-2026-11-06
- Candidate Commit: 5cde9eaa28a2cd79f640e8932c4572573ab2323a
- Baseline Commit: 5e84ca928deeacb4eee656806a003f27d1eca82f
- Disposition: PASS (0 blockers)

## Findings Summary
1. Allocator-first synchronous swapin: In mm/memory.c:do_swap_page, synchronous devices cleanly bypass preliminary cache lookups and enter swapin_sync directly. swapin_sync reorders allocation before lookup, eliminating redundant table lookups.
2. Single-lock order-0 allocation: In mm/swap_state.c:__swap_cache_alloc, preliminary cluster locking is omitted for order-0 demand faults, halving lock acquisitions. Authoritative cluster lock post-allocation validates the slot safely.
3. Adaptive stride streak-gating: Gating window expansion on 2+ contiguous hits and immediate window collapse to 1 on non-contiguous access prevents speculative readahead thrashing on random workloads.
4. Decoupled async zswap prefetch: Offloads speculative decompression batches to background workqueue zswap_prefetch_wq. The demanded order-0 folio is decompressed synchronously, unblocking user threads immediately. All 4 prior defects (IS_ERR_OR_NULL device validation, locked deletion on error, safe PTE tracking without drift, and deferred LRU addition) are completely resolved.
