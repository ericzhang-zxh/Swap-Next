# Metrics and Acceptance Protocol v1

## No Single Composite Score

Each campaign freezes one primary objective; other metrics serve as regression
constraints for each workload. The initial primary objective is **valid operation
throughput in ops/s**. Latency-oriented tasks require a new frozen protocol;
never choose the most favorable metric after the run. Current thresholds are
null, intentionally preventing an uncalibrated ACCEPT.

| Metric | Definition | Direction |
|---|---|---|
| throughput_ops_s | Successfully completed operations that pass data validation / steady-state elapsed_s | Higher |
| latency_p99_us | Nearest-rank p99 of all operation latencies, in µs | Lower |
| cpu_ns_per_op | CPU core-seconds × 1e9 / completed operations | Lower |
| io_bytes_per_op | Backend read+write bytes / completed operations | Lower |
| metadata_bytes_per_slot_peak | Maximum attributable bytes / occupied slots from simultaneous samples | Lower |

In v1, latency samples must cover every completed operation; per-run p99 values
are not raw latency samples. Metadata must be attributable to swap; total guest
RSS is not a substitute. Also record swap-in/out page counts, logical data
volume, compression ratio, occupancy, PSI, and p50/p95. Metrics absent from the
current raw schema may be retained in supplementary logs; they must not replace
existing fields without authorization.

## Workload Coverage

The discovery and independent confirmation partitions each cover:

1. anon_disk: anonymous-page reclaim/swap-in without zswap;
2. anon_zswap: compression hits and controlled writeback;
3. fragmented_swap: a fixed, preconfigured fragmentation state;
4. mixed_file_anon: competition between file and anonymous pages, to prevent shifting costs to the page cache.

Once an xswap implementation baseline exists, establish a new campaign with
dedicated tests for logical identity, backend ownership, and accounting. The
current mainline baseline has no xswap; xswap paths cannot be reported as passing.
Freeze each workload’s operations, inputs, duration, load intensity, and warmup
in the suite.

## Statistics

- At least 10 independent paired runs per workload per partition, with at least 5 pairs each in AB and BA order.
- Baseline and candidate use the same environment hashes, config/rootfs/compiler/suite, inputs, and seeds.
- Each measurement run uses an independent boot ID; repeated measurements from one boot do not count as independent repetitions.
- Use a fixed, predeclared sample size; do not stop early because interim results are significant.
- Bootstrap paired relative effects with a fixed seed to obtain 95% CIs. Apply Bonferroni adjustment across all workloads/metrics/partitions. Require at least 30 expected bootstrap tail samples at each end (64,000 resamples by default). Percentile-bootstrap coverage is approximate, not a formal guarantee; calibrate its actual behavior with A/A runs.
- The primary metric’s adjusted CI lower bound must exceed the frozen practical-gain threshold. Every guardrail’s adjusted CI lower bound must be no lower than the negative allowed regression.
- Report each workload; do not hide individual regressions behind averages.
- These CIs do not resolve selection bias from adaptive search over multiple candidates. Preserve independent confirmation and a final controller-only holdout; do not expose the holdout to proposers for repeated tuning.
- Virtualized results describe only that controlled environment; do not extrapolate them to bare-metal hardware.

## Calibration Procedure

First deploy a trusted runner and collect baseline-vs-baseline A/A measurements
to estimate noise and reproducibility. The owner/controller freezes
min_gain/max_regression based on noise and practical requirements, versions the
policy, and only then sets thresholds_calibrated=true. Do not reuse old data
across protocols. Missing calibration values produce NEEDS_CALIBRATION, rather
than applying arbitrary 3%/5% “universal standards.”

## Correctness Gates

config/policy.json lists the GCC build matrix, sparse, checkpatch, boot identity,
data roundtrip, fork/COW, concurrent fault, swapoff, fault injection, memcg,
large folio, LOCKDEP/KASAN/KCSAN, and new-warning checks. Run each sanitizer with
its own configuration; do not claim that all are measured in the same benchmark
kernel. A missing, skipped, timed-out, or unsupported-by-evidence gate does not
pass. Investigate existing baseline failures separately; the same failure in
baseline and candidate does not make the candidate pass.
