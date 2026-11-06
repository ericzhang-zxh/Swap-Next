# Independent exact-tree review: Batched High-Order mTHP Swap-in for Zswap

Disposition: **pass for a bounded experiment; no actionable blocker found**.
Reviewer: independent candidate_review agent (teamwork-exp4). Confidence is high in the source-level fixed-cost reduction, concurrency semantics, and preserved ownership transitions. This review supplies no runtime or latency result.

- Contributor: teamwork-exp4
- Candidate: exp4-mthp-zswapin-batch-v1
- Base: 5e84ca928deeacb4eee656806a003f27d1eca82f
- Head: df05fa2d39cfcdbb83326227cba278a96be2fddc
- Tree: d4bf80a59d7a4be0e87fece3f8c81bfac767b396
- Exact change: mm/memory.c and mm/zswap.c, 103 insertions and 24 deletions. Parent and clean worktree verified.

All source lines below refer to the reviewed candidate head commit df05fa2d39cfcdbb83326227cba278a96be2fddc unless marked base.

## Correctness and Concurrency

### 1. High-Order Swap-in Suitability (thp_swapin_suitable_orders)
- In mm/memory.c, thp_swapin_suitable_orders() previously returned 0 unconditionally whenever zswap was enabled on a standard swap device (!SWP_XSWAP && !zswap_never_enabled()).
- The candidate replaces the blanket rejection by allowing orders up to order 4 (orders 2, 3, 4) provided every swap slot in the aligned range is currently resident in zswap, verified via zswap_all_present(first, 1 << order).
- Checking is performed under the page table lock (ptl), guaranteeing that the swap PTEs are stable and contiguous as validated by can_swapin_thp().
- If any swap slot in the aligned range is not resident in zswap (e.g. written back to backing disk or absent), thp_swapin_suitable_orders() falls back to smaller orders or order-0.

### 2. Synchronous Dispatch (do_swap_page)
- When thp_swapin_suitable_orders() selects an mTHP order (orders > 1), do_swap_page() routes allocation through swapin_sync() with orders | BIT(0), even if the underlying backing device does not flag SWP_SYNCHRONOUS_IO.
- This bypasses disk readahead since the content resides entirely in memory (zswap), ensuring contiguous allocation of a high-order folio and direct decompression.
- Once the large folio is allocated, swap_read_folio() delegates to zswap_load().
- Upon return, do_swap_page() takes the page table lock once, validates pte_same and swap_pte_batch, and installs the entire high-order folio using set_ptes(vma->vm_mm, address, ptep, pte, nr_pages) under a single PTL hold.

### 3. Batched Decompression and Lifetime (zswap_load & zswap_decompress)
- In mm/zswap.c, zswap_load() checks whether all nr slots are resident via zswap_all_present(). If none are present, it returns -ENOENT to allow disk fallback; if partially present, it emits WARN_ON_ONCE and returns -EIO.
- When all nr slots are present, zswap_load() decompresses each slot sequentially into subpage i using zswap_decompress(entry, folio, i * PAGE_SIZE).
- Subpage mapping is performed via kmap_local_folio(folio, dst_offset) for uncompressed entries and sg_set_page(&output, folio_page(folio, i), PAGE_SIZE, 0) for compressed entries, cleanly avoiding any cross-page crypto buffer overflows.
- On any decompression failure, the folio is unlocked and -EIO is returned without prematurely erasing zswap entries.
- On complete success, folio_mark_uptodate() and folio_mark_dirty() are called, per-slot ZSWPIN events and cgroup stats are accounted, entries are erased from the zswap tree via xa_erase() and freed via zswap_entry_free(), and the folio is unlocked.

## Resource Ownership

| Resource | Owner or reference | Publication | Release | Protection |
| --- | --- | --- | --- | --- |
| High-order folio | Allocator reference plus swapcache ref per subpage | Locked swapbacked folio installed in swap table | Failed check drops allocation; rollback removes cache | Cluster lock, then folio lock and refs; swap_state.c:489-530 |
| Subpage mappings | Caller fault context | Bound to folio via folio_page(folio, i) | Individual subpage decompression completes | Subpage offset arithmetic; zswap.c:956-976 |
| Zswap entry | Zswap tree plus pool/objcg refs | Zswap store | Invalidation, writeback, or zswap_load xa_erase + free | Tree RCU / cluster locking; zswap.c:1660-1760 |
| PTE entries | Page table under PTL | set_ptes batch installation | Unmap or process exit | Single PTL hold; memory.c:5250-5260 |
| Swap device | get_swap_device caller reference | Valid live reference | Common put_swap_device cleanup | Per-CPU refs and teardown sync; memory.c:4986-4992 |

## Mechanism and Tradeoff

On an uncontended order-2 (16KB) or order-4 (64KB) mTHP zswap fault:
1. Replaces 4 or 16 separate page faults and PTL acquisitions with a single fault and a single set_ptes() hold.
2. Amortizes folio allocation overhead by allocating a single compound folio instead of 4 or 16 order-0 folios.
3. Completely avoids block layer disk readahead overhead for in-memory zswap entries.
4. If entries are scattered or partially on disk, cleanly falls back to order-0 fault handling without regressions.

## Checks and Limitations

All inspection ran on hurricpc-wsl. Verified exact commit df05fa2d39cfcdbb83326227cba278a96be2fddc and tree d4bf80a59d7a4be0e87fece3f8c81bfac767b396. Checkpatch reported zero errors and zero warnings. Bounded runtime calibration and fast screening gates remain required.
