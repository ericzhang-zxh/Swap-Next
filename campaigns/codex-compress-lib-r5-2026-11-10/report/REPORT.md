# Shared compression library: correctness passed, timing unresolved

**inconclusive** — The full correctness matrix passed. The first baseline timing guest failed decode observation, leaving performance unmeasured.

## Separate reusable mechanism from frontend policy

The experiment extracts codec contexts and compressed-object storage from ZSwap. Existing policy, indexes, accounting and lifetime ownership stay with the frontend. This is the first step toward independent XSwap and later tier migration.

The full correctness matrix passed. The first baseline timing guest failed decode observation, leaving performance unmeasured.

R5 collected eight fresh correctness guests and two disabled-configuration builds before timing. All required correctness rows passed; its subsequent baseline measurement failed.

Evidence: campaigns/codex-compress-lib-r5-2026-11-10/research.json, campaigns/codex-compress-lib-r5-2026-11-10/ledger/session-closeout.json

## 1. Whole system: restore the application page

An application needs its full page in physical RAM. Stored contents may be compressed inside RAM or reside on a backing device. Compression trades CPU work for less storage traffic.

The candidate changes the compressed-storage implementation. The existing frontend still decides admission, accounting and writeback. No new RAM-to-disk migration policy is implemented here.

Evidence: campaigns/codex-compress-lib-r5-2026-11-10/research.json, campaigns/codex-compress-lib-r5-2026-11-10/patches/c1-shared-store-r5.patch

## 2. Subsystem: policy keeps the object identity

ZSwap retains the entry index, memory-group charge, ordering and lifetime pins. A shared page library owns per-CPU codec contexts, scratch buffers and compressed-object storage.

The unchanged ownership boundary passed exact-source review. R5 subsequently passed complete required correctness, including NUMA placement, guest CPU hotplug, legacy behavior and accounting.

Evidence: campaigns/codex-compress-lib-r5-2026-11-10/patches/c1-shared-store-r5.patch, campaigns/codex-compress-lib-r5-2026-11-10/reviews/k2-c1-shared-store-r5-7d5a3cf.json

## 3. Concrete change: one object engine, the same frontend owner

Before extraction, ZSwap owns both policy and the codec/object engine. After extraction, the library returns a handle and length while ZSwap keeps publication, charges, LRU and references. Each stored object retains its original representation.

The review found no per-object wrapper or context-size increase. Extraction adds a pool allocation and a small requested pool-size increase; allocator rounding is unmeasured. New API and test obligations remain.

Evidence: campaigns/codex-compress-lib-r5-2026-11-10/patches/c1-shared-store-r5.patch, campaigns/codex-compress-lib-r5-2026-11-10/reviews/k2-c1-shared-store-r5-7d5a3cf.json

## Proceed to independent XSwap with fresh measurement evidence

Keep original A as the comparison anchor. C2 must demonstrate actual compressed objects, decoder calls, generic objcg charges and balanced teardown with ZSWAP disabled. Its prospective observer isolation is applied to both arms and needs fresh calibration.

Source identities and saved correctness have high confidence. The timing cause remains unresolved: R6 collected no trace. No performance winner, baseline advancement or code promotion exists. C2/C3 execution still requires its own gates.

Evidence: campaigns/codex-compress-lib-r5-2026-11-10/research.json, campaigns/codex-compress-lib-r5-2026-11-10/ledger/session-closeout.json

## Core shared-library patches

These hunks belong to the unchanged K1 source used throughout C1. R5 supplies complete correctness; R6 adds no runtime sample.

### Same K1: the API keeps publication, accounting and handle lifetime with its caller

Source: `campaigns/codex-compress-lib-r5-2026-11-10/patches/c1-shared-store-r5.patch`

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

### Same K1: the library compresses and allocates before returning a usable handle

Source: `campaigns/codex-compress-lib-r5-2026-11-10/patches/c1-shared-store-r5.patch`

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

### Same K1: frontend pool creation delegates the engine and preserves its reference lifetime

Source: `campaigns/codex-compress-lib-r5-2026-11-10/patches/c1-shared-store-r5.patch`

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

## Outcomes

| Evaluation | Candidate | Tier | Result |
| --- | --- | --- | --- |
| 07bd9dd43a244a7590f9ca7ea1b8fc77 |  | correctness | BUILD_VERIFIED |
| adf0fccb7e8c4a0dbedc7d7d99af2760 | c1-shared-store-r5 | correctness | BUILD_VERIFIED |
| 457baa414e03478ead7089412884a4fb | c1-shared-store-r5 | correctness | BUILD_VERIFIED |
| 4977d4969cfc4195aa78d8c0f83f3cd4 |  | correctness | BUILD_VERIFIED |
| 96a631933b224dd98e46e3d0ef2d2a39 | c1-shared-store-r5 | correctness | BUILD_VERIFIED |
| cea9eee3891045ad869e90600f7e11c0 | c1-shared-store-r5 | correctness | BUILD_VERIFIED |
| c9173cca017042b3a004b7494281ef01 | c1-shared-store-r5 | correctness | BUILD_VERIFIED |
| bf0dafb88d744b5192f634e4e1f49580 | c1-shared-store-r5 | correctness | BUILD_VERIFIED |
| 5239a706edc54efaa166e63f9da152b8 | c1-shared-store-r5 | correctness | BUILD_VERIFIED |
| b9816127cec74100a6ff7ce7bdaa297e | c1-shared-store-r5 | correctness | BUILD_VERIFIED |
| 48fd11859f014277b7188b6874673175 | c1-shared-store-r5 | probe | INCOMPLETE |

<details>
<summary>Functional coverage and cumulative resources</summary>

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

[Public observations and exact hashes](observations.json)

</details>

## Limitations

C1 functional coverage is complete on the retained R5 source/config/image. Its first baseline timing guest failed before complete latency samples. The saved run validity and failed integration fields remain separate. No calibration, performance equivalence, speedup, baseline advancement or code promotion is established.

H26 diagnostics are source-reviewed, while R6 expired before final admission and collected no runtime trace. One unlaunched R6 reservation remains counted. The earlier observer cause remains unproven. C2/C3 implementation and runtime are not C1 outcomes.

The archived-parser reconciliation reproduces historical gates and metrics; it creates no fresh runtime sample. Per-object/context representation is preserved by source review. Requested pool overhead and unmeasured allocator rounding remain distinct.

[Interactive explanation](codex-compress-lib-r5-2026-11-10-2026-11-11/explainer.html)
