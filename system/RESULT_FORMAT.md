# 原始结果契约 v1

此契约用于未来独立 runner 接入。当前没有部署采集器；不要由 worker 编造该格式
来冒充测量。测试目录生成的 synthetic fixture 仅验证分析器，不是实测。

## Manifest

保存 manifest.json；所有 evidence 的相对路径必须留在同一证据目录内，不允许
符号链接、空文件、../、重复 raw 文件。使用 controller protocol 查询当前协议 hash。
每个 gate 需要 candidate_commit + pass + 非空日志哈希；skip 不等于 pass。

```json
{
  "schema_version": 1,
  "experiment_id": "trial-001-eval-001",
  "execution_kind": "isolated_guest",
  "protocol_sha256": "<controller protocol 输出>",
  "baseline_commit": "<pinned upstream commit>",
  "candidate_commit": "<候选完整 SHA>",
  "environment": {
    "compiler_sha256": "<sha256>",
    "config_sha256": "<sha256>",
    "rootfs_sha256": "<sha256>",
    "suite_sha256": "<sha256>",
    "machine_profile_sha256": "<sha256>"
  },
  "gates": {
    "<policy 中每一个 gate>": {
      "status": "pass",
      "candidate_commit": "<候选完整 SHA>",
      "evidence": {"path": "gates/example.log", "sha256": "<sha256>"}
    }
  },
  "planned_run_ids": ["<执行前冻结的全部 run ID，包含所有尝试>"],
  "runs": [{"path": "runs/example.json", "sha256": "<sha256>"}]
}
```

## 每个 raw run

```json
{
  "schema_version": 1,
  "status": "completed",
  "experiment_id": "trial-001-eval-001",
  "run_id": "unique-run-001",
  "boot_id": "unique-boot-001",
  "variant": "baseline",
  "kernel_commit": "<完整 SHA>",
  "booted_commit": "<独立验证的实际 boot SHA>",
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
  "latency_us": ["每个完成操作的正数延迟；此占位符不是有效数据"],
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

- baseline/candidate 按同 workload、partition、pair_id 配对，输入 seed 与工作量相同。
- AB 表示 baseline 先执行，BA 反之，时间戳必须与顺序一致。
- 每次使用不同 boot_id；所有测量区间不重叠。
- 每 workload 每分区至少 10 对、两种顺序各至少 5 对。
- 每分区内 seed 唯一；confirmation 不复用 discovery 的 seed。
- environment 在 pair 及整个报告内相同；debug gates 可以单独配置，
  对应配置/工具信息保存在 gate evidence 中，由 reviewer 检查。
- 分母必须反映真正完成且校验成功的工作。超时、无 swap 活动、零工作均拒绝。
- 不允许 NaN/Infinity、bool 冒充数字、缺字段、重复 JSON key、错 SHA 或 stale gate。

## 信任边界

哈希只能发现文件变化，不能证明内容是真的。schema 中的 booted_commit、
gates 和计数仍是输入声明。分析器输出始终 provenance_verified=false、
holdout_verified=false、auto_promote=false。必须由 controller 的可信采集
通道验证 boot/kernel image/日志/计数，并审核 hash 对应的内容；不能让候选同时
控制日志和 hash。报告是 review 输入，不是签名证书。

NEEDS_CALIBRATION：还没冻结数值阈值。
REJECT_OR_NO_GAIN：统计效果没有达到已校准约束。
REVIEW_REQUIRED：数值约束满足，但仍不是可自动合并的结论。
