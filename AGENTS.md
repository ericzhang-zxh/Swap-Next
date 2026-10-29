# Swap Next contributor contract

This contract binds every agent that works in this repository, whatever its
vendor or harness (Claude Code, Codex, Cursor, Grok Bot or any other), and
every human who runs a campaign. Vendor entry files such as `CLAUDE.md` and
`GEMINI.md` only point here. A section scoped to one runner adds to these
rules and never relaxes them.

## Read first

1. [README.md](README.md) and [DESIGN.md](DESIGN.md): purpose, cost model, measurement principles.
   Read the active campaign's `campaigns/<c>/report/` and line history for findings and next steps.
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
  are not weakened. A screen uses its protocol's `required_correctness_gates`;
  the policy's `required_gates` belong to formal acceptance (see
  [DESIGN.md#limitations](DESIGN.md#limitations)).
- **Host**: no host reboot, host swap changes, raw host disks or sudo.
- **Fast tier is a screen**: a fast-tier pass selects a candidate for the
  owner's review; it never accepts one. Fast-tier A/A calibration, including
  renewing an expired passed calibration, is part of the fast tier and needs
  no approval.
- **Slow tier**: do not run the slow tier, its calibration, or any other
  multi-round confirmation on the Linux worker by default. It is reserved for
  an exceptionally strong fast-tier result, and the owner must explicitly
  approve each slow-tier run first. A fast-tier pass alone does not qualify.
  Stop experiment execution after the fast tier, then complete the report
  delivery below.
- **Metrics**: every new campaign's primary metric is swap-in latency
  (`swapin_seq.mean_ns` or `swapin_rand.mean_ns`). The probe tier guards
  metadata bytes per capacity slot for plain-mode campaigns. Other metrics
  are guardrails. Frozen older protocols keep their original contract.
- **Mechanism**: a new probe candidate declares one case, measured counter and
  direction. A probe pass establishes cumulative mechanism engagement. Report
  parent-to-child evidence separately; an inherited counter change does not
  establish the child's contribution.
- **Evolution**: a fast pass may enter the exploratory population, including a
  neutral candidate. Advancing a cross-campaign baseline requires improvement
  above its calibrated noise and passing scored guards. Preserve the line's
  original anchor and evidence; do not call a neutral screen progress. A slow
  regression, correctness failure or stale fingerprint removes parent
  eligibility while keeping history. Screen evidence never promotes code.
- **Identity**: record commit and source-tree identities. A child must change
  its parent's tree. An equivalent tree cannot buy another attempt by changing
  commit metadata. Revised measurements preserve and supersede earlier results.
- **Promotion**: candidate code is never applied to `linux/`, sent upstream or
  promoted automatically. Keeping a candidate's patch and evidence on `main`
  is a record, not a merge.
- **Commits**: track campaign ledgers, candidate records, patches and archive
  summaries; keep raw `runs/`, secrets, machine paths and credentials out of commits. AI tools add no `Signed-off-by`; a human certifies upstream
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

## What needs owner approval

This applies to every agent and runner.

- **No approval needed**: opening a campaign within the approved measurement
  contract. Write `campaigns/<c>/policy.json` and `protocol.json`, then use
  `controller.py --campaign <c> open-campaign --line L --machine M`.
  Its file list keeps or narrows the base list. Candidates, probe and fast
  calibration, screening, and report delivery follow from that campaign.
- **Default campaign budget cap**: 120 guest attempts total across probe and
  latency pools, including correctness and validity attempts, and 18 hours
  (`wall_seconds: 64800`). `open-campaign`, the workflow and counted guest
  reservations enforce it. Candidate counts are ceilings; report the actual
  attainable population and generation depth within the remaining pools.
- **Ownership and recovery**: at most one open campaign per machine. Every
  launch checks open status, machine, claim, both STOP files and a single-use
  counted reservation. `release-claim --reason` clears a stale claim;
  `resume-campaign --reason` restores an existing open campaign's ownership
  without changing its budgets, deadline, evidence or STOP files. Closed
  `status`, `plan` and `next` reads do not rewrite stored state.
- **Approval needed (core)**: changes to `AGENTS.md`, `README.md`, `DESIGN.md`,
  `evolve/control/PRINCIPLES.md`, `CODE_PATTERNS.md`, `METRICS.md`, skills
  under `.agents/`, the base policy `evolve/control/config/policy.json`,
  controller, analysis and loop code, benchmark runners, guest images and
  parsers, and any protocol measurement parameter: accelerator, guest size,
  tier cases and pair counts, noise envelope and ceiling, validity rules. The
  slow tier and candidate promotion also need approval.
- A frozen protocol file is never edited. A change is a new file, with old
  protocols and evidence preserved.
- Grok Bot asks for core approval with a pull request (see
  [Grok Bot runs](#grok-bot-runs-cloud-box-qemu-tcg)). An agent in a session
  the owner attends asks the owner directly.

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

1. **Open**: work directly on current `main`. Read the line history. Write the
   campaign policy and frozen protocol, then `open-campaign` with line and
   machine. Inherited baselines name exact source evidence on the same line;
   the seed, protocol baseline and inherited commit agree. Retain `line_anchor_commit`.
2. **Run**: keep candidates in controller-created isolated kernel worktrees.
   Commit `campaigns/<c>/ledger/`, `candidates/`, `patches/` and `archive/` at
   each calibration and candidate outcome boundary. Raw `runs/` stays ignored.
   The agent chooses which probe passes enter fast and records its reason.
   A durable brief permits the sampled exact parent or the baseline; record
   the actual choice. Scope and line limits cover the cumulative baseline diff.
3. **Close**: retain patches and failed evidence, use `close-campaign --reason`,
   regenerate campaign and line indexes, write the review report and publish
   it under the standing publication rule. Run the project checks before pushing.
4. **Clean up**: remove finished candidate worktrees, preserving their
   `agents/<candidate>` branches because evidence cites their commits. Integrate
   any useful isolated implementation branches before removing their worktrees;
   preserve uncommitted work instead of discarding it.

Historical migration preserves frozen file bytes in one commit, then rewrites
report links separately. `campaigns/MOVED.json` pins the pre-migration commit.
Each additional machine explicitly runs `migrate.py import-state` to import its
own ignored evidence with conflict checks; the shared layout marker alone does
not mean that machine's state was imported.

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
- Set `SWAP_NEXT_ACCEL=tcg` for every guest run. The swap-standard runner
  defaults to KVM for hurricpc-wsl, so a run without it would start KVM and
  crash the box. `SWAP_NEXT_TCG_SMP` and `SWAP_NEXT_TCG_MEM_MIB` size the
  guest (default 4 vCPU, 4096 MiB); each result records the accelerator and
  guest size.
- Only swap-standard runs under TCG. The kernel, xswap, xswap-structure,
  xswap-p123 and xswap-hole-probe runners are KVM-only and refuse to start
  when `SWAP_NEXT_ACCEL` is not `kvm`; `evolve/loop.py` refuses those suites
  the same way.
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
  result. A revision 3 evaluation sets `SWAP_NEXT_ACCEL=tcg` itself and
  rejects any result whose accelerator is not `tcg`.
- Tag every result in `campaigns/<campaign>/report/` with the TCG protocol revision.

### Baseline ancestry

A TCG baseline must be built from a commit with a verified lineage. The xswap
baseline `5e84ca92` is proven by replaying the xswap patch series on base
`9a0542b1`: every resulting commit hash matches, provided the last two patches
are committed with commit date equal to author date. Record the replay command,
base and resulting hashes with the campaign (example layout:
`/workspace/xswap-replay` on the box; do not commit that path).

### Closed loop

1. **Coordinator** is the primary agent. It opens the campaign: objective,
   frozen TCG protocol revision, baseline, budgets, STOP state and evidence
   destination.
2. **Hypothesis** proposes candidates, each with a mechanism, expected effect
   and kill criteria. Every candidate's parent is the campaign baseline; the
   controller rejects any other parent (see
   [DESIGN.md](DESIGN.md#where-openevolve-fits)).
3. The most promising candidates run automatically. When the owner triggers a
   round (for example "run 3 experiments"), that is the authorization; do not
   ask again per candidate.
4. **Experiment** creates each candidate with `evolve/control/controller.py`
   (scope and line budget enforced by `check`) and evaluates it through
   `evolve/loop.py` with the TCG protocol. It stops after the fast tier.
5. **Review** independently checks the diff, scope, evidence binding and
   statistics before a decision is recorded.
6. **Report** writes the audit and an HTML report (`explainer.html`), then
   publishes for the Coordinator, following
   [Report publication](#report-publication) and
   [Campaign lifecycle](#campaign-lifecycle).

### Rules and scaffolding

Grok Bot and its Swap bot group make core changes (see
[What needs owner approval](#what-needs-owner-approval)) only through a pull
request for the owner's review, and never merge it themselves. Opening a new
campaign needs no pull request: its policy, protocol and experiment work
follow [Campaign lifecycle](#campaign-lifecycle) and go directly to `main`.

### Owner gates that still apply

- The slow tier, core changes and new protocol measurement parameters
  (including a new TCG revision or guest size) need the owner's explicit
  approval.
- The `linux/` submodule stays frozen at its pinned commit.
- Commits and report publication follow [Report publication](#report-publication).

### TCG revision 3

- TCG protocol revision 3 and its protocol file:
  [campaigns/xswap-tcg-rev3-2026-10-25/protocol.json](campaigns/xswap-tcg-rev3-2026-10-25/protocol.json),
  campaign `xswap-tcg-rev3-2026-10-25`. The owner approved its parameters
  below on 2026-10-25 and closed the campaign on 2026-10-27, when swap-standard
  moved to Chris Li's kbench setup (see
  [benchmark/swap-standard/README.md](benchmark/swap-standard/README.md)).
  A new TCG run needs a new protocol revision on that setup. It was frozen before the **Metrics** rule and has no
  metadata case. Adding one to a TCG protocol changes its tier cases, so it
  needs the owner's approval.
  Revisions 1 and 2 stay frozen. Verdicts are TCG-only screens for effects of
  roughly 15–25% or larger. KVM confirmation is an open owner decision.
- Scaled guest size for revision 3: 4 vCPU, 4096 MiB RAM, 16 GiB swap.
- TCG A/A method: nearest-rank p90 of at least 10 pairs, scored ceiling 25%,
  `.p99_ns` advisory, median of at least 4 AB/BA pair deltas per backend.
  The numeric envelope is whatever a fresh revision 3 calibration measures.
  A fast-tier pass under this file is a screen, not an acceptance.
- TCG guest wall time per case: unmeasured. The protocol's `guest_timeout`
  (900 s) and `wall_seconds` (64800 s) are scaffold caps.

### TCG kbench revision 6

Prepared, not opened:
[campaigns/xswap-tcg-kbench-2026-10-29/protocol.json](campaigns/xswap-tcg-kbench-2026-10-29/protocol.json).
Owner pre-approved 2026-10-29 01:36 PT. It is the TCG protocol on the kbench
setup: QEMU TCG, 4 vCPU, 4096 MiB, 16 GiB swap, p90 envelope, 25% ceiling,
median of at least 4 AB/BA pairs, advisory p99, and the revision 3 validity
gates. The probe tier is mandatory (9-guest calibration: disk, zram-64k, brd
metadata). Fast calibration is 40 guests (disk and zram-64k). Three rounds
use the 71 guests left under the 120-guest cap. Swap-in and correctness are
xswap on baseline build `kb-xs-desc-v1` (`5e84ca92`). That commit is not an
ancestor of the `linux/` pin `744e5400`; the runner archives the requested
commit from the linux object store and leaves HEAD on the pin. The build
workload is excluded. `vm.page-cluster` stays at the kernel default 3. Open
it on grok-cloud with `SWAP_NEXT_MACHINE=grok-cloud` and `SWAP_NEXT_ACCEL=tcg`;
the protocol forces TCG and rejects any other accelerator. Rebuild the guest
image there with `prepare-image.py` before the first guest. The baseline
config is `benchmark/config/swap-standard.config` (`input_config_sha256` in
the protocol), which sets `CONFIG_TRANSPARENT_HUGEPAGE` and `CONFIG_THP_SWAP`.
No slow tier.

### TCG kbench revision 7

Proposed, not opened:
[campaigns/xswap-tcg-kbench-rev7-2026-10-29/protocol.json](campaigns/xswap-tcg-kbench-rev7-2026-10-29/protocol.json).
Revision 6's probe calibration eval `469ee19c2a064c7393cbd5e9fea3687c` was
`CALIBRATION_NOISY` because `metadata-brd` scored `-ΔMemAvailable`. That
numerator followed MemFree (about −29.6 to −31.4 MiB) while `VmallocUsed`
stayed at 28728 KiB. Revision 7 scores `SUnreclaim + VmallocUsed +
PageTables + Percpu` over the same brd capacity, keeps the 1% spread, and
keeps the revision 6 swap-in cases, 25% ceiling, and guest shape. A missing
counter, a `VmallocUsed` decrease, or a negative sum fails the guest. The
stored eval can be re-scored from `metadata_delta_kib` without new guests.
`calibrate` still boots a tier. This proposal does not open the campaign.
