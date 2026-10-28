# Descriptor retirement lifetime review finding

Status: source-supported correctness finding, not runtime reproduced. No security
classification or publication. Applies to observation baseline
4f83412c1d59eaf6a4d2460cb47fe0177a3be0c4 and both mechanism candidates.
It blocks promotion and must be addressed before broadening reclamation to holes.

## Concrete stale-entry interleaving

1. mm/zswap.c:shrink_memcg_cb copies swpentry, then drops the LRU lock. Its
   documented contract explicitly allows concurrent entry invalidation. The list
   walker supplies no outer RCU read section spanning this unlocked work.
2. The callback is delayed. Another task frees the last user and swapcache
   association for that high slot. __free_cluster returns its descriptor to the
   free list and schedules shrink.
3. A sufficiently large contiguous free suffix satisfies existing shrink/slack
   rules. xswap_try_shrink isolates it; xswap_unmap_clusters_locked flushes
   allocation caches, waits for RCU, and unmaps descriptor pages. Choose a
   descriptor wholly in removed pages, away from a retained boundary page.
4. The callback resumes in zswap_writeback_entry. get_swap_device succeeds because
   the device is live and offset < si->max; it does not pin a descriptor mapping.
5. __swap_cache_alloc_folio derives ci directly. __swap_cache_alloc takes ci->lock
   before its stale-slot check, potentially dereferencing an unmapped descriptor.

An independent interval exists between the two ci locks in __swap_cache_alloc:
the first availability check does not reserve the slot; folio allocation can
sleep, the slot can disappear, then the second lock uses the saved descriptor.

## Scope and protecting invariants

Concurrent target faults can also retain a saved entry after pte_unmap_same and
before swap_cache_get_folio. Later PTE validation protects semantic correctness
only if descriptor access remains safe. Table-level RCU begins after direct ci
lookup and does not validate a descriptor that was absent before the read section.

Do not generalize every reader as unsafe. move_swap_pte holds/revalidates PTLs
for swap_cache_has_folio. filemap_cachestat supplies outer RCU for its shmem entry
observation and shadow lookup. Locked swapcache folios preserve live ownership.
xswap_unuse_rmap holds owner xswap_lock and checks the dense bound. Swapoff disables
allocation, cancels work, and stabilizes mapping before its walkers.

Xswap target readahead explicitly skips neighbor speculation in both cluster and
VMA paths. An ordinary xswap-neighbor example would be incorrect; the zswap
callback and concurrent target-fault sequences do not need neighbor readahead.

## Required design response

A prefix or bitmap check in get_swap_device alone is not sufficient: checking
then sleeping/dereferencing leaves a race. Protect speculative mapping lookup
through every descriptor access, and either pin mapping lifetime across sleeping
allocation or drop/relookup with RCU plus mapped-state validation afterward.
Persistent group state must outlive reclaimed pages for an interior-hole design.
Retain existing allocation-cache RCU and FREE-only isolation rules.

Confidence is high for the source-level interleaving, with no runtime reproduction.
Current isolated measurements are discovery evidence and do not discharge this
finding. Neither passing workload data checks nor absence of warnings proves
this race cannot occur.
