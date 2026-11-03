# Upstream comparison contract

A comparison round uses the existing standard-suite runner, validity parser,
correctness validator, analyzer and campaign budget. Its immutable input is
`campaigns/<campaign>/comparisons/<id>.json`. This file is a measurement plan,
not a new ledger or permission to execute. The ordinary evaluation row stores
the plan hash and explicit comparison identities.

## Arm model

A plan contains `baseline` (B), `upstream` (B+P), `candidate` (B+C), and
optionally `combined` (B+P+C). B is the campaign's frozen baseline; an inherited
experimental stack must be described as such, never as pristine upstream.

Each compatible arm records:

- Exact `commit`, `tree`, `build` and `build_manifest_sha256`.
- `patch_sha256`: SHA256 of the cumulative B-to-arm diff produced with
  `git diff --no-ext-diff --no-textconv --binary --full-index B COMMIT --`.
- A `candidate` controller record ID, except for B.
- `correctness`: raw evidence references, each `{"path": "...", "sha256": "..."}`.

The upstream arm also records `source`: primary HTTPS URL, series `revision`,
original patch/mbox `patch_sha256`, exact `dependencies` (commit IDs), and the
downloaded `artifact` reference. Preparation can omit the artifact; execution
cannot. The source patch hash identifies the received patch bytes, while the
arm patch hash identifies the cumulative applied diff.

A compatible combined arm records `composition.upstream_commit`,
`composition.candidate_commit` and a rationale. Its actual Git ancestry must
include P. Independent review still checks that the implementation preserves
the intended mechanisms and explains any conflict resolution; ancestry alone
does not establish semantic composition.

An upstream or combined arm can instead have
`"compatibility": "incompatible"` and a concrete `reason`. Such contrasts
are `NOT_COMPARABLE`, with no score or inferred zero benefit.

## Plan shape

Hashes below are explanatory placeholders, not runnable provenance:

```json
{
  "schema_version": 1,
  "id": "readahead-comparison",
  "campaign": "example-campaign",
  "protocol_sha256": "<frozen campaign protocol byte hash>",
  "environment": {
    "machine": "hurricpc",
    "fingerprint": "<current trusted evaluator fingerprint>",
    "accelerator": "kvm",
    "guest": {"vcpus": 8, "mem_mib": 8192, "swap_gib": 16},
    "input_config_sha256": "<swap-standard.config byte hash>",
    "guest_image_sha256": "<image.json image_sha256>"
  },
  "common_base": {"commit": "<B commit>", "tree": "<B tree>"},
  "tier": "fast",
  "pair_order": ["AB", "BA", "AB", "BA"],
  "correctness_routes": [{"mode": "xswap", "backend": "disk"}],
  "arms": {
    "baseline": {"compatibility": "compatible", "...": "..."},
    "upstream": {"compatibility": "compatible", "...": "..."},
    "candidate": {"compatibility": "compatible", "...": "..."}
  },
  "contrasts": [
    {"id": "upstream-control", "control": "baseline", "treatment": "upstream"},
    {"id": "candidate-control", "control": "baseline", "treatment": "candidate"}
  ]
}
```

Those two contrasts are required. Add a direct candidate-versus-upstream
contrast or upstream-versus-combined contrast when its research question and
cost justify it. The list order is the frozen comparison sequence.

Case definitions, metric directions, primary endpoints, calibration/comparison
pair counts, validity rules and budgets come from the campaign protocol. Plans
cannot override them. Each contrast repeats controls using alternating AB/BA
pairs. Every distinct control needs its own A/A calibration. Identical control
identity, input configuration, protocol, environment and fresh calibration can
be reused across contrasts. B's calibration cannot silently validate P as a
new control.

Correctness coverage defaults to every distinct swap-in mode/backend in the
protocol. A reviewed new protocol may explicitly set
`comparison_correctness_routes` to define its coverage contract. A comparison
plan cannot narrow that set. The current raw correctness parser has limited
backend/mode support; an unsupported route is a real capability blocker.

## Integration API

All functions live in `evolve/comparisons.py`:

