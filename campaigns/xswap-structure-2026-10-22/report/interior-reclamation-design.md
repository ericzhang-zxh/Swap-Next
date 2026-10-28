# Interior descriptor reclamation: implementation boundary

Status: architecture inventory, not implemented or runtime validated. Source
inventory was performed on observation baseline plus the unrelated low-first
allocator tweak. The next design must preserve the kernel entry lifetime rules.

## Representation

Keep the reserved linear cluster_info virtual address range and existing free
lists. Add persistent group state outside reclaimable descriptors, with a mapped
capacity separate from the highest mapped index. Derive group alignment as
PAGE_SIZE / gcd(PAGE_SIZE, sizeof(struct swap_cluster_info)) clusters. The normal
56-byte/4-KiB configuration yields 512 clusters (seven pages); lockdep changes the
descriptor size, so hardcoding this is invalid.

Remap absent groups before extending the high-water extent. Initialize descriptors
before publishing mapping visibility and before adding free-list entries, under
xswap_lock. Reclaim only wholly FREE and empty groups; an empty NONE descriptor
can belong to a sleeping population operation and must block reclaim. Group zero
remains mapped. Remove a retiring group from allocation, retire mapping visibility,
drain readers, then unmap its aligned pages. Desired capacity uses mapped count.

## Required consumers

- swap_info_struct: persistent group state, mapped count and extent.
- setup_swap_clusters_info: allocate tracking first; initialize group zero;
  unwind all setup failures; list only mapped descriptors.
- xswap_map_clusters / xswap_grow: support holes and initialize-before-publish;
  remove the current gap between mapping and allocation-list publication.
- xswap_should_grow: capacity rather than extent.
- xswap_try_shrink / xswap_unmap_clusters_locked: whole-group isolation and reader
  retirement; separate unmapping from prefix accounting.
- find_next_to_unuse / wait_for_allocation / free_swap_cluster_info: skip absent
  groups before descriptor access; prove stable mapping during teardown.
- xswap_unuse_rmap: validate owner bounds and mapped state under owner mutex.
- xswap_debugfs_read: actual mapped capacity differs from position; existing
  mapped-minus-highest tail calculation and parser bounds must be revised.

This is a new benchmark protocol: current highest-position <= mapped-count
checks are invalid with interior holes. Recalibration is required before any
comparison; old observations remain historical.

## Architectural safety blocker

Speculative swap-cache operations cannot rely solely on a live device reference.
swap_cache_get_folio, swap_cache_has_folio and swap_cache_get_shadow derive ci
before table-level RCU. __swap_cache_alloc can retain ci across sleeping folio
allocation and lock it afterward. Speculative readahead may no longer own a live
slot. xswap_reclaim_backing can start from a stale physical reverse mapping.

Choose and prove one explicit lifetime model before implementation: persistent
per-group pins spanning sleeping accesses, or RCU-protected mapped-state lookup
at every descriptor access, dropping and relooking up after sleeping allocations.
A bitmap test followed by sleep or unprotected dereference is insufficient.
Owned live slots may retain their fast lookup contract; speculative offsets need
an explicit safe helper.

Per-CPU allocation offsets also require proof: prevent retiring-group offsets
from being republished after cache flush, or validate mapped state at consumption
under RCU. Existing live-device flush plus grace period is not by itself a complete
proof. Preserve RCU across current fast-allocation and unlocked reclaim paths.

## Evidence needed before execution

The high-anchor diagnostic first establishes whether free interior space persists
while high live references remain. Placement success alone is insufficient.
Then test group reclaim/remap cycles, speculative lookup and readahead races,
population failures, concurrent faults, swapoff, backend-owner walking, and
multiple descriptor layouts. Sanitizer/lockdep and actual physical metadata
accounting remain necessary. No promotion or performance claim follows from
this inventory.
