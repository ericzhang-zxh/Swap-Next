# xswap-swapin-2026-10-23

Status: 2 candidates screened out; none eligible for slow confirmation. No formal acceptance, promotion, or publication.

4 retained failed harness attempts preceded calibration; they are not candidate-bug findings.

Observed guest attempts: 46; integration passes: 42; completed failed: 4; running: 0; incomplete: 0; stopped: 0; effective KASAN passes: 9.

## Evaluations
| Action | Tier | Candidate | Status | Reason |
|---|---|---|---|---|
| calibrate | fast | None | CALIBRATED |  |
| evaluate | fast | xs-ra-phys-v1 | REGRESSION |  |
| evaluate | fast | xs-ra-zswap-v1 | REGRESSION |  |

## Metric ratios and failed guards
Fast is a screening result; slow is confirmation evidence. Few fast pairs do not establish a persistent causal regression. H1 has no compressed readahead path; observed zswap differences, including baseline random-tail outliers, are not credited as H1 mechanism improvements.
| Candidate | Tier | Pairs | Metric | Baseline/candidate | Latency change % | Noise % | Guard |
|---|---|---|---|---|---|---|---|
| xs-ra-phys-v1 | fast | 2 | swapin-disk.swapin_seq.mean_ns | 6.533107 | -84.69 | 4.48 | PASS |
| xs-ra-phys-v1 | fast | 2 | swapin-disk.swapin_seq.p99_ns | 1.113266 | -10.17 | 3.06 | PASS |
| xs-ra-phys-v1 | fast | 2 | swapin-disk.swapin_rand.mean_ns | 0.987356 | 1.28 | 3.0 | PASS |
| xs-ra-phys-v1 | fast | 2 | swapin-disk.swapin_rand.p99_ns | 0.904953 | 10.5 | 3.0 | FAIL |
| xs-ra-phys-v1 | fast | 2 | swapin-zswap.swapin_seq.mean_ns | 1.006231 | -0.62 | 3.0 | PASS |
| xs-ra-phys-v1 | fast | 2 | swapin-zswap.swapin_seq.p99_ns | 1.05638 | -5.34 | 7.73 | PASS |
| xs-ra-phys-v1 | fast | 2 | swapin-zswap.swapin_rand.mean_ns | 1.162207 | -13.96 | 3.0 | PASS |
| xs-ra-phys-v1 | fast | 2 | swapin-zswap.swapin_rand.p99_ns | 2.665868 | -62.49 | 10.88 | PASS |
| xs-ra-zswap-v1 | fast | 2 | swapin-disk.swapin_seq.mean_ns | 1.015766 | -1.55 | 4.48 | PASS |
| xs-ra-zswap-v1 | fast | 2 | swapin-disk.swapin_seq.p99_ns | 1.048207 | -4.6 | 3.06 | PASS |
| xs-ra-zswap-v1 | fast | 2 | swapin-disk.swapin_rand.mean_ns | 1.091175 | -8.36 | 3.0 | PASS |
| xs-ra-zswap-v1 | fast | 2 | swapin-disk.swapin_rand.p99_ns | 1.053169 | -5.05 | 3.0 | PASS |
| xs-ra-zswap-v1 | fast | 2 | swapin-zswap.swapin_seq.mean_ns | 1.004084 | -0.41 | 3.0 | PASS |
| xs-ra-zswap-v1 | fast | 2 | swapin-zswap.swapin_seq.p99_ns | 0.262609 | 280.79 | 7.73 | FAIL |
| xs-ra-zswap-v1 | fast | 2 | swapin-zswap.swapin_rand.mean_ns | 1.005972 | -0.59 | 3.0 | PASS |
| xs-ra-zswap-v1 | fast | 2 | swapin-zswap.swapin_rand.p99_ns | 1.006824 | -0.68 | 10.88 | PASS |

## Failed guards
- xs-ra-phys-v1 fast REGRESSION: swapin-disk.swapin_rand.p99_ns
- xs-ra-zswap-v1 fast REGRESSION: swapin-zswap.swapin_seq.p99_ns

## H2 compressed latency distribution
Inference: synchronous compressed prefetch concentrates decompression cost into fewer fault bursts. Source paths, readahead counters and the p50/p90 distribution support this interpretation; independent profiling has not established causality.
| Candidate | Pair | Arm | p50 us | p90 us | Mean us | p99 us |
|---|---|---|---|---|---|---|
| xs-ra-zswap-v1 | 0 | a | 13.509 | 13.932 | 11.683 | 25.374 |
| xs-ra-zswap-v1 | 0 | b | 0.528 | 82.369 | 11.633 | 97.538 |
| xs-ra-zswap-v1 | 1 | b | 0.528 | 82.68 | 11.629 | 98.27 |
| xs-ra-zswap-v1 | 1 | a | 13.535 | 13.941 | 11.674 | 26.051 |

