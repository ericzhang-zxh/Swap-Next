# Stacked xswap chain: batch swap-in, mTHP reassembly and radix hole reclaim

**needs-review** — Rejected chain: three stacked xswap commits never beat calibrated noise. M2 failed disk swap-in guards; probe metadata stayed at 0.111 bytes per slot. Every value review rejected; nothing to promote.

## Why this experiment

Upstream xswap swaps in one page per fault and only shrinks metadata from the tail. Three stacked commits tested batching, mTHP reassembly and interior hole reclaim.

Git ancestry confirms the chain. Candidate records were relabelled generations 1 to 3 to match it; measurements and reviews are unchanged.

Evidence: campaigns/xswap-radix-hole-reclaim-2026-11-06/campaign.json, campaigns/xswap-radix-hole-reclaim-2026-11-06/protocol.json, campaigns/xswap-radix-hole-reclaim-2026-11-06/candidates/xswap-fast-in-v1.json, campaigns/xswap-radix-hole-reclaim-2026-11-06/candidates/xswap-mthp-reassembly-v1.json, campaigns/xswap-radix-hole-reclaim-2026-11-06/candidates/xswap-radix-hole-reclaim-v1.json

## Where the cost appears

Each stage targeted a hypothesised cost: per-fault swap-in work, mTHP folios split on zswap swap-in, and interior metadata pages pinned by one live high slot.

These are the stated hypotheses, not measured findings.

Evidence: campaigns/xswap-radix-hole-reclaim-2026-11-06/candidates/xswap-fast-in-v1.json, campaigns/xswap-radix-hole-reclaim-2026-11-06/candidates/xswap-mthp-reassembly-v1.json, campaigns/xswap-radix-hole-reclaim-2026-11-06/candidates/xswap-radix-hole-reclaim-v1.json

## The affected path

M1 and M2 change the fault and readahead path; M3 changes how swapfile.c stores and frees cluster metadata.

The probe and fast tiers measure swap-in latency and metadata bytes per slot.

Evidence: campaigns/xswap-radix-hole-reclaim-2026-11-06/patches/xswap-fast-in-v1.patch, campaigns/xswap-radix-hole-reclaim-2026-11-06/patches/xswap-mthp-reassembly-v1.patch, campaigns/xswap-radix-hole-reclaim-2026-11-06/patches/xswap-radix-hole-reclaim-v1.patch

## What actually changed

M1 gates readahead on contiguous hits and enters synchronous swap-in allocator-first. M2 checks zswap residency for order-2 and order-4 folios. M3 stores clusters in 64-cluster chunks.

The independent exact-tree review of M3 recorded no blockers.

Evidence: campaigns/xswap-radix-hole-reclaim-2026-11-06/patches/xswap-fast-in-v1.patch, campaigns/xswap-radix-hole-reclaim-2026-11-06/patches/xswap-mthp-reassembly-v1.patch, campaigns/xswap-radix-hole-reclaim-2026-11-06/patches/xswap-radix-hole-reclaim-v1.patch, campaigns/xswap-radix-hole-reclaim-2026-11-06/reviews/xswap-radix-hole-reclaim-independent-v1.json

## The next decision

Gains were M1 +3.5% (noise 9.0%), M2 +0.2% (noise 3.5%, guards failed) and M3 -0.05% (noise 4.2%). All value reviews rejected the chain.

Baseline and every stage measured 0.111 metadata bytes per slot. The probe likely created no interior holes, so M3's reclaim benefit is unmeasured (inference).

Evidence: campaigns/xswap-radix-hole-reclaim-2026-11-06/candidates/xswap-fast-in-v1/value.json, campaigns/xswap-radix-hole-reclaim-2026-11-06/candidates/xswap-mthp-reassembly-v1/value.json, campaigns/xswap-radix-hole-reclaim-2026-11-06/candidates/xswap-radix-hole-reclaim-v1/value.json, campaigns/xswap-radix-hole-reclaim-2026-11-06/ledger/ledger.json

## Core kernel patches (M1 → M2 → M3)

Verbatim largest hunks of each stage's incremental git diff; full cumulative patches are the pinned sources.

### M1 5cde9eaa: allocator-first sync swap-in and streak-gated readahead (git diff 5e84ca92..5cde9eaa)

Source: `campaigns/xswap-radix-hole-reclaim-2026-11-06/patches/xswap-fast-in-v1.patch`

