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

The initial integration evidence is in [the dated report](../../results/swap-standard-integration-2026-10-22/README.md).

## Prepare on the Linux worker

Run from the repository root, with the two tool checkouts under `TOOLS` and a
trusted guest-only BusyBox tree under `TEMPLATE`:

```sh
python3 benchmark/kernel/build.py --commit 744e5400b36f84b4816e3ff8531ec2dff52b474c \
  --name standard-upstream --config benchmark/config/swap-standard.config --no-instrumentation
python3 benchmark/swap-standard/prepare-image.py --src "$TOOLS" --busybox-template "$TEMPLATE"
python3 benchmark/swap-standard/run.py --build standard-upstream --backend disk --workload usemem
```

The preparer builds tools from immutable Git archives, records binary hashes,
and packages the Linux build source independently of the kernel under test.
The guest userland comes from the worker toolchain directories; the complete
image is hashed. Existing images are never overwritten. Archive old runtime
outputs before rebuilding. Images and toolchain contents remain local.

Use `--check-only` to verify inputs without booting. `--timeout` defaults to
900 seconds and is bounded at 3600. Kernel build workloads can require a
longer timeout. The common runtime lock prevents concurrent benchmark guests.
`evolve/control/state/STOP` stops the run. Failed boots and timeouts retain their
logs and results under ignored `runs/`; `started.json` also records interrupted
launches. Existing campaign budgets and protocols are not changed.

## Evidence and acceptance

A measurement requires verified kernel/config/guest hashes, complete workload
output, the intended swap device, actual swap activity, and a clean kernel log.
The build and each measured Valkey phase require their own swap activity.
usemem requires all eight workers' expected byte counts and free timings.
BGSAVE requires a successful start, completed polling and a nonempty snapshot.
Metadata requires memory fields, active device evidence and a capacity increase.
A measurement failure is retained, never silently dropped.

```sh
python3 -m unittest discover -s benchmark/swap-standard -p 'test_*.py' -v
python3 benchmark/swap-standard/summarize.py
```

Every result has `performance_accepted=false` and `calibrated=false`. Before a
candidate campaign, freeze the image, configuration, runner and parameters;
run repeated A/A measurements; define variance limits, AB/BA ordering, budget
and confirmation/holdout. The existing evolve adapters remain on their frozen
historical suites until a separately frozen campaign admits this suite.

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

## Evolve tiers

Use `evolve/.venv/bin/python evolve/loop.py swap-standard <action>`.
Actions are `plan`, `status`, `next`, `calibrate`, `reference-check`, and
`evaluate --candidate NAME --correctness PATH`. `--tier fast|slow|auto`
selects the tier; auto evaluates fast before slow. Reference checks are fast only.

| Tier | Cases | A/A pairs per case | Candidate AB/BA pairs per case |
|---|---|---:|---:|
| fast | usemem/disk, Valkey/zram, swapin/disk | 2 | 2 |
| slow | fast cases plus build/zswap and metadata/brd | 4 | 10 |

This table is the default `protocol.json` (campaign `swap-standard-2026-10-22`).
The xswap-next-2026-10-24 protocol is a different frozen file: its fast cases
are only `swapin-disk` and `swapin-zswap`, with 2 calibration pairs and 2
comparison pairs, and it defines no slow tier. The byte copy is
[protocol-revision2.json](../../results/xswap-next-2026-10-24/protocol-revision2.json),
taken from `benchmark/swap-standard/protocol-xswap-next-2026-10-24.json` at
snapshot `15bf186`. Revision 1, retained after the noisy sparse-image A/A, is
beside it. Neither copy changes the default protocol in this directory.

Protocol revision 3 is
[protocol-tcg-revision3.json](protocol-tcg-revision3.json). It is the QEMU TCG
screen for this suite's xswap swap-in cases. Revisions 1 and 2 are unchanged.
Its fast tier calibrates with 10 A/A pairs per backend and compares with 4
AB/BA pairs per backend. The noise envelope is the nearest-rank p90. The scored
ceiling is 25%. Metrics ending in `.p99_ns` are advisory. The decision
statistic is the median pair delta. The guest is 4 vCPU, 4096 MiB and a 16 GiB
preallocated scratch swap image, under TCG. A run is invalid and is rerun, up
to two replacements, when the guest reports TSC unstable or a clocksource
fallback, when wall time exceeds 1.5 times the running median of prior valid
runs of that case, or when more than 60 seconds elapse before QEMU launches.
Each attempt records host loadavg and PSI when `/proc/pressure` is present.
There is no slow tier. A passing verdict is a TCG-only screen for effects of
roughly 15–25% or larger. KVM confirmation is an open owner decision.

