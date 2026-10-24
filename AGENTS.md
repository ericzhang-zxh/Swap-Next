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
- **Slow tier**: do not run the slow tier, or any other multi-round confirmation,
  on the Linux worker by default. It is reserved for an exceptionally strong
  fast-tier result, and the owner must explicitly approve each slow-tier run
  first. A fast-tier pass alone does not qualify. Stop experiment execution
  after the fast tier, then complete the report delivery below.
- **Merging**: candidate code is never merged or promoted automatically. Report-only
  publication follows the standing policy below.
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

## Report publication

- Every campaign report is uploaded and published, then handed to the owner for
  review. The handoff includes rejected and inconclusive outcomes. Do not wait
  for another approval before publishing, unless the owner explicitly asks to
  keep that report private or local.
- Experiment work is committed directly to `main` without a pull request. Do
  the work on a branch, rebase onto `main` if it moved, and fast-forward
  `main`. Never force-push `main`.
- Candidate code is never promoted automatically. Publishing the report or
  committing the experiment record is not acceptance, and it does not authorize
  another experiment.
- Include `explainer.html`, `explainer.json`, the written report and a public data
  summary. Preserve failed gates, uncertainty and pinned source/evidence links;
  omit credentials, host-specific paths and raw private runtime data.
- Inspect the complete diff, build the Pages index and push to `main`. Pages
  collects the checked-out main tree, not reports across all branches.
- Verify the deployment for that commit and the live campaign page and index
  before reporting publication complete.
- Frozen baselines, protocols, STOP state and budgets remain unchanged. An
  agent-authored `publication: false` field does not revoke this rule. Only an
  explicit owner request keeps a report private or withholds a push. For an
  older checkout, reconcile delivery instructions against current `origin/main`
  before closeout.
