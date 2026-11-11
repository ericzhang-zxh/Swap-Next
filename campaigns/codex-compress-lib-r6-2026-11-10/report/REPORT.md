# Shared compression library: complete C1 evidence and decision

**inconclusive** — One shared-library source passed functional coverage; timing remains unresolved. The diagnostic continuation expired before launch.

## Separate reusable mechanism from frontend policy

The experiment extracts codec contexts and compressed-object storage from ZSwap. Existing policy, indexes, accounting and lifetime ownership stay with the frontend. This is the first step toward independent XSwap and later tier migration.

One shared-library source passed functional coverage; timing remains unresolved. The diagnostic continuation expired before launch.

Six retained contracts concern one unchanged kernel hypothesis. The family view preserves every frozen ledger and failed attempt; exact resources and historical outcomes are available in the audit details.

Evidence: campaigns/codex-compress-lib-r6-2026-11-10/research.json, campaigns/codex-compress-lib-r6-2026-11-10/ledger/session-closeout.json

## 1. Whole system: restore the application page

An application needs its full page in physical RAM. Stored contents may be compressed inside RAM or reside on a backing device. Compression trades CPU work for less storage traffic.

The candidate changes the compressed-storage implementation. The existing frontend still decides admission, accounting and writeback. No new RAM-to-disk migration policy is implemented here.

Evidence: campaigns/codex-compress-lib-r6-2026-11-10/research.json, campaigns/codex-compress-lib-r6-2026-11-10/patches/c1-shared-store-r6.patch

## 2. Subsystem: policy keeps the object identity

ZSwap retains the entry index, memory-group charge, ordering and lifetime pins. A shared page library owns per-CPU codec contexts, scratch buffers and compressed-object storage.

The unchanged ownership boundary passed exact-source review. R5 subsequently passed complete required correctness, including NUMA placement, guest CPU hotplug, legacy behavior and accounting.

Evidence: campaigns/codex-compress-lib-r6-2026-11-10/patches/c1-shared-store-r6.patch, campaigns/codex-compress-lib-r6-2026-11-10/reviews/k2-c1-shared-store-r6-7d5a3cf.json

## 3. Concrete change: one object engine, the same frontend owner

Before extraction, ZSwap owns both policy and the codec/object engine. After extraction, the library returns a handle and length while ZSwap keeps publication, charges, LRU and references. Each stored object retains its original representation.

The review found no per-object wrapper or context-size increase. Extraction adds a pool allocation and a small requested pool-size increase; allocator rounding is unmeasured. New API and test obligations remain.

Evidence: campaigns/codex-compress-lib-r6-2026-11-10/patches/c1-shared-store-r6.patch, campaigns/codex-compress-lib-r6-2026-11-10/reviews/k2-c1-shared-store-r6-7d5a3cf.json

## Retain the library; complete C2 capability before execution

C2 host parsing and compressed-observer preparation remain isolated. Its guest-driver worker was interrupted by platform content-safety review, with the exact refused step unavailable. The partial driver is not build-complete; no C2 kernel candidate or guest was launched.

C1 correctness and closure have high confidence. C2 guest capability is incomplete; its profile remains inactive and C3 has not run. No blocked action was retried. Performance, baseline advancement and code promotion remain unestablished.

Evidence: campaigns/codex-compress-lib-r6-2026-11-10/research.json, campaigns/codex-compress-lib-r6-2026-11-10/ledger/session-closeout.json

## Core shared-library patches

These hunks belong to the unchanged K1 source used throughout C1. R5 supplies complete correctness; R6 adds no runtime sample.

### Same K1: the API keeps publication, accounting and handle lifetime with its caller

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

### Same K1: the library compresses and allocates before returning a usable handle

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

### Same K1: frontend pool creation delegates the engine and preserves its reference lifetime

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

## Outcomes

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
| codex-compress-lib-r6-2026-11-10 | 1 | 0 | 0 |

[Public observations and exact hashes](observations.json)

</details>

## Limitations

C1 functional coverage is complete on the retained R5 source/config/image. Its first baseline timing guest failed before complete latency samples. The saved run validity and failed integration fields remain separate. No calibration, performance equivalence, speedup, baseline advancement or code promotion is established.

H26 diagnostics are source-reviewed, while R6 expired before final admission and collected no runtime trace. One unlaunched R6 reservation remains counted. The earlier observer cause remains unproven. C2/C3 implementation and runtime are not C1 outcomes.

The archived-parser reconciliation reproduces historical gates and metrics; it creates no fresh runtime sample. Per-object/context representation is preserved by source review. Requested pool overhead and unmeasured allocator rounding remain distinct.

[Interactive explanation](codex-compress-lib-r6-2026-11-10-2026-11-11/explainer.html)