```diff
--- a/mm/swap_state.c
+++ b/mm/swap_state.c
@@ -889,6 +913,66 @@ static unsigned long swapin_nr_pages(unsigned long offset)
 	return pages;
 }
 
+#define ZSWAP_PREFETCH_BATCH 32
+
+struct zswap_prefetch_batch {
+	struct work_struct work;
+	unsigned int nr;
+	swp_entry_t entries[ZSWAP_PREFETCH_BATCH];
+};
+
+static struct workqueue_struct *zswap_prefetch_wq;
+
+static void zswap_prefetch_work_fn(struct work_struct *work)
+{
+	struct zswap_prefetch_batch *batch =
+		container_of(work, struct zswap_prefetch_batch, work);
+	unsigned int i;
+
+	for (i = 0; i < batch->nr; i++) {
+		swp_entry_t entry = batch->entries[i];
+		struct swap_info_struct *si;
+		struct folio *folio;
+		int ret;
+
+		si = get_swap_device(entry);
+		if (IS_ERR_OR_NULL(si))
+			continue;
+
+		folio = swap_cache_get_folio(entry);
+		if (folio) {
+			folio_put(folio);
+			put_swap_device(si);
+			continue;
+		}
+
+		folio = __swap_cache_alloc_folio(entry,
+						 GFP_NOWAIT | __GFP_NOWARN | __GFP_NORETRY,
+						 BIT(0), NULL, NULL, 0);
+		if (IS_ERR_OR_NULL(folio)) {
+			put_swap_device(si);
+			continue;
+		}
+
+		ret = zswap_load(folio);
+		if (ret == 0) {
+			folio_add_lru(folio);
+			folio_set_readahead(folio);
+			count_vm_event(SWAP_RA);
+		} else {
+			if (!folio_test_locked(folio))
+				folio_lock(folio);
+			swap_cache_del_folio(folio);
+			folio_unlock(folio);
+		}
+
+		folio_put(folio);
+		put_swap_device(si);
+	}
+
+	kfree(batch);
+}
+
 /**
  * swap_cluster_readahead - swap in pages in hope we need them soon
  * @entry: swap entry of this memory
@@ -920,9 +1004,9 @@ struct folio *swap_cluster_readahead(swp_entry_t entry, gfp_t gfp_mask,
 	struct blk_plug plug;
 	swp_entry_t ra_entry;
 
-	/* xswap entries live only in zswap; readahead does not help. */
-	if (si->flags & SWP_XSWAP)
-		goto skip;
+	bool zswap_active;
+
+	zswap_active = zswap_is_enabled() || (si->flags & SWP_XSWAP);
 
 	mask = swapin_nr_pages(offset) - 1;
 	if (!mask)
```

### M2 53e02e86: zswap mTHP residency check and subpage zswap_load (git diff 5cde9eaa..53e02e86)

Source: `campaigns/xswap-radix-hole-reclaim-2026-11-06/patches/xswap-mthp-reassembly-v1.patch`

```diff
--- a/include/linux/zswap.h
+++ b/include/linux/zswap.h
@@ -73,6 +74,11 @@ static inline bool zswap_never_enabled(void)
 	return true;
 }
 
+static inline bool zswap_all_present(swp_entry_t entry, unsigned int nr)
+{
+	return false;
+}
+
 #endif
 
 #endif /* _LINUX_ZSWAP_H */
--- a/mm/zswap.c
+++ b/mm/zswap.c
@@ -1694,20 +1721,60 @@ int zswap_load(struct folio *folio)
 	 * it outright. The caller has pinned every slot, so zswap cannot start
 	 * a store or a writeback into the range while we look.
 	 */
+	/*
+	 * A large folio can legitimately reach zswap_load() when all slots
+	 * reside in zswap (mTHP swap-in batch) or when the whole range is
+	 * on the backing device.
+	 */
 	if (folio_test_large(folio)) {
-		if (WARN_ON_ONCE(zswap_is_present(swp,
-						  folio_nr_pages(folio)))) {
-			folio_unlock(folio);
-			return -EIO;
+		unsigned int nr = folio_nr_pages(folio);
+		unsigned int i;
+
+		if (!zswap_all_present(swp, nr)) {
+			if (WARN_ON_ONCE(zswap_is_present(swp, nr))) {
+				folio_unlock(folio);
+				return -EIO;
+			}
+			return -ENOENT;
 		}
-		return -ENOENT;
+
+		/* Phase 1: decompress all N subpages into folio offsets i * PAGE_SIZE */
+		for (i = 0; i < nr; i++) {
+			entry = xa_load(tree, offset + i);
+			if (WARN_ON_ONCE(!entry)) {
+				folio_unlock(folio);
+				return -EIO;
+			}
+			if (!zswap_decompress(entry, folio, i * PAGE_SIZE)) {
+				folio_unlock(folio);
+				return -EIO;
+			}
+		}
+
+		/* Phase 2: upon complete success, mark folio uptodate/dirty, batch erase & free */
+		folio_mark_uptodate(folio);
+		folio_mark_dirty(folio);
+
+		for (i = 0; i < nr; i++) {
+			entry = xa_load(tree, offset + i);
+			if (WARN_ON_ONCE(!entry))
+				continue;
+			count_vm_event(ZSWPIN);
+			if (entry->objcg)
+				count_objcg_events(entry->objcg, ZSWPIN, 1);
+			xa_erase(tree, offset + i);
+			zswap_entry_free(entry);
+		}
+
+		folio_unlock(folio);
+		return 0;
 	}
 
 	entry = xa_load(tree, offset);
 	if (!entry)
 		return -ENOENT;
 
-	if (!zswap_decompress(entry, folio)) {
+	if (!zswap_decompress(entry, folio, 0)) {
 		folio_unlock(folio);
 		return -EIO;
 	}
```

