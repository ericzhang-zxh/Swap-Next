# Isolating the compressed swap timing tool

**Observer repair verified.** Both kernels completed the compressed-swap diagnostic with exactly one verified decompression for every timed page. The shared library also passed the functional rerun.

## Results

The old timing tool saw two decoder returns for one timed access. With the tool's own memory pinned, the baseline and the shared-library kernel each completed the sequential and shuffled reads with full data checks.

The timing tool verified that its own mappings stayed locked and the target range stayed unlocked. Neither run lost or missed a probe. One run per kernel shows the measurement path works and leaves the speed difference unmeasured.

## Why time compressed swap

A memory page can be stored as a smaller compressed copy. Restoring it takes work, so the experiment measures how long the application waits.

The shared library moves compression and storage code behind one interface. The experiment tests whether existing behavior survives the change.

## Where compressed swap operates

An application reads a page that is no longer resident in working memory.

## What the timing observer sees

A return probe reports successful decompression for the benchmark process.

## Keep the timing tool resident

The original trace identified the process. It did not record a page address for either return. The repair keeps the tool's non-target mappings resident and leaves the test region available to swap.

## What remains to test

The full comparison needs repeated calibration plus matched runs for the compressed and physical paths. It needs more guest attempts than remain in the original budget.

Independent XSwap still needs its guest driver and physical-path validation. A platform review interrupted the driver work. The pressure-driven migration test starts after independent XSwap passes correctness.

<details>
<summary>Shared compression library source</summary>

Free compressed objects through the shared library

[Pinned patch](https://github.com/ericzhang-zxh/Swap-Next/blob/8da7561b69705d0f6738cf312a52bef94453d94f/campaigns/codex-compress-lib-r8-2026-11-11/patches/c1-shared-store-r8.patch)

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

- [campaigns/codex-compress-lib-r8-2026-11-11/candidates/c1-shared-store-r8/correctness.json](https://github.com/ericzhang-zxh/Swap-Next/blob/8da7561b69705d0f6738cf312a52bef94453d94f/campaigns/codex-compress-lib-r8-2026-11-11/candidates/c1-shared-store-r8/correctness.json)
- [campaigns/codex-compress-lib-r8-2026-11-11/ledger/ledger.json](https://github.com/ericzhang-zxh/Swap-Next/blob/8da7561b69705d0f6738cf312a52bef94453d94f/campaigns/codex-compress-lib-r8-2026-11-11/ledger/ledger.json)
- [campaigns/codex-compress-lib-r8-2026-11-11/patches/c1-shared-store-r8.patch](https://github.com/ericzhang-zxh/Swap-Next/blob/8da7561b69705d0f6738cf312a52bef94453d94f/campaigns/codex-compress-lib-r8-2026-11-11/patches/c1-shared-store-r8.patch)
- [campaigns/codex-compress-lib-r8-2026-11-11/protocol.json](https://github.com/ericzhang-zxh/Swap-Next/blob/8da7561b69705d0f6738cf312a52bef94453d94f/campaigns/codex-compress-lib-r8-2026-11-11/protocol.json)
- [campaigns/codex-compress-lib-r8-2026-11-11/report/observations.json](https://github.com/ericzhang-zxh/Swap-Next/blob/8da7561b69705d0f6738cf312a52bef94453d94f/campaigns/codex-compress-lib-r8-2026-11-11/report/observations.json)

</details>

[Interactive report](codex-compress-lib-r8-2026-11-11-2026-11-11/explainer.html)
