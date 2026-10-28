# Campaign directories, an evaluation cascade, and inheritance

Status: approved by the owner 2026-10-27, with the subsequent
[evolution review corrections](2026-10-27-evolution-review.md). The owner approved the direction in session:
make Swap Next actually evolve, give every campaign one directory, move the
existing campaigns into it, add a cheap probe stage before the latency screen,
and cap campaign budgets by default.
Target path: `docs/superpowers/specs/2026-10-27-campaigns-cascade-evolution-design.md`.
Supersedes the unpublished 2026-10-25 cascade draft.

## Why

Evolution needs variation, selection and inheritance. Swap Next has only the
first.

- **No inheritance.** Every candidate branches from the campaign seed
  (`controller.py:179`, `:220`), and `next` pins `required_patch_base` to the
  baseline. A result that passes the screen is never the start of the next
  candidate. The only inheritance so far was manual and at campaign level:
  the xswap baseline moved from the xswap reference to Phase III to
  `5e84ca92`, one individual per generation, recorded nowhere but in reports.
- **Selection without a population.** A fast-tier screen costs 12 to 16 guests
  per candidate, plus up to 40 for calibration, with A/A noise of 3% to 25%.
  Campaigns therefore stop at three candidates.
- **An empty archive.** Only an approved slow-tier result enters the
  OpenEvolve `ProgramDatabase` (`standard_workflow.py:435`), so no
  swap-standard state directory has a database and `next` never samples.
- **One campaign is spread over six places**: policy under
  `evolve/control/campaigns/`, protocol under `benchmark/swap-standard/`,
  report under `results/`, patches under `patches/`, and two gitignored
  ledgers (`evolve/swap-standard/state-<c>/`, `evolve/control/state/<c>/`).
  Budget spent and calibration results are not on `main`, there is no
  "closed" marker, and the relations between campaigns are implicit.

## Goals

1. One directory per campaign holding everything about it, tracked in git,
   with an explicit status, line and baseline origin. Existing campaigns move
   into it.
2. A probe stage with low-noise signals (mechanism counters, metadata bytes
   per slot) between correctness and the latency screen, with budget counted
   per stage, so a campaign can try about ten candidates.
3. Inheritance: a candidate may build on a screened candidate of the same
   campaign, and a campaign may start from a screened candidate of an earlier
   campaign on the same line.
4. An archive that actually fills, and briefs that hand the next agent the
   parent's diff and evidence.
5. Mechanical enforcement of the default budget cap, of closed campaigns, and
   of one campaign running guests per machine.

## Non-goals

- MAP-Elites feature dimensions (latency ratio x metadata ratio). Deferred
  until metadata has been measured across a few campaigns.
- OpenEvolve's controller loop, LLM ensemble and prompt templates. Agents in
  sessions keep writing the patches.
- Changing the slow tier, its approval rule, or promotion.
- Widening the candidate file list. It stays the eight files of the
  MEMORY MANAGEMENT - SWAP entry in MAINTAINERS.

## Anti-goals (failure even if the code works)

- A screen or probe pass treated as acceptance. Only slow tier plus owner
  review accepts.
- A child compared only with its parent. Every generation is measured against
  the campaign baseline, so errors do not compound.
- A move that changes a number, a claim, or a pinned hash's meaning in an old
  report, or changes a published page's URL.
- Re-running a probe or a screen until it passes.
- A campaign that silently exceeds the default cap.

## Part 1: campaign directory

### Layout

```
campaigns/
  README.md                 index of campaigns and lines (generated)
  lines/<line>.md           one line's history (generated)
  <campaign>/
    campaign.json           identity, status, line, baseline origin, machine, budget
    policy.json             was evolve/control/campaigns/<c>/policy.json
    protocol.json           was benchmark/swap-standard/protocol-*.json (bytes unchanged)
    ledger/                 budget, calibrations, run and evaluation summaries (tracked)
    candidates/<name>.json  controller record: parent, mechanism, status, reason
    patches/<name>.patch    was patches/<c>/<name>.patch
    archive/                OpenEvolve ProgramDatabase save directory
    report/                 was results/<c>/ (REPORT.md, explainer.*, data)
```

Raw run output (guest logs, swap images, per-run directories) of new
campaigns goes to a gitignored `campaigns/<c>/runs/`. Existing raw output in
`benchmark/swap-standard/runs/` and `evaluations/` (keyed by id, not by
campaign) stays where it is, because archive metadata and evidence manifests
point at it. Builds stay in `benchmark/kernel/builds/`, worktrees in
`worktrees/`. (My call.)

