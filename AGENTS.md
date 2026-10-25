# Swap Next contributor contract

This contract binds every agent that works in this repository, whatever its
vendor or harness (Claude Code, Codex, Cursor, Grok Bot or any other), and
every human who runs a campaign. Vendor entry files such as `CLAUDE.md` and
`GEMINI.md` only point here. A section scoped to one runner adds to these
rules and never relaxes them.

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
- The editable file list in `evolve/control/config/policy.json` is fixed.
  No agent or campaign policy adds files to it; design within those files.
- If a larger design needs a different experiment budget, the primary agent may
  establish a documented new protocol within the time and resources authorized
  by the owner, preserving old protocols and evidence. Explicit compatibility,
  host safety and delivery constraints apply.

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
- Experiment work is committed directly to `main` without a pull request,
  following [Campaign lifecycle](#campaign-lifecycle). Never force-push `main`.
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

## Campaign lifecycle

Every campaign, whoever runs it, follows the same branch lifecycle.

1. **Open**: work on one branch named `experiments/<campaign>`, created from
   current `origin/main`. Scratch and publication worktrees belong to that
   campaign and live outside the main checkout.
2. **Run**: commit harness, policy, protocol and evidence changes on that
   branch as they happen. Keep runtime state, ledgers and images uncommitted.
3. **Close**: bring everything worth keeping onto `main`.
   - Reports and evidence go to `results/<campaign>/`.
   - Candidate patches go to `patches/<campaign>/`.
   - Harness, policy and protocol changes go to their usual paths.
   - Merge the branch into `main` with `--no-ff`. Do not rebase or squash
     commits that a report or evidence manifest cites, because their hashes
     must stay valid. A branch with no cited commits may instead be rebased
     and fast-forwarded.
   - When rules, skills or published reports conflict, keep the `main` side
     unless the campaign deliberately changes them.
   - Run the project tests before pushing `main`.
4. **Clean up**: once `main` contains the branch, delete it locally and on
   `origin` and remove its worktrees. No finished campaign leaves a branch,
   a worktree or uncommitted work behind. If a worktree holds changes that
   are not on `main`, commit them to `main` or report them to the owner;
   never discard them silently.

An agent that finds stale experiment branches or worktrees from an earlier
campaign applies steps 3 and 4 to them before starting new work.

## Grok Bot runs (cloud box, QEMU TCG)

This section applies only to experiments initiated by Grok Bot or its Swap bot
group (Swap Coordinator, Hypothesis, Experiment, Review, Report). Human runs and
runs on hurricpc-wsl keep the rules above unchanged. Where this section is
silent, the rules above still apply.

### Where it runs

- Builds and guests for Grok Bot runs execute on Grok Bot's own cloud box, not
  on hurricpc-wsl. The box is the Linux worker for these runs.
- **KVM is forbidden on the box.** `/dev/kvm` exists, but starting a KVM guest
  crashes the host kernel (KVM is built in with `enable_virt_at_load=Y` and the
  instance is snapshot-forked). Never pass `-enable-kvm` or `-accel kvm`.
- Never offline or online host CPUs.
- The runner defaults to QEMU TCG. `SWAP_NEXT_ACCEL=kvm` is opt-in and must
  not be used on the cloud box. A revision 3 evaluation forces
  `SWAP_NEXT_ACCEL=tcg` and the protocol guest size. `SWAP_NEXT_TCG_SMP` and
  `SWAP_NEXT_TCG_MEM_MIB` still override a direct `run.py` call. Each result
  records the accelerator and guest size.
- The host rules above (no reboot, host swap changes, raw disks or sudo) apply.

### TCG protocol revision

- All guests run under QEMU TCG (pure software emulation). TCG is a separate
  protocol revision with its own `protocol.json`, budgets and calibration;
  KVM evidence stays historical.
- Compare each candidate only against a baseline measured in the same TCG
  environment. Never compare TCG numbers with hurricpc-wsl KVM numbers.
- Run TCG A/A noise calibration for each tier before any accept or reject
  decision. Uncalibrated TCG results are diagnostics only.
- The standard guest for TCG revision 3 is 4 vCPU, 4 GiB RAM and a 16 GiB
  swap image (`-accel tcg,thread=multi,tb-size=256 -machine pc -cpu max`).
  Record the vCPU count, RAM, swap size and QEMU accelerator options in every
  result. KVM remains opt-in through `SWAP_NEXT_ACCEL=kvm` and is rejected by
  a revision 3 evaluation.
- Tag every result in `results/<campaign>/` with the TCG protocol revision.

### Baseline ancestry

A TCG baseline must be built from a commit with a verified lineage. The xswap
baseline `5e84ca92` is proven by replaying the xswap patch series on base
`9a0542b1`: every resulting commit hash matches, provided the last two patches
are committed with commit date equal to author date. Record the replay command,
base and resulting hashes with the campaign (example layout:
`/workspace/xswap-replay` on the box; do not commit that path).

### Closed loop

1. **Coordinator** opens the campaign: objective, frozen TCG protocol revision,
   baseline, budgets, STOP state and evidence destination.
2. **Hypothesis** proposes candidates, each with a mechanism, expected effect,
   parent lineage (baseline or prior candidate) and kill criteria.
3. The most promising candidates run automatically. When the owner triggers a
   round (for example "run 3 experiments"), that is the authorization; do not
   ask again per candidate.
4. **Experiment** creates each candidate with `evolve/control/controller.py`
   (scope and line budget enforced by `check`) and evaluates it through
   `evolve/loop.py` with the TCG protocol. It stops after the fast tier.
5. **Review** independently checks the diff, scope, evidence binding and
   statistics before a decision is recorded.
6. **Report** writes the audit and an HTML report (`explainer.html`), then
   follows [Report publication](#report-publication) and
   [Campaign lifecycle](#campaign-lifecycle).

### Rules and scaffolding

Grok Bot and its Swap bot group change project rules or scaffolding only
through a pull request for the owner's review, and never merge it
themselves. That covers `AGENTS.md`, `README.md`, `DESIGN.md`,
[PRINCIPLES.md](evolve/control/PRINCIPLES.md), skills under `.agents/`,
policy and protocol files, `evolve/` controller and loop code, and benchmark
runners and tooling. Their experiment work (hypotheses, candidate runs,
results, reports) follows [Campaign lifecycle](#campaign-lifecycle) and goes
directly to `main`.

### Owner gates that still apply

- The slow tier and any protocol change (including a new TCG revision or guest
  size) need the owner's explicit approval.
- The `linux/` submodule stays frozen at its pinned commit.
- Commits and report publication follow [Report publication](#report-publication).

### Open items (TBD)

- TCG protocol revision 3 and its protocol file:
  [benchmark/swap-standard/protocol-tcg-revision3.json](benchmark/swap-standard/protocol-tcg-revision3.json).
  The campaign is `xswap-tcg-r3-2026-10-24`, with
  [policy.json](evolve/control/campaigns/xswap-tcg-r3-2026-10-24/policy.json).
  Its ledger is `evolve/swap-standard/state-protocol-tcg-revision3`. The closed
  `xswap-next-2026-10-24` ledger and its spent guest budget stay unread.
  Revisions 1 and 2 stay frozen. Verdicts are TCG-only screens for effects of
  roughly 15–25% or larger. KVM confirmation is an open owner decision.
- Scaled guest size for revision 3: 4 vCPU, 4096 MiB RAM, 16 GiB swap.
- TCG A/A method: nearest-rank p90 of at least 10 pairs, scored ceiling 25%,
  `.p99_ns` advisory, median of at least 4 AB/BA pair deltas per backend.
  The numeric envelope is whatever a fresh revision 3 calibration measures.
  A fast-tier pass under this file is a screen, not an acceptance.
- TCG guest wall time per case: unmeasured. The protocol's `guest_timeout`
  (900 s) and `wall_seconds` (64800 s) are scaffold caps.
