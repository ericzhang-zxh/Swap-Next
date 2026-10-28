# Dense-prefix lifetime repair plan

Status: source-reviewed proposal, not implemented or runtime validated.
The finding in descriptor-lifetime-review.md blocks candidate promotion.

## Chosen next approach

Prefer RCU-protected mapping checks and relookup for the existing dense prefix.
Persistent group pins are deferred until interior-hole representation requires
persistent group state. A sleeping pin held while reclaim needs xswap_lock can
deadlock a retiring writer waiting under that mutex.

Under xswap_lock, retire isolated tail visibility by release-publishing the reduced
nr_clusters_mapped before the RCU grace period and physical unmapping. Preserve
growth's initialized-before-release publication. Speculative readers enter RCU
before acquire-reading the bound, derive a descriptor only if mapped, and retain
RCU through descriptor accesses and cluster locking. The bound lives in persistent
swap_info_struct. Ordinary swap remains dense.

Add an explicit guarded helper rather than silently making every unconditional
cluster helper nullable. Existing ownership-protected paths may retain their
unconditional lookup. Mapping safety and slot identity are separate obligations.

## Required reader changes

- swap_cache_get_folio: guarded lookup through table lookup and folio reference
  acquisition. Apply consistent handling to swap_cache_has_folio and
  swap_cache_get_shadow.
- __swap_cache_alloc_folio and __swap_cache_alloc: do not keep ci across folio
  allocation. Each preallocation and postallocation check independently enters
  RCU, validates mapping, derives ci, locks it, and performs the existing slot
  check. If absent after allocation, free the new folio and return -ENOENT.
  On success, publish the locked swapcache folio before dropping protection;
  that ownership prevents descriptor retirement during charging/cleanup.
  Preserve EEXIST/EBUSY, charge rollback, order fallback and allocation failures.
- swap_retry_table_alloc and swap_extend_table_alloc: allocate extension storage
  first, then guarded relookup. copy_pte_range drops both PTLs before retry;
  its saved entry can become stale while allocation sleeps.
- swap_alloc_fast and swap_alloc_hibernation_slot: validate cached offsets inside
  existing RCU sections before ci locking. Retain per-CPU cache flushing.
- swp_swapcount: consider consistent guarded zero-on-absent behavior. Its current
  proc caller has PTE protection; this is not the main demonstrated failure.

xswap_alloc_slot_local receives physical devices; xswap_alloc_phys_slot skips
SWP_XSWAP. No speculative xswap mapping repair is needed there.
zswap_writeback_entry can use the repaired allocation contract without a new
mapping mutex. Preserve its locked-folio ownership and zswap tree identity check.

## Review obligations

Never hold RCU or ci spinlock across allocation or charging. Never hold
xswap_lock around generic swap-in allocation or folio waits. A check in
get_swap_device alone does not protect later use. Regrowth may reuse the same
descriptor address: rederive and check current slot state after sleep. Preserve
PTE, folio-entry and zswap-tree identity checks; a saved entry does not own its
original contents. Review table-free ordering separately from descriptor lifetime.
For future holes, replace the prefix bound with persistent mapped-group state
while retaining the reader protocol.

## Focused next reproduction campaign

Use test-only controlled pauses in isolated guests:
1. After shrink_memcg_cb copies its entry and drops LRU lock, pause; free the
   high slot, reclaim eligible tail, verify its descriptor page unmapped, resume.
2. Pause __swap_cache_alloc between initial check and the second descriptor lock;
   retire tail; resume, requiring -ENOENT and full folio/charge cleanup.
3. Repeat with regrowth before resume and check stale ownership validation.
4. Inject an extension-table allocation delay to exercise retry after PTL release.

Use fresh lockdep guests and suitable memory diagnostics. Check stale descriptor
access, atomic sleeping, stuck shrink, charge leaks and complete data integrity.
An unmapped-page access is a direct oracle; absence of KASAN findings alone is
insufficient. The current campaign supplies no runtime evidence for this repair.