### campaign.json

```json
{
  "campaign": "xswap-next-2026-10-24",
  "status": "closed",
  "line": "xswap",
  "baseline_from": {"campaign": "xswap-p123-2026-10-23",
                    "candidate": "xs-desc-lifetime-v1",
                    "commit": "5e84ca928deeacb4eee656806a003f27d1eca82f"},
  "machine": "hurricpc",
  "opened": "2026-10-24",
  "closed": "2026-10-25",
  "budget": {"guest_attempts": 120, "wall_seconds": 64800,
             "probe_guest_attempts": 45, "approved_over_cap": null}
}
```

- `status` is `open` or `closed`. At most one campaign per machine is `open`
  (see below). Closing is a controller command that also
  closes active candidates and refuses while any is unexported. Code that
  starts a guest, creates a candidate or writes a ledger refuses a closed
  campaign. This replaces the hard-coded refusal proposed in PR #5.
- `baseline_from` is `null` for a campaign whose baseline is an upstream or
  imported commit, and otherwise names a candidate of an earlier campaign on
  the same line, plus `evidence`: either `{"kind": "fast_pass", "ledger_row":
  <id>}` or `{"kind": "correctness_fix", "report": <path>}`. `open` checks a
  `fast_pass` row mechanically; a `correctness_fix` must name a report that
  states the fix and its correctness evidence, and the agent opening the
  campaign is responsible for that claim. Migration fills `baseline_from` for
  old campaigns by hand from their reports, each with its `evidence`, and
  `null` where the report does not say. The check runs only when a campaign
  opens, never on migrated closed campaigns. (My call.)
- `machine` is a name from a small host table; it is what "one campaign
  running guests per machine" is checked against.
- `budget` must be within the default cap (120 guests including validity
  reruns and calibration, 18 hours). `approved_over_cap` holds a pointer to the
  owner's approval (date and where it was given) when it is exceeded;
  otherwise the controller refuses to open the campaign.

### Lines

A line is a sequence of campaigns that build on each other. It is only a
field; directories stay flat, so regrouping never moves files.
`campaigns/lines/<line>.md` is generated from every `campaign.json` and
report on the line: per campaign, the baseline and where it came from, the
hypotheses tried with their outcomes, and the line's current baseline. An
agent opening a campaign on a line reads it first.

### One campaign per machine

The rule is enforced as "at most one open campaign per machine", which is
stricter than "one running guests at a time" and keeps two campaigns'
calibrations from sharing host conditions. (My call.) `open` refuses when the
machine's claim file outside the repository (default
`~/.cache/swap-next/campaign.claim`, holding the campaign name) names another
open campaign; `close` releases it. A claim whose campaign is already
`closed` in git is stale and is replaced with a logged warning; any other
stale claim needs `controller.py release-claim --reason`. Every guest start
also checks that the claim names its campaign. The per-suite `.runtime.lock`
stays.

### Migration

All existing campaigns move, including the controller-only ones and the two
`results/` directories without a policy (`swap-standard-evolve-2026-10-22`,
`swap-standard-integration-2026-10-22`; these join `swap-standard-2026-10-22`
as subdirectories of its `report/`, my call).

Rules for the move:

1. A tool `campaigns/migrate.py` produces `campaigns/MOVED.json`, a complete
   old-path to new-path table, and performs the moves with `git mv`, so
   history follows. Gitignored ledgers are copied into `ledger/` and
   `candidates/` and become tracked; absolute paths inside them (for example
   worktree paths) are rewritten to repository-relative ones, and the rewrite
   is listed in `MOVED.json`.
2. Moved files keep their bytes. Frozen protocols in particular are byte
   identical, so `protocol_sha256` values in old evidence still match. Fields
   inside old protocols that name old paths (such as `state_directory`) are
   historical; new code locates state from the campaign directory.
3. Links inside old Markdown and HTML reports are rewritten in one separate
   commit that changes link targets only. Any evidence manifest that pins
   such a file's hash is verified at the pre-migration commit, which
   `MOVED.json` records.
4. `build_site.py` reads `campaigns/*/report/explainer.html` and keeps the
   published URL `/<campaign>/`, so no published link changes.
5. The `CONTRACT_EXEMPT` list is keyed by campaign name instead of protocol
   file name.
