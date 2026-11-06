# Independent Exact-Tree Review: xswap-mthp-reassembly-v1

- Campaign: xswap-mthp-reassembly-2026-11-06
- Candidate Commit: 53e02e8615a30d927daf77e5f1f7a7182a1c6ec5
- Baseline Commit: 5e84ca928deeacb4eee656806a003f27d1eca82f
- Disposition: PASS (0 blockers)

## Findings Summary
1. Blackout Lifting & Order Routing: In mm/memory.c:thp_swapin_suitable_orders, the conservative blackout is replaced with an exact RCU-safe contiguous presence check zswap_all_present() across candidate orders 2 and 4. In do_swap_page(), orders > 1 are routed directly to swapin_sync() allocator-first, avoiding disk readahead delays.
2. Contiguous Presence Probing: In mm/zswap.c:zswap_all_present() and include/linux/zswap.h, all slots within the mTHP range are verified via RCU xa_load() across swap_zswap_tree(). If any slot is missing or written back to disk, the check returns false and execution falls back cleanly to smaller orders or order-0.
3. Two-Phase Commit Decompression: In mm/zswap.c:zswap_load(), Phase 1 speculatively decompresses each subpage into kmap_local_folio subpage offsets without modifying or freeing any zswap entries. If any subpage fails, -EIO is returned with the folio unlocked and not uptodate, cleanly triggering order-0 fallback with zero memory leaks. Phase 2 marks the folio uptodate and dirty, batch-erases all entries from the tree, charges events, and unlocks the folio.
4. Single-PTL Multi-PTE Installation: In mm/memory.c:do_swap_page(), all subpages of the high-order folio are atomically mapped using set_ptes() under a single vmf->ptl acquisition, eliminating 75% to 93.75% of page table lock holds and per-page fault entries.