## Mechanism counters
| Candidate/action | Tier | Pair | Case | Arm | swap_ra | swap_ra_hit | pswpin | zswpin |
|---|---|---|---|---|---|---|---|---|
| calibrate | fast | 0 | swapin-disk | a | 0 | 0 | 262140 | 0 |
| calibrate | fast | 0 | swapin-disk | b | 0 | 1 | 262167 | 0 |
| calibrate | fast | 0 | swapin-zswap | a | 0 | 0 | 0 | 262166 |
| calibrate | fast | 0 | swapin-zswap | b | 0 | 0 | 0 | 262160 |
| calibrate | fast | 1 | swapin-disk | b | 0 | 0 | 262155 | 0 |
| calibrate | fast | 1 | swapin-disk | a | 0 | 0 | 262152 | 0 |
| calibrate | fast | 1 | swapin-zswap | b | 0 | 0 | 0 | 262160 |
| calibrate | fast | 1 | swapin-zswap | a | 0 | 0 | 0 | 262167 |
| xs-ra-phys-v1 | fast | 0 | swapin-disk | a | 0 | 0 | 262170 | 0 |
| xs-ra-phys-v1 | fast | 0 | swapin-disk | b | 114943 | 114936 | 262176 | 0 |
| xs-ra-phys-v1 | fast | 0 | swapin-zswap | a | 0 | 0 | 0 | 262160 |
| xs-ra-phys-v1 | fast | 0 | swapin-zswap | b | 0 | 0 | 0 | 262160 |
| xs-ra-phys-v1 | fast | 1 | swapin-disk | b | 114832 | 114827 | 262152 | 0 |
| xs-ra-phys-v1 | fast | 1 | swapin-disk | a | 0 | 0 | 262163 | 0 |
| xs-ra-phys-v1 | fast | 1 | swapin-zswap | b | 0 | 0 | 0 | 262166 |
| xs-ra-phys-v1 | fast | 1 | swapin-zswap | a | 0 | 0 | 0 | 262160 |
| xs-ra-zswap-v1 | fast | 0 | swapin-disk | a | 0 | 0 | 262132 | 0 |
| xs-ra-zswap-v1 | fast | 0 | swapin-disk | b | 0 | 2 | 262146 | 0 |
| xs-ra-zswap-v1 | fast | 0 | swapin-zswap | a | 0 | 0 | 0 | 262166 |
| xs-ra-zswap-v1 | fast | 0 | swapin-zswap | b | 114780 | 114773 | 0 | 262170 |
| xs-ra-zswap-v1 | fast | 1 | swapin-disk | b | 0 | 2 | 262145 | 0 |
| xs-ra-zswap-v1 | fast | 1 | swapin-disk | a | 0 | 2 | 262146 | 0 |
| xs-ra-zswap-v1 | fast | 1 | swapin-zswap | b | 114736 | 114729 | 0 | 262166 |
| xs-ra-zswap-v1 | fast | 1 | swapin-zswap | a | 0 | 0 | 0 | 262163 |