5a. Whole-suite protocols of the older suites (`benchmark/xswap/protocol.json`,
   `benchmark/xswap-p123/protocol.json`, `benchmark/xswap-structure/protocol.json`
   and similar) stay in place, because their runners read them from a fixed
   path and several campaigns may share one. Those campaigns' `campaign.json`
   carries `"protocol_ref": <path>, "protocol_sha256": <hash>` instead of a
   `protocol.json` copy. The older suites stay runnable but get no new
   features; their scattered state directories (`benchmark/*/state*`,
   `evolve/*/state*`) are copied into the owning campaigns' `ledger/` where
   the owner is unambiguous, and listed in `MOVED.json` as left in place
   otherwise. Untracked leftovers outside git (`Evolve/`, `system/`) are not
   migrated. (My call.)
6. Old directories are removed after the move. No compatibility stubs, except
   a one-line `results/README.md` and `patches/README.md` pointing to
   `campaigns/`.
7. Pre-campaign patch directories with no campaign
   (`patches/xswap-experiments`, `patches/xswap-p123`, `patches/xswap-phase3`,
   `patches/xswap-reference`, `patches/xswap-structure`, `patches/xswap-swapin`
   and the three loose `*.patch` files) go to `campaigns/_unassigned/patches/`
   unchanged, listed in `MOVED.json`, unless the builder can tie one to a
   campaign from its commit hashes.
8. Campaign set and status: every policy under `evolve/control/campaigns/`
   and every protocol's `campaign` name becomes a campaign directory, plus
   `confirm-h1-ra-phys-2026-10-23` (closed, with its `confirmations/` ledger).
   `evolve/swap-standard/state-layout-v1` is the ledger of `protocol.json`,
   whose campaign is `swap-standard-2026-10-22`. All are `closed` except
   `xswap-tcg-rev3-2026-10-25`, which is `open` on machine `grok-cloud` and
   has no ledger on hurricpc. Closed campaigns are not checked against the
   cap; several were budgeted 160 to 240 guests before it existed.
   (My call.)
