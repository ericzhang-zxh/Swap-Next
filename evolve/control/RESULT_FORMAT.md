# Raw Result Contract v1

This v1 contract supports future integration with an independent runner. A
collector implementing this full contract is not deployed. The benchmark pilot uses
a separate, narrower protocol; its output does not satisfy this contract. Workers
must not fabricate this format and present it as measurements. Synthetic fixtures generated in the test directory
validate only the analyzer; they are not empirical measurements.

## Manifest

Save manifest.json. All relative evidence paths must remain inside the same
evidence directory. Symlinks, empty files, ../, and duplicate raw files are
forbidden. Use controller protocol to query the current protocol hash. Every
gate requires candidate_commit + pass + a hash of a nonempty log; skip is not pass.

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

## Each Raw Run

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
  "latency_us": ["positive latency for every completed operation; this placeholder is not valid data"],
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

- Pair baseline/candidate by the same workload, partition, and pair_id, with identical input seeds and amounts of work.
- AB means baseline executes first; BA means the reverse. Timestamps must agree with that order.
- Use a different boot_id each time; all measurement intervals must be nonoverlapping.
- At least 10 pairs per workload per partition, with at least 5 pairs in each order.
- Seeds are unique within each partition; confirmation does not reuse discovery seeds.
- The environment is identical within each pair and throughout the report. Debug gates may use separate configurations; record the corresponding configuration/tool information in gate evidence for reviewer inspection.
- Denominators must reflect work actually completed and successfully validated. Reject timeouts, no swap activity, and zero work.
- Reject NaN/Infinity, bool values masquerading as numbers, missing fields, duplicate JSON keys, incorrect SHAs, and stale gates.

## Trust Boundary

Hashes detect file changes; they do not prove that the contents are true. The
schema’s booted_commit, gates, and counters remain input claims. Analyzer output
always sets provenance_verified=false, holdout_verified=false, and
auto_promote=false. The controller’s trusted collection channel must verify
boot/kernel image/logs/counters and review the contents associated with each
hash; candidates must not control both logs and hashes. A report is input to
review, not a signed certificate.

NEEDS_CALIBRATION: numerical thresholds have not yet been frozen.
REJECT_OR_NO_GAIN: statistical effects do not satisfy the calibrated constraints.
REVIEW_REQUIRED: numerical constraints are satisfied, but the result still does not authorize automatic merging.