## Xswap occupancy snapshots
| Candidate/action | Pair | Case | Arm | Phase | Mapped | Usage | Grows | Shrinks |
|---|---|---|---|---|---|---|---|---|
| calibrate | 0 | swapin-disk | a | swapin_start | 73 | 0 | 0 | 0 |
| calibrate | 0 | swapin-disk | a | swapin_end | 657 | 0 | 10 | 1 |
| calibrate | 0 | swapin-disk | b | swapin_start | 73 | 0 | 0 | 0 |
| calibrate | 0 | swapin-disk | b | swapin_end | 657 | 0 | 10 | 1 |
| calibrate | 0 | swapin-zswap | a | swapin_start | 73 | 0 | 0 | 0 |
| calibrate | 0 | swapin-zswap | a | swapin_end | 657 | 1 | 10 | 1 |
| calibrate | 0 | swapin-zswap | b | swapin_start | 73 | 0 | 0 | 0 |
| calibrate | 0 | swapin-zswap | b | swapin_end | 657 | 1 | 10 | 1 |
| calibrate | 1 | swapin-disk | b | swapin_start | 73 | 0 | 0 | 0 |
| calibrate | 1 | swapin-disk | b | swapin_end | 146 | 0 | 10 | 1 |
| calibrate | 1 | swapin-disk | a | swapin_start | 73 | 0 | 0 | 0 |
| calibrate | 1 | swapin-disk | a | swapin_end | 657 | 0 | 10 | 1 |
| calibrate | 1 | swapin-zswap | b | swapin_start | 73 | 0 | 0 | 0 |
| calibrate | 1 | swapin-zswap | b | swapin_end | 657 | 0 | 10 | 1 |
| calibrate | 1 | swapin-zswap | a | swapin_start | 73 | 0 | 0 | 0 |
| calibrate | 1 | swapin-zswap | a | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-phys-v1 | 0 | swapin-disk | a | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-phys-v1 | 0 | swapin-disk | a | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-phys-v1 | 0 | swapin-disk | b | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-phys-v1 | 0 | swapin-disk | b | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-phys-v1 | 0 | swapin-zswap | a | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-phys-v1 | 0 | swapin-zswap | a | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-phys-v1 | 0 | swapin-zswap | b | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-phys-v1 | 0 | swapin-zswap | b | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-phys-v1 | 1 | swapin-disk | b | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-phys-v1 | 1 | swapin-disk | b | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-phys-v1 | 1 | swapin-disk | a | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-phys-v1 | 1 | swapin-disk | a | swapin_end | 146 | 0 | 10 | 1 |
| xs-ra-phys-v1 | 1 | swapin-zswap | b | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-phys-v1 | 1 | swapin-zswap | b | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-phys-v1 | 1 | swapin-zswap | a | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-phys-v1 | 1 | swapin-zswap | a | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-zswap-v1 | 0 | swapin-disk | a | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-zswap-v1 | 0 | swapin-disk | a | swapin_end | 657 | 1 | 10 | 1 |
| xs-ra-zswap-v1 | 0 | swapin-disk | b | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-zswap-v1 | 0 | swapin-disk | b | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-zswap-v1 | 0 | swapin-zswap | a | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-zswap-v1 | 0 | swapin-zswap | a | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-zswap-v1 | 0 | swapin-zswap | b | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-zswap-v1 | 0 | swapin-zswap | b | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-zswap-v1 | 1 | swapin-disk | b | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-zswap-v1 | 1 | swapin-disk | b | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-zswap-v1 | 1 | swapin-disk | a | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-zswap-v1 | 1 | swapin-disk | a | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-zswap-v1 | 1 | swapin-zswap | b | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-zswap-v1 | 1 | swapin-zswap | b | swapin_end | 657 | 0 | 10 | 1 |
| xs-ra-zswap-v1 | 1 | swapin-zswap | a | swapin_start | 73 | 0 | 0 | 0 |
| xs-ra-zswap-v1 | 1 | swapin-zswap | a | swapin_end | 657 | 0 | 10 | 1 |

## Correctness and build evidence
Exact run gates, output-config sanitizer settings, result and serial hashes are preserved in summary.json. Debug names alone do not establish KASAN coverage.

## Sparse coverage
- results/xswap-swapin-2026-10-23/h1-sparse.json: no_new_diagnostics=True, full_tool_success=False. Baseline diagnostics remain a tool-coverage gap.
- results/xswap-swapin-2026-10-23/h2-sparse.json: no_new_diagnostics=True, full_tool_success=False. Baseline diagnostics remain a tool-coverage gap.

## Missing policy gates
- baseline: gcc_swap_off
- baseline: checkpatch
- baseline: allocation_failure
- baseline: io_failure
- baseline: memcg_limits
- baseline: large_folio
- baseline: kcsan
- xs-ra-phys-v1: gcc_swap_off
- xs-ra-phys-v1: allocation_failure
- xs-ra-phys-v1: io_failure
- xs-ra-phys-v1: memcg_limits
- xs-ra-phys-v1: large_folio
- xs-ra-phys-v1: kcsan
- xs-ra-zswap-v1: gcc_swap_off
- xs-ra-zswap-v1: allocation_failure
- xs-ra-zswap-v1: io_failure
- xs-ra-zswap-v1: memcg_limits
- xs-ra-zswap-v1: large_folio
- xs-ra-zswap-v1: kcsan

## Exact patches

