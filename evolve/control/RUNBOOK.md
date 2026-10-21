# Execution runbook

The authoritative agent workflow is the repository
[closed-loop-evolve skill](../../.agents/skills/closed-loop-evolve/SKILL.md).
Read its [Swap Next binding](../../.agents/skills/closed-loop-evolve/references/swap-next.md)
for current controller/adapter commands, state recovery, calibration and stop behavior.

Use [benchmark setup](../../benchmark/SETUP.md) for environment preparation and
[CODE_PATTERNS.md](CODE_PATTERNS.md) for kernel invariants. Verify the designated
Linux worker, pinned source, KVM access and actual baseline guest behavior before
interpreting measurements. Device access or static tests alone are insufficient.

State, builds, worktrees and VM images are ignored runtime artifacts. Historical
results are not validation of a relocated harness. Discovery is separate from
formal statistical acceptance; missing gates stay explicit and no promotion is
automatic. STOP controls owned runner stages, not arbitrary host processes.
