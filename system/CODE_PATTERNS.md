# Code patterns：让差异容易解释、审查与回滚

## 每次只有一个假设

先记录触发条件、已有 profile、预期热点及可能付出的代价，再改代码。
以小差异修复或优化；初始默认不做新框架、大重构、全局替换与格式清洗。
遵循目标文件既有风格及 Documentation/process/coding-style.rst。

## 所有权表（每个候选必须填写）

| 资源 | 谁创建/持有 | 何时发布 | 何时释放 | 保护机制 |
|---|---|---|---|---|
| folio | 待填写 | 待填写 | 待填写 | folio lock/ref |
| swap entry/slot | 待填写 | 待填写 | 待填写 | 目标版本实际锁 |
| 压缩对象 | 如涉及 | 如涉及 | 如涉及 | 如涉及 |
| memcg charge | 如涉及 | 如涉及 | 如涉及 | 如涉及 |

## 常见可接受模式

- 将错误处理集中到语义清楚的 cleanup 标签，按取得资源的逆序释放。
- 锁外做允许的昂贵准备，锁内重检共享状态；不能盲目移动分配或 I/O。
- 使用现有引用、锁、RCU helpers；给出锁顺序和对象存活依据。
- 在 API 边界保留原有错误返回与 accounting，处理部分成功。
- 复杂状态转换解释“为什么”，不逐句复述 C。
- 构建产物放 O= 外部目录，源 worktree 不产生隐藏临时文件。

## 必须拒绝的“优化”

- 为减少 contention 而删除锁/引用计数，却没有新的正确性论证。
- 用 READ_ONCE/WRITE_ONCE 替代所需的同步或 lifetime 管理。
- 将无法分配改成虚假成功；吞掉 I/O 错误或 bypass memcg。
- 简化路径时移除 large-folio、swapoff、NOFS/NOIO 或失败处理。
- 修改测试/统计让回归看不见，或加入 benchmark 名称特判。
- 在源码中硬编码运行机器、种子、测试路径或评测 ID。
- 为减少 warning 而禁用 sanitizer、assertion 或调低 warning flags。

## review 输出

每个候选说明：问题/证据、最小改变、invariants、锁与失败路径、
覆盖/未覆盖测试、逐 workload 收益/退化、可回滚 commit。
对于 bug，遵循 upstream coding-assistants.rst 的复现与验证流程。
不添加 Signed-off-by；未来提交由 owner 负责 DCO 和工具使用披露。
