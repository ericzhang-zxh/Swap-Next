# Formal acceptance protocol v1

This protocol is implemented by `analysis.py` (`controller.py analyze`) and is
**disabled**: `policy.json` has `runtime_enabled: false`, null thresholds, and
no collector that produces this format. The discovery suites in `benchmark/`
use their own narrower protocols. Their reports do not satisfy this one.
Test fixtures exercise only the analyzer.

## Metrics

Each campaign freezes one primary metric before running; the others are
guardrails checked per workload. Policy v1 makes throughput primary.

| Metric | Definition | Better |
|---|---|---|
| `throughput_ops_s` | validated completed operations / steady-state `elapsed_s` | higher |
| `latency_p99_us` | nearest-rank p99 over every operation latency | lower |
| `cpu_ns_per_op` | CPU core-seconds × 1e9 / completed operations | lower |
| `io_bytes_per_op` | backend read + write bytes / completed operations | lower |
| `metadata_bytes_per_slot_peak` | max attributable bytes / occupied slots, from simultaneous samples | lower |

Latency uses every operation's sample, not per-run p99 values. Metadata
must be attributable to swap; guest RSS does not count. Also record:

- swap-in/out pages
- logical data volume
- compression ratio
- occupancy
- PSI
- p50 and p95

## Workloads and partitions

Each of the two partitions, discovery and confirmation, runs four workloads:

- `anon_disk`
- `anon_zswap` (compression hits and controlled writeback)
- `fragmented_swap` (a fixed preconditioned state)
- `mixed_file_anon` (catches costs shifted into the page cache)

A final holdout is run by the controller only and is never shown to proposers.

## Statistics

- **Pairs**: at least 10 independent pairs per workload and partition, with at
  least 5 in AB order and 5 in BA. Each run gets its own boot, and
  measurement intervals do not overlap.
- **Identical inputs**: within a pair, the environment hashes, config, rootfs,
  compiler, suite, seed and amount of work are identical. Seeds are unique
  within a partition, and confirmation does not reuse discovery seeds.
- **Fixed sample size**: no early stopping.
- **Intervals**: paired relative effects with a fixed-seed percentile
  bootstrap (64,000 resamples, at least 30 expected tail samples per end),
  at 95% after Bonferroni correction across workloads, metrics and partitions.
- **Accept** only when the primary metric's adjusted lower bound exceeds the
  frozen minimum gain and every guardrail's lower bound stays above its
  maximum regression.
- **Report per workload.** An average does not hide a regression.

The bootstrap does not correct for selection across many searched candidates.
Confirmation and the holdout do.

## Calibration

Run baseline-vs-baseline A/A on the deployed runner, set `min_gain` and
`max_regression` from the observed noise and practical need, version the
policy, then set `thresholds_calibrated: true`. Until then the analyzer returns
`NEEDS_CALIBRATION`. Calibration data is never carried across protocols.

## Gates

Every gate in `policy.json` `required_gates` must report `pass` for the exact
candidate commit, with the hash of a non-empty log. Skipped, timed-out,
missing and unsupported gates fail. Each sanitizer runs with its own config.
A failure shared with the baseline still fails the candidate; investigate it
separately.

## Result format

`manifest.json`, with every evidence path relative and inside the evidence
directory (no symlinks, `..`, empty or reused files):

```json
{
  "schema_version": 1,
  "experiment_id": "trial-001-eval-001",
  "execution_kind": "isolated_guest",
  "protocol_sha256": "<controller protocol output>",
  "baseline_commit": "<pinned upstream commit>",
  "candidate_commit": "<full candidate SHA>",
  "environment": {
    "compiler_sha256": "<sha256>",
    "config_sha256": "<sha256>",
    "rootfs_sha256": "<sha256>",
    "suite_sha256": "<sha256>",
    "machine_profile_sha256": "<sha256>"
  },
  "gates": {
    "<every gate in the policy>": {
      "status": "pass",
      "candidate_commit": "<full candidate SHA>",
      "evidence": {"path": "gates/example.log", "sha256": "<sha256>"}
    }
  },
  "planned_run_ids": ["<all run IDs frozen before execution, including every attempt>"],
  "runs": [{"path": "runs/example.json", "sha256": "<sha256>"}]
}
```

Each raw run:

```json
{
  "schema_version": 1,
  "status": "completed",
  "experiment_id": "trial-001-eval-001",
  "run_id": "unique-run-001",
  "boot_id": "unique-boot-001",
  "variant": "baseline",
  "kernel_commit": "<full SHA>",
  "booted_commit": "<independently verified actual boot SHA>",
  "environment": {"compiler_sha256": "...", "config_sha256": "...", "rootfs_sha256": "...", "suite_sha256": "...", "machine_profile_sha256": "..."},
  "partition": "discovery",
  "workload": "anon_disk",
  "pair_id": "pair-001",
  "order": "AB",
  "seed": 123,
  "started_unix": 1000000,
  "finished_unix": 1000030,
  "attempted_operations": 1000,
  "completed_operations": 1000,
  "elapsed_s": 20,
  "cpu_core_seconds": 10,
  "latency_us": ["one positive value per completed operation"],
  "backend_read_bytes": 4096000,
  "backend_write_bytes": 4096000,
  "metadata_samples": [{"attributable_bytes": 8192, "occupied_slots": 1024}],
  "swapout_pages": 1024,
  "swapin_pages": 1024,
  "data_mismatches": 0,
  "timeouts": 0,
  "kernel_warnings": 0
}
```

The analyzer rejects the following:

- **Bad values**: NaN/Infinity, booleans used as numbers, duplicate JSON keys,
  missing fields, malformed SHAs.
- **Inconsistent runs**: stale gates, runs whose order contradicts their
  timestamps, incomplete work, and runs with no swap activity.

## Trust boundary

Hashes detect changed files; they do not make the contents true.
`booted_commit`, gates and counters are claims made by the collector.
The analyzer therefore always reports `provenance_verified=false`,
`holdout_verified=false` and `auto_promote=false`. Its verdicts are:

- `NEEDS_CALIBRATION`: thresholds are not frozen.
- `REJECT_OR_NO_GAIN`: the effects miss the calibrated bounds.
- `REVIEW_REQUIRED`: the bounds are met. A human reviews before any merge.
