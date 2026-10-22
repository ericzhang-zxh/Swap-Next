# Design

Swap Next searches for Linux swap changes that lower a measured cost without
breaking correctness. A candidate is one small patch on a frozen kernel; a
benchmark boots it next to the baseline in KVM; OpenEvolve archives the result
and picks references for the next proposal. The proposer is the assistant in
the current session.

This document states what we optimize, where the upstream work stands, what
the first campaign showed, and what to try next. Every other document links
here for the "why".

## What swap costs

| Cost | Where it arises | Measured here |
|---|---|---|
| Fault latency | swap cache lookup, zswap decompression, block I/O on swap-in | yes: p99 first access to a swapped PTE |
| Metadata RAM | per-slot swap table, `cluster_info`, zswap entries; for xswap the mapped part of `cluster_info` | yes: mapped clusters (xswap), requested bytes (kernel suite) |
| Physical slot use | a zswap-resident page still holds a disk slot on ordinary swap | recorded (disk sectors), not scored |
| Reclaim CPU | compression, cluster allocation, swap-out path | no |
| Scalability | `si->lock`, cluster locks, per-CPU cluster cache | no: guests have two vCPUs |

A campaign picks one row as its primary metric and keeps the others as
guardrails. The formal policy in `evolve/control/config/policy.json` names
throughput, but no suite measures throughput yet. Until one does, the
measured rows above are the only valid choices.

## Upstream roadmap

- **Base**: `linux/` is pinned at `744e5400` (v7.4 merge window). The swap
  table (`mm/swap_table.h`) is already upstream there.
- **xswap Phase I v4** (14 patches; Baoquan He, Chris Li). This adds a virtual
  swap device with no backing store, held in zswap. It keeps `cluster_info` in
  a `VM_SPARSE` area that is mapped lazily, grows the mapping at 85% use
  towards a 65% target, and unmaps a free *tail* once use drops to 50%.
  It also adds sysfs create/destroy and debugfs counters.
