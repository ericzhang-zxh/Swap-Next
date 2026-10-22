# xswap campaign 2026-10-21

**Result: none of the three constant changes had a detectable effect.**
The primary metric, retained mapped clusters, is set by one binary event
during the pressure phase. That event decides the result and dominates
every candidate comparison. No patch was promoted.

Baseline: imported xswap Phase I v4 + Phase II v1 (`37de636c`), see
[patches/xswap-reference](../../patches/xswap-reference/README.md). This campaign
compares xswap variants with each other, not xswap with ordinary swap.

## What ran

- 35 guest boots: 2 smoke, 8 A/A, 24 candidate/reference, and 1 startup failure
  (xswap creation with zswap disabled; the harness was fixed before A/A).
- All 34 completed boots passed the integrity, fork/COW, xswap PTE identity,
  live-destroy, swapoff, backend-activity and no-warning gates. Each recorded
  16,384 timed first accesses.
- The imported reference was replayed exactly (26 commits, identical tree).
  All candidates passed the scope, diff and checkpatch checks, and all builds
  used the same normalized config.

## Why there is no effect

Per-phase snapshots in [summary.json](summary.json), all 32 measured boots:

| Backend | Shrink during pressure | Boots | Retained clusters |
|---|---|---:|---|
| disk | yes | 9 | 219 in every boot |
| disk | no | 7 | 1679–1898 |
| zswap | yes | 8 | 219 (5), 2409–2482 (3) |
| zswap | no | 8 | 2774–3066 |

From the end of `usemem` onward, neither `clusters_mapped` nor `shrinks`
changes in any boot. The "after settle" value is therefore the post-pressure
value. Usage still falls from about 25,400 to about 9,000 pages during that
time.

The A/A runs show the same split (disk 219/1898, zswap 219/2774) with
identical kernels.

**Mechanism (high confidence).** Shrink unmaps only a contiguous free tail.
One long-lived slot high in the range keeps everything below it mapped.
The 64 MiB target's slots are allocated first, so they sit low, and freeing
them never creates a tail. Occupancy at the end is 7.9% in the low regime
and 0.6–1.2% in the high regime, so about 99% of the mapped metadata is unused.

**What pins the high clusters (medium confidence, untested).** Probably
cache-only slots: swap-cache folios whose PTE references were dropped when
`usemem` exited but whose slots were not freed because the folio was locked
or under writeback. That would explain both the randomness (writeback timing
at exit) and the roughly 9,000 pages still in use after the target is read back.

**Upstream inconsistency.** The `06.patch` commit message says the minimum
shrink is four chunks, but the code defines `XSWAP_SHRINK_MIN` as eight.
The first candidate set the code to the value the message states.

## Candidates

Reference → candidate means over two boots per backend. The arrows show
which regime each boot happened to land in. They do not estimate an effect.

| Trial | Change | Disk clusters | Zswap clusters | Disk p99 µs | Zswap p99 µs |
|---|---|---:|---:|---:|---:|
| xswap-shrink-min4 | `XSWAP_SHRINK_MIN` 8 → 4 chunks | 1058.5 → 219 | 1642.5 → 2445.5 | 369 → 337 | 259 → 252 |
| xswap-grow-cap8 | `XSWAP_GROW_CHUNKS` 4 → 8 | 1058.5 → 219 | 1350.5 → 1496.5 | 336 → 333 | 223 → 234 |
| xswap-grow-target75 | cap 8, grow target 65% → 75% | 1898 → 949 | 2774 → 2920 | 363 → 385 | 258 → 218 |

The growth counters do show the expected mechanism. Cap 8 cut zswap growth
operations from 15–16 to 13. Target 75% raised them to 18–23. These effects
are real, but they do not reach the retained-metadata metric.

Latency is the mean of per-run p99. Identical kernels already differ by
this much. In A/A, disk per-run p99 ranged from 300 to 458 µs and the two
side means differed by 31%. Zswap ranged from 220 to 256 µs. Every latency
delta above falls inside that A/A spread.

## Lessons

- **The metric was never validated.** The A/A runs showed the split, and the
  campaign compared candidates anyway.
- **Constant tuning cannot reach the problem.** The bottleneck is
  free-tail-only shrink.

## Next steps for this direction

The next protocol should measure the structure, not one snapshot:

- **Add debugfs counters**: the highest in-use cluster index, the number of
  non-empty clusters, and the number of cache-only slots. Then
  - `mapped − (highest + 1)` is what tail shrink could still reclaim;
  - `mapped − non_empty` is what any shrink design could reclaim.
- **Report a regime rate**: the fraction of boots in the high state, with a
  binomial interval, over at least 10 boots per side.
- **Run a cheap diagnostic first**: in the high state, force reclaim of the
  swap cache (for example, by applying pressure again after `usemem` exits)
  and record whether the pinned clusters free up and the shrink then fires.

Hypotheses, ranked:

1. **Interior unmap.** Unmap any fully free cluster, not only the tail.
   `VM_SPARSE` already allows holes. The obstacle is that `cluster_info`
   walkers and the grow path treat the mapped range as a dense prefix
   bounded by `nr_clusters_mapped`. Replacing that prefix with a mapped
   bitmap or per-chunk state is the structural fix. It touches lock and
   lifetime rules.
2. **Low-first allocation while sparse.** When occupancy is low, allocate
   from the lowest free cluster, so long-lived slots do not land high.
   This is cheaper than (1) and leaves the lifetime rules unchanged. Risks
   are allocator lock traffic and weaker per-CPU cluster locality. It is
   falsified if the high-state rate does not fall.
3. **Eager cache-only reclaim on exit.** Use this if the diagnostic confirms
   that cache-only slots pin the tail. It has the smallest scope, but it
   addresses only one source of pinning.

## Evidence

- [summary.json](summary.json): per-run metrics, snapshots, counters, gates,
  and source/image/raw-log hashes.
- [review.md](review.md): per-candidate source review.
- [Experimental patches](../../patches/xswap-experiments/manifest.json):
  independent alternatives, each based on the reference.
- [Harness](../../benchmark/xswap/README.md).

Raw serial logs, guest disks and the OpenEvolve database stay on the Linux worker.
