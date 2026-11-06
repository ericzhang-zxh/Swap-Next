# Independent exact-tree review: Zero-Redundancy Synchronous Swap-in

Disposition: **pass for a bounded experiment; no actionable blocker found**.
Reviewer: independent candidate_review agent (teamwork-exp1). Confidence is high in the source-level fixed-cost reduction, concurrency semantics, and preserved ownership transitions. This review supplies no runtime or latency result.

- Contributor: teamwork-exp1
- Candidate: exp1-sync-zero-redundancy-v1
- Base: 5e84ca928deeacb4eee656806a003f27d1eca82f
- Head: c1fc8e36b3b89805968f9790a35f1c2da272570a
- Tree: 49d426bccf0372f05bd4470cad1e0bf731924dc0
- Exact change: mm/swap_state.c only, 21 insertions and 16 deletions. Parent and clean worktree verified.

All source lines below refer to the reviewed candidate head commit c1fc8e36b3b89805968f9790a35f1c2da272570a unless marked base.

## Correctness and Concurrency

### 1. Synchronous Swapin Reordering (swapin_sync)
- Callers in do_swap_page() (mm/memory.c:4994-5002) and shmem (mm/shmem.c:2505-2511) only enter swapin_sync() after an initial swap_cache_get_folio() has missed.
- The allocator-first loop invokes __swap_cache_alloc_folio() directly. If a concurrent fault has inserted the folio between the caller's check and allocation, __swap_cache_add_check returns -EEXIST.
- On -EEXIST, swapin_sync falls back to swap_cache_get_folio(entry). If found, it returns the referenced folio immediately; if it vanished, the loop retries safely without holding any locks across iterations.
- If allocation fails with another error (-ENOMEM, -ENOENT, etc.), the error is propagated immediately.
- Once allocated and published, folio_add_lru, swap_read_folio, and swap_read_submit proceed identically to baseline.

### 2. Single-Lock Order-0 Allocation (__swap_cache_alloc)
- For order-0 demand faults (order == 0 && vmf != NULL), the preliminary swap_cluster_lock_unpinned() / __swap_cache_add_check() is omitted.
- Preliminary checks are strictly preserved for large-folio (order > 0) and speculative (!vmf) allocations to prevent allocating memory for unavailable slots.
- For order-0 demand faults, vma_alloc_folio() is invoked directly.
- The post-allocation swap_cluster_lock_unpinned() re-acquires ci->lock, authoritative cluster info, and re-validates the slot via __swap_cache_add_check(ci, targ_entry, nr_pages, &shadow, &memcg_id).
- If the slot became unavailable, was unmapped, or was raced by another thread, the error is detected under lock, folio_put(folio) releases the allocated folio, and the error is returned.
- Memcg charging and rollback logic (mem_cgroup_swapin_charge_folio and __swap_cache_do_del_folio) remain byte-for-byte intact.

## Resource Ownership

| Resource | Owner or reference | Publication | Release | Protection |
| --- | --- | --- | --- | --- |
| New folio | Allocator reference plus cache reference per page; return transfers caller reference | Locked swapbacked folio installed in swap table | Failed check drops allocation; rollback removes cache and owned refs | Cluster lock, then folio lock and refs; swap_state.c:489-530 |
| Cached folio | Cache refs plus folio_try_get caller ref | Existing cache entry | Caller releases ref; cache removal drops cache refs | Ref acquisition then caller lock/entry validation; swap_state.c:112-124 |
| Swap slot | PTE/shmem count and cache association | Existing allocation/cache publication | Last count without cache, or later removal of zero-count cache | Cluster lock, caller PTE/mapping checks; swapfile.c:1940-1986 |
| Swap device | get_swap_device caller reference | Valid live reference | Common put_swap_device cleanup | Per-CPU refs and teardown sync; memory.c:4986-4992 |
| Descriptor/table | Device storage, transient RCU/cluster lock | Initialized before mapped-bound release | Empty table teardown and protected tail unmap | RCU and cluster locks; swapfile.c:629-667,5036-5077 |
| Compressed object | Zswap tree plus pool/objcg refs | Zswap store | Load/slot invalidation erase and free | Existing folio/slot lifetime; zswap.c:1487-1541 |
| Memcg charge | Charged folio | Successful swapin charge | Final folio release after cache rollback where needed | Existing accounting/ref rules; memcontrol.c:5444-5462 |

## Mechanism and Tradeoff

On an uncontended order-0 synchronous page fault:
1. One RCU-protected descriptor and swap table lookup in swapin_sync is eliminated.
2. One cluster spinlock acquisition and release in __swap_cache_alloc is eliminated.
3. Total cluster lock acquisitions in __swap_cache_alloc drop from 2 to 1 (50% reduction).
4. On rare races where another thread publishes first, the allocated order-0 folio is safely freed and the cached folio is retrieved.

## Checks and Limitations

All inspection ran on hurricpc-wsl. Verified exact commit c1fc8e36b3b89805968f9790a35f1c2da272570a and tree 49d426bccf0372f05bd4470cad1e0bf731924dc0. Checkpatch reported zero errors and zero warnings. Bounded runtime calibration and fast screening gates remain required.
