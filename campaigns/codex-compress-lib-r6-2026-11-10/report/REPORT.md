# Sharing memory-compression code: functional checks passed, performance unmeasured

**Functional checks passed; performance unmeasured.** The shared compression library passed its required functional checks. A failure in the timing setup left its effect on speed unknown.

## Why make compression reusable?

Linux can save working memory (RAM) by compressing inactive application data. ZSwap is its existing compressed-memory cache; XSwap is this project's alternative swap design. XSwap currently relies on ZSwap for compression.

The goal is to let both systems use the same compression code. Later work would let XSwap operate independently and move stored data to disk when RAM is tight.

<details>
<summary>Sources for this explanation</summary>

- [campaigns/codex-compress-lib-r6-2026-11-10/research.json](https://github.com/ericzhang-zxh/Swap-Next/blob/2c026d27660f6427da9b2e7019d148b805000e4a/campaigns/codex-compress-lib-r6-2026-11-10/research.json)
- [campaigns/codex-compress-lib-r6-2026-11-10/ledger/session-closeout.json](https://github.com/ericzhang-zxh/Swap-Next/blob/2c026d27660f6427da9b2e7019d148b805000e4a/campaigns/codex-compress-lib-r6-2026-11-10/ledger/session-closeout.json)

</details>

## 1. The system: keep application data available

A memory page is a fixed-size block of application data. When an inactive page is removed from active RAM, its contents must remain available in compressed RAM or on disk, ready to restore when needed.

This experiment changes the compression code inside RAM. Moving stored data from RAM to disk under memory pressure is a later stage.

<details>
<summary>Sources for this explanation</summary>

- [campaigns/codex-compress-lib-r6-2026-11-10/research.json](https://github.com/ericzhang-zxh/Swap-Next/blob/2c026d27660f6427da9b2e7019d148b805000e4a/campaigns/codex-compress-lib-r6-2026-11-10/research.json)
- [campaigns/codex-compress-lib-r6-2026-11-10/patches/c1-shared-store-r6.patch](https://github.com/ericzhang-zxh/Swap-Next/blob/2c026d27660f6427da9b2e7019d148b805000e4a/campaigns/codex-compress-lib-r6-2026-11-10/patches/c1-shared-store-r6.patch)

</details>

## 2. The boundary: decisions versus compression

ZSwap decides which data to keep, tracks where it is stored and accounts for its memory use. The new library compresses, stores, restores and frees that data. XSwap still reaches the library through ZSwap at this stage.

ZSwap remains responsible for keeping stored data alive while another operation uses it. The library does the compression and storage work without taking over those decisions.

<details>
<summary>Sources for this explanation</summary>

- [campaigns/codex-compress-lib-r6-2026-11-10/patches/c1-shared-store-r6.patch](https://github.com/ericzhang-zxh/Swap-Next/blob/2c026d27660f6427da9b2e7019d148b805000e4a/campaigns/codex-compress-lib-r6-2026-11-10/patches/c1-shared-store-r6.patch)
- [campaigns/codex-compress-lib-r6-2026-11-10/reviews/k2-c1-shared-store-r6-7d5a3cf.json](https://github.com/ericzhang-zxh/Swap-Next/blob/2c026d27660f6427da9b2e7019d148b805000e4a/campaigns/codex-compress-lib-r6-2026-11-10/reviews/k2-c1-shared-store-r6-7d5a3cf.json)

</details>

## 3. The change: extract one reusable library

Before the change, compression and storage code lived inside ZSwap. After the change, ZSwap calls a shared library named page_compress. The stored data format and the rules for tracking and freeing it stay the same.

Benefit: future callers can reuse one implementation. Cost: another interface to maintain and another allocation for each storage pool, the container for compressed data. The actual memory overhead and effect on speed remain unmeasured.

<details>
<summary>Sources for this explanation</summary>

- [campaigns/codex-compress-lib-r6-2026-11-10/patches/c1-shared-store-r6.patch](https://github.com/ericzhang-zxh/Swap-Next/blob/2c026d27660f6427da9b2e7019d148b805000e4a/campaigns/codex-compress-lib-r6-2026-11-10/patches/c1-shared-store-r6.patch)
- [campaigns/codex-compress-lib-r6-2026-11-10/reviews/k2-c1-shared-store-r6-7d5a3cf.json](https://github.com/ericzhang-zxh/Swap-Next/blob/2c026d27660f6427da9b2e7019d148b805000e4a/campaigns/codex-compress-lib-r6-2026-11-10/reviews/k2-c1-shared-store-r6-7d5a3cf.json)

</details>

## Results: function checked, speed still unknown

Functional checks passed, but the speed comparison could not begin. In the original, unchanged kernel, the timing tool could not confirm that the measured reads had successfully decompressed stored pages.

It therefore produced no complete valid timing sample. The cause is still unknown. A later diagnostic attempt was reserved but never launched before its time window expired. There is no measured speedup or slowdown for the library change.

## Next: finish measurement and independent XSwap support

Keep the library as a development candidate. First make the timing setup reliable enough to compare the original and modified kernels. Separately, finish the test support needed for XSwap to use the library with ZSwap disabled.

Reject the next design if it corrupts data, miscounts memory or frees data still in use. Any speed claim requires repeatable measurements of both versions. Independent XSwap and pressure-driven disk migration have not run.

<details>
<summary>Sources for this explanation</summary>

- [campaigns/codex-compress-lib-r6-2026-11-10/research.json](https://github.com/ericzhang-zxh/Swap-Next/blob/2c026d27660f6427da9b2e7019d148b805000e4a/campaigns/codex-compress-lib-r6-2026-11-10/research.json)
- [campaigns/codex-compress-lib-r6-2026-11-10/ledger/session-closeout.json](https://github.com/ericzhang-zxh/Swap-Next/blob/2c026d27660f6427da9b2e7019d148b805000e4a/campaigns/codex-compress-lib-r6-2026-11-10/ledger/session-closeout.json)

</details>

<details>
<summary>Implementation details: shared compression library</summary>

The following source excerpts show the tested library extraction. All experiment continuations used this same kernel change.

### The caller keeps responsibility for tracking and freeing stored data

Source: `campaigns/codex-compress-lib-r6-2026-11-10/patches/c1-shared-store-r6.patch`

```diff
--- /dev/null
+++ b/include/linux/page_compress.h
@@ -0,0 +8,43 @@
+struct folio;
+struct page_compress_pool;
+
+enum page_compress_failure {
+	PAGE_COMPRESS_NONE,
+	PAGE_COMPRESS_CODEC,
+	PAGE_COMPRESS_ALLOC,
+};
+
+struct page_compress_result {
+	unsigned long handle;
+	unsigned int length;
+	enum page_compress_failure failure;
+};
+
+/*
+ * Pools own their codec contexts and object storage, but no frontend references.
+ * The caller pins the pool and handle across each operation, and drains all
+ * handles and users before destroy. Creation requires initialized crypto.
+ */
+struct page_compress_pool *page_compress_create(const char *codec,
+						const char *name);
+void page_compress_destroy(struct page_compress_pool *pool);
+/* The returned name remains valid while the caller pins the pool. */
+const char *page_compress_codec(struct page_compress_pool *pool);
+
+/*
+ * Store/load operate on one base page and may sleep for codec completion even
+ * with a nonblocking allocation mask. A successful store transfers one handle;
+ * a failed store leaves handle/length zero. PAGE_SIZE length denotes raw data.
+ * Load does not consume the handle, including on error. The caller owns folio
+ * locking, index publication, accounting and the decision to store raw data.
+ */
+int page_compress_store(struct page_compress_pool *pool, struct folio *folio,
+			long index, gfp_t gfp, int nid,
+			struct page_compress_result *result);
+int page_compress_store_raw(struct page_compress_pool *pool, struct folio *folio,
+			    long index, gfp_t gfp, int nid,
+			    struct page_compress_result *result);
+int page_compress_load(struct page_compress_pool *pool, unsigned long handle,
+		       unsigned int length, struct folio *folio, long index);
+void page_compress_free(struct page_compress_pool *pool, unsigned long handle);
+unsigned long page_compress_backing_pages(struct page_compress_pool *pool);
```

### The library compresses a page and returns its storage reference

Source: `campaigns/codex-compress-lib-r6-2026-11-10/patches/c1-shared-store-r6.patch`

```diff
--- /dev/null
+++ b/mm/page_compress.c
@@ -0,0 +257,50 @@
+int page_compress_store(struct page_compress_pool *pool, struct folio *folio,
+			long index, gfp_t gfp, int nid,
+			struct page_compress_result *result)
+{
+	struct page_compress_ctx *ctx;
+	struct scatterlist input, output;
+	unsigned int dlen;
+	unsigned long handle;
+	u8 *dst;
+	int ret;
+
+	*result = (struct page_compress_result) {
+		.failure = PAGE_COMPRESS_CODEC,
+	};
+	if (index < 0 || index >= folio_nr_pages(folio))
+		return -EINVAL;
+
+	ctx = raw_cpu_ptr(pool->ctx);
+	mutex_lock(&ctx->mutex);
+
+	dst = ctx->buffer;
+	sg_init_table(&input, 1);
+	sg_set_folio(&input, folio, PAGE_SIZE, index * PAGE_SIZE);
+	sg_init_one(&output, dst, PAGE_SIZE);
+	acomp_request_set_params(ctx->req, &input, &output, PAGE_SIZE, PAGE_SIZE);
+
+	/* The frontend is synchronous even when the codec completes async. */
+	ret = crypto_wait_req(crypto_acomp_compress(ctx->req), &ctx->wait);
+	dlen = ctx->req->dlen;
+	if (ret || !dlen || dlen >= PAGE_SIZE) {
+		ret = ret ? ret : -EINVAL;
+		goto unlock;
+	}
+
+	handle = pc_object_alloc(pool->zs_pool, dlen, gfp, nid);
+	if (IS_ERR_VALUE(handle)) {
+		result->failure = PAGE_COMPRESS_ALLOC;
+		ret = PTR_ERR((void *)handle);
+		goto unlock;
+	}
+
+	zs_obj_write(pool->zs_pool, handle, dst, dlen);
+	result->handle = handle;
+	result->length = dlen;
+	result->failure = PAGE_COMPRESS_NONE;
+	ret = 0;
+unlock:
+	mutex_unlock(&ctx->mutex);
+	return ret;
+}
```

### ZSwap delegates compression storage while preserving its existing lifetime rules

Source: `campaigns/codex-compress-lib-r6-2026-11-10/patches/c1-shared-store-r6.patch`

```diff
--- a/mm/zswap.c
+++ b/mm/zswap.c
@@ -152,13 +140,10 @@ struct crypto_acomp_ctx {
  * needs to be verified that it's still valid in the tree.
  */
 struct zswap_pool {
-	struct zs_pool *zs_pool;
-	struct crypto_acomp_ctx __percpu *acomp_ctx;
+	struct page_compress_pool *compress;
 	struct percpu_ref ref;
 	struct rcu_work release_rwork;
-	struct hlist_node node;
 	u8 idx;
-	char tfm_name[CRYPTO_MAX_ALG_NAME];
 };
 
 /*
@@ -309,33 +266,9 @@ static struct zswap_pool *zswap_pool_create(char *compressor)
 
 	/* unique name for each pool specifically required by zsmalloc */
 	snprintf(name, 38, "zswap%x", atomic_inc_return(&zswap_pools_count));
-	pool->zs_pool = zs_create_pool(name);
-	if (!pool->zs_pool)
-		goto error;
-
-	strscpy(pool->tfm_name, compressor, sizeof(pool->tfm_name));
-
-	/* Many things rely on the zero-initialization. */
-	pool->acomp_ctx = alloc_percpu_gfp(*pool->acomp_ctx,
-					   GFP_KERNEL | __GFP_ZERO);
-	if (!pool->acomp_ctx) {
-		pr_err("percpu alloc failed\n");
-		goto error;
-	}
-
-	/*
-	 * This is serialized against CPU hotplug operations. Hence, cores
-	 * cannot be offlined until this finishes.
-	 */
-	ret = cpuhp_state_add_instance(CPUHP_MM_ZSWP_POOL_PREPARE,
-				       &pool->node);
-
-	/*
-	 * cpuhp_state_add_instance() will not cleanup on failure since
-	 * we don't register a hotunplug callback.
-	 */
-	if (ret)
-		goto cpuhp_add_fail;
+	pool->compress = page_compress_create(compressor, name);
+	if (IS_ERR(pool->compress))
+		goto free_pool;
 
 	/* being the current pool takes 1 ref; this func expects the
 	 * caller to always add the new pool as the current pool
@@ -343,7 +276,7 @@ static struct zswap_pool *zswap_pool_create(char *compressor)
 	ret = percpu_ref_init(&pool->ref, __zswap_pool_empty,
 			      PERCPU_REF_ALLOW_REINIT, GFP_KERNEL);
 	if (ret)
-		goto ref_fail;
+		goto destroy_compress;
 
 	/*
 	 * Publish only after the pool is fully built, so lockless walkers
```

</details>

<details>
<summary>Exact outcomes, functional coverage and resources</summary>

Native verdict: `inconclusive`. It refers to the unfinished performance comparison.

| Evaluation | Candidate | Tier | Result |
| --- | --- | --- | --- |
| 2324006c3711482a98691746b692d184 |  | correctness | BUILD_VERIFIED |
| 6d4ef0c65f504b6a87e4bcf663cc9522 |  | correctness | BUILD_VERIFIED |
| 9e23c77a29e749879c3c255185338ade | c1-shared-store-r6 | correctness | BUILD_VERIFIED |
| 85c9b2126f5940ce853bfb3bb3c3a0cd | c1-shared-store-r6 | correctness | BUILD_VERIFIED |
| 98544bcda7ae44dbb3dead2f8ec7d1a6 | c1-shared-store-r6 | correctness | BUILD_VERIFIED |
| e7413abe7952461e8c572b9692e69060 | c1-shared-store-r6 | correctness | BUILD_VERIFIED |
| 31d21ea9600f48e5939a769a3a2b8c6d | c1-shared-store-r6 | correctness | BUILD_VERIFIED |
| 0631d47b8af9402994267c46b437910d | c1-shared-store-r6 | correctness | BUILD_VERIFIED |
| 4d19e06a70894f36ac710efe3af32b81 | c1-shared-store-r6 | correctness | BUILD_VERIFIED |
| 5225803012fd4c7c81fbebcbd5f791f6 | c1-shared-store-r6 | correctness | BUILD_VERIFIED |

| Case | Configuration | Gate result | Valid |
| --- | --- | --- | --- |
| b-common | c1-common | all pass | true |
| b-legacy | c1-legacy | all pass | true |
| c-common | c1-common | all pass | true |
| c-compressed | c1-common | all pass | true |
| c-debug | c1-debug-v2 | all pass | true |
| c-legacy | c1-legacy | all pass | true |
| c-numa | c1-debug-v2 | all pass | true |
| c-race | c1-kcsan | all pass | true |

| Contract | Counted | Launched | Builds |
| --- | --- | --- | --- |
| codex-compress-lib-2026-11-10 | 3 | 3 | 3 |
| codex-compress-lib-r2-2026-11-10 | 2 | 2 | 1 |
| codex-compress-lib-r3-2026-11-10 | 3 | 3 | 0 |
| codex-compress-lib-r4-2026-11-10 | 2 | 2 | 0 |
| codex-compress-lib-r5-2026-11-10 | 9 | 9 | 5 |
| codex-compress-lib-r6-2026-11-10 | 1 | 0 | 0 |

[Public observations and exact hashes](observations.json)

</details>

## Limitations

Functional checks cover the retained source, kernel configurations and test image. They support continuing development; performance and real-world memory overhead remain unmeasured. The library remains an experimental candidate, with no code promotion or change to the reference kernel.

Independent XSwap test support is incomplete. An automated platform content-safety review interrupted its test-driver worker; the exact refused operation was not supplied. The partial driver was retained and the blocked operation was not retried. Independent XSwap and pressure-driven movement to disk have not run.

Earlier failed attempts remain in the resource totals. The final family report also counts the diagnostic reservation that never launched. Replaying archived results checks their interpretation; it adds no new experiment.

[Interactive explanation](codex-compress-lib-r6-2026-11-10-2026-11-11/explainer.html)