### M3 2c1ddb53: two-level cluster_dir chunks and interior hole reclaim (git diff 53e02e86..2c1ddb53)

Source: `campaigns/xswap-radix-hole-reclaim-2026-11-06/patches/xswap-radix-hole-reclaim-v1.patch`

```diff
--- a/mm/swapfile.c
+++ b/mm/swapfile.c
@@ -4823,108 +4872,170 @@ void xswap_backend_free(swp_entry_t entry, swp_entry_t phys, unsigned int order)
 	xswap_backend_uncharge(entry, 1UL << order);
 }
 
-static int xswap_map_clusters(struct swap_info_struct *si,
-			      unsigned long start_idx, unsigned long nr)
+static struct kmem_cache *xswap_chunk_cache;
+
+static struct swap_cluster_chunk *xswap_alloc_chunk(struct swap_info_struct *si,
+						    unsigned long chunk_idx)
 {
-	unsigned long start_addr = (unsigned long)si->cluster_info +
-				   (size_t)start_idx * sizeof(struct swap_cluster_info);
-	unsigned long end_addr = start_addr + (size_t)nr * sizeof(struct swap_cluster_info);
-	unsigned long vm_start = PAGE_ALIGN(start_addr);
-	unsigned long vm_end = PAGE_ALIGN(end_addr);
-	unsigned int noreclaim_flags;
-	unsigned long mapped_end;
-	unsigned long npages;
-	struct page **pages;
+	struct swap_cluster_chunk *chunk;
 	unsigned long i;
-	int err;
 
-	mutex_lock(&si->xswap_lock);
+	chunk = kmem_cache_zalloc(xswap_chunk_cache, GFP_KERNEL);
+	if (!chunk)
+		return NULL;
 
-	/* Refuse a stale range: the boundary moved since the caller read it. */
-	if (start_idx != READ_ONCE(si->nr_clusters_mapped)) {
-		mutex_unlock(&si->xswap_lock);
-		return -EAGAIN;
-	}
-	if (start_idx + nr > si->nr_clusters_max) {
-		mutex_unlock(&si->xswap_lock);
-		return -EAGAIN;
+	atomic_set(&chunk->live_clusters, 0);
+	chunk->chunk_idx = chunk_idx;
+	chunk->flags = 0;
+	if (chunk_idx == 0)
+		chunk->flags |= XSWAP_CHUNK_PERMANENT;
+
+	for (i = 0; i < XSWAP_CLUSTERS_PER_CHUNK; i++) {
+		struct swap_cluster_info *ci = &chunk->clusters[i];
+
+		spin_lock_init(&ci->lock);
+		ci->flags = CLUSTER_FLAG_NONE;
 	}
 
-	/*
-	 * Page-granular mapping can cover clusters past the previous chunk.
-	 * Find the already-mapped prefix and map only the rest.
-	 */
-	mapped_end = vm_start;
-	if (vm_start < vm_end)
-		apply_to_existing_page_range(&init_mm, vm_start,
-					     vm_end - vm_start,
-					     xswap_mapped_end, &mapped_end);
-	if (vm_start >= vm_end || mapped_end == vm_end)
-		goto mapped;
-	vm_start = mapped_end;
+	return chunk;
+}
 
-	npages = (vm_end - vm_start) >> PAGE_SHIFT;
+static void xswap_free_all_chunks(struct swap_info_struct *si)
+{
+	unsigned long chunk_idx, i;
 
-	/* Prevent recursive reclaim during vmap page table allocation. */
-	noreclaim_flags = memalloc_noreclaim_save();
+	cancel_work_sync(&si->xswap_shrink_work);
+	rcu_barrier();
 
-	pages = kmalloc_array(npages, sizeof(*pages),
-			      __GFP_HIGH | __GFP_NOMEMALLOC | GFP_KERNEL);
-	if (!pages) {
-		memalloc_noreclaim_restore(noreclaim_flags);
-		mutex_unlock(&si->xswap_lock);
-		return -ENOMEM;
+	for (chunk_idx = 0; chunk_idx < si->nr_chunks_max; chunk_idx++) {
+		struct swap_cluster_chunk *chunk;
+
+		if (!si->cluster_dir)
+			break;
+		chunk = rcu_dereference_raw(si->cluster_dir[chunk_idx]);
+		if (!chunk)
+			continue;
+
+		for (i = 0; i < XSWAP_CLUSTERS_PER_CHUNK; i++) {
+			struct swap_cluster_info *ci = &chunk->clusters[i];
+
+			spin_lock(&ci->lock);
+			xswap_free_xs_table(si, ci);
+			if (cluster_table_is_alloced(ci)) {
+				swap_cluster_assert_empty(ci, 0, SWAPFILE_CLUSTER, true);
+				swap_cluster_free_table(ci);
+			}
+			spin_unlock(&ci->lock);
+		}
+		kmem_cache_free(xswap_chunk_cache, chunk);
 	}
+	xswap_debugfs_del(si);
+	kvfree(si->cluster_dir);
+	bitmap_free(si->empty_chunks_bm);
+	si->cluster_dir = NULL;
+	si->empty_chunks_bm = NULL;
+	si->nr_chunks_mapped = 0;
+	/* Pairs with READ_ONCE(si->nr_clusters_mapped) in lockless lookups */
+	smp_store_release(&si->nr_clusters_mapped, 0);
+}
+
+static void xswap_reclaim_interior_holes(struct swap_info_struct *si)
+{
+	unsigned long chunk_idx;
+	int i, j;
 
-	for (i = 0; i < npages; i++) {
-		/* __GFP_ZERO: cluster_info pointer fields must start NULL. */
-		pages[i] = alloc_page(__GFP_HIGH | __GFP_NOMEMALLOC |
-				      GFP_KERNEL | __GFP_ZERO);
-		if (!pages[i])
-			goto fail;
+	for_each_set_bit(chunk_idx, si->empty_chunks_bm, si->nr_chunks_max) {
+		struct swap_cluster_chunk *chunk;
+
+		clear_bit(chunk_idx, si->empty_chunks_bm);
+		if (chunk_idx == 0)
+			continue;
+
+		chunk = rcu_dereference_protected(si->cluster_dir[chunk_idx],
+						  lockdep_is_held(&si->xswap_lock));
+		if (!chunk || (chunk->flags & XSWAP_CHUNK_PERMANENT))
+			continue;
+
+		if (atomic_read(&chunk->live_clusters) != 0)
+			continue;
+
+		spin_lock(&si->lock);
+		if (atomic_read(&chunk->live_clusters) != 0) {
+			spin_unlock(&si->lock);
+			continue;
+		}
+
+		for (i = 0; i < XSWAP_CLUSTERS_PER_CHUNK; i++) {
+			struct swap_cluster_info *ci = &chunk->clusters[i];
+
+			if (READ_ONCE(ci->flags) != CLUSTER_FLAG_FREE ||
+			    READ_ONCE(ci->count) != 0 ||
+			    !spin_trylock(&ci->lock)) {
+				for (j = 0; j < i; j++)
+					spin_unlock(&chunk->clusters[j].lock);
+				spin_unlock(&si->lock);
+				goto next_chunk;
+			}
+		}
+
+		for (i = 0; i < XSWAP_CLUSTERS_PER_CHUNK; i++) {
+			struct swap_cluster_info *ci = &chunk->clusters[i];
+
+			list_del_init(&ci->list);
+			WRITE_ONCE(ci->flags, CLUSTER_FLAG_NONE);
+			spin_unlock(&ci->lock);
+		}
+		spin_unlock(&si->lock);
+
+		rcu_assign_pointer(si->cluster_dir[chunk_idx], NULL);
+		if (si->nr_chunks_mapped > 0)
+			si->nr_chunks_mapped--;
+
+		kfree_rcu(chunk, rcu);
+		atomic_long_inc(&si->xswap_shrinks);
+
+next_chunk:
+		cond_resched();
 	}
+}
 
-	err = vm_area_map_pages(si->cluster_vm, vm_start, vm_end, pages);
-	if (err) {
-		i = npages;
-		goto fail;
+static int xswap_map_clusters(struct swap_info_struct *si,
+			      unsigned long start_idx, unsigned long nr)
+{
+	unsigned long start_chunk = start_idx / XSWAP_CLUSTERS_PER_CHUNK;
+	unsigned long end_chunk = DIV_ROUND_UP(start_idx + nr, XSWAP_CLUSTERS_PER_CHUNK);
+	unsigned long chunk_idx;
+
+	mutex_lock(&si->xswap_lock);
+	if (start_idx != READ_ONCE(si->nr_clusters_mapped) ||
+	    start_idx + nr > si->nr_clusters_max) {
+		mutex_unlock(&si->xswap_lock);
+		return -EAGAIN;
 	}
 
-	for (i = start_idx; i < start_idx + nr; i++)
-		spin_lock_init(&si->cluster_info[i].lock);
+	for (chunk_idx = start_chunk; chunk_idx < end_chunk; chunk_idx++) {
+		struct swap_cluster_chunk *chunk;
 
-	kfree(pages);
-	memalloc_noreclaim_restore(noreclaim_flags);
+		if (chunk_idx >= si->nr_chunks_max)
+			break;
 
-	/*
-	 * Publish the new mappings and cluster lock initialization before
-	 * the count; walkers without xswap_lock use smp_load_acquire().
-	 */
-	smp_store_release(&si->nr_clusters_mapped, start_idx + nr);
-	mutex_unlock(&si->xswap_lock);
-	return 0;
+		if (rcu_dereference_protected(si->cluster_dir[chunk_idx],
+					     lockdep_is_held(&si->xswap_lock)))
+			continue;
+
+		chunk = xswap_alloc_chunk(si, chunk_idx);
+		if (!chunk) {
+			mutex_unlock(&si->xswap_lock);
+			return -ENOMEM;
+		}
 
-mapped:
-	for (i = start_idx; i < start_idx + nr; i++)
-		spin_lock_init(&si->cluster_info[i].lock);
+		rcu_assign_pointer(si->cluster_dir[chunk_idx], chunk);
+		si->nr_chunks_mapped++;
+	}
 
-	/* Publish the advanced count. */
 	smp_store_release(&si->nr_clusters_mapped, start_idx + nr);
 	mutex_unlock(&si->xswap_lock);
 	return 0;
-
-fail:
-	/* Clear PTEs vm_area_map_pages() may have left before freeing pages. */
-	vm_area_unmap_pages(si->cluster_vm, vm_start, vm_end);
-	while (i > 0) {
-		i--;
-		if (pages[i])
-			__free_page(pages[i]);
-	}
-	memalloc_noreclaim_restore(noreclaim_flags);
-	kfree(pages);
-	mutex_unlock(&si->xswap_lock);
-	return -ENOMEM;
 }
 
 static bool xswap_should_grow(struct swap_info_struct *si)
```

