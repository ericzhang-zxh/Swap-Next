# Shared compression library: runtime validation blocked

**inconclusive** — The library compiled, but a conflicting debug setup stopped runtime validation.

## A reusable engine, awaiting runtime evidence

The aim is to share compression and object storage while keeping the current swap policy and ownership. Independent XSwap and pressure-driven disk demotion are later phases.

Hypothesis: a common engine can serve another frontend without duplicating codec and storage cleanup. Source review gives high confidence in the boundary; runtime behavior remains untested.

Two baseline guests passed; one earlier baseline attempt remains infrastructure-invalid with an audited replacement. Three builds were charged: two valid baseline builds and one candidate image rejected by its required configuration gate.

Evidence: campaigns/codex-compress-lib-2026-11-10/research.json, campaigns/codex-compress-lib-2026-11-10/ledger/session-closeout.json, campaigns/codex-compress-lib-2026-11-10/ledger/budget.json

## 1. Whole system: restore the application page

An application needs its full page in physical RAM. Stored contents may be compressed inside RAM or reside on a backing device. Compression trades CPU work for less storage traffic.

The candidate changes the compressed-storage implementation. The existing frontend still decides admission, accounting and writeback. No new RAM-to-disk migration policy is implemented here.

Evidence: campaigns/codex-compress-lib-2026-11-10/research.json, campaigns/codex-compress-lib-2026-11-10/patches/c1-shared-store-v1.patch

## 2. Subsystem: policy keeps the object identity

ZSwap retains the entry index, memory-group charge, ordering and lifetime pins. A shared page library owns per-CPU codec contexts, scratch buffers and compressed-object storage.

Each successful store returns a handle and length. The caller publishes and accounts for that object, retains it across loads, and releases it after users drain. Failed compression leaves the raw-storage policy with ZSwap.

Evidence: campaigns/codex-compress-lib-2026-11-10/patches/c1-shared-store-v1.patch, campaigns/codex-compress-lib-2026-11-10/reviews/k2-c1-shared-store-7d5a3cf.json

## 3. Concrete change: one explicit library boundary

The same page A and stored object A appear before and after. The extraction moves mechanism ownership; it does not remove compression work or change what is stored.

Source review found unchanged per-object entries and per-CPU context layout. A separate pool wrapper adds an allocation. Allocator footprint, call overhead and fault latency remain unmeasured.

Compilation passed. The frozen debug input enabled SLUB_TINY, which prevents the required KASAN memory checker. Configured coverage failed before any candidate guest, KUnit execution, sanitizer run, calibration or performance comparison.

Evidence: campaigns/codex-compress-lib-2026-11-10/patches/c1-shared-store-v1.patch, campaigns/codex-compress-lib-2026-11-10/ledger/ledger.json, campaigns/codex-compress-lib-2026-11-10/ledger/session-closeout.json

## Continue under a separately frozen correction

Preserve this closed contract and test the unchanged candidate only after correcting the debug input. Independent XSwap and tier migration stay behind successful C1 correctness coverage.

The correction preserves the original resource ceiling and deadline. Ownership, accounting, cleanup, metadata or calibrated latency failures would falsify the candidate. This attempt provides no speed or equivalence result.

Evidence: campaigns/codex-compress-lib-2026-11-10/ledger/session-closeout.json, campaigns/codex-compress-lib-2026-11-10/protocol.json, campaigns/codex-compress-lib-2026-11-10/research.json

## Core kernel patches

Exact excerpts from the pinned full candidate patch. Added-file excerpts retain their source line positions; omitted hunks remain in that patch.

### K1: the API keeps publication, accounting and handle lifetime with its caller

Source: `campaigns/codex-compress-lib-2026-11-10/patches/c1-shared-store-v1.patch`

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

### K1: the library compresses and allocates before returning a usable handle

Source: `campaigns/codex-compress-lib-2026-11-10/patches/c1-shared-store-v1.patch`

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

### K1: frontend pool creation delegates the engine and preserves its reference lifetime

Source: `campaigns/codex-compress-lib-2026-11-10/patches/c1-shared-store-v1.patch`

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
| 3868cc40b0944c8f9b13b3aa529b5005 |  | correctness | BUILD_VERIFIED |
| 4894c2e365c1463292ae02dd5914fffd |  | correctness | BUILD_VERIFIED |
| 6e88313ec6184c6a9e46c510e55150e0 |  |  | INFRA_RETRY_REQUIRED |
| 6be443dc6e384b909ef8dd544f9e7211 | c1-shared-store-v1 | correctness | BUILD_FAILED |

## Limitations

Evidence is limited to source review, baseline checks and candidate compilation. Required candidate configuration failed before runtime. No candidate correctness, KUnit, sanitizer, calibration, speed or equivalence result exists.

Raw runtime evidence remains retained outside this public report. The original closeout record pins its observed artifact hashes; summary.json preserves the failed build, audited infrastructure retry, budget and closed outcome.

[Interactive explanation](codex-compress-lib-2026-11-10-2026-11-10/explainer.html)