### xs-ra-phys-v1
Source: evolve/control/state/xswap-swapin-2026-10-23/xs-ra-phys-v1/candidate.patch
```diff
diff --git a/mm/memory.c b/mm/memory.c
index 6fd925877..300515fb8 100644
--- a/mm/memory.c
+++ b/mm/memory.c
@@ -4995,8 +4995,12 @@ vm_fault_t do_swap_page(struct vm_fault *vmf)
 	if (folio)
 		swap_update_readahead(folio, vma, vmf->address);
 	if (!folio) {
-		/* Swapin bypasses readahead for SWP_SYNCHRONOUS_IO devices */
-		if (data_race(si->flags & SWP_SYNCHRONOUS_IO))
+		/*
+		 * Swapin bypasses readahead for SWP_SYNCHRONOUS_IO devices,
+		 * except an xswap slot written back to a physical backend.
+		 */
+		if (data_race(si->flags & SWP_SYNCHRONOUS_IO) &&
+		    !xswap_readahead_wanted(si, entry))
 			folio = swapin_sync(entry, GFP_HIGHUSER_MOVABLE,
 					    thp_swapin_suitable_orders(vmf) | BIT(0),
 					    vmf, NULL, 0);
diff --git a/mm/swap.h b/mm/swap.h
index b9e7c8a4c..fd9452dd2 100644
--- a/mm/swap.h
+++ b/mm/swap.h
@@ -397,6 +397,7 @@ struct folio *swap_cluster_readahead(swp_entry_t entry, gfp_t flag,
 		struct mempolicy *mpol, pgoff_t ilx);
 struct folio *swapin_readahead(swp_entry_t entry, gfp_t flag,
 		struct vm_fault *vmf);
+bool xswap_readahead_wanted(struct swap_info_struct *si, swp_entry_t entry);
 struct folio *swapin_sync(swp_entry_t entry, gfp_t flag, unsigned long orders,
 			   struct vm_fault *vmf, struct mempolicy *mpol, pgoff_t ilx);
 void swap_update_readahead(struct folio *folio, struct vm_area_struct *vma,
@@ -477,6 +478,12 @@ static inline struct folio *swapin_readahead(swp_entry_t swp, gfp_t gfp_mask,
 	return NULL;
 }
 
+static inline bool xswap_readahead_wanted(struct swap_info_struct *si,
+					  swp_entry_t entry)
+{
+	return false;
+}
+
 static inline struct folio *swapin_sync(
 	swp_entry_t entry, gfp_t flag, unsigned long orders,
 	struct vm_fault *vmf, struct mempolicy *mpol, pgoff_t ilx)
diff --git a/mm/swap_state.c b/mm/swap_state.c
index 7ac1808ae..99672718b 100644
--- a/mm/swap_state.c
+++ b/mm/swap_state.c
@@ -753,6 +753,34 @@ static struct folio *swap_cache_read_folio(struct swap_io_ctx *ctx,
 	return folio;
 }
 
+/**
+ * xswap_readahead_wanted - Check whether an xswap slot has a physical backend.
+ * @si: the swap device of @entry.
+ * @entry: the swap entry, which need not be pinned.
+ *
+ * This is a readahead hint, not a pin on the slot or its backend. The swap
+ * cache allocation and read paths must revalidate the entry after this
+ * returns. No cluster pointer or physical entry escapes the lock.
+ *
+ * Context: Caller must protect @si with a reference count or locks.
+ * Return: true if an xswap slot has a physical backend, false otherwise.
+ */
+bool xswap_readahead_wanted(struct swap_info_struct *si, swp_entry_t entry)
+{
+	struct swap_cluster_info *ci;
+	bool backed;
+
+	if (!(si->flags & SWP_XSWAP))
+		return false;
+	ci = swap_cluster_lock_unpinned(si, swp_offset(entry));
+	if (!ci)
+		return false;
+	backed = xswap_slot_backend(ci, swp_cluster_offset(entry)).val;
+	swap_cluster_unlock(ci);
+
+	return backed;
+}
+
 /**
  * swapin_sync - swap-in one or multiple entries skipping readahead.
  * @entry: swap entry indicating the target slot
@@ -920,8 +948,8 @@ struct folio *swap_cluster_readahead(swp_entry_t entry, gfp_t gfp_mask,
 	struct blk_plug plug;
 	swp_entry_t ra_entry;
 
-	/* xswap entries live only in zswap; readahead does not help. */
-	if (si->flags & SWP_XSWAP)
+	/* Keep compressed xswap targets on the single-folio path. */
+	if ((si->flags & SWP_XSWAP) && !xswap_readahead_wanted(si, entry))
 		goto skip;
 
 	mask = swapin_nr_pages(offset) - 1;
@@ -940,6 +968,9 @@ struct folio *swap_cluster_readahead(swp_entry_t entry, gfp_t gfp_mask,
 	for (offset = start_offset; offset <= end_offset ; offset++) {
 		/* Ok, do the async read-ahead now */
 		ra_entry = swp_entry(swp_type(entry), offset);
+		if ((si->flags & SWP_XSWAP) && offset != entry_offset &&
+		    !xswap_readahead_wanted(si, ra_entry))
+			continue;
 		folio = swap_cache_read_folio(&ctx, ra_entry, gfp_mask, mpol,
 				ilx, offset != entry_offset);
 		if (!folio)
@@ -1009,7 +1040,6 @@ static int swap_vma_ra_win(struct vm_fault *vmf, unsigned long *start,
 static struct folio *swap_vma_readahead(swp_entry_t targ_entry, gfp_t gfp_mask,
 		struct mempolicy *mpol, pgoff_t targ_ilx, struct vm_fault *vmf)
 {
-	struct swap_info_struct *si = __swap_entry_to_info(targ_entry);
 	struct swap_io_ctx ctx = {};
 	struct blk_plug plug;
 	struct folio *folio;
@@ -1018,10 +1048,6 @@ static struct folio *swap_vma_readahead(swp_entry_t targ_entry, gfp_t gfp_mask,
 	unsigned long start, end, addr;
 	pgoff_t ilx = targ_ilx;
 
-	/* xswap entries live only in zswap; readahead does not help. */
-	if (si->flags & SWP_XSWAP)
-		goto skip;
-
 	win = swap_vma_ra_win(vmf, &start, &end);
 	if (win == 1)
 		goto skip;
@@ -1054,8 +1080,13 @@ static struct folio *swap_vma_readahead(swp_entry_t targ_entry, gfp_t gfp_mask,
 			if (IS_ERR_OR_NULL(si))
 				continue;
 		}
-		folio = swap_cache_read_folio(&ctx, entry, gfp_mask, mpol, ilx,
-					      addr != vmf->address);
+		if (addr != vmf->address &&
+		    (__swap_entry_to_info(entry)->flags & SWP_XSWAP) &&
+		    !xswap_readahead_wanted(__swap_entry_to_info(entry), entry))
+			folio = NULL;
+		else
+			folio = swap_cache_read_folio(&ctx, entry, gfp_mask, mpol,
+						      ilx, addr != vmf->address);
 		if (si)
 			put_swap_device(si);
 		if (!folio)

```

