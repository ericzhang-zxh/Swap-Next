# Design

Swap Next searches for Linux swap changes that lower a measured cost without
breaking correctness. A candidate is one small patch on a frozen kernel; a
benchmark boots it next to the baseline in KVM; OpenEvolve archives the result
and picks references for the next proposal. The proposer is the assistant in
the current session.

Each exploration direction is a campaign with its own baseline, protocol and
report in `results/`. This document holds what every campaign shares.

## What swap costs

| Cost | Where it arises | Measured by the harness |
|---|---|---|
| Fault latency | swap cache lookup, zswap decompression, block I/O on swap-in | yes: p99 first access to a swapped PTE |
| Metadata RAM | per-slot swap table, `cluster_info`, zswap entries; for xswap the mapped part of `cluster_info` | yes: mapped clusters (xswap), requested bytes (kernel suite) |
| Physical slot use | a zswap-resident page still holds a disk slot on ordinary swap | recorded (disk sectors), not scored |
| Reclaim CPU | compression, cluster allocation, swap-out path | standard suite records cgroup system/user CPU, not reclaim-only CPU |
| Scalability | `si->lock`, cluster locks, per-CPU cluster cache | historical guests have two vCPUs; standard suite uses eight, without a scaling study |

A campaign picks one row as its primary metric and keeps the others as
guardrails. The formal policy in `evolve/control/config/policy.json` names
throughput. The new [standard suite](benchmark/swap-standard/README.md) records
usemem throughput, kernel-build time and Valkey RPS. Its parameters still need
repeated A/A calibration before they can define a candidate campaign.

## Upstream landscape

- **Base**: `linux/` is pinned at `744e5400` (v7.4 merge window). The swap
  table (`mm/swap_table.h`) is already upstream there.
- **xswap Phase I v4** (14 patches; Baoquan He, Chris Li). This adds a virtual
  swap device with no backing store, held in zswap. It keeps `cluster_info` in
  a lazily mapped `VM_SPARSE` area, grows it at 85% use towards a 65% target,
  and unmaps a free tail once use drops to 50%. It also adds sysfs
  create/destroy and debugfs counters.
- **xswap Phase II v1** (12 patches; includes Nhat Pham's I/O work). This gives
  each xswap slot an optional physical backend. Pages that zswap refuses are
  written to disk, the backend can be swapped off, cache-only physical slots
  are reclaimed, and THP swap-in is enabled.
- **Phase III** is not imported and has not been reviewed.
- **vswap** (Nhat Pham) is a competing virtual-swap design. Attribution is
  disputed upstream ([thread](https://lists.openwall.net/linux-kernel/2026/10/12/779)).
  We take no side.

Known open items in the xswap reference: virtual capacity accounting, a
recycled integer destroy handle, and interface documentation. See
[patches/xswap-reference](patches/xswap-reference/README.md).

## Measurement principles

- **Validate the metric before comparing candidates.** Run A/A on the
  identical kernel first. If A/A splits into regimes or drifts, the metric
  measures something other than the code. Fix the measurement before
  searching.
- **Prefer state over snapshots.** A single end-of-run value is valid only if
  the system has reached a steady state. Record counters across phases and
  check that the scored value is stable.
- **Report a rate when the outcome is discrete.** If boots fall into
  regimes, compare regime frequencies over enough boots (at least ten per
  side), not means of two.
- **Tie every candidate to a mechanism counter.** A change should move a
  counter it targets, such as grow operations or shrink events, before
  anyone reads the end-to-end metric.
- **Do not tune constants until the metric is validated.** Tuning a
  threshold only shifts the probability of a regime the protocol cannot
  yet measure.

## Where OpenEvolve fits

At present OpenEvolve stores evaluated candidates and samples references.
Every candidate is generation 1 on the frozen seed, so sampling a "parent" has
no effect on the next patch. Two changes would make it useful:

- **Allow lineage.** Let a candidate build on a selected, already-evaluated
  parent, so that successful mechanisms can stack.
- **Map the trade-off.** Define MAP-Elites feature dimensions, for example
  metadata occupancy and worst-backend latency ratio. The archive then keeps
  the trade-off frontier instead of a single scalar ranking.

Until then, treat it as a ledger with a sampler.

## Limitations

This section is the single list of what the harness cannot measure. Other
documents link here instead of repeating it.

- **Historical suites**: one synthetic anonymous workload (64 MiB target,
  `usemem -O 5G`, 4 GiB guest, two vCPUs). There is no file/anonymous mix,
  fragmentation, oscillating pressure, memcg limits or multiple devices in those
  frozen suites. The standard suite adds usemem, kernel build and Valkey under
  memcg pressure; its current limits are documented in its README.
- **Latency includes cache effects**: first-access latency includes
  swap-cache hits, readahead, scheduling and timer cost. It is not device
  service time.
- **Metadata is partial**: it is one structure (mapped clusters) or requested
  bytes. Total RAM is not accounted.
- **Statistics**: there is no independent confirmation or holdout, and formal
  acceptance (`analysis.py`) stays disabled until the gates listed in
  `benchmark/<suite>/protocol.json` and `policy.json` exist.
- **Correctness**: the guests check data integrity, fork/COW, live destroy and
  swapoff. There is no lockdep, KASAN, KCSAN or fault injection.