9. The migration runs on hurricpc. The tool is idempotent, so a machine with
   its own state (Grok Bot's) can run it later; the owner said not to wait for
   or coordinate with Grok Bot.

## Part 2: evaluation cascade

| Stage | What | Exists? |
|---|---|---|
| 0 static | `controller.py check`: scope, diff check, checkpatch, build, sparse | yes |
| 1 correctness | `--correctness` proof with the protocol's `required_correctness_gates` | yes |
| 2 probe | single runs of the probe cases; mechanism and metadata decisions | **new** |
| 3 fast screen | AB/BA latency pairs against the campaign baseline | yes; now requires a probe pass |
| 4 slow | current slow tier, owner approval per run | unchanged |

For non-exempt protocols, `evaluate --tier fast` requires a `PROBE_PASS` for
the exact candidate commit under the current fingerprint. Which probe passes
enter the fast screen is the primary agent's choice, recorded with its reason
in the ledger; the workflow enforces only the cap and never ranks or
auto-advances probe passes. (Owner's decision, 2026-10-27: probe signals are
not comparable across candidates that declare different counters, and
first-come admission would remove selection.)

### Probe tier

```json
"tiers": {
  "probe": {"kind": "probe", "cases": ["swapin-disk", "swapin-zswap", "metadata-brd"],
            "calibration_runs": 3, "candidate_runs": 1},
  "fast": {"cases": ["swapin-disk", "swapin-zswap"], "calibration_pairs": 10, "comparison_pairs": 4}
}
```

- `calibrate --tier probe` boots the baseline `calibration_runs` times per
  probe case, with the same fingerprint, max-age and renewal rules as other
  calibrations. `evaluate --tier probe` boots the candidate `candidate_runs`
  times per case and compares with the calibration band. The validity
  wall-time rule uses the probe calibration runs as prior valid runs.
- Runner, workloads and parser are unchanged. `swapin` already emits
  `swapin_vmstat_delta` (`pswpin`, `zswpin`, `swap_ra`, `swap_ra_hit`,
  `pgmajfault`, `swpin_zero`, `zswpwb`) and, in xswap mode,
  `swapin_xswap_snapshots` at `swapin_start` and `swapin_end`. `metadata`
  emits `metadata_delta_bytes_per_capacity_slot`.
- If `validity.protocol_rules` rejects a probe tier because of pair-count
  rules written for latency tiers, those rules apply to latency tiers only.

### Decisions

- **Band**: `[min, max]` of the calibration runs per case and signal, widened
  by `max(1% of |median|, 1)` for integer counters and by `1% of |median|` for
  floats (metadata is about 0.206 bytes per slot at baseline, so an absolute
  floor would disable it). Constants are frozen in the protocol. (My call.)
- **Mechanism**: each candidate declares `CASE:KEY:DIRECTION`, for example
  `swapin-disk:swapin_vmstat_delta.swap_ra_hit:up`. `KEY` is
  `swapin_vmstat_delta.<counter>`, `xswap.<counter>` (end minus start of the
  snapshots), or `metadata_delta_bytes_per_capacity_slot`. Inside the band is
  `MECHANISM_NOT_ENGAGED`, outside in the wrong direction is
  `MECHANISM_REVERSED`; both reject. One mechanism per candidate.
- **Metadata guard**: above the band's upper edge is `METADATA_REGRESSION` and
  rejects. A raw calibration spread above 1% of the median makes the probe
  calibration noisy for metadata and blocks probing.
- **Outcome**: `PROBE_PASS`, `PROBE_REJECT` with reasons, or `INCOMPLETE`
  (never a pass). A `PROBE_REJECT` is final for that commit under every
  fingerprint; a `PROBE_PASS` from an older fingerprint may be probed once
  more under the current one. (My call.)
- **Child probes**: a child's probe band is the campaign baseline's, like
  every other comparison.

### Controller and budget

- `controller.py new --mechanism CASE:KEY:DIRECTION`, required when the
  campaign policy sets `"mechanism_required": true` (absent means false, so
  migrated policies keep their bytes). The controller checks syntax; the
  workflow checks `CASE` and `KEY` against the protocol's probe cases.
- Protocol `budget.probe_guest_attempts` is a separate pool for probe
  calibration and probes; the ledger records the pool of each guest. Both
  pools together stay within the campaign cap.
- Protocol `max_candidates` counts candidates entering the fast screen; new
  `max_probe_candidates` counts probed candidates; the controller policy's
  `budget.max_candidates` counts every `new` and must be at least
  `max_probe_candidates`.
- Defaults (my call): probe calibration 3 runs x 3 cases = 9 guests; 3 guests
  per probed candidate; `max_probe_candidates` 10; `probe_guest_attempts` 45;
  `max_candidates` 3. With a 40-guest fast calibration and 3 screened
  candidates at about 16 guests each, a campaign stays near the 120 cap.

### Contract and rules

- `contract_errors()` for non-exempt protocols requires a probe tier with a
  swap-in case, and, for plain-mode swap-in cases, a metadata case scoring
  `metadata_delta_bytes_per_capacity_slot`. The metadata requirement moves
  from the fast tier to the probe tier. The fast tier still needs a swap-in
  latency mean as its primary.
- `AGENTS.md`: the **Metrics** rule says "every probe tier" instead of
  "every fast tier"; a new **Mechanism** rule says every candidate declares
  one counter and direction; the **Campaign lifecycle** and
  **What needs owner approval** sections use the campaign directory, lines
  and inheritance below. `DESIGN.md` describes the cascade and the evolution
  loop. These are core changes; approving this design approves them.
- Probe runs and probe calibration need no per-run approval.

### Known limitation: metadata in xswap mode

The `metadata` workload requires `backend=brd`, a SwapTotal increase of
exactly 1 TiB minus one page, and `/dev/ram0` in `/proc/swaps`; an xswap guest
also creates an xswap device, so these gates fail. Until an xswap-mode
metadata case exists (a guest and parser change, separate approval), xswap
campaigns probe mechanisms only.

## Part 3: inheritance, archive, briefs

### A: what enters the archive

`campaigns/<c>/archive/` holds an OpenEvolve `ProgramDatabase`. A candidate
enters it when it gets a `FAST_PASS` (tagged `tier: fast`, `screen_only`), and
its entry is updated if it later gets a slow result. Each entry carries the
patch against the campaign baseline, `parent_id`, `generation`, the fast
analysis (`combined_score` and per-case ratios), its probe signals and its
mechanism. `PROBE_PASS` alone does not enter the archive. Rejected and
inconclusive results stay in the ledger only. The database configuration
stays `num_islands: 1`; `population_size` and `archive_size` are at least
`max_probe_candidates`.

### B: lineage

- Within a campaign, a new candidate's parent is the campaign baseline or an
  archived candidate of the same campaign. The controller records the parent
  candidate and its commit, branches the worktree from it, and drops the
  "parent must equal seed" check for this case.
- Scope and the line budget are checked on the cumulative diff from the
  campaign baseline, not the diff from the parent.
- Probe and fast compare the child with the campaign baseline. The parent's
  result is reported next to it but never decides.
- The child's mechanism may differ from the parent's. Its probe must show its
  own declared mechanism against the baseline band.
- No depth limit beyond the campaign budget. (My call.)
- Across campaigns, `baseline_from` in `campaign.json` carries inheritance to
  the next campaign on the line (Part 1).

### D: briefs

The brief is rendered with OpenEvolve's `PromptSampler.build_prompt` and a
Swap Next template, so parent, inspirations, metrics, artifacts and later the
feature dimensions come from the same `ProgramDatabase` entries. OpenEvolve's
`Evaluator` cascade and its controller loop and LLM providers are not used:
the cascade's gates are categorical and budgeted, and the loop's text-only
providers can neither read the kernel tree nor build it. `next` writes a
brief with: the sampled parent (or the baseline), its patch
against the baseline, its mechanism, probe signals, fast analysis and report
path; two inspirations with the same fields; the last three ledger outcomes
including rejections; the line history file; and the remaining probe and fast
budget. The agent either builds on the sampled parent or on the baseline and
records which. Choosing any other parent is refused. (My call.)

## First campaign: protocol revision 4 (KVM, plain mode)

The owner chose a new KVM measurement revision for the first campaign, run on
hurricpc, so the cascade is validated with both mechanism and metadata
signals. No approved KVM protocol has usable statistics today: revision 3's
rules are TCG-only in `validity.protocol_rules`, and `protocol.json` has two
pairs per case without enforced validity. Approving this design approves
revision 4's measurement parameters:

- Statistics and validity identical to revision 3: 10 A/A calibration pairs,
  p90 noise envelope, noise ceiling between 25% and 30% (25% used), 4 AB/BA
  comparison pairs decided by the median, at least one validity rerun per arm,
  60 s pre-QEMU limit, wall-time factor 1.5, p99 advisory, swap image
  preallocated.
- Accelerator `kvm`, guest 8 vCPU, 8192 MiB, 16 GiB swap (the runner's KVM
  default).
- Plain mode. Fast tier: `swapin-disk`, `swapin-zswap`, primary
  `swapin_seq.mean_ns`. Probe tier: `swapin-disk`, `swapin-zswap`,
  `metadata-brd`.
- Budget within the default cap, using the probe defaults above.

`validity.protocol_rules` keys the guest and accelerator checks by revision
(3: TCG, 4 vCPU, 4096 MiB; 4: KVM, 8 vCPU, 8192 MiB) and applies the pair-count
rules to latency tiers only. The campaign is a new campaign on a new line
(`plain`); its name and dates are set when it opens. The xswap line gets the
cascade once the xswap-mode metadata case exists.

## Build order

1. Campaign directory, `campaign.json`, migration tool and migration commit,
   link-rewrite commit, `build_site.py` change, closed-campaign refusal,
   default-cap check, per-machine lock, line index generator.
2. Probe tier, mechanism declaration, separate probe budget, contract change,
   revision 4 rules in `validity.py` and the revision 4 protocol file.
3. Archive admission on `FAST_PASS`, lineage in the controller, briefs.
4. Rules and design docs updated in the same commits as the behavior they
   describe. The project tests from the skill's Checks list pass after each
   step.

Ledger files are written during runs and committed by the agent running the
campaign, directly to `main`, at each stage boundary (after a calibration,
after each candidate's probe and fast outcome) and at close, so budget spent
is on `main` while a campaign runs. New writes use repository-relative paths.
This replaces AGENTS.md's "keep runtime state out of commits" for
`campaigns/<c>/ledger/`, `candidates/` and `archive/`; raw `runs/` stay
uncommitted. Grok Bot commits its campaign ledgers directly too, since they
are campaign work rather than core changes. (My call.)

Every step changes `standard_workflow.py` or `controller.py` and therefore
every protocol fingerprint; calibrations taken before a step are stale after
it. The owner chose not to coordinate this with Grok Bot.

## Tests

Guest-free unit tests for: migration (every tracked file in `MOVED.json`,
moved bytes identical, protocols' hashes unchanged, idempotent rerun, Pages
output paths unchanged); closed-campaign refusal; cap refusal and approved
override; per-machine lock; band computation; mechanism engaged, not engaged
and reversed; metadata regression and noisy calibration; probe budget pool;
fast refused without an exact-commit probe pass; probe attempts per commit
and fingerprint; contract errors; `--mechanism` parsing; archive admission on
`FAST_PASS` only; lineage branch point, cumulative scope check, and
comparison against the baseline; brief contents and refused parent choices.
Existing tests keep passing; exempt protocols keep their behavior. The first
real probe calibration is an experiment run after building, not part of it.

## Left to the builder

Code structure, ledger field names beyond those fixed here, report layout,
the host table format, whether band constants become protocol fields,
explainer integration, and the exact `MOVED.json` format.