### xs-ra-zswap-v1
Source: evolve/control/state/xswap-swapin-2026-10-23/xs-ra-zswap-v1/candidate.patch
```diff
diff --git a/mm/memory.c b/mm/memory.c
index 6fd925877..b24a1be83 100644
--- a/mm/memory.c
+++ b/mm/memory.c
@@ -4995,8 +4995,9 @@ vm_fault_t do_swap_page(struct vm_fault *vmf)
 	if (folio)
 		swap_update_readahead(folio, vma, vmf->address);
 	if (!folio) {
-		/* Swapin bypasses readahead for SWP_SYNCHRONOUS_IO devices */
-		if (data_race(si->flags & SWP_SYNCHRONOUS_IO))
+		/* Prefetch compressed xswap neighbors into the swap cache. */
+		if (data_race(si->flags & SWP_SYNCHRONOUS_IO) &&
+		    !((si->flags & SWP_XSWAP) && zswap_entry_present(entry)))
 			folio = swapin_sync(entry, GFP_HIGHUSER_MOVABLE,
 					    thp_swapin_suitable_orders(vmf) | BIT(0),
 					    vmf, NULL, 0);
diff --git a/mm/swap.h b/mm/swap.h
index b9e7c8a4c..fa84319a1 100644
--- a/mm/swap.h
+++ b/mm/swap.h
@@ -530,6 +530,15 @@ static inline void __swap_cache_replace_folio(struct swap_cluster_info *ci,
 }
 #endif /* CONFIG_SWAP */
 
+#ifdef CONFIG_ZSWAP
+bool zswap_entry_present(swp_entry_t entry);
+#else
+static inline bool zswap_entry_present(swp_entry_t entry)
+{
+	return false;
+}
+#endif
+
 extern const struct swap_ops swap_bdev_ops;
 
 int shmem_writeout(struct swap_io_ctx *ctx, struct folio *folio,
diff --git a/mm/swap_state.c b/mm/swap_state.c
index 7ac1808ae..a3787f6ed 100644
--- a/mm/swap_state.c
+++ b/mm/swap_state.c
@@ -920,8 +920,8 @@ struct folio *swap_cluster_readahead(swp_entry_t entry, gfp_t gfp_mask,
 	struct blk_plug plug;
 	swp_entry_t ra_entry;
 
-	/* xswap entries live only in zswap; readahead does not help. */
-	if (si->flags & SWP_XSWAP)
+	/* Only compressed xswap targets initiate speculative reads. */
+	if ((si->flags & SWP_XSWAP) && !zswap_entry_present(entry))
 		goto skip;
 
 	mask = swapin_nr_pages(offset) - 1;
@@ -940,6 +940,9 @@ struct folio *swap_cluster_readahead(swp_entry_t entry, gfp_t gfp_mask,
 	for (offset = start_offset; offset <= end_offset ; offset++) {
 		/* Ok, do the async read-ahead now */
 		ra_entry = swp_entry(swp_type(entry), offset);
+		if ((si->flags & SWP_XSWAP) && offset != entry_offset &&
+		    !zswap_entry_present(ra_entry))
+			continue;
 		folio = swap_cache_read_folio(&ctx, ra_entry, gfp_mask, mpol,
 				ilx, offset != entry_offset);
 		if (!folio)
@@ -1018,8 +1021,8 @@ static struct folio *swap_vma_readahead(swp_entry_t targ_entry, gfp_t gfp_mask,
 	unsigned long start, end, addr;
 	pgoff_t ilx = targ_ilx;
 
-	/* xswap entries live only in zswap; readahead does not help. */
-	if (si->flags & SWP_XSWAP)
+	/* Only compressed xswap targets initiate speculative reads. */
+	if ((si->flags & SWP_XSWAP) && !zswap_entry_present(targ_entry))
 		goto skip;
 
 	win = swap_vma_ra_win(vmf, &start, &end);
@@ -1054,8 +1057,13 @@ static struct folio *swap_vma_readahead(swp_entry_t targ_entry, gfp_t gfp_mask,
 			if (IS_ERR_OR_NULL(si))
 				continue;
 		}
-		folio = swap_cache_read_folio(&ctx, entry, gfp_mask, mpol, ilx,
-					      addr != vmf->address);
+		if (addr != vmf->address &&
+		    (__swap_entry_to_info(entry)->flags & SWP_XSWAP) &&
+		    !zswap_entry_present(entry))
+			folio = NULL;
+		else
+			folio = swap_cache_read_folio(&ctx, entry, gfp_mask, mpol,
+						      ilx, addr != vmf->address);
 		if (si)
 			put_swap_device(si);
 		if (!folio)
diff --git a/mm/zswap.c b/mm/zswap.c
index 789730c22..fc92e00af 100644
--- a/mm/zswap.c
+++ b/mm/zswap.c
@@ -1632,6 +1632,26 @@ bool zswap_store(struct folio *folio, bool may_enter_fs)
 	return ret;
 }
 
+/**
+ * zswap_entry_present - Check whether a slot currently has a zswap entry.
+ * @entry: valid swap entry to query, which need not be pinned.
+ *
+ * This is only a readahead hint. A concurrent store or invalidation can
+ * change the result, so the read path must resolve residency again after
+ * acquiring a locked swap-cache folio. Never dereference the entry returned
+ * by the XArray lookup here: only the tree lifetime is protected.
+ *
+ * Context: Caller must hold a reference to the swap device.
+ * Return: true if the slot has a zswap entry at the time of the lookup.
+ */
+bool zswap_entry_present(swp_entry_t entry)
+{
+	if (zswap_never_enabled())
+		return false;
+
+	return xa_load(swap_zswap_tree(entry), swp_offset(entry));
+}
+
 /**
  * zswap_is_present() - is any slot in [entry, entry + nr) in zswap?
  * @entry: base swap entry of the range

```

## Next hypotheses
- H1 adaptive readahead window with a tail guard: Reject a new candidate if random p99 exceeds its calibrated envelope.
- H2 bound synchronous decompression work: Reject unbounded prefetch or added demand-fault latency.
- Further validation only for a new candidate: Require fresh correctness evidence and a fast pass before slow confirmation.

## Limitations
- No processes remain active in the extracted campaign ledger.
- Retained failed harness attempts are not classified as candidate kernel defects.
- Gate inventory is conservative and may require manual matching of static reports.
- No formal acceptance, promotion, or publication.
