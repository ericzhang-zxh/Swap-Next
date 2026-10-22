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
The common guest has 8 vCPUs and 8 GiB RAM. Each run uses a fresh 16 GiB swap
file exposed only inside KVM. Disk, zswap, and zram are selectable. The VM has
no external network interface; Valkey uses guest loopback only. brd is reserved
for metadata measurements. Large folios are disabled for this initial protocol.

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
- xswap execution is held pending resolution of the descriptor lifetime review.
- These workloads provide performance coverage; they do not certify data
  integrity, concurrency, swapoff, sanitizers or upstream readiness.