- **xswap Phase II v1** (12 patches; includes Nhat Pham's I/O work). This gives
  each xswap slot an optional physical backend. Pages that zswap refuses are
  written to disk, the backend can be swapped off, cache-only physical slots
  are reclaimed, and THP swap-in is enabled.
- **Phase III** is not imported and has not been reviewed here.
- **vswap** (Nhat Pham) is a competing virtual-swap design. Attribution is
  disputed upstream ([thread](https://lists.openwall.net/linux-kernel/2026/10/12/779)).
  We take no side.

Open items in the imported reference:

- virtual capacity accounting
- a recycled integer destroy handle
- interface documentation
- the free-tail-only shrink analysed below
- the minimum shrink size: the `06.patch` commit message says four chunks,
  but the code defines `XSWAP_SHRINK_MIN` as eight

## What the first campaign showed

The `xswap-2026-10-21` campaign scored three constant changes by
`mapped_clusters_after_settle`. The per-phase snapshots in
`results/xswap-2026-10-21/summary.json` show what that metric actually captures:

1. **The state is fixed before the timed reads begin.** In all 32 boots,
   `clusters_mapped` and `shrinks` stay constant from the end of the `usemem`
   pressure phase onward. Usage still falls from about 25,400 to about 9,000
   pages during that time.
2. **One event decides the outcome: whether a tail shrink succeeds during
   pressure.**

   | Backend | Shrink during pressure | Boots | Retained clusters | Occupancy at end |
   |---|---|---:|---|---|
   | disk | yes | 9 | 219 (all) | 7.9% |
   | disk | no | 7 | 1679–1898 | 0.9–1.2% |
   | zswap | yes | 8 | 219 (5), 2409–2482 (3) | 7.9% / 0.7% |
   | zswap | no | 8 | 2774–3066 | 0.6–1.1% |

3. **The mechanism is the shrink design.** Shrink unmaps only a contiguous free
   tail. One long-lived slot high in the range keeps everything below it
   mapped. The 64 MiB target's slots are allocated first, so they sit low, and
   freeing them never creates a tail. In the high state, about 99% of the
   mapped metadata is unused.

**Conclusion (high confidence):** the three constant changes had no
detectable effect on retained metadata. Each boot lands in one of two
regimes, and two pairs per backend cannot estimate how often a regime occurs.
The disk-column "reductions" in the old report are regime luck: the A/A runs
show the same 219/1898 split. Tuning `XSWAP_GROW_CHUNKS`, `XSWAP_SHRINK_MIN` or
the occupancy targets can change only that probability, and only indirectly.

**What pins the high clusters (medium confidence, untested):** probably
cache-only slots, that is swap-cache folios whose PTE references were dropped
when `usemem` exited but whose slots were not freed because the folio was
locked or under writeback. That would explain both the randomness (writeback
timing at exit) and the roughly 9,000 pages left in use after the target is
read back.

## Next protocol revision

Measure the structure, not one snapshot:

- **Add debugfs counters**: the highest in-use cluster index, the number of
  non-empty clusters, and the number of cache-only slots. Then
  - `mapped − (highest + 1)` is what tail shrink could still reclaim;
  - `mapped − non_empty` is what any shrink design could reclaim.
- **Report a regime rate**: the fraction of boots in the high state, with a
  binomial interval, over at least 10 boots per side. A mean of two runs is
  not enough.
- **Run a cheap diagnostic first**: in the high state, force reclaim of the
  swap cache (for example, by applying memory pressure again after
  `usemem` exits) and record whether the pinned clusters free up and the
  shrink then fires. That answers the cache-only question before any
  allocator work.

## Hypotheses, ranked

1. **Interior unmap.** Unmap any fully free cluster, not only the tail.
   `VM_SPARSE` already allows holes. The obstacle is that `cluster_info`
   walkers and the grow path treat the mapped range as a dense prefix
   bounded by `nr_clusters_mapped`. A mapped bitmap or per-chunk state
   would remove that assumption. This is the structural fix. It touches lock
   and lifetime rules, so it needs the full review in `CODE_PATTERNS.md`.
2. **Low-first allocation while sparse.** When occupancy is low, allocate
   from the lowest free cluster, so that long-lived slots do not land high.
   This is cheaper than (1) and does not change the lifetime rules. Risks are
   allocator lock traffic and weaker per-CPU cluster locality. It is
   falsified if the high-state rate does not fall.
3. **Eager cache-only reclaim on exit.** Use this if the diagnostic confirms
   that cache-only slots pin the tail. It has the smallest scope, but it also
   addresses only one source of pinning.

Do not tune constants further until the next protocol can measure a regime rate.

## Where OpenEvolve fits

At present OpenEvolve stores evaluated candidates and samples references.
Every candidate is generation 1 on the frozen seed, so sampling a "parent" has
no effect on the next patch. Two changes would make it useful:

- **Allow lineage.** Let a candidate build on a selected, already-evaluated
  parent, so that successful mechanisms can stack.
- **Map the trade-off.** Define MAP-Elites feature dimensions, for example
  retained occupancy and worst-backend latency ratio. The archive then keeps
  the trade-off frontier instead of a single scalar ranking.

Until then, treat it as a ledger with a sampler.

## Limitations

This section is the single list of what current evidence cannot support.
Other documents link here instead of repeating it.

- **One workload**: one synthetic anonymous workload (64 MiB target,
  `usemem -O 5G`, 4 GiB guest, two vCPUs). There is no file/anonymous mix,
  fragmentation, oscillating pressure, memcg limits or multiple devices.
- **Latency includes cache effects**: first-access latency includes swap-cache
  hits, readahead, scheduling and timer cost. It is not device service time.
- **Metadata is partial**: it is one structure (mapped clusters) or requested
  bytes. Total RAM is not accounted.
- **Statistics**: there is no independent confirmation or holdout, and formal
  acceptance (`analysis.py`) stays disabled until the gates listed in
  `benchmark/<suite>/protocol.json` and `policy.json` exist.
- **Correctness**: the guests check data integrity, fork/COW, live destroy and
  swapoff. There is no lockdep, KASAN, KCSAN or fault injection.
