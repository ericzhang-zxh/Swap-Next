# Shared compression library: a NUMA boot warning stopped validation

**inconclusive** — Baseline and debug runs passed; a NUMA boot warning kept correctness incomplete.

Earlier frozen contracts: [Original C1 contract](https://ericzhang-zxh.github.io/Swap-Next/codex-compress-lib-2026-11-10/) · [R2 closeout](https://ericzhang-zxh.github.io/Swap-Next/codex-compress-lib-r2-2026-11-10/). One unchanged kernel hypothesis.

## One hypothesis across retained infrastructure contracts

R3 tested the same shared compression library. Fresh baseline and candidate debug runs passed their per-run gates. The two-node NUMA guest failed on a genuine boot warning, closing this infrastructure contract.

The unchanged kernel reached validated debug coverage. The full required matrix remains incomplete, so calibration, performance and dependent architecture phases remain pending.

R3 used 3 probe guests and no new builds; existing builds were revalidated and reused. Through this closeout, original C1 plus R2 and R3 consumed 8 guests and 4 builds.

Evidence: campaigns/codex-compress-lib-r3-2026-11-10/research.json, campaigns/codex-compress-lib-r3-2026-11-10/ledger/session-closeout.json, campaigns/codex-compress-lib-r3-2026-11-10/ledger/budget.json

## 1. Whole system: restore the application page

An application needs its full page in physical RAM. Stored contents may be compressed inside RAM or reside on a backing device. Compression trades CPU work for less storage traffic.

The candidate changes the compressed-storage implementation. The existing frontend still decides admission, accounting and writeback. No new RAM-to-disk migration policy is implemented here.

Evidence: campaigns/codex-compress-lib-r3-2026-11-10/research.json, campaigns/codex-compress-lib-r3-2026-11-10/patches/c1-shared-store-r3.patch

## 2. Subsystem: policy keeps the object identity

ZSwap retains the entry index, memory-group charge, ordering and lifetime pins. A shared page library owns per-CPU codec contexts, scratch buffers and compressed-object storage.

High-confidence source review supports this ownership boundary. CPU-local codec contexts and requested memory placement require runtime coverage. The single-node debug case passed; the NUMA warning preserves an unresolved validation boundary.

Evidence: campaigns/codex-compress-lib-r3-2026-11-10/patches/c1-shared-store-r3.patch, campaigns/codex-compress-lib-r3-2026-11-10/reviews/k2-c1-shared-store-r3-7d5a3cf.json

## 3. Concrete test: split memory nodes exposed a boot warning

The same candidate image passed its single-node debug case. The auxiliary NUMA guest split four virtual CPUs across two memory nodes while retaining an implicit package topology.

The NUMA library, hotplug and memory-accounting subcases passed, including matching requested and actual memory nodes. The boot warning failed both kernel-warning gates, keeping the overall run failed.

High-confidence diagnosis: the virtual CPU and memory-node mapping conflict. The warning appears during CPU boot. No candidate-source defect is established by this run; complete coverage remains required.

Evidence: campaigns/codex-compress-lib-r3-2026-11-10/patches/c1-shared-store-r3.patch, campaigns/codex-compress-lib-r3-2026-11-10/ledger/ledger.json, campaigns/codex-compress-lib-r3-2026-11-10/ledger/session-closeout.json

## Review the topology correction, then gather fresh evidence

This frozen contract is closed with its warning intact. A separately reviewed topology correction and new remaining-budget contract must collect fresh correctness evidence before calibration.

A fresh correctly mapped topology that produces the same warning would contradict the current diagnosis. No outcome is predicted for that correction. Remaining resource ceilings and the earlier enforced deadline remain binding.

Evidence: campaigns/codex-compress-lib-r3-2026-11-10/ledger/session-closeout.json, campaigns/codex-compress-lib-r3-2026-11-10/protocol.json, campaigns/codex-compress-lib-r3-2026-11-10/research.json

## Core kernel patches

The exact K1 source is unchanged across these infrastructure contracts. The pinned excerpts show the shared-library mechanism; R3 adds no new kernel hypothesis.

### Same K1: the API keeps publication, accounting and handle lifetime with its caller

Source: `campaigns/codex-compress-lib-r3-2026-11-10/patches/c1-shared-store-r3.patch`

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

Source: `campaigns/codex-compress-lib-r3-2026-11-10/patches/c1-shared-store-r3.patch`

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

Source: `campaigns/codex-compress-lib-r3-2026-11-10/patches/c1-shared-store-r3.patch`

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
| 91345b54260646f08085ebf30ac1f80a |  | correctness | BUILD_VERIFIED |
| 35a0cbd3f5b7415d99bd4c140eab3bc9 | c1-shared-store-r3 | correctness | BUILD_VERIFIED |
| e01123bd58c44c31977862326be05785 | c1-shared-store-r3 | correctness | BUILD_VERIFIED |

<details>
<summary>Per-run evidence and cumulative costs</summary>

| Run | Passed gates / total | Original integration |
| --- | --- | --- |
| c1r3-b-common-001 | 19 / 19 | true |
| c1r3-c-debug-001 | 20 / 20 | true |
| c1r3-c-numa-001 | 15 / 17 | false |

Retained NUMA warning: `sched: CPU #2's llc-sibling CPU #0 is not on the same node! [node: 1 != 0]. Ignoring dependency.`

| Contract | Counted guests | Counted builds |
| --- | --- | --- |
| Original C1 | 3 | 3 |
| R2 | 2 | 1 |
| R3 | 3 | 0 |
| C1 through R3 | 8 | 4 |

[Public observations and hashes](observations.json)

</details>

## Limitations

The two per-run passes cover their named cases. The retained NUMA failure and remaining matrix rows keep full candidate correctness incomplete. No calibration, speed or equivalence result exists. A future topology correction has no outcome in this report.

Raw results, serial logs, sidecars and the pre-correction runtime archive remain retained outside this public report. Their hashes, reused builds, failed warning gates and frozen budget costs are bound in observations.json and the native closeout summary.

[Interactive explanation](codex-compress-lib-r3-2026-11-10-2026-11-10/explainer.html)
