# Design

Swap Next searches for Linux swap changes that lower a measured cost without
breaking correctness. A candidate is a frozen-kernel change under that
campaign's policy: a small patch or a larger redesign of the swap path. A
benchmark boots it next to the baseline in a QEMU guest (KVM, or TCG on Grok
Bot's cloud box); OpenEvolve archives the result
and picks references for the next proposal. The proposer is the assistant in
the current session.

Each exploration direction is a campaign with its own baseline, protocol and
report in `campaigns/<c>/report/`. This document holds what every campaign shares.

## What swap costs

| Cost | Where it arises | Measured by the harness |
|---|---|---|
| Fault latency | swap cache lookup, zswap decompression, block I/O on swap-in | yes: p99 first access to a swapped PTE |
| Metadata RAM | per-slot swap table, `cluster_info`, zswap entries; for xswap the mapped part of `cluster_info` | yes: mapped clusters (xswap), requested bytes (kernel suite) |
| Physical slot use | a zswap-resident page still holds a disk slot on ordinary swap | recorded (disk sectors), not scored |
| Reclaim CPU | compression, cluster allocation, swap-out path | standard suite records cgroup system/user CPU, not reclaim-only CPU |
| Scalability | `si->lock`, cluster locks, per-CPU cluster cache | historical guests have two vCPUs; standard suite uses eight, without a scaling study |

Every campaign's primary metric is swap-in latency; metadata bytes per capacity slot
is screened in each new plain-mode probe tier and the other rows are guardrails (AGENTS.md
**Metrics**). The disabled formal policy in `evolve/control/config/policy.json`
still names throughput (see [METRICS.md](evolve/control/METRICS.md)). The new [standard suite](benchmark/swap-standard/README.md) records
usemem throughput, kernel-build time and Valkey RPS. Passing repeated A/A for
a frozen campaign protocol is recorded in that campaign's report. The default
matrix is not itself a calibrated candidate campaign;
[xswap-next-2026-10-24](campaigns/xswap-next-2026-10-24/report/REPORT.md) froze a
narrower swap-in protocol and recorded both a noisy sparse-image A/A and a
passing preallocated A/A. QEMU TCG revision 3 is closed. The prepared kbench
successor is [protocol revision 6](campaigns/xswap-tcg-kbench-2026-10-29/protocol.json).
It is not opened.

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
- **xswap Phase III** (6 patches; Baoquan He, Nhat Pham). This charges memcg only when an xswap entry gains a physical backend, instead of at slot allocation. Imported as [patches/xswap-phase3](campaigns/_unassigned/patches/xswap-phase3/README.md) on top of Phase II (`b2beda7f`); not yet measured.
- **vswap** (Nhat Pham) is a competing virtual-swap design. Attribution is
  disputed upstream ([thread](https://lists.openwall.net/linux-kernel/2026/10/12/779)).
  We take no side.

Known open items in the xswap reference: virtual capacity accounting, a
recycled integer destroy handle, and interface documentation. See
[patches/xswap-reference](campaigns/_unassigned/patches/xswap-reference/README.md).

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
  side), not means of two. A fast tier with fewer pairs is a screen; this
  bar applies to acceptance.
- **Tie every candidate to a mechanism counter.** A change should move a
  counter it targets, such as grow operations or shrink events, before
  anyone reads the end-to-end metric.
- **Do not tune constants until the metric is validated.** Tuning a
  threshold only shifts the probability of a regime the protocol cannot
  yet measure.

## Where OpenEvolve fits

The loop has variation, selection and inheritance. A candidate declares a
hypothesis and mechanism, passes scope and correctness, then enters the cheap
probe tier. The agent selects engaged, non-regressing candidates for the paired
latency screen and records its selection reason. A passing screen enters an
OpenEvolve population as exploratory evidence.

A neutral candidate may be a parent. Preserve the line's original anchor and
its best evidence; advancing a later campaign's baseline requires improvement
above calibrated noise and passing scored guards. Record parent-to-child
changes alongside cumulative baseline comparisons, so inherited mechanism
engagement is not mistaken for a new contribution. Equivalent source trees do
not get additional attempts through new commit messages.

`ProgramDatabase` keeps eligible parents and inspirations. `PromptSampler`
renders briefs containing the exact permitted parent, cumulative patch,
mechanism, probe signals, latency evidence, relevant failures, line history and
remaining pools. Sampling receipts and the actual parent choice are tracked.
Only the sampled parent or the frozen baseline can be chosen. Scope checks
cover the full baseline-to-child diff. The assistant proposes and edits;
OpenEvolve's LLM providers and autonomous evaluator are not used.

The archive retains history when correctness fails, later evidence regresses,
or the fingerprint changes. Such records cannot silently remain eligible
parents. Fast scores from different measurement identities are not one ranking.
MAP-Elites dimensions remain deferred; one island suffices for the first loop.

Each campaign owns policy, protocol, ledger, candidate records, patches,
population and report in `campaigns/<c>/`. Only raw runs, images and locks stay
local. A layout migration and a machine's evidence import are separate steps.
The approved design and review corrections are in
[the framework specification](docs/superpowers/specs/2026-10-27-campaigns-cascade-evolution-design.md)
and [the evolution review](docs/superpowers/specs/2026-10-27-evolution-review.md).

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
  `benchmark/<suite>/protocol.json` and `policy.json` exist. The policy's
  `required_gates` include KCSAN and fault injection, which no harness runs, so
  no candidate can be promoted yet. Screens use their protocol's
  `required_correctness_gates`.
- **Correctness**: historical kernel and xswap guests check data integrity,
  fork/COW, live destroy and swapoff. Those checked-in suites do not run
  lockdep, KASAN, KCSAN or fault injection. The xswap-next-2026-10-24 report
  records targeted KASAN and lockdep builds; the KASAN and debug configs are in
  `benchmark/config/`. KCSAN and fault injection remain uncovered.

## Revision 4 readiness

The revision 4 template describes the approved KVM plain-mode measurements. It
is not an open campaign or execution evidence. The current correctness guest
requires xswap interfaces, so plain-mode full correctness remains an explicit
runtime capability gap. No plain proof is inferred from an xswap-only run.
Framework validation uses guest-free end-to-end tests; real calibration and
performance evaluation are separate authorized work.

## TCG kbench revision 6

[The revision 6 protocol](campaigns/xswap-tcg-kbench-2026-10-29/protocol.json)
is the TCG measurement on the kbench setup. It is prepared and not opened.
Swap-in and correctness run in xswap mode on `kb-xs-desc-v1` (`5e84ca92`),
not the plain `744e5400` baseline in the revision 4 template. The probe tier
adds a plain brd metadata guest because that gate expects the brd device
alone. Fast screening is disk and zram-64k swap-in. The build workload is
excluded. `vm.page-cluster` stays at the kernel default 3. Builds, the guest
image, and guests run on grok-cloud. The parameter table lives in the protocol.
