# Standard benchmark integration — 2026-10-22

[Visual review](explainer.html) · [Published review](https://ericzhang-zxh.github.io/Swap-Next/swap-standard-integration-2026-10-22/)

The new performance suite runs usemem, a kernel build on tmpfs, and Valkey
GET/BGSAVE in isolated KVM guests. Confidence in basic execution is high:
all three completed with workload-specific swap activity and clean kernel
logs. A failed replay on the same frozen artifacts would change this finding.

| Workload | Backend | Outcome | Guest seconds |
|---|---|---|---|
| usemem | disk | pass | 58.53 |
| build | zswap | pass | 164.63 |
| redis | zram | pass | 44.52 |
| metadata | brd | pass | 7.01 |
| swapin | disk | pass | 34.52 |
| usemem-rand | zswap | fail | 128.56 |

The table covers the final guest image. Guest seconds include boot and setup;
they are integration timings, not comparative workload performance. All raw
metrics, statuses and serial-log hashes are in [validation.json](validation.json).
The nine development/integration boots are all retained there, including both
failures; local raw evidence lives under `benchmark/swap-standard/runs/`.

## Failures and corrections

- The first disk usemem guest completed, but its parser rejected the reported
  byte count. Pinned upstream `do_unit()` counts allocation as `bytes/8` plus
  one full pass. The parser was corrected to require 9/8 of the allocation per
  worker. The original failed result and separate passing reanalysis remain;
  the final-image rerun passed directly.
- Random usemem with eight 1 GiB workers under a 4 GiB memcg triggered three
  guest OOM kills. The guest was explicitly terminated after the diagnostics,
  because usemem's synchronization could wait for killed children. Its 128.56
  seconds is an interrupted run, not a completed measurement. This profile
  remains outside the admitted scoring workload set. The runner now detects
  live kernel diagnostics and stops such a run automatically.

## What changed

- Added a pinned, hashed guest root with tools rebuilt from immutable source
  archives, complete build-tool data, and guest-only loopback for Valkey.
- Added bounded execution, shared guest locking, stop handling, source snapshots,
  raw-log hashes, and a summary that retains failures and incomplete attempts.
- Required all usemem workers and byte counts, active backend evidence,
  per-phase swap activity, complete BGSAVE evidence, and metadata fields plus
  the exact 1 TiB brd capacity. Early kernel diagnostics fail the measurement.
- Recorded swapon memory deltas and their capacity-slot ratio. This replaces
  mapped-cluster count as the new suite's metadata observation.
- Updated project entry points for new performance studies. Frozen historical
  evaluator protocols and evidence remain unchanged.

## Checks

- 14 parser regression tests and 4 repository layout tests passed.
- Python compilation, shell syntax checks and Git whitespace checks passed.
- The upstream test kernel was built in the existing unprivileged namespace
  launcher. Tools, image hashes and kernel commit are recorded in the run data.
- Final-image usemem/disk, kernel-build/zswap, Valkey/zram, metadata/brd and
  supplemental swap-in/disk guests passed. No kernel source was changed.

## Limitations and next step

These are integration checks. There is no completed repeated A/A calibration,
AB/BA candidate comparison, confirmation/holdout, or performance acceptance.
One tested backend per main workload does not validate the whole matrix.
The randomized usemem profile must be revised and calibrated separately.
The historical evolve adapters have not been retargeted to this suite; admitting
it requires a frozen new campaign protocol. xswap execution remains held pending
resolution of the existing descriptor lifetime review. Other measurement limits
are in [the suite README](../../benchmark/swap-standard/README.md#limitations).
