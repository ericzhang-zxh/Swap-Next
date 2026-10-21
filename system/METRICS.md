# 指标与验收协议 v1

## 不做单一混合总分

每个 campaign 冻结一个主目标，其他指标是逐 workload 的回归约束。
初始主目标为 **有效操作吞吐 ops/s**；延迟导向任务应建立新的冻结协议，
不能跑完再挑最漂亮的指标。当前门槛值为 null，刻意阻止未经校准的 ACCEPT。

| 指标 | 定义 | 方向 |
|---|---|---|
| throughput_ops_s | 成功完成且通过数据校验的操作数 / 稳态 elapsed_s | 高 |
| latency_p99_us | 所有操作延迟的 nearest-rank p99，单位 µs | 低 |
| cpu_ns_per_op | CPU core-seconds × 1e9 / completed operations | 低 |
| io_bytes_per_op | 后端 read+write bytes / completed operations | 低 |
| metadata_bytes_per_slot_peak | 同时采样的 attributable bytes / occupied slots 的最大值 | 低 |

latency 样本在 v1 要求覆盖所有完成操作；不是把单个运行的 p99 再当原始样本。
元数据必须可归因于 swap；不能拿整个 guest RSS 冒充。
另记录 swap-in/out 页数、逻辑数据量、压缩比、occupancy、PSI、p50/p95。
其中不在当前 raw schema 的指标可保留在扩展日志，不能擅自替换现有字段。

## 工作负载覆盖

discovery 和独立 confirmation 分区分别覆盖：
1. anon_disk：无 zswap 的匿名页回收/换入；
2. anon_zswap：压缩命中与受控回写；
3. fragmented_swap：固定预置碎片状态；
4. mixed_file_anon：文件页与匿名页竞争，防止把代价转移给 page cache。

有了 xswap 实现基线后建立新的 campaign，增加逻辑身份、后端归属和计费专测。
当前 mainline 基线无 xswap，不能将 xswap 路径记为通过。
每个 workload 的操作、输入、duration、负载强度、warmup 在 suite 中冻结。

## 统计

- 每个 workload、每个分区至少 10 个独立 paired runs，AB/BA 各至少 5 对。
- baseline 与 candidate 使用相同环境哈希、config/rootfs/compiler/suite、输入和 seed。
- 每个 measurement run 使用独立 boot ID，避免同一次启动重复计作独立重复。
- 固定预先声明的采样量，不因中间结果显著就提前停止。
- 对 paired relative effects 做固定种子的 bootstrap，给 95% CI；
  所有 workload/metric/partition 做 Bonferroni 调整；每端至少要求 30 个期望 bootstrap 尾部样本（默认 64,000 次重采样）。
  percentile-bootstrap 的覆盖率是近似的，不是形式保证，须用 A/A 校准其实际表现。
- primary 的调整后 CI 下界需超过冻结的实际收益阈值；
  所有 guardrail 的调整后 CI 下界不得低于负的允许回归值。
- 报告每个 workload，不用平均值遮盖单项退化。
- 自适应搜索的多候选选择偏差不由上述 CI 解决：独立 confirmation 及最终
  controller-only holdout 必须保留，holdout 不能给 proposer 反复调参。
- 虚拟化结果只代表该受控环境，不外推为裸机硬件结论。

## 校准流程

先部署可信 runner，采集 baseline-vs-baseline 的 A/A，估计噪声和可复现性。
由 owner/controller 根据噪声与实际需求固定 min_gain/max_regression，
版本化 policy 后才置 thresholds_calibrated=true；旧数据不跨协议复用。
没有校准值会得到 NEEDS_CALIBRATION，而不是采用随意的 3%/5%“通用标准”。

## 正确性 gates

config/policy.json 列出 GCC 构建矩阵、sparse、checkpatch、boot identity、
数据 roundtrip、fork/COW、concurrent fault、swapoff、故障注入、memcg、
large folio、LOCKDEP/KASAN/KCSAN 及新 warning 检查。
各 sanitizer 在独立配置运行；不要声称都在同一 benchmark kernel 中测量。
gate 缺失、skip、timeout 或无证据均不通过；现有 baseline 失败要单独调查，
不能把同样失败就算 candidate pass。
