# Xswap discovery review

Reference: 37de636c972a413f5c25e5b6c891fb4df2f53aed, imported Phase I v4
and Phase II v1. This is a different source baseline and workload from the
historical ordinary-swap pilots. Their results must not be pooled.

## First hypothesis: smaller minimum tail shrink

Candidate e3c6ac74d117d5fe065cbc0c7a591347663430ce changes one constant in
mm/swapfile.c: XSWAP_SHRINK_MIN from eight to four growth chunks. Initial smoke
snapshots retained 429 free tail clusters on disk and 471 with zswap, with zero
shrink operations. The candidate tests whether the minimum batch gate retains
avoidable mapped clusters after pressure subsides. Timing benefits are not
assumed. More frequent unmap, PCP flush and RCU waits can increase runtime or
cause regrowth under alternating pressure.

The resource owner remains swap_info_struct. xswap_map_clusters initializes
cluster locks and publishes the mapped bound with release ordering. Shrink
runs under xswap_lock, checks occupancy, scans the exact contiguous free tail,
keeps one growth chunk as slack, then revalidates flags and cluster-lock
availability under si->lock. It detaches only the free tail before unmapping.
The unmap helper releases backing records, flushes PCP references, waits for RCU,
and frees mapped pages, with a bounded fallback on allocation failure. Destroy
cancels shrink work and follows the existing swapoff lifetime path. This patch
changes none of those operations, folio references, backend ownership or memcg
charge paths. It changes how often that existing path can be reached.

Static diff and checkpatch passed. Source review supports proceeding to bounded
experiments, not merging. Runtime observations and missing gates are recorded
separately. No concurrency or allocator-failure proof is inferred from a one-line
diff or a successful pilot. Original reference behavior remains experimental.

## Baseline and measurement limits

The first disk smoke boot intentionally failed closed when xswap creation was
attempted with zswap disabled. The reference requires zswap enabled at creation.
The final harness enables it during creation and disables it afterward for the
forced-disk scenario, before baseline activity counters and workload begin.
This was corrected before candidate evaluation and A/A calibration. Both final
smoke backends passed, including exact xswap PTE type checks and live teardown.

The workload uses page-distinct compressible data so that the zswap case actually
exercises compression; it is not a general incompressible workload. Children
check one page each, including COW; the parent verifies all words. First-access
latency includes swap-cache, readahead, scheduling and timer effects. Mapped
cluster counts describe one metadata structure, not physical bytes or total RAM.
Six snapshots give a sampled maximum, not a continuous peak. A/A observations
are an initial noise diagnostic, not full statistical calibration.

A/A exposed a major measurement limitation: identical disk kernels retained
either 219 or 1,898 mapped clusters; identical zswap kernels retained either
219 or 2,774. The different retention regimes are consistent with asynchronous shrink
and allocation-layout effects even with the same source and guest inputs. The low retained
state coincides with shrink activity. Two pairs per backend cannot separate
this variation from a candidate effect. All discovery rankings remain
provisional; candidate-average reductions cannot establish causality.

## Second hypothesis: larger growth cap

The first round passed eight guest gates but did not justify selection: average
settled mappings fell on disk and rose with zswap. Both zswap candidate runs
performed a shrink yet retained 2,409/2,482 mapped clusters with only 82/121 free
tail clusters. Lowering the shrink minimum again would not explain how to
release a mapped range whose high clusters remain in use. This is a reason to
change the hypothesis rather than keep tuning the same threshold blindly.

The second candidate changes only XSWAP_GROW_CHUNKS from four to eight.
The source computes required growth from usage, rounds to a chunk, applies
the cap, then clamps to the device maximum. The larger cap can reduce the
12-16 observed growth episodes if the cap binds. It preserves xswap_lock,
stale-range EAGAIN checks, no-reclaim allocation, rollback, release/acquire
publication and cluster-list locking after the PCP lock is reacquired.
It can increase allocation bursts and mapped-cluster retention. A change
in runtime without a corresponding growth-counter change is weak mechanism
evidence. The candidate remains independent and based on the frozen seed.

## Third hypothesis: tighter growth headroom

Round two's zswap candidate made 13 recorded growth operations in each run versus 16 and
15 for its paired references. Disk candidate runs still made 12 calls.
The cap change therefore has observable mechanism evidence on zswap, but
its zswap p99 mean rose by about 4.7 percent and settled mapped clusters
rose by about 10.8 percent. Both comparisons are exploratory and noisy.

The third candidate retains the eight-chunk cap and raises the occupancy
target from 65 to 75 percent. This mutates one parameter relative to the
second candidate, while the complete two-constant patch is based on the
frozen reference as required by the controller. The coherent hypothesis
is to retain batching while asking for less spare mapping. The target
remains strictly inside the 50/85 trigger band. Smaller requests can
increase growth frequency; all clamps, lock ordering, publication and
allocation failure paths remain unchanged. It is an experimental tradeoff,
not an assertion that tighter headroom is universally better.

## AI assistance

Codex assisted source exploration, experiment design, harness/controller code,
experimental patches, checks and this report in response to a request for a
few bounded xswap evolution rounds. OpenEvolve stores and selects feedback;
the active assistant makes proposal and acceptance decisions. No model API
worker runs unattended, no patch is auto-promoted, and no new DCO sign-off was
added. Human review and certification remain necessary for upstream work.
