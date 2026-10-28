# Standard swap workloads

This suite replaces the synthetic workload as the starting point for new
performance studies. Historical suites and frozen campaign evidence remain in
place. Correctness campaigns must retain their existing data, COW and swapoff
gates; this performance suite does not replace them.

| Workload | Executable | Measurements |
|---|---|---|
| `usemem` / `usemem-rand` | pinned vm-scalability `usemem` | per-worker throughput, free latency, cgroup CPU, swap counters |
| `build` | pinned Linux source, `make -j16 vmlinux` on tmpfs | elapsed time, cgroup system/user CPU, phase swap counters |
| `redis` | pinned Valkey server and benchmark | GET RPS, GET during BGSAVE, save completion and phase swap counters |
| `metadata` | 1 TiB guest brd device, swapon | before/after memory fields and configured swap capacity |
| `swapin` | supplemental local probe | sequential/random first-touch latency and data verification |

`tools.json` fixes source revisions. `params.sh` owns workload parameters.
The common guest runs under KVM, the default accelerator, with 8 vCPUs and
8 GiB RAM. `SWAP_NEXT_ACCEL=tcg` selects QEMU TCG with 4 vCPUs and 4 GiB RAM;
`SWAP_NEXT_TCG_SMP` and `SWAP_NEXT_TCG_MEM_MIB` override that size.
Each run uses a fresh 16 GiB swap file exposed only inside the guest. Disk,
zswap, and zram are selectable. The VM has no external network interface;
Valkey uses guest loopback only. brd is reserved for metadata measurements.
Large folios are disabled for this initial protocol.

The initial integration evidence is in [the dated report](../../campaigns/swap-standard-2026-10-22/report/swap-standard-integration-2026-10-22/README.md).

## Inputs and execution

The trusted preparer pins vm-scalability, Valkey, guest sources and binary/image
hashes. Build products and images stay local. `--check-only` verifies inputs
without a guest. Image rebuilds and experiments are separate from framework
implementation. Both `campaigns/STOP` and `campaigns/<c>/STOP` always apply.

All execution belongs to an open campaign with a current machine claim. The
workflow reserves each guest before launch. The standalone runner also needs
an explicit `--run-id` and matching `--reservation`; auxiliary correctness
attempts reserve through `evolve/control/guest_budget.py`. A consumed ticket
cannot start another run. Invalid/setup-failed attempts remain spent.

## Evaluation and evolution

Use `evolve/.venv/bin/python evolve/loop.py swap-standard <action> --campaign <c>`.
Actions include `status`, `plan`, `next`, `calibrate`, `reference-check` and
`evaluate --candidate NAME --correctness PATH`. New protocols use a mechanism
probe, followed by agent-selected fast AB/BA screening. The slow tier retains
its separate owner approval. Each frozen campaign protocol owns case/run counts.

The probe records finite, protocol-allowed mechanism signals and metadata
bytes per capacity slot. Its baseline band is widened by frozen constants;
missing, reversed, noisy or incomplete evidence cannot pass. Fast admission
requires current exact candidate/tree/fingerprint probe evidence and the
agent's selection reason. The parent-to-child contribution is descriptive and
reported separately from comparisons to the campaign baseline.

A fast pass enters the exploratory population, including neutral candidates.
Advancement requires improvement above calibrated primary noise and passing
scored guards; the line's original anchor is retained. Durable briefs use the
pinned OpenEvolve population and include exact permitted parent, inspirations,
relevant failures and remaining pools. Equivalent code does not gain more
attempts merely by using a new commit.

## Frozen historical protocols

- [Original standard campaign](../../campaigns/swap-standard-2026-10-22/protocol.json).
- [Repaired xswap swap-in](../../campaigns/xswap-swapin-2026-10-23/protocol.json).
- [Xswap next](../../campaigns/xswap-next-2026-10-24/protocol.json), with its
  [retained revisions](../../campaigns/xswap-next-2026-10-24/report/).
- [TCG revision 3](../../campaigns/xswap-tcg-rev3-2026-10-25/protocol.json).

Revision 3 retains TCG, 4 vCPU/4096 MiB/16 GiB swap, 10 A/A and 4 comparison
pairs per backend, p90 calibration, 25% ceiling, median decisions and advisory
p99. Frozen older protocols retain their own cases and gates. Select them by
campaign name; closed campaigns support inspection, not execution.

## Revision 4 template

[revision4-protocol-template.json](revision4-protocol-template.json) describes
KVM, 8 vCPU/8192 MiB/16 GiB swap and the approved revision 3 statistics. Probe
cases are disk/zswap swap-in and brd metadata; latency cases are disk/zswap
swap-in. Its 36 probe and 84 fast pool ceilings total 120. Eight probes and
two fast screens require at least 105 performance guests; 15 remain for
correctness and validity attempts. Counts are ceilings and not a promise to
complete them under failures or an expired deadline.

This file is a template, not a campaign. The existing correctness guest
requires xswap interfaces and cannot certify plain mode. A future plain
correctness adapter must provide exact source/mode/backend/config evidence;
no xswap-only proof stands in for it. No real revision 4 run is claimed.

## Evidence

The runner binds source/config/image identity, complete output, intended
backend, actual swap activity and clean logs. The workflow fingerprints trusted
inputs before each attempt and analysis. Its tracked campaign ledger preserves
reservations, invalid attempts, interrupted outcomes, calibrations and
selection decisions. Raw guest logs and images remain in ignored `runs/`.
Pure unit and lifecycle fixtures start no guests.

## Limitations

- The initial `usemem-rand` zswap profile triggered memcg OOM during integration.
  It is a retained failed stress case, not an admitted scoring workload. Its
  resource profile needs separate calibration before use in a campaign.

- The initial workload sizes are adaptations to this VM, not exact replication
  of every upstream email's hardware or configuration. No comparative finding
  is inferred from an integration run.
- Memory-pressure workloads use memcg limits. Global-pressure and large-folio
  coverage require separately frozen configurations.
- The metadata delta includes VM noise and measures swapon-time allocation;
  it is not total runtime metadata or a proven bytes-per-live-slot measure.
- Valkey GET includes misses because random SET does not fill every possible
  key. BGSAVE can finish during GET; the interval includes overlap but is not
  guaranteed to be entirely concurrent.
- The optional swap-in probe includes readahead, swap-cache and timer costs.
  It is a local diagnostic, not a standardized device-latency benchmark.
- xswap performance execution requires ancestry from descriptor repair `5e84ca92`; campaign admission also requires exact-commit correctness evidence.
- These workloads provide performance coverage; they do not certify data
  integrity, concurrency, swapoff, sanitizers or upstream readiness.