| API | Result |
| --- | --- |
| `validate(contract, protocol, protocol_sha256=None)` | Validate schema and fixed measurement bindings without I/O. |
| `freeze(project, contract, protocol)` | Create canonical immutable bytes; an identical repeat is a no-op, a replacement is refused. |
| `load(project, campaign, comparison_id, protocol)` | Load canonical bytes and verify protocol hash and path identities. |
| `execution_plan(contract, protocol, contrast_id, action="evaluate")` | Explicit schedule, arm bindings, metric specification, required guests and ledger identity; `action="calibrate"` uses the control in both slots. |
| `planned_cost(contract, protocol)` | Minimum calibration/comparison/correctness counts and maximum performance counts including validity retries; no budget writes. |
| `verify_sources(contract, source_repo)` | Actual commit/tree, common-base ancestry and full cumulative diff hashes. |
| `validate_evidence(contract, protocol, project, fingerprint, machine, source_repo=None)` | Build files plus native counted raw correctness proofs for all compatible arms. |
| `reusable_calibration(row, plan, contract, now, max_age)` | Exact-control, protocol, environment, shape and freshness decision. |
| `reconcile(contract, protocol, ledger_rows)` | Evidence-bound measured contrast summaries; missing/incompatible evidence remains explicit. |

`execution_plan` returns `identity`; persist it as `row["comparison"]`,
along with `row["protocol_sha256"]`, `row["fingerprint"]`, `row["tier"]`,
`row["action"]` (`calibrate` or `evaluate`), and ordinary result fields.
Each schedule item has `pair`, `case`, `slot` (a/b), actual `arm`,
`ordinal` and `order`. Select the arm's build and commit directly; do not
replace `protocol["baseline_commit"]` or rewrite the frozen protocol.

Before execution the trusted controller must independently check source scope,
review dispositions and eligibility for every non-baseline arm. The workflow
must enforce campaign ownership, STOP, tier authority, deadline and budget,
follow the plan sequence, retain failed reservations, and exclude comparison
rows from ordinary candidate-only duplicate/admission logic. Comparison
results do not automatically add a candidate to the population.

Use the same validity and analysis functions on the explicit A/B schedule.
Keep `calibration_key` on the calibration row; ordinary calibration without
this binding requires explicit provenance reconciliation before reuse.
Calibration and comparison rows remain in the existing campaign ledger.

## Limitations

These helpers do not establish live environmental stability, retrieve upstream
patches, approve scope, dispatch workers or run measurements. The caller owns
those steps. A report does not synthesize C-versus-P effects from unrelated
historical numbers. Fast results stay screens, and code promotion remains a
human decision.

Tests use temporary Git fixtures, fake kernel-image bytes and an injected
correctness validator where appropriate; one fixture confirms that the real
validator refuses summary-only proof. No fixture is runtime performance
evidence.


## Workflow runtime and shared upstream references

`comparison_runtime.prepare(flow, project, protocol_path, comparison_id,
contrast_id, action, row, output_dir, fingerprint)` returns `PLANNED`, `REUSED`,
or `NOT_COMPARABLE`. `PLANNED` supplies the exact control/treatment builds and
commits, pair count and verified control calibration to the existing workflow
loop. The workflow retains campaign/STOP/deadline/budget gates, guest
reservations, validity checks, analysis and final ledger/report writes.
Comparison rows never enter the ordinary population archive.

Within a campaign, reuse replays the original report, complete scheduled raw
attempts including invalid retries, serial logs, reservation tickets and A/A
analysis. A new plan ID cannot retry an incomplete, failed, stale or duplicate
source-tree contrast. Passed A/A may renew only after its fixed expiry.

The repository-wide `benchmark/reference-cache` can supply an intact measured
B/P contrast across campaigns. `register_reference(flow, project,
protocol_path, row)` indexes a completed, saved original `upstream-control`
comparison and leaves that report, ledger and budget unchanged. Store its
registration receipt separately. `reference_identity(...)` pins the actual
B/P commits/trees, build image/config hashes, upstream source revision, guest
image and shape, accelerator, measurement harness, protocol science, tier and
contrast. Reuse requires an exact semantic key and finite original lifetime;
only explicitly cosmetic campaign/location/budget metadata is excluded.

The trusted `validate_cached_reference(project, identity, provenance)` callback
always replays the source campaign's original frozen protocol and fingerprint,
including its original calibration. It checks current source review vetoes
and immutable raw evidence again. The target's scope, exact-tree reviews and
correctness evidence still pass normal preparation. Expired, modified or
scientifically mismatched references cannot skip a measurement.

A reused alias keeps `reused_from.campaign`, `measurement_started`,
`measurement_finished`, original report/hash and cache record/key bindings.
It declares `measurement_reused=true`, `independent_measurement=false`,
`new_guest_attempts=0`, and `may_pair_with_new_arm=false`; no source budget or
sample count is increased. Original B/P pairs stay together. The target C
comparison needs its own current-campaign raw control/treatment pairs and
fresh exact-control A/A. No C/P effect is inferred from cached B/P and new B/C.

Runtime fixtures exercise the actual `Workflow.run` path using synthetic
results: a nonbaseline P control reaches the existing runner, and cache hits
invoke no guest/build reservation, guest process, or population archive.
These tests launch no real kernel build or guest.