```sh
python3 evolve/loop.py swap-standard calibrate --tier fast \
  --protocol benchmark/swap-standard/protocol-tcg-revision3.json
python3 evolve/loop.py swap-standard evaluate --tier fast \
  --protocol benchmark/swap-standard/protocol-tcg-revision3.json \
  --candidate <name> --correctness path/to/<name>-correctness.json
```

Revision 3 belongs to its own controller campaign, `xswap-tcg-rev3-2026-10-25`, with the ledger
`evolve/swap-standard/state-xswap-tcg-rev3-2026-10-25`. Register candidates there with
`controller.py --campaign xswap-tcg-rev3-2026-10-25 new`; the correctness file must name the
candidate's commit. The baseline build name is `xs-desc-v1`. Calibration and
evaluation set `SWAP_NEXT_ACCEL=tcg`, 4 vCPU and 4096 MiB on the runner child,
ignoring the caller's accelerator and guest-size environment, and reject any
result whose accelerator is not `tcg`. A revision 3 protocol whose campaign, state directory,
or controller policy is the closed `xswap-next-2026-10-24` campaign is refused
before that ledger, budget, STOP file, candidates file, policy, or controller
check is read. Nothing starts a calibration by itself. The first calibration
waits for the owner's explicit approval of the revision 3 parameters.

Each pair uses fresh boots in alternating AB then BA order. One primary metric
per scored workload contributes equally to the geometric mean of direction-correct
ratios; all secondary metrics retain regression guards. Metadata is descriptive.
The protocol excludes the random-usemem case after its integration OOM/hang.
This matrix covers representative combinations rather than every backend/workload.

A/A sets a per-metric envelope with a 3% floor. Any metric varying by more than
20% blocks its tier. Fast admits candidates without median regressions beyond
those envelopes. Slow requires the exact fast-pass commit and fingerprint, its
own calibration, ten pairs, and paired-vector bootstrap intervals. A slow result
enters the OpenEvolve reference database only when the aggregate lower bound
exceeds the largest primary noise envelope and every guard passes. It remains
`NEEDS_REVIEW`; no result auto-promotes. `next` samples measured references and
emits a task with the frozen patch base. The baseline is never assigned a fake
measured score. A same-kernel `reference-check` exercises scoring and is excluded
from candidate admission and the database.

`--correctness` names a trusted JSON report with `candidate_commit` and boolean
`gates` for the protocol-required data/COW/concurrent-fault/swapoff/no-warning
checks. The controller separately verifies scope, parent, clean worktree,
checkpatch and immutable commit identity. Full project promotion gates remain
in the controller policy. Historical xswap candidates are held by the descriptor
lifetime review before builds or boots, including requests supplied as commit IDs.

The ignored `evolve/swap-standard/state-layout-v1/` stores the shared ledger,
budget, per-tier calibration and OpenEvolve database. Every request and resource
attempt is reserved before execution. Interrupted detailed reports are reconciled
into the ledger; attempted candidate/tier identities cannot silently rerun.
Calibration attempts cannot be repeated under the same fingerprint to pick a
better result. Both tiers share the 240-guest/4-build/8-hour campaign cap and the
runner lock; a tier needs enough remaining boots to finish before it can start.
The two-candidate limit is a ceiling, not a guarantee that both fit the boot cap.

The adapter supervises owned subprocesses directly because the OpenEvolve
thread timeout cannot terminate a synchronous guest evaluator. Parent-death,
per-process deadlines and both global/campaign STOP files stop owned execution.
The runner verifies actual image/config hashes; the adapter binds source,
protocol, build recipe and image manifests into a fingerprint checked before
each guest and analysis. Changing those inputs requires fresh calibration.
Runtime failures, diagnostics, budgets and stale/missing evidence fail closed.

## Residency-aware swap-in continuation

`protocol-xswap-swapin-2026-10-23.json` binds the independent
`xswap-swapin-2026-10-23` campaign to the repaired baseline. Pass it with
`--protocol` to the standard adapter; the original standard protocol and its
STOP state remain historical. The selected protocol has a separate ledger,
160 total guests (including auxiliary correctness runs), eight kernel builds,
and a ten-hour wall limit. Fast and slow calibration/comparison use identical
frozen images and both xswap/disk and xswap/zswap. The primary is sequential
first-touch mean latency; sequential p99 and random mean/p99 are guards.

The `correctness` workload uses verified swapped xswap PTEs, 48 children
faulting/COW-writing 16 shared target pages, full-word data checks, physical
backend swapoff while xswap remains live, reactivation, live xswap destruction,
and final empty swapoff. Disk admission also requires positive physical slot
usage before the live backend swapoff. Exact-commit debug runs complement the
standard-config proof. The workload uses 4 KiB pages and does not cover fault
injection, KCSAN or large folios.

Swapin snapshots retain xswap occupancy and `swap_ra`/`swap_ra_hit` counters.
The timed probe and its fixed sequential-then-random order are unchanged.
A calibrated result remains bounded discovery for human review.
