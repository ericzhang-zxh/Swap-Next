# Independent exact-tree review: allocation-first swap-in

Disposition: **pass for a bounded experiment; no actionable blocker found**.
Reviewer: independent candidate_review agent. Confidence is high in the source-level reduction and preserved ownership transitions. This review supplies no runtime or latency result.

- Contributor: codex-r02-20261103
- Candidate: codex-r02-alloc-first-v1
- Base: 5e84ca928deeacb4eee656806a003f27d1eca82f
- Head: 3fe7af01da59a8ade95823a13c25a8c796c6321f
- Tree: 0c83218561a357c129c5d93ac45a0530e0ad1df6
- Exact change: mm/swap_state.c only, seven insertions and three deletions. Parent and clean worktree verified.

All source lines below refer to the reviewed head unless marked base.

## Correctness and concurrency

Both callers already missed the cache. Anonymous faults perform their first lookup in mm/memory.c:4994-5002; shmem does so in mm/shmem.c:2505-2511 before shmem_swap_alloc_folio at 2266. Both hold a swap-device reference.

Cached-folio progress remains intact. __swap_cache_add_check tests for a folio and returns -EEXIST before testing swap count (mm/swap_state.c:194-204). A cached zero-count folio therefore still reaches the referenced-cache fallback; its slot remains allocated until cache removal (mm/swapfile.c:1955-1977). The fallback uses the existing folio_try_get lookup (mm/swap_state.c:112-124). If the folio vanishes, retry. A stable cached state returns a folio, a stable available uncached slot allocates, and other allocator errors return. Continuous adversarial insertion/removal has the baseline loop's unbounded-retry limitation. No lock is held across retries.

Both allocator checks remain byte-for-byte unchanged. The initial locked lookup is released before allocation, followed by a fresh descriptor lookup and locked validation before publication (mm/swap_state.c:460-505). The unpinned helper discovers the descriptor under RCU and locks before leaving RCU (mm/swap.h:177-235). Xswap shrink lowers the mapped bound, waits for readers and locks affected clusters before unmapping (mm/swapfile.c:5036-5077). Published locked cache folios pin entries through charge and I/O. Device teardown waits for device references and RCU readers (mm/swapfile.c:4116-4126).

Callers still lock and revalidate folio identity, mapping/PTE state and uptodate data (mm/memory.c:5026-5040, 5073-5080; mm/shmem.c:2563-2578). A reference to a subsequently rolled-back folio cannot make that folio usable.

Large-order behavior is retained. Target cache detection precedes range validation; uncached ranges still validate counts, zero flags, memcg and xswap backing contiguity (mm/swap_state.c:178-232; mm/swapfile.c:4528-4555). Order fallback remains restricted to eligible -EBUSY/-ENOMEM results (mm/swap_state.c:569-587). Anonymous order/PTE validation and shmem's order-zero retry and mapping split remain unchanged.

Allocation, failed-recheck and charge/deferred-accounting errors retain their cleanup (mm/swap_state.c:486-526). Cache publication is removed before owned references are dropped. Independent acquired references remain with their holders. Final folio release uncharges memcg (mm/folio.c:91-106). Cached hits bypass LRU insertion and I/O; new folios keep that sequence (mm/swap_state.c:780-795). I/O errors leave the folio not uptodate and callers reject it (mm/page_io.c:595-637; mm/zswap.c:1662-1733).

## Resource ownership

| Resource | Owner or reference | Publication | Release | Protection |
| --- | --- | --- | --- | --- |
| New folio | Allocator reference plus cache reference per page; return transfers caller reference | Locked swapbacked folio installed in table | Failed check drops allocation; rollback removes cache and owned refs; final release | Cluster lock, then folio lock and refs; swap_state.c:235-256,489-526 |
| Cached folio | Cache refs plus folio_try_get caller ref | Existing cache entry | Caller releases ref; cache removal drops cache refs | Ref acquisition then caller lock/entry validation; swap_state.c:112-124,369-378 |
| Swap slot | PTE/shmem count and cache association | Existing allocation/cache publication | Last count without cache, or later removal of zero-count cache | Cluster lock, caller PTE/mapping checks; swapfile.c:1940-1986 |
| Swap device | get_swap_device caller reference | Valid live reference | Common put_swap_device cleanup | Per-CPU refs and teardown sync; memory.c:4986-4992,5300-5302; shmem.c:2486-2496,2607-2622 |
| Descriptor/table | Device storage, transient RCU/cluster lock; occupied entries pin cluster | Initialized before mapped-bound release | Empty table teardown and protected tail unmap | RCU and cluster locks; swapfile.c:629-667,832-849,4893-4904,5036-5077 |
| Compressed object | Zswap tree plus pool/objcg refs | Zswap store | Load/slot invalidation erase and free | Existing folio/slot lifetime; zswap.c:1487-1541,1678-1754,777-793 |
| Memcg charge | Charged folio | Successful swapin charge | Final folio release after cache rollback where needed | Existing accounting/ref rules; memcontrol.c:5444-5462,5499-5554; folio.c:103-106 |
| Physical backing record | Virtual slot's xs_table association | Existing backend setter | Slot/backend release and empty-cluster cleanup | Xswap lock then physical lock; swapfile.c:3350-3375,4588-4621 |

## Mechanism and tradeoff

An uncontended cold success removes one swap_cache_get_folio invocation inside swapin_sync (base swap_state.c:778-790; candidate:778-794). That lookup includes RCU-protected descriptor/table access (swap_state.c:85-95; swap_table.h:335-346). Both allocator pre/post checks remain at 465-495, with unchanged LRU insertion and read submission.

A raced hit now takes the allocator's cluster-locked precheck before retrieving the folio. The old helper could return that hit immediately. No persistent metadata is added; the retained precheck avoids allocation when it observes a cached folio.

Xswap sets SWP_SYNCHRONOUS_IO (swapfile.c:5507-5512); both protocol latency arms therefore exercise the helper on cold faults. The workload disables THP. A useful latency gain remains uncertain and may be below TCG noise. The frozen threshold is a resolved 5% gain beyond noise with passing guards.

No blocking maintainability finding. One coherent reorder, no helper or state, unchanged cleanup. The commit records the race-hit lock cost and does not claim speedup.

## Checks and limitations

All inspection ran over SSH on the designated Linux worker. Verified exact base/parent/head/tree, full diff, path scope and clean tree; enumerated callers; inspected allocator/publication/removal, charging, I/O, device teardown and descriptor lifetime. git diff --check passed. Pinned checkpatch with --no-tree --no-signoff --strict reported zero errors, warnings and checks over 19 patch lines.

Inspected mm/swap_state.c, mm/swap.h, mm/swap_table.h, mm/memory.c, mm/shmem.c, mm/swapfile.c, mm/page_io.c, mm/zswap.c, mm/memcontrol.c, mm/folio.c and include/linux/mm.h. Reviewed repository policy, protocol, proposal, brief and relevant process guidance. Benchmark correctness.c:67-72 and swapin.c:157-166 use anonymous base pages.

No build, sparse, guest, reproducer, fault injection or sanitizer execution was part of this review. Dedicated shmem, large-folio, memcg/I/O-failure and sustained-race coverage is absent. Candidate runtime correctness was pending at review time. The review authorizes no promotion.

Revert target: 3fe7af01da59a8ade95823a13c25a8c796c6321f. No reviewer process remains active.
