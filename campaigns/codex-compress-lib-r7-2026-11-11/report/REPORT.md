# Why the compressed swap timing run stopped

**Timing ambiguity reproduced.** The shared compression library passed its functional checks. The timing tool rejected the first read after it saw two successful decompressions in the same observation window.

## Results

The original kernel reproduced the timing failure in a valid virtual machine. Its first observation contained two successful return records for the same process and no missed probe.

The trace reader completed without truncation. The observer requires exactly one decode per timed page, so the workload stopped before collecting usable measurements. The trace does not identify the page address for either return.

## Why time compressed swap

A memory page can be stored as a smaller compressed copy. Restoring it takes work, so the experiment measures how long the application waits.

The shared library moves compression and storage code behind one interface. The experiment tests whether existing behavior survives the change.

## Where compressed swap operates

An application reads a page that is no longer resident in working memory.

## What the timing observer sees

A return probe reports successful decompression for the benchmark process.

## Shared compression and diagnostic capture

The candidate uses the shared library. The follow-up also records the original bytes when a timing observation is rejected.

## Isolate the timing tool

Keep the tool's non-target memory resident and prove that the target region is still eligible for swap. Use the same observer on both kernels before collecting any new comparison.

Independent XSwap still needs its guest driver and physical-route evidence. Pressure-driven migration depends on an independently verified XSwap frontend.

<details>
<summary>Shared compression library source</summary>

Free compressed objects through the shared library

[Pinned patch](https://github.com/ericzhang-zxh/Swap-Next/blob/78fc4bbc351d11872768b83b80956b8954bca73c/campaigns/codex-compress-lib-r7-2026-11-11/patches/c1-shared-store-r7.patch)

```diff
diff --git a/mm/zswap.c b/mm/zswap.c
index 789730c22..e5b93c7da 100644
--- a/mm/zswap.c
+++ b/mm/zswap.c
@@ -780,7 +693,7 @@ static void zswap_entry_free(struct zswap_entry *entry)
 
 	zswap_lru_del(entry);
 	if (!WARN_ON_ONCE(!pool)) {
-		zs_free(pool->zs_pool, entry->handle);
+		page_compress_free(pool->compress, entry->handle);
 		zswap_pool_put(pool);
 	}
 	if (entry->objcg) {
```

</details>

<details>
<summary>Exact evidence</summary>

[Public observations](observations.json) · [Native summary](summary.json)

- [campaigns/codex-compress-lib-r7-2026-11-11/ledger/ledger.json](https://github.com/ericzhang-zxh/Swap-Next/blob/78fc4bbc351d11872768b83b80956b8954bca73c/campaigns/codex-compress-lib-r7-2026-11-11/ledger/ledger.json)
- [campaigns/codex-compress-lib-r7-2026-11-11/patches/c1-shared-store-r7.patch](https://github.com/ericzhang-zxh/Swap-Next/blob/78fc4bbc351d11872768b83b80956b8954bca73c/campaigns/codex-compress-lib-r7-2026-11-11/patches/c1-shared-store-r7.patch)
- [campaigns/codex-compress-lib-r7-2026-11-11/protocol.json](https://github.com/ericzhang-zxh/Swap-Next/blob/78fc4bbc351d11872768b83b80956b8954bca73c/campaigns/codex-compress-lib-r7-2026-11-11/protocol.json)

</details>

[Interactive report](codex-compress-lib-r7-2026-11-11-2026-11-11/explainer.html)
