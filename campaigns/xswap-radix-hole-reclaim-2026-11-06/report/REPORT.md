# Unified xswap Superset Chain: Batch Swap-In, Order-4 mTHP Reassembly, and 2-Level RCU Radix Reclaim

**needs-review** — A three-stage compounding kernel chain evolved upstream xswap across synchronous zswap batching (M1), 64KB mTHP fault reassembly (M2), and 2-level RCU radix hole reclamation (M3), achieving -63.1% fragmented metadata overhead across all 17 correctness gates.

## Why this experiment

Upstream xswap stops at dynamic VM_SPARSE high-water-mark growth and single-page synchronous swap-in, leaving three structural gaps along the swap lifecycle.

Each candidate commits directly atop the previous milestone tree, forming a verified 3-stage lineage.

Evidence: campaigns/xswap-radix-hole-reclaim-2026-11-06/campaign.json, campaigns/xswap-radix-hole-reclaim-2026-11-06/protocol.json, campaigns/xswap-radix-hole-reclaim-2026-11-06/candidates/xswap-fast-in-v1.json, campaigns/xswap-radix-hole-reclaim-2026-11-06/candidates/xswap-mthp-reassembly-v1.json, campaigns/xswap-radix-hole-reclaim-2026-11-06/candidates/xswap-radix-hole-reclaim-v1.json

## Where the cost appears

Single-page faults repeat radix lookups, split 64KB folios stay fragmented as 4KB pages, and high-offset pinned slots block tail-only VM_SPARSE shrink.

In upstream xswap, a single live high-offset slot pins every interior swap_cluster_info page below the high-water mark.

Evidence: campaigns/xswap-radix-hole-reclaim-2026-11-06/ledger/ledger.json

## The affected path

The compounding chain spans do_swap_page(), swapin_sync(), xswap.c zswap helpers, and swapfile.c cluster directory management.

swap_cluster_lookup_rcu() re-verifies si->cluster_dir[chunk_idx] == chunk after acquiring ci->lock to close races against concurrent chunk unlinking.

Evidence: campaigns/xswap-radix-hole-reclaim-2026-11-06/patches/xswap-fast-in-v1.patch, campaigns/xswap-radix-hole-reclaim-2026-11-06/patches/xswap-mthp-reassembly-v1.patch, campaigns/xswap-radix-hole-reclaim-2026-11-06/patches/xswap-radix-hole-reclaim-v1.patch

## What actually changed

M1 adds batched zswap prefetching, M2 reassembles 16 contiguous slots into an order-4 folio, and M3 replaces flat VM_SPARSE arrays with 64-cluster RCU chunks.

When any slot in a 64KB block fails exclusive count==1 validation, M2 falls back cleanly to M1 order-0 swap-in without partial state leakage.

Evidence: campaigns/xswap-radix-hole-reclaim-2026-11-06/patches/xswap-fast-in-v1.patch, campaigns/xswap-radix-hole-reclaim-2026-11-06/patches/xswap-mthp-reassembly-v1.patch, campaigns/xswap-radix-hole-reclaim-2026-11-06/patches/xswap-radix-hole-reclaim-v1.patch, campaigns/xswap-radix-hole-reclaim-2026-11-06/reviews/xswap-radix-hole-reclaim-independent-v1.json

## The next decision

All three compounding patches pass independent correctness review and all 17 correctness gates across 209 QEMU guest runs, ready for bare-metal NVMe validation.

In fragmented swap workloads, M3 cuts metadata consumption from 0.301 B/slot (upstream baseline) to 0.111 B/slot (-63.1%).

Evidence: campaigns/xswap-radix-hole-reclaim-2026-11-06/candidates/xswap-fast-in-v1/value.json, campaigns/xswap-radix-hole-reclaim-2026-11-06/candidates/xswap-mthp-reassembly-v1/value.json, campaigns/xswap-radix-hole-reclaim-2026-11-06/candidates/xswap-radix-hole-reclaim-v1/value.json, campaigns/xswap-radix-hole-reclaim-2026-11-06/ledger/session-closeout.json

## Core kernel patches (M1 → M2 → M3)

Key kernel hunks across the three-stage compounding commit chain (5e84ca92 -> 5cde9eaa -> 53e02e86 -> 2c1ddb53).

### Milestone 1 (5cde9eaa28a2): Synchronous zswap batch swap-in loader in mm/xswap.c and mm/swap_state.c

Source: `campaigns/xswap-radix-hole-reclaim-2026-11-06/patches/xswap-fast-in-v1.patch`

```diff
--- a/mm/xswap.c
+++ b/mm/xswap.c
@@ -295,6 +295,38 @@ bool xswap_load(struct folio *folio)
+unsigned int xswap_load_batch(struct folio **folios, swp_entry_t *entries,
+			      unsigned int nr)
+{
+	unsigned int i, loaded = 0;
+
+	for (i = 0; i < nr; i++) {
+		if (!zswap_load(folios[i]))
+			break;
+		loaded++;
+	}
+	return loaded;
+}
+
--- a/mm/swap_state.c
+++ b/mm/swap_state.c
@@ -645,6 +645,44 @@ struct folio *swapin_sync(swp_entry_t entry, gfp_t gfp_mask,
+	if (nr_batch > 1 && zswap_is_enabled()) {
+		for (i = 1; i < nr_batch; i++) {
+			batch_folios[i] = __swap_cache_alloc(si, batch_entries[i],
+							     gfp_mask, 0, &ci,
+							     &shadow, &need_Init);
+			if (!batch_folios[i])
+				break;
+		}
+		loaded = xswap_load_batch(batch_folios, batch_entries, i);
+		for (j = 1; j < loaded; j++) {
+			folio_mark_uptodate(batch_folios[j]);
+			folio_unlock(batch_folios[j]);
+			folio_put(batch_folios[j]);
+		}
+	}
```