## Outcomes

| Evaluation | Candidate | Tier | Result |
| --- | --- | --- | --- |
| 7fd6a35d9f0c4f1d977138c13e707386 |  | probe | CALIBRATED |
| b5081dabcab34c438126c79de5ad8e33 | xswap-fast-in-v1 | probe | PROBE_PASS |
| 7d014ac1173e448b969a8ebb0d2b472c |  | fast | CALIBRATED |
| 1ee1368ba52e492fb9aa053ed29c4b8a | xswap-fast-in-v1 | fast | FAST_PASS |
| edc1ee76e7d94a64a01ec371b5a8944f |  | probe | CALIBRATED |
| 0af203f743bf4038a97bf4ffa9e11f2c | xswap-mthp-reassembly-v1 | probe | PROBE_PASS |
| 4d9b2ef33400429c9d774adc8c5f86a2 |  | fast | CALIBRATED |
| 8f4c32b846084f769aae5dd2e5cd83f1 | xswap-mthp-reassembly-v1 | fast | REGRESSION |
| 8eda31b19eff4af5a704c5c73578a1b2 |  | probe | CALIBRATED |
| e0f075ffbf2a4614a3a2be191781f5d6 | xswap-radix-hole-reclaim-v1 | probe | PROBE_PASS |
| 2e0d35e724f449d79888a19659a9ffaa |  | fast | CALIBRATED |
| 0f361c6c5428419d9d04479921fab02a | xswap-radix-hole-reclaim-v1 | fast | FAST_PASS |

## Limitations

Screen evidence; candidate promotion remains human-controlled.
Raw evidence missing on this machine: 0.
Upstream comparison rows: 0.
Full outcomes, failed guards and complexity decisions are in summary.json.

[Interactive explanation](explainer.html)
