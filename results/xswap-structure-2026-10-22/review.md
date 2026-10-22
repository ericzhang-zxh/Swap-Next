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

## Bounded cache-only tail candidate

Candidate xs-tailcache-v1 is commit b674f0d1e90c5b158f0a31d4ea877c4876535c2a,
independently based on observation baseline. Primary reviewed the actual 77-line
diff and controller scope/diff/checkpatch all pass. The observation function is
unchanged. The scan pins descriptor mappings with xswap_lock, checks cluster
contents under ci lock, and drops that lock for each RCU-protected existing
reclamation helper. It revalidates occupancy/table after each attempt and does
not dereference a speculative folio pointer. Existing tail isolation/unmap remains
the final authority. Only same-worker requeue is suppressed.

The outer window includes free clusters and stops at a persistent blocker.
The reused helper has an internal identity retry, so the outer loop bound is
not a strict runtime bound. No completion trigger or delayed retry exists; a
negative result cannot rule out a broader cache-only reclamation mechanism.
Confidence: medium pending runtime/lockdep; large-folio and writeback timing
remain coverage gaps. A lockdep build has started; no runtime pass is claimed yet.

## Lockdep interruption and isolated repair

Tailcache v1 lockdep disk smoke failed only the no-kernel-warning gate;
all data/lifecycle gates passed. A same-config observation-baseline disk control
reproduced the xswap_grow assertion warning. Failed runs remain charged as
attempts 51 and 52; no normal tailcache comparison was launched.

Source audit found that local_lock translates its per-CPU symbol, whereas
lockdep_assert_held checks the supplied address directly. xswap_grow used the
untranslated address. The isolated candidate xs-lockassert-v1 at
8f02472031fb71b9791a5199872701c645afd276 uses the current-CPU lock, matching
swap_cluster_populate. No acquisition/release behavior or warning gate changes.
Scope, diff and checkpatch passed; same-config build and disk control are running.
This source explanation has high confidence; runtime repair confirmation remains
pending. Tailcache v1 is closed, and a revised candidate requires new checks.

Budget allocation changed in response to this discovered warning: reserve one
extra isolated-repair control. If that and two revised-candidate lockdep boots
pass, 55 attempts will have been spent; a 40-boot comparison leaves one attempt
for the high-anchor disk diagnostic. The planned zswap high-anchor diagnostic
will remain unrun within the fixed 96-attempt cap. No old attempts are erased.

The isolated repair control subsequently passed all gates with the same normalized
lockdep configuration hash b0335fc99be930268729ad1c158e5c0a672f58ffb2d4ef9195b809b8734bed3b.
The original baseline and tailcache-v1 controls failed only the warning gate.
This supports the diagnosed assertion-address defect; it is not proof that all
locking paths are correct. Candidate xs-lockassert-v1 is closed with this result.

Revised tailcache candidate xs-tailcache-v2 is
615f839bb6653ffd56dbb66ebdc855dea0823d54. Primary checked its exact difference
from v1: only the independently verified assertion repair. Controller static
gates pass. Disk and zswap lockdep smoke checks are in progress. Normal comparison
remains blocked until both pass.

Both revised-candidate lockdep boots subsequently passed all pilot gates, disk
and zswap, without kernel diagnostics. Together with the isolated-repair control
this brings the shared ledger to 55 attempts: 53 pass and two retained warning
failures. Full normal-config comparison of xs-tailcache-v2 has now started;
its results remain pending. These lockdep boots do not establish large-folio,
failure-injection or general concurrency coverage.
