# Shared compression library: debug run reached, validation blocked

**inconclusive** — The debug guest completed, but parser defects blocked validated coverage.

Continuation of [Original C1 contract](https://ericzhang-zxh.github.io/Swap-Next/codex-compress-lib-2026-11-10/) on the same kernel source.

## Same candidate, further debug evidence

R2 continues the original shared-library hypothesis on unchanged kernel source. A corrected debug setup reached the guest; the complete correctness matrix still gates every performance measurement.

The fresh baseline guest passed. The candidate debug build enabled KASAN and its guest completed. The saved integration result remains failed because strict parsing rejected an expected diagnostic.

R2 consumed 2 guests and 1 build. With the original contract, C1 has spent 5 guests and 4 builds. No calibration or performance comparison ran.

Evidence: campaigns/codex-compress-lib-r2-2026-11-10/research.json, campaigns/codex-compress-lib-r2-2026-11-10/ledger/session-closeout.json, campaigns/codex-compress-lib-r2-2026-11-10/ledger/budget.json

## 1. Whole system: restore the application page

An application needs its full page in physical RAM. Stored contents may be compressed inside RAM or reside on a backing device. Compression trades CPU work for less storage traffic.

The candidate changes the compressed-storage implementation. The existing frontend still decides admission, accounting and writeback. No new RAM-to-disk migration policy is implemented here.

Evidence: campaigns/codex-compress-lib-r2-2026-11-10/research.json, campaigns/codex-compress-lib-r2-2026-11-10/patches/c1-shared-store-r2.patch

## 2. Subsystem: policy keeps the object identity

ZSwap retains the entry index, memory-group charge, ordering and lifetime pins. A shared page library owns per-CPU codec contexts, scratch buffers and compressed-object storage.

High-confidence source review supports this ownership boundary. Each successful store returns a caller-owned handle; publication, charging and release stay with ZSwap. The retained debug log adds observations, while the full matrix remains incomplete.

Evidence: campaigns/codex-compress-lib-r2-2026-11-10/patches/c1-shared-store-r2.patch, campaigns/codex-compress-lib-r2-2026-11-10/reviews/k2-c1-shared-store-r2-7d5a3cf.json

## 3. Concrete change: the same kernel reached the debug guest

The candidate source is unchanged. R2 repaired the debug configuration, advancing from a build gate to recorded guest output; evidence parsing then stopped formal coverage.

The retained log reports PASS for 6 subcases and ok for 3 named KUnit cases, with no kernel warning found. These are raw observations; the original integration result remains failed.

The parser rejected the deliberate invalid-codec message. Diagnostic replay also exposed a false rejection of the standard skip:0 summary. Corrected replay diagnoses those rules; it creates no new successful guest observation.

Evidence: campaigns/codex-compress-lib-r2-2026-11-10/patches/c1-shared-store-r2.patch, campaigns/codex-compress-lib-r2-2026-11-10/ledger/ledger.json, campaigns/codex-compress-lib-r2-2026-11-10/ledger/session-closeout.json

## Repair parsing, then collect fresh counted evidence

Keep the failed result and archive intact. A separately frozen correction must validate fresh correctness evidence on the same source before calibration or dependent architecture phases.

Confidence is high in the two observed parser defects. A kernel diagnostic, failed raw subcase or unexplained replay mismatch would stop continuation. Remaining resources and the earlier enforced deadline stay binding.

Evidence: campaigns/codex-compress-lib-r2-2026-11-10/ledger/session-closeout.json, campaigns/codex-compress-lib-r2-2026-11-10/protocol.json, campaigns/codex-compress-lib-r2-2026-11-10/research.json

## Core kernel patches

The unchanged K1 patch is retained in R2. These exact code excerpts explain the shared-library mechanism; they introduce no new scientific hypothesis.

### Same K1: the API keeps publication, accounting and handle lifetime with its caller

Source: `campaigns/codex-compress-lib-r2-2026-11-10/patches/c1-shared-store-r2.patch`

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

Source: `campaigns/codex-compress-lib-r2-2026-11-10/patches/c1-shared-store-r2.patch`

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

Source: `campaigns/codex-compress-lib-r2-2026-11-10/patches/c1-shared-store-r2.patch`

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
| 38f0482dac984d48a7d4e9cc7289f1b0 | c1-shared-store-r2 | correctness | BUILD_VERIFIED |

<details>
<summary>Retained guest observations and cumulative costs</summary>

| Run | Original integration | Raw observation |
| --- | --- | --- |
| c1r2-b-common-001 | true | Fresh baseline passed |
| c1r2-c-debug-001 | false | Debug log completed; parsing rejected |

| Contract | Counted guests | Counted builds |
| --- | --- | --- |
| Original C1 | 3 | 3 |
| R2 | 2 | 1 |
| C1 cumulative | 5 | 4 |

[Public observations and hashes](observations.json)

</details>

## Limitations

R2 records raw candidate debug output from the unchanged kernel. The saved integration result remains failed and the complete required correctness matrix is unfinished. Diagnostic replay identifies parser defects; it replaces no failed observation. No calibrated speed or equivalence result exists.

Raw runtime bytes and the pre-fix runtime archive remain retained outside this public report. The closeout record pins the original hashes; observations.json summarizes the raw signals and cumulative costs. Fresh counted correctness evidence is required under any correction.

[Interactive explanation](codex-compress-lib-r2-2026-11-10-2026-11-10/explainer.html)
