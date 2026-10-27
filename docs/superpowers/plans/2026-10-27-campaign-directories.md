# Campaign Directories Implementation Plan (part 1 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every Swap Next campaign one tracked directory `campaigns/<c>/`, move all existing campaigns into it, and enforce campaign status, the default budget cap and one open campaign per machine.

**Architecture:** A small stdlib module `evolve/control/campaign_store.py` owns the layout, `campaign.json`, the host table and the machine claim. The controller and `evolve/standard_workflow.py` locate policy, protocol, ledger, candidates, patches and archive through it. A migration tool `evolve/control/migrate.py` moves the old layout with `git mv`, copies gitignored ledgers into tracked files, and writes `campaigns/MOVED.json`; a second tool pass rewrites report links. Parts 2 (probe cascade, revision 4) and 3 (archive, lineage, briefs) get their own plans once this lands.

**Tech Stack:** Python 3 stdlib, `unittest`, git. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-27-campaigns-cascade-evolution-design.md` (Part 1). Read it before starting.

## Global Constraints

- Work on `hurricpc-wsl` in `~/playground/Swap-Next`, on `main`, committing directly. Author every commit as `Eric Zhang <zxh@xh-zhang.com>` (`git -c user.name="Eric Zhang" -c user.email=zxh@xh-zhang.com commit ...`); end messages with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never force-push.
- No guest boots, calibrations or campaign runs while this plan executes. Tests are guest-free.
- Default cap: `guest_attempts` 120 (probe pool included) and `wall_seconds` 64800 per campaign; more needs `approved_over_cap`. Closed campaigns are never checked against the cap.
- Campaign names match `[a-z][a-z0-9-]{0,47}`; line names match the same pattern.
- Moved files keep their bytes (`git mv`). Frozen protocols stay byte identical.
- Published page URLs stay `/<name>/` exactly as today.
- The global emergency stop stays at `evolve/control/state/STOP` (eight runners read it). Per-campaign STOP becomes `campaigns/<c>/STOP`.
- The candidate file list (eight MAINTAINERS files) and `diff_guard` are unchanged.
- After every task, the full Checks list passes:
  ```sh
  python3 -m unittest discover -s evolve/control/tests -v
  python3 -m unittest discover -s benchmark/tests -v
  for suite in swap-standard xswap xswap-structure xswap-hole-probe kernel; do
    evolve/.venv/bin/python -m unittest discover -s benchmark/$suite -p 'test_*.py' -v
  done
  evolve/.venv/bin/python -m unittest evolve.test_standard_workflow -v
  ```

## Review Focus

1. A claim file left behind by a crash: `open-campaign` must replace a claim naming a campaign that is `closed` in git (logged warning) and refuse any other foreign claim until `release-claim --reason`. Test in Task 1.
2. `SWAP_NEXT_MACHINE` unset on a host missing from `hosts.json`: guest starts and `open-campaign` refuse with a message naming `SWAP_NEXT_MACHINE`, never guess. Test in Task 1.
3. Running the migration twice, or after a partial failure: the second run is a no-op that reports "already migrated" and changes no file. Test in Task 6.
4. A gitignored ledger that holds absolute paths (`/home/xuanhao/...` worktree paths, `report` fields): after migration no tracked file under `campaigns/` contains the string `/home/`. Test in Task 6, check in Task 7.
5. `close-campaign` while a candidate has no exported patch: refuse and list the candidates. Test in Task 2.

---

### Task 1: `campaign_store.py` — layout, campaign.json, cap, hosts, claim

**Files:**
- Create: `evolve/control/campaign_store.py`
- Create: `campaigns/hosts.json`
- Test: `evolve/control/tests/test_campaign_store.py`

**Interfaces:**
- Produces (all in `campaign_store`):
  - `class CampaignError(ValueError)`
  - `PROJECT: Path` (repo root), `CAMPAIGNS = PROJECT / "campaigns"`, `HOSTS = CAMPAIGNS / "hosts.json"`
  - `CAP_GUEST_ATTEMPTS = 120`, `CAP_WALL_SECONDS = 64800`
  - `campaign_dir(name: str) -> Path` — validates the name, returns `CAMPAIGNS / name` (may not exist)
  - `load(name: str) -> dict` — reads and validates `campaign.json`
  - `write(name: str, record: dict) -> None` — validates, writes atomically (tmp + replace), `indent=2`, trailing newline
  - `candidates(name: str) -> dict[str, dict]` — every `candidates/<id>.json` keyed by `id`
  - `write_candidate(name: str, record: dict) -> None`
  - `budget_errors(record: dict) -> list[str]`
  - `require_open(name: str) -> dict`
  - `current_machine() -> str`
  - `claim_path() -> Path` — `$SWAP_NEXT_CLAIM` or `~/.cache/swap-next/campaign.claim`
  - `read_claim() -> str | None`, `take_claim(name: str) -> None`, `release_claim(name: str | None, reason: str) -> None`, `require_claim(name: str) -> None`
- `campaign.json` keys (spec, Part 1): `campaign`, `status` (`open`|`closed`), `line`, `baseline_from` (`null` or `{campaign, candidate, commit, evidence}` where `evidence` is `{"kind": "fast_pass", "ledger_row": str}` or `{"kind": "correctness_fix", "report": str}`), `machine`, `opened`, `closed` (`null` while open), `budget` (`{guest_attempts, wall_seconds, probe_guest_attempts, approved_over_cap}`), and optionally `protocol_ref` + `protocol_sha256` for older-suite campaigns.

- [ ] **Step 1: Write the failing tests** in `test_campaign_store.py`, each using a temp dir patched over `CAMPAIGNS`, `HOSTS` and `$SWAP_NEXT_CLAIM`:
  - `test_name_validation`: `campaign_dir("../x")`, `campaign_dir("A")`, `campaign_dir("a/b")` raise `CampaignError`.
  - `test_load_rejects_bad_records`: missing `line`, `status: "paused"`, `machine` absent from hosts, `baseline_from.evidence.kind: "vibes"` each raise.
  - `test_budget_cap`: `budget_errors` is `[]` for 120/64800; for `guest_attempts: 121` it names `guest_attempts`; for `wall_seconds: 64801` it names `wall_seconds`; `approved_over_cap: "2026-10-27 owner in session"` clears both; `probe_guest_attempts` counts inside the 120 (`guest_attempts` 80 + probe 45 → error).
  - `test_current_machine`: `SWAP_NEXT_MACHINE=hurricpc` → `"hurricpc"`; `SWAP_NEXT_MACHINE=nope` raises; unset with `platform.node()` patched to `"Hurricpc"` → `"hurricpc"`; unset with an unknown node raises with `"SWAP_NEXT_MACHINE"` in the message.
  - `test_claim_lifecycle`: `take_claim("a")` then `read_claim() == "a"`; `take_claim("b")` raises while `a` is open; with `a` written `closed`, `take_claim("b")` succeeds and emits a warning (`assertLogs`); `require_claim("c")` raises when the claim names `b`; `release_claim("b", "done")` removes it; `release_claim(None, "crash")` removes any claim and appends the reason to `claim_path().with_suffix(".log")`.
  - `test_candidates_roundtrip`: `write_candidate` then `candidates()` returns the record keyed by `id`; a file whose `id` differs from its filename raises.
- [ ] **Step 2: Run** `python3 -m unittest evolve/control/tests/test_campaign_store.py -v` — expected: ImportError / FAIL.
- [ ] **Step 3: Implement `campaign_store.py`.** Stdlib only, no import of `analysis.py`. `hosts.json` is `{"hurricpc": {"hostnames": ["Hurricpc"]}, "grok-cloud": {"hostnames": []}}`; hostname match is case-insensitive. The claim file holds the campaign name and a newline; write it via tmp + `os.replace` after creating its parent.
- [ ] **Step 4: Run** the test file and the full Checks list — expected: PASS.
- [ ] **Step 5: Commit** `controller: add the campaign directory store`.

### Task 2: Controller on the campaign directory

**Files:**
- Modify: `evolve/control/controller.py` (`configure_campaign`, `stopped`, `lock`, `registry`, `event`, `create`, `check_candidate`, `get_candidate`, `main`)
- Modify: `evolve/control/tests/test_campaign.py`, `evolve/control/tests/test_controller.py` (fixture paths only, plus new tests)

**Interfaces:**
- Consumes: Task 1 `campaign_store` (all names).
- Produces, with `--campaign <c>`: `POLICY = campaigns/<c>/policy.json`; candidate records in `campaigns/<c>/candidates/<id>.json`; per-candidate artifacts (`task.json`, `scope.json`, `static.json`, `analysis.json`, `*.log`) in `campaigns/<c>/candidates/<id>/`; `check` writes the patch to `campaigns/<c>/patches/<id>.patch`; events to `campaigns/<c>/ledger/events.jsonl`; lock file `campaigns/<c>/.lock`; `stopped()` checks `evolve/control/state/STOP` and `campaigns/<c>/STOP`. Recorded `worktree` values are repository-relative (`worktrees/<c>/<id>`) and resolved against `PROJECT` when used. Without `--campaign` the unscoped base-policy mode keeps today's `evolve/control/state` paths.
- New subcommands (all require `--campaign`):
  - `open-campaign --line L --machine M [--baseline-from CAMPAIGN:CANDIDATE] [--evidence-report PATH | --evidence-row ID] [--over-cap-approval TEXT]` — requires `policy.json` and `protocol.json` already in the directory and no `campaign.json`; checks the policy keeps or narrows the base list, `budget_errors` on the protocol's `budget` (`guest_attempts`, `wall_seconds`, `probe_guest_attempts` default 0), `M == current_machine()`, the baseline evidence (a `fast_pass` row must exist in that campaign's `ledger/ledger.json` with `status == "FAST_PASS"` and matching `candidate_commit`; a `correctness_fix` report must exist), then writes `campaign.json` (`status: open`, `opened` = UTC date) and takes the claim.
  - `close-campaign --reason TEXT` — refuses if any candidate is `active` without `patches/<id>.patch`; otherwise closes active candidates with the reason, sets `status: closed`, `closed` date, releases the claim.
  - `release-claim --reason TEXT` — `release_claim(None, reason)`; works without `--campaign`.
- `protocol_hash()` keeps hashing by file *name*, so a moved `policy.json` keeps its old hash.

- [ ] **Step 1: Write failing tests** (temp project with a fake `linux` git repo, as `test_controller.py` already builds):
  - `test_campaign_paths`: after `configure_campaign("demo")`, `new` writes `campaigns/demo/candidates/<id>.json` with `worktree == "worktrees/demo/<id>"`, and `check` writes `campaigns/demo/patches/<id>.patch`.
  - `test_closed_campaign_refuses_work`: with `campaign.json` `status: closed`, `new` and `check` return `BLOCKED_OR_REJECTED` with `"closed"` in the error.
  - `test_open_campaign_checks`: refuses a second open campaign on the same machine; refuses `guest_attempts: 121` without `--over-cap-approval`; refuses `--machine grok-cloud` on hurricpc; refuses `--baseline-from` naming a candidate without a `FAST_PASS` row; accepts a `correctness_fix` report that exists.
  - `test_close_campaign_requires_exported_patches`: an active candidate without a patch blocks closing and the error lists its id; after `check` (patch written) closing succeeds, the candidate is `closed` and the claim is gone.
  - Update existing fixtures from `CONTROL/"campaigns"`/`CONTROL/"state"/<c>` to the new layout; `test_invalid_or_unknown_campaign_does_not_mutate_paths` and `test_global_and_campaign_stop` keep their assertions with the new STOP path.
- [ ] **Step 2: Run** `python3 -m unittest discover -s evolve/control/tests -v` — expected: new tests FAIL.
- [ ] **Step 3: Implement** in `controller.py` using `campaign_store`; `get_candidate` resolves the relative worktree against `PROJECT` and keeps `record["parent"] == seed()` (lineage is part 3).
- [ ] **Step 4: Run** the full Checks list — expected: PASS.
- [ ] **Step 5: Commit** `controller: campaigns live in campaigns/<c>/ with open and close`.

### Task 3: Standard workflow and runner on the campaign directory

**Files:**
- Modify: `evolve/standard_workflow.py` (globals, `select_protocol` → `select_campaign`, `CONTRACT_EXEMPT`, `fingerprint`, `Workflow.__init__`, `check`, `reserve`, `candidate`, `run`, `archive`, `main`)
- Modify: `benchmark/swap-standard/run.py` (add `--run-root`)
- Modify: `evolve/test_standard_workflow.py`, `benchmark/swap-standard/test_runner.py`, `benchmark/swap-standard/test_validity.py`

**Interfaces:**
- Consumes: Task 1 `campaign_store.load`, `require_open`, `candidates`, `require_claim`, `budget_errors`; Task 2 candidate record format.
- Produces:
  - `select_campaign(name: str) -> None` sets globals `CAMPAIGN = campaigns/<c>`, `PROTOCOL = CAMPAIGN / "protocol.json"`, `STATE = CAMPAIGN / "ledger"`, `EVALUATIONS = CAMPAIGN / "runs/evaluations"`, `RUNS = CAMPAIGN / "runs/guests"`, `ARCHIVE = CAMPAIGN / "archive"`, `TASKS = CAMPAIGN / "runs/tasks"`. Module defaults point at `campaigns/swap-standard-2026-10-22`.
  - CLI: `--campaign NAME` replaces `--protocol`. `status`, `plan` and `next` work on closed campaigns; `calibrate`, `evaluate` and `reference-check` call `require_open`, check `budget_errors` against `campaign.json` unless closed, and refuse with a `BLOCKED:` reason before any ledger row reserves budget.
  - `reserve("guest")` calls `require_claim(campaign)` first; failure is `BLOCKED:`.
  - `CONTRACT_EXEMPT = {"swap-standard-2026-10-22", "confirm-h1-ra-phys-2026-10-23", "xswap-swapin-2026-10-23", "xswap-next-2026-10-24", "xswap-tcg-rev3-2026-10-25"}`, compared with `p["campaign"]`.
  - `fingerprint` hashes `CAMPAIGN / "policy.json"` and `PROTOCOL` in place of the old paths; everything else unchanged.
  - `Workflow.candidate` reads `campaign_store.candidates(p["campaign"])` and resolves `worktree` against `ROOT`; the historical `xswap-structure-2026-10-22` block reads that campaign's candidates the same way.
  - `run.py --run-root PATH` (absolute, must resolve inside `PROJECT / "campaigns"` and end in `runs/guests`) replaces `BASE / "runs"`; default stays `BASE / "runs"`. The workflow always passes `--run-root RUNS` and reads `RUNS / run_id / "result.json"`.
  - Per-campaign STOP passed to `run.py --stop-file` is `CAMPAIGN / "STOP"`.

- [ ] **Step 1: Write failing tests:**
  - In `test_standard_workflow.py`, `setUp` patches `CAMPAIGN`, `STATE`, `EVALUATIONS`, `RUNS`, `ARCHIVE`, `TASKS`, `ROOT` to a temp tree and writes an `open` `campaign.json` for `self.p["campaign"]`; update the `evaluations` paths in `test_interrupted_identity_is_recovered_from_report` and the candidates path in `test_exact_commit_proof_alias_still_requires_all_gates`.
  - `test_closed_campaign_blocks_before_budget`: `status: closed` → `run("calibrate", "fast")` is `BLOCKED`, `budget["guests"] == 0`, no ledger row has `execution_started`.
  - `test_guest_needs_machine_claim`: claim names another campaign → `reserve("guest")` raises with `"claim"`; budget unchanged.
  - `test_over_cap_open_campaign_blocks`: `campaign.json` budget `guest_attempts: 200` without approval → `BLOCKED`.
  - `test_contract_exemption_is_by_campaign`: a protocol copied to a new campaign name with the old fast tier is `BLOCKED` by the contract; under `xswap-next-2026-10-24` it is not.
  - Replace `test_protocol_campaign_selects_its_own_state_directory` with `test_select_campaign_paths` asserting every global above for `xswap-tcg-rev3-2026-10-25`.
  - In `test_runner.py`, `test_run_root_must_be_inside_campaigns`: `/tmp/x/runs/guests` and `campaigns/x/runs` (no `guests`) are rejected by argument parsing; `campaigns/x/runs/guests` is accepted.
  - In `test_validity.py`, the revision 1/2 protocol paths become `campaigns/xswap-next-2026-10-24/report/protocol-revision1.json` and `...revision2.json` (they pass after Task 7; mark them with `@unittest.skipUnless(path.exists(), "before migration")` until then).
- [ ] **Step 2: Run** `evolve/.venv/bin/python -m unittest evolve.test_standard_workflow -v` — expected: new tests FAIL.
- [ ] **Step 3: Implement** the interfaces above. Load `campaign_store` with `importlib` from `ROOT / "evolve/control/campaign_store.py"`, the way `analysis_module()` loads its module.
- [ ] **Step 4: Run** the full Checks list — expected: PASS.
- [ ] **Step 5: Commit** `standard workflow: one campaign directory per protocol, claim and cap checks`.

### Task 4: Older entry points follow the new layout

**Files:**
- Modify: `evolve/loop.py` (`Suite.candidates`), `evolve/confirm.py` (state directory), `benchmark/xswap/import-reference.py` (`PATCHES`, policy paths), and the per-campaign STOP paths in `benchmark/xswap/run.py`, `benchmark/xswap/evaluate_kernel.py`, `benchmark/xswap-structure/run.py`, `benchmark/xswap-structure/evaluate_kernel.py`, `benchmark/xswap-hole-probe/run.py`
- Modify: `benchmark/xswap-structure/test_campaign.py`, `benchmark/tests/test_layout.py`
- Create: `benchmark/tests/test_no_old_paths.py`

**Interfaces:**
- Consumes: Task 1 `campaign_store.candidates`, `campaign_dir`.
- Produces: `Suite.candidates()` returns `campaign_store.candidates(self.campaign)`; `confirm.py` keeps its ledger in `campaigns/<c>/ledger/confirmation.json`; `import-reference.py` reads `campaigns/xswap-2026-10-21/import-policy.json` and writes the replay campaign into `campaigns/xswap-reference-replay/`, patches from `campaigns/_unassigned/patches/xswap-reference/`; per-campaign STOP is `campaigns/<c>/STOP`. Legacy suites keep their own `state-layout-v1` directories and their whole-suite `protocol.json` files in place.

- [ ] **Step 1: Write the failing test** `test_no_old_paths.py::test_code_uses_campaign_layout`: `git grep -n -E "evolve/control/campaigns|evolve/control/state/[a-z]|evolve/control/state\" */|evolve/swap-standard/state|confirmations|results/|patches/"` over tracked `*.py`, `*.sh`, `*.yml`, excluding `campaigns/*/report/**` (historical report scripts) and `linux/`, returns no lines. The global `evolve/control/state/STOP` is allowed.
- [ ] **Step 2: Run** `python3 -m unittest benchmark/tests/test_no_old_paths.py -v` — expected: FAIL listing the files above.
- [ ] **Step 3: Update** each file to the interfaces above; `test_layout.py` and `benchmark/xswap-structure/test_campaign.py` assert the new STOP path.
- [ ] **Step 4: Run** the full Checks list — expected: PASS except `test_no_old_paths` for `build_site.py` and `pages.yml`, which Task 5 fixes.
- [ ] **Step 5: Commit** `evolve, benchmark: older entry points use the campaign directory`.

### Task 5: Pages site reads `campaigns/`

**Files:**
- Modify: `.agents/skills/explaining-campaign-results/scripts/build_site.py`, `.github/workflows/pages.yml`
- Test: `evolve/control/tests/test_build_site.py`

**Interfaces:**
- Produces: `python3 build_site.py campaigns _site` publishes `campaigns/<c>/report/explainer.html` at `/<c>/` and `campaigns/<c>/report/<sub>/explainer.html` at `/<sub>/`; a duplicate published name is an error; sort order and card text as today. `pages.yml` triggers on `campaigns/*/report/**/explainer.*` and runs `build_site.py campaigns _site`.

- [ ] **Step 1: Write the failing test** `test_site_urls`: a temp `campaigns/` with `xswap-next-2026-10-24/report/explainer.html` and `swap-standard-2026-10-22/report/swap-standard-evolve-2026-10-22/explainer.html` produces `_site/xswap-next-2026-10-24/index.html` and `_site/swap-standard-evolve-2026-10-22/index.html`, and the index links both; two sources publishing the same name exit non-zero.
- [ ] **Step 2: Run** `python3 -m unittest evolve/control/tests/test_build_site.py -v` — expected: FAIL.
- [ ] **Step 3: Implement** the collection rule; keep `campaign_date` on the published name.
- [ ] **Step 4: Run** the full Checks list — expected: PASS, including `test_no_old_paths`.
- [ ] **Step 5: Commit** `pages: publish campaign reports from campaigns/ at unchanged URLs`.

### Task 6: Migration tool

**Files:**
- Create: `evolve/control/migrate.py`, `campaigns/migration-seed.json`
- Test: `evolve/control/tests/test_migrate.py`

**Interfaces:**
- Consumes: Task 1 `campaign_store.write`, `write_candidate`.
- Produces: `python3 evolve/control/migrate.py plan` prints the full old→new table without changing anything; `migrate.py apply` performs it and writes `campaigns/MOVED.json` (`{"pre_migration_commit": sha, "moves": [{"from", "to", "how": "git-mv"|"copy"|"copy-rewritten"|"left-in-place", "note"}]}`); `migrate.py links` rewrites Markdown and HTML link targets under `campaigns/*/report/` from `MOVED.json` and records each changed file in `MOVED.json` as `{"rewritten_links": path}`. All three are idempotent; a completed migration makes `apply` print `already migrated` and exit 0 without writing.
- Move rules (from the spec; the seed file carries the per-campaign values):
  - `git mv`: `evolve/control/campaigns/<c>/*` → `campaigns/<c>/`; `benchmark/swap-standard/protocol.json` → `campaigns/swap-standard-2026-10-22/protocol.json`; `benchmark/swap-standard/protocol-<x>.json` → `campaigns/<its campaign field>/protocol.json`; `results/<c>/` → `campaigns/<c>/report/`; `results/swap-standard-evolve-2026-10-22/` and `results/swap-standard-integration-2026-10-22/` → `campaigns/swap-standard-2026-10-22/report/<same name>/`; `results/pilot-summary.json` → `campaigns/_unassigned/report/pilot-summary.json`; `patches/<c>/` → `campaigns/<c>/patches/`; every other `patches/*` entry → `campaigns/_unassigned/patches/`; `benchmark/swap-standard/confirmations/<c>/ledger.json` → `campaigns/<c>/ledger/confirmation.json`.
  - `copy` (gitignored sources, then tracked): `evolve/swap-standard/state-<c>/` and `state-layout-v1/` (→ `swap-standard-2026-10-22`) into `campaigns/<c>/ledger/` except `.lock`, with `task-*.json` into `campaigns/<c>/ledger/tasks/`; `evolve/control/campaigns/xswap-reference-replay/policy.json` (untracked) into its campaign.
  - `copy-rewritten`: `evolve/control/state/<c>/candidates.json` split into `candidates/<id>.json`; `evolve/control/state/<c>/<id>/*` into `candidates/<id>/` except `candidate.patch` (must equal `campaigns/<c>/patches/<id>.patch` byte for byte, else stop with an error); `events.jsonl` into `ledger/events.jsonl`. Any string value starting with `str(PROJECT) + "/"` becomes repository-relative.
  - `left-in-place`: whole-suite protocols `benchmark/{xswap,xswap-p123,xswap-structure,xswap-hole-probe,kernel}/protocol.json`, legacy state `evolve/{xswap,kernel,xswap-structure}/state-layout-v1`, `benchmark/xswap-structure/state-*`, raw `benchmark/swap-standard/runs/` and `evaluations/`. Each listed with a note.
  - After moves, `campaign.json` per seed entry; `protocol_ref`/`protocol_sha256` for `xswap-2026-10-21` (`benchmark/xswap/protocol.json`), `xswap-structure-2026-10-22` (`benchmark/xswap-structure/protocol.json`, note that `benchmark/xswap-hole-probe/protocol.json` also names it) and `xswap-p123-2026-10-23` (`benchmark/xswap-p123/protocol.json`).
  - Empty old directories are removed; `results/README.md` and `patches/README.md` are created with one line each: `Moved to campaigns/<campaign>/ on 2026-10-27; see campaigns/MOVED.json.`
- `migration-seed.json` values (decided here; do not invent others):
  - `line`: `plain` for `swap-standard-2026-10-22`; `xswap` for every other campaign.
  - `machine`: `grok-cloud` for `xswap-tcg-rev3-2026-10-25`; `hurricpc` otherwise.
  - `status`: `open` for `xswap-tcg-rev3-2026-10-25`; `closed` otherwise. `opened`/`closed` dates: first and last `time_unix` in the campaign's `events.jsonl` or ledger, else the date in the name; `closed: null` when open.
  - `baseline_from`: for `xswap-swapin-2026-10-23`, `xswap-next-2026-10-24`, `xswap-tcg-rev3-2026-10-25` and `confirm-h1-ra-phys-2026-10-23`: `{"campaign": "xswap-p123-2026-10-23", "candidate": "xs-desc-lifetime-v1", "commit": "5e84ca928deeacb4eee656806a003f27d1eca82f", "evidence": {"kind": "correctness_fix", "report": "campaigns/xswap-swapin-2026-10-23/report/lifetime-review.md"}}`. `null` for every other campaign.
  - `budget`: copied from each protocol's `budget` (`guest_attempts`, `wall_seconds`) with `probe_guest_attempts: 0` and `approved_over_cap: null`; campaigns with no protocol use `{"guest_attempts": 0, "wall_seconds": 0, ...}`.
  - Campaign set: the eleven policy directories, plus `confirm-h1-ra-phys-2026-10-23`, plus `_unassigned` (no `campaign.json`; holds only `patches/` and `report/`).

- [ ] **Step 1: Write failing tests** on a temp git repo fixture that mirrors one campaign of each kind (swap-standard protocol campaign, older-suite campaign with `protocol_ref`, controller-only campaign, the nested `swap-standard-*` reports, an unassigned patch dir, a gitignored ledger with a `/home/...` worktree path):
  - `test_plan_changes_nothing`: `plan` leaves `git status --porcelain` empty.
  - `test_apply_moves_and_keeps_bytes`: every tracked file existing before `apply` either appears in `MOVED.json` or is outside the moved roots; each `git-mv` destination has the source's sha256; protocol files' sha256 unchanged.
  - `test_no_absolute_paths`: no file under `campaigns/` contains `/home/` or `str(PROJECT)`.
  - `test_campaign_json_valid`: `campaign_store.load` succeeds for every seeded campaign; `xswap-tcg-rev3-2026-10-25` is `open` on `grok-cloud`.
  - `test_patch_mismatch_stops`: a `candidate.patch` differing from the exported patch makes `apply` exit non-zero before any move (moves happen only after all checks pass).
  - `test_idempotent`: second `apply` prints `already migrated`, no file changes; `links` twice gives the same tree.
  - `test_links_rewritten`: a report linking `../../benchmark/swap-standard/protocol-xswap-next-2026-10-24.json` links `../protocol.json` afterwards; numbers and other text are unchanged (diff limited to link targets).
- [ ] **Step 2: Run** `python3 -m unittest evolve/control/tests/test_migrate.py -v` — expected: FAIL.
- [ ] **Step 3: Implement** `migrate.py` (stdlib, `subprocess` for `git mv`). Order: compute the full plan, run every check, then move, then copy, then write `campaign.json` and `MOVED.json`.
- [ ] **Step 4: Run** the full Checks list — expected: PASS.
- [ ] **Step 5: Commit** `controller: add the campaign migration tool and seed`.

### Task 7: Run the migration, rewrite links, generate the index

**Files:**
- Create: `evolve/control/lines.py`, `campaigns/README.md` (generated), `campaigns/lines/plain.md`, `campaigns/lines/xswap.md` (generated)
- Modify: `.gitignore`
- Test: `evolve/control/tests/test_lines.py`

**Interfaces:**
- Consumes: Task 1 `campaign_store.load`; Task 6 `migrate.py`.
- Produces: `python3 evolve/control/lines.py` regenerates `campaigns/README.md` (table: campaign, status, line, machine, opened, closed, baseline) and `campaigns/lines/<line>.md` (campaigns on the line in `opened` order; per campaign its baseline and `baseline_from`, candidates with `status` and `reason`, and a link to `report/REPORT.md` or `report/README.md` when present; last line `Current baseline: <commit> (<campaign>)` from the newest campaign's protocol `baseline_commit`). `close-campaign` (Task 2) calls it after closing.

- [ ] **Step 1: Write the failing test** `test_lines.py::test_line_index`: two fixture campaigns on line `xswap` produce `lines/xswap.md` listing both in date order with their candidates, and `README.md` lists both rows; regenerating twice gives identical bytes.
- [ ] **Step 2: Run** it — expected: FAIL. **Step 3: Implement** `lines.py`; call it from `close-campaign`. **Step 4: Run** — PASS. **Step 5: Commit** `controller: generate campaign and line indexes`.
- [ ] **Step 6: Migrate the real repo.** Run `python3 evolve/control/migrate.py plan > /tmp/migration-plan.txt`; read it; confirm every directory under `evolve/control/campaigns`, `results`, `patches` appears. Run `python3 evolve/control/migrate.py apply`. Add to `.gitignore`: `campaigns/*/runs/`, `campaigns/*/.lock`, `campaigns/*/STOP`, `campaigns/*/ledger/*.tmp`. Verify `grep -rl /home/ campaigns` prints nothing and `git status` shows only renames, additions under `campaigns/`, and the two README stubs. Run the full Checks list — PASS. Commit `campaigns: move every campaign into campaigns/<c>/` with the body naming the pre-migration commit.
- [ ] **Step 7: Rewrite links.** Run `python3 evolve/control/migrate.py links`; `git diff --stat` touches only `campaigns/*/report/**`; `git diff -U0 | grep '^[-+][^-+]'` shows only changed link targets. Commit `campaigns: point report links at the moved files` noting that pinned hashes of these files verify at the pre-migration commit.
- [ ] **Step 8: Regenerate indexes and the site.** Run `python3 evolve/control/lines.py` and `python3 .agents/skills/explaining-campaign-results/scripts/build_site.py campaigns /tmp/site`; compare `ls /tmp/site` with the six names published before (`swap-standard-evolve-2026-10-22`, `swap-standard-integration-2026-10-22`, `xswap-2026-10-21`, `xswap-next-2026-10-24`, `xswap-structure-2026-10-22`, `xswap-swapin-2026-10-23`). Commit `campaigns: generated campaign and line indexes`.
- [ ] **Step 9: Push** `git push origin main`; after the Pages run, open `https://<pages-host>/xswap-next-2026-10-24/` and one nested page and confirm both load.

### Task 8: Rules and docs

**Files:**
- Modify: `AGENTS.md` (**Campaign lifecycle**, **What needs owner approval** first bullet, **Report publication**, **Default campaign budget cap** sentence "Nothing enforces this mechanically yet"), `DESIGN.md` (layout section), `README.md`, `evolve/README.md`, `.agents/skills/closed-loop-evolve/SKILL.md` and `references/swap-next.md` (paths and commands), `benchmark/swap-standard/README.md` (commands use `--campaign`)
- Test: `benchmark/tests/test_no_old_paths.py` (extend)

**Interfaces:**
- Consumes: commands and paths from Tasks 2, 3, 6, 7.
- Produces, in `AGENTS.md`:
  - Lifecycle **Open**: write `campaigns/<c>/policy.json` and `protocol.json`, then `controller.py --campaign <c> open-campaign --line ... --machine ...`.
  - **Run**: commit `campaigns/<c>/ledger/`, `candidates/`, `patches/` and `archive/` directly to `main` at each stage boundary (after a calibration, after each candidate's outcome) and at close; `runs/` is never committed. This replaces "keep runtime state out of commits" for those directories.
  - **Close**: `close-campaign`, which regenerates the indexes.
  - The cap sentence reads "`open-campaign` and the workflow enforce this."
  - "At most one open campaign per machine"; `release-claim --reason` for a stale claim.

- [ ] **Step 1: Extend** `test_no_old_paths` to Markdown files outside `campaigns/*/report/**` and `docs/superpowers/**`: no `results/<c>`, `patches/<c>`, `evolve/control/campaigns`, `evolve/swap-standard/state`, `--protocol benchmark/swap-standard`. **Step 2: Run** — FAIL. **Step 3: Update** the docs. **Step 4: Run** the full Checks list — PASS. **Step 5: Commit** `docs: campaign directories, claim and cap in the rules`, push.

---

## After this plan

Write part 2 (probe tier, mechanism declaration, probe budget pool, contract change, revision 4 KVM protocol and `validity.py` rules) and part 3 (archive admission on `FAST_PASS`, lineage, `PromptSampler` briefs) as separate plans against the layout this plan creates.
