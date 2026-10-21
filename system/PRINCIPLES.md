# 原则与强边界

## 正确性优先，性能其次

数据正确、引用一致、无 use-after-free、无 double free、无锁反转、
charge/uncharge 对称是硬门槛。不能用吞吐提升抵消其中任意失败。
不要把“没有崩溃”“成功退出”“编译成功”描述成正确性证明。

## 三种边界，不能混为一谈

- **指令边界**：AGENTS、任务契约要求 worker 不越界。
- **机械门槛**：diff allowlist、大小预算、输入校验、固定配置哈希拒绝不合规结果。
- **安全边界**：独立 VM/容器/权限主体、无凭据、无主机写挂载、网络及资源隔离。

控制器提供前两层；Evolve pilot 另提供 namespace 构建和 KVM guest 隔离，仍需在部署环境验证。相同 Unix 用户可篡改规则与证据，
所以 worktree/JSON/hash 都不是对恶意 agent 的隔离或真实性证明。
不要让 host runner 执行来自候选的 Makefile、脚本、模型命令或任意 shell。

## 范围

默认允许改 swap 核心的少量指定文件；以 config/policy.json 的精确清单为准。
mm/memory.c、mm/vmscan.c、memcontrol、架构代码、Kconfig、Makefile、UAPI、
全局 VM 策略不属于初始自动搜索范围。需要时由 controller 发起新范围任务，
不能由候选自行放宽 allowlist。
允许新增命名受限的回归测试源文件，但它们不替代不可变的 golden 验收套件。

## 不变量

- entry 与 slot、folio、压缩对象的归属必须明确。
- 仍可被 PTE、cache 或 in-flight I/O 使用的资源不得提前释放。
- 发布映射之前完整初始化；拆除后遵守目标代码的生命周期协议。
- 每条失败出口都撤销已经完成的分配/引用/计费动作。
- RCU 不替代对象状态验证、folio 锁或正确引用获取。
- reclaim 路径的分配上下文不得引入回收递归。
- 大 folio、部分失败、swapoff、memcg 与并发 fault 都要列入影响分析。

## 防止为了得分而改题

禁止删除工作量、提前结束、减少实际回收、隐藏错误、修改随机种子集、
篡改统计、阈值、基线、计时区间或 holdout。不允许用 agent 写的成绩摘要
替代 raw 测量。保存失败和超时；不得只筛选较快样本。

## 权限与动作

只有 controller/owner 可以改变策略和基线。没有 host root、凭据、发布、
邮件、push、reboot、修改 host swap/内核的授权。默认无自动合并。
候选可用局部小 commit 表达完整改动；不自动添加 DCO 签名。
