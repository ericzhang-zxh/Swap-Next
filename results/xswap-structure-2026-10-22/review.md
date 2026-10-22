# Structural candidate review

## Observation baseline

Commit `4f83412c1d59eaf6a4d2460cb47fe0177a3be0c4` adds debugfs topology
observations to `37de636c972a413f5c25e5b6c891fb4df2f53aed`. Primary review
checked the actual diff and allocation/free callers before guest execution.

| Resource | Protection and observation |
|---|---|
| Descriptor mapping | Existing xswap_lock excludes grow/unmap during the scan |
| Cluster count and table | One ci lock; skip table inspection for empty clusters and absent tables |
| Table entries | Existing __swap_table_get and swp_tb_get_count, no folio pointer dereference |
| Device teardown | Existing debugfs removal and mapping mutex protocol; reserved cluster may retain count after table removal |
| Scheduling | cond_resched only after releasing the cluster spinlock |

Confidence: high for the read-only implementation scope. The counters describe
a sequential scan, not one atomic snapshot. A table/pointer publisher found to
violate the counted-cluster lifetime assumption would invalidate this review.
Scope, diff and checkpatch passed. Isolated build and disk/zswap smoke guests
passed. The real-disk evidence mutation/provenance suite passed all 8 tests.

## Low-first free-cluster selection

Candidate `xs-lowfree-v1`, commit
`157c4a178c587add1d22f4b483629b49a6ff0eca`, adds 11 lines to
isolate_lock_cluster on the observation baseline.

While holding the existing si list lock, the xswap free list is scanned and its
lowest-address member is moved to the head. The original trylock/isolation loop
then runs unchanged. No cluster lock is acquired by the new scan, no list
membership changes, and the flags/population/error paths are unchanged.
Contended lowest clusters still fall back to other members.

Confidence: high for preservation of the inspected list and lifetime rules.
An unlocked list writer or new lock-order dependency would change that judgment.
The mechanism intentionally trades O(free clusters) device-lock work per fresh
cluster for lower-address selection. Per-CPU reuse and nonfull priority remain
unchanged. High-position slots already allocated are never relocated.

Scope, diff and checkpatch passed. Evaluation
`764ad8b5-1810-49ef-8d82-300adf732b37` completed 40/40 pilot-passing boots;
the export reverified raw evidence and identities. Closed as inconclusive,
without acceptance or promotion.

| Backend | Baseline mean clusters | Candidate mean clusters | High regime A/B | Mean first-access p99 A/B (us) |
|---|---:|---:|---|---|
| disk | 722.7 | 554.8 | 3/10 vs 2/10 | 355.866 / 353.288 |
| zswap | 2299.5 | 1496.5 | 9/10 vs 5/10 | 243.577 / 257.695 |

The high-regime Wilson intervals overlap (disk A 0.108-0.603, B 0.057-0.510;
zswap A 0.596-0.982, B 0.237-0.763). These intervals describe samples rather
than a calibrated paired treatment test. The zswap mean p99 regressed about
5.8%. The exploratory discovery score 1.231 does not establish reliable benefit.
The low-first mechanism does not eliminate high retention. The next independent
candidate addresses high cache-only blockers while keeping the baseline allocator.
At this point the common ledger contains 50 guest attempts, all pilot-passing:
2 initial smoke, 8 calibration, and 40 candidate comparison boots.

## Initial observation evidence

Two smoke boots and 8 fresh A/A boots passed all pilot gates.
A/A first-cycle retained clusters were disk [219, 219, 219, 219] and
zswap [2774, 2482, 219, 2774]. On the three high zswap A/A boots, the highest
cache-only positions (index plus one) were [2315, 2350, 2325], while the highest
referenced positions were [100, 99, 100]. Confidence: high for these recorded
samples. New samples with high referenced positions can establish other causes.

The earlier assumption that the roughly 9,000 residual pages are mostly
cache-only is contradicted in these samples: roughly 8,850–8,896 slots still
have PTE references. A small number of high cache-only slots can nevertheless
pin the metadata tail. A second pressure cycle has mixed results and sometimes
places real references at high indices, so it is not a dependable cleanup.

## Limits

The workload is synthetic; these are discovery observations. Missing correctness,
sanitizer, confirmation, and holdout coverage remains recorded in the protocol.
Instrumentation changes timing and is present in every compared kernel.
See [DESIGN.md](../../DESIGN.md#limitations).