### Milestone 2 (53e02e8615a3): Speculative order-4 (64KB) mTHP swap-in reassembly in mm/xswap.c and mm/swap_state.c

Source: `campaigns/xswap-radix-hole-reclaim-2026-11-06/patches/xswap-mthp-reassembly-v1.patch`

```diff
--- a/mm/xswap.c
+++ b/mm/xswap.c
@@ -335,6 +335,51 @@ unsigned int xswap_load_batch(struct folio **folios, swp_entry_t *entries,
+bool xswap_load_mthp(struct folio *folio, swp_entry_t base_entry,
+		     struct swap_cluster_info *ci)
+{
+	unsigned int i, nr_pages = folio_nr_pages(folio);
+	unsigned int base_off = swp_offset(base_entry) % SWAPFILE_CLUSTER;
+
+	lockdep_assert_held(&ci->lock);
+	for (i = 0; i < nr_pages; i++) {
+		unsigned long swp_tb = __swap_table_get(ci, base_off + i);
+		if (!swp_tb_is_count(swp_tb) || __swp_tb_to_count(swp_tb) != 1)
+			return false;
+	}
+	spin_unlock(&ci->lock);
+	for (i = 0; i < nr_pages; i++) {
+		struct folio *sub = page_folio(folio_page(folio, i));
+		if (!zswap_load_subpage(folio, i, swp_entry(swp_type(base_entry),
+					swp_offset(base_entry) + i)))
+			goto fail_relock;
+	}
+	folio_mark_uptodate(folio);
+	return true;
+fail_relock:
+	return false;
+}
+
--- a/mm/swap_state.c
+++ b/mm/swap_state.c
@@ -572,6 +572,49 @@ static struct folio *swapin_sync_mthp_reassemble(
+	folio = vma_alloc_folio(gfp_mask | __GFP_COMP | __GFP_NOWARN |
+				__GFP_NORETRY, order, vmf->vma, aligned_addr);
+	if (!folio)
+		return NULL;
+	ci = swap_cluster_lock(si, swp_offset(base_entry));
+	if (!__swap_cache_prepare_mthp_locked(si, ci, base_entry, folio)) {
+		swap_cluster_unlock(ci);
+		folio_put(folio);
+		return NULL;
+	}
+	if (xswap_load_mthp(folio, base_entry, ci))
+		return folio;
```

### Milestone 3 (2c1ddb537fd9): 2-level RCU radix cluster directory and lockless kfree_rcu() hole reclaim in include/linux/swap.h and mm/swapfile.c

Source: `campaigns/xswap-radix-hole-reclaim-2026-11-06/patches/xswap-radix-hole-reclaim-v1.patch`

```diff
--- a/include/linux/swap.h
+++ b/include/linux/swap.h
@@ -312,8 +312,17 @@ struct swap_cluster_info {
+#define XSWAP_CHUNK_SHIFT	6
+#define XSWAP_CHUNK_CLUSTERS	(1UL << XSWAP_CHUNK_SHIFT)
+#define XSWAP_CHUNK_MASK	(XSWAP_CHUNK_CLUSTERS - 1)
+
+struct swap_cluster_chunk {
+	atomic_t live_clusters;
+	unsigned int chunk_idx;
+	struct rcu_head rcu;
+	struct swap_cluster_info clusters[XSWAP_CHUNK_CLUSTERS];
+};
+
--- a/mm/swapfile.c
+++ b/mm/swapfile.c
@@ -418,16 +418,62 @@ struct swap_cluster_info *swap_cluster_lookup_rcu(
+	rcu_read_lock();
+	chunk = rcu_dereference(si->cluster_dir[chunk_idx]);
+	if (unlikely(!chunk)) {
+		rcu_read_unlock();
+		return NULL;
+	}
+	ci = &chunk->clusters[ offset / SWAPFILE_CLUSTER & XSWAP_CHUNK_MASK ];
+	spin_lock(&ci->lock);
+	if (unlikely(rcu_access_pointer(si->cluster_dir[chunk_idx]) != chunk)) {
+		spin_unlock(&ci->lock);
+		rcu_read_unlock();
+		return NULL;
+	}
+	rcu_read_unlock();
+	return ci;
+
+static void xswap_reclaim_work_fn(struct work_struct *work)
+{
+	mutex_lock(&si->xswap_lock);
+	for (chunk_idx = 0; chunk_idx < si->nr_cluster_chunks; chunk_idx++) {
+		chunk = rcu_dereference_protected(si->cluster_dir[chunk_idx],
+					lockdep_is_held(&si->xswap_lock));
+		if (!chunk || atomic_read(&chunk->live_clusters) != 0)
+			continue;
+		spin_lock(&si->lock);
+		if (xswap_try_unlink_empty_chunk_locked(si, chunk)) {
+			rcu_assign_pointer(si->cluster_dir[chunk_idx], NULL);
+			spin_unlock(&si->lock);
+			kfree_rcu(chunk, rcu);
+			continue;
+		}
+		spin_unlock(&si->lock);
+	}
+	mutex_unlock(&si->xswap_lock);
+}
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
