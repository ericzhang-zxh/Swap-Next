# Swap Next contributor contract

## Read first

1. [README.md](README.md) and [DESIGN.md](DESIGN.md): purpose, cost model, measurement principles.
   Read the active campaign's report in `results/` for its findings and next steps.
2. [evolve/control/PRINCIPLES.md](evolve/control/PRINCIPLES.md): scope, invariants,
   trust boundary, permissions.
3. [evolve/control/CODE_PATTERNS.md](evolve/control/CODE_PATTERNS.md): kernel code
   taste. Use [kernel-patch-review](.agents/skills/kernel-patch-review/SKILL.md)
   to review patches.
4. The active policy (`evolve/control/config/policy.json` or `campaigns/<c>/policy.json`).
5. `linux/Documentation/process/coding-assistants.rst` before kernel work.

Run campaigns with [closed-loop-evolve](.agents/skills/closed-loop-evolve/SKILL.md), and explain
finished ones for review with [explaining-campaign-results](.agents/skills/explaining-campaign-results/SKILL.md).
Loading that skill does not authorize running or publishing experiments.

## Rules

- **Where work runs**: kernel builds, sparse and guests run on the Linux worker,
  never the controller laptop.
- **Source trees**: never modify the `linux/` submodule. Create candidate
  worktrees with `evolve/control/controller.py`.
- **Workers**: a worker executes one assigned hypothesis. It does not delegate,
  change scope or the evaluator, or publish.
- **Evidence**: missing evidence is a failure, never a pass. Correctness gates
  are not weakened.
- **Host**: no host reboot, host swap changes, raw host disks or sudo.
- **Merging**: nothing is merged or promoted automatically.
- **Commits**: keep runtime state, secrets, machine paths and credentials out
  of commits. AI tools add no `Signed-off-by`; a human certifies upstream
  submissions.
- **Language**: project-authored text (docs, comments, commit messages,
  reviews) is English. Upstream and third-party text is preserved as is.

## Design freedom and experimental scope

- Research and optimization may include substantial redesigns or replacing the
  existing approach entirely. Investigate fundamental costs and architecture;
  do not default to parameter tuning or small patches.
- Within the authorized objective, candidates may replace core data structures,
  redesign algorithms and execution paths, change module responsibilities, or
  implement an independent alternative. Phase 1, 2, 3 and pending patches are
  designs to evaluate, not mandatory foundations to preserve unless specified.
- Choose distinct, substantive hypotheses with meaningful potential benefit and
  a falsifiable mechanism. Judge scope by expected value, not patch size.
- Use isolated candidates and reproducible baseline comparisons. Evaluate
  correctness, memory and CPU cost, throughput, tail latency and regressions;
  retain failed attempts and report uncertainty. Design freedom does not lower
  verification or acceptance standards.
- If a larger design needs broader edit scope or a different experiment budget,
  the primary agent may establish a documented new protocol within the time and
  resources authorized by the owner, preserving old protocols and evidence. Do
  not let an old narrow file list or diff limit silently dictate research
  direction. Explicit compatibility, host safety and delivery constraints apply.

## Writing

- State each finding as a positive claim with its evidence and a confidence
  (high / medium / low), and name the observation that would change it.
- Do not append "this does not imply / establish / mean ..." to individual
  sentences. Each document keeps its limitations in one Limitations section,
  or links to [DESIGN.md#limitations](DESIGN.md#limitations).
- Say a thing once. Link to the document that owns it instead of restating it.
- Prefer a short table of numbers to a paragraph of qualifiers.
