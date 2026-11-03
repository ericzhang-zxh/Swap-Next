# Reference evidence cache, version 1

`reference_cache.py` indexes original evidence under
`benchmark/reference-cache/<kind>/<record_sha256>.json`. Registration appends an
immutable reference. Lookup reads the original files again; it creates no
build, guest, reservation, candidate, archive entry or campaign. Cache data is
local ignored runtime state. Keep raw evidence at its original paths.

## Public API

- `semantic_identity(kind, identity)` returns the scientific identity used for
  matching. `cache_key(kind, identity)` hashes its canonical finite JSON.
- `register(root, kind, identity, provenance, coverage=None,
  max_age_seconds=None)` verifies and indexes an original artifact. Failed
  verification produces a historical record, never a passing result.
- `lookup(root, kind, identity, context=None, now=None)` returns `reusable`,
  `new-measurement-needed`, or `historical`, with reasons, original provenance,
  coverage and differing identity fields. It rechecks recorded file hashes and
  invokes the native verifier before returning `reusable`.
- `inventory(root, kind=None)` is a cheap integrity-checked index listing; it
  does not establish current usability. The CLI exposes the same three
  operations using JSON identity, provenance and optional context files.

All identities require exact `source_commit` and `source_tree` Git object IDs.
Unknown identity and protocol fields remain significant. Only the explicit
`COSMETIC_PROTOCOL_FIELDS` allowlist is omitted from semantic matching: campaign
and output-location names, aggregate attempt/wall budgets and population
ceilings. Guest timeout, tier cases, pair counts, validity, calibration age,
noise policy, source revision, environment and evaluator hashes remain bound.

## Kinds and native verification

| Kind | Additional identity | Verification and reuse |
| --- | --- | --- |
| `upstream-source` | Pinned URL, revision, base commit and source-byte hash | Retained source bytes, manifest and Git tree must agree. A new upstream revision has a different key. |
| `build` | Input and output config, image and build-manifest hashes | Exact uninstrumented successful build, existing image, config and log. |
| `review` | Review-policy hash | Native immutable review record for the exact source tree, hashed policy/evidence and current review blockers. An unresolved veto blocks reuse. |
| `correctness` | Runtime identity below | Native `correctness_proof.validate`, counted reservation, raw serial and result sidecar, exact build and original campaign binding. |
| `calibration` | Runtime identity, tier and A/A contrast | Raw attempts, reservation proofs, serial reparsing, validity and native analysis replay. Expiry uses the original observation time. |
| `performance` | Runtime identity, tier and exact contrast | Complete paired raw observations and native analysis replay, including original valid A/A. New B/P/C reports use `evaluation_format: comparison-runtime-v1` and `comparison_runtime.validate_cached_reference`. |

Runtime identity contains the complete source `protocol`, `machine`,
`accelerator`, guest vCPU/RAM/swap shape, exact `builds` keyed by commit, guest
image/initrd/source provenance and `harness` path-to-hash map. Harness hashes
include runner, parser, validity and evaluator/proof code; comparison-runtime
records additionally bind the comparison modules. The original protocol file
must equal the unstripped source identity during registration and revalidation.

Provenance always requires `artifact`, `artifact_sha256` and `observed_unix`.
Runtime evidence also requires original `campaign`, `protocol_path` and raw
`protocol_sha256`; measurements bind their evaluator `fingerprint`. Reviews
name `review_policy`; upstream sources name `source_manifest`. Legacy
performance reports name `calibration_report`. All evidence paths are
normalized repository-relative existing regular files; symlinks are rejected.

## Time, coverage and comparison boundaries

Calibration expires at `observed_unix + calibration_max_age_seconds` from its
original frozen protocol. An optional shorter age is allowed; registering or
referencing it never renews that clock. A legacy performance report must have
used A/A within that validity window at its original measurement time.

Cross-campaign performance is historical by default. Reuse of a complete
upstream B/P contrast requires all of:

- Exact scientific identity with `reference_role: upstream`.
- A finite `max_age_seconds` set when registering the original evidence.
- Lookup context `reuse_intact_contrast: true` and
  `purpose: upstream-reference`.
- Intact raw paired evidence and a currently valid reference window.

The result retains its original campaign, fingerprint and timestamp, sets
`cross_campaign_reused: true`, and always reports
`independent_measurement: false` and `may_pair_with_new_arm: false`. A cached
baseline arm cannot be paired with a fresh candidate arm. Current C comparisons
and their required A/A remain separate measurements under the active protocol.

`context.required_coverage` can require `gates`, `cases` and `backends`;
uncovered requirements return `new-measurement-needed`.
`context.review_blocked: true` makes any reference historical. Correctness
always returns `reconciliation_required: true`: the caller must reconcile
coverage and the active protocol and retain the original proof provenance.
Cache lookup never relabels a proof as a new campaign execution.

## Stored record and limitations

Each record contains schema version, kind, semantic key, full original
identity/provenance, native verification, hashed evidence list, expiry and
`original_budget_unchanged: true`. `record_sha256` hashes all other fields and
matches its filename. Re-registering identical evidence is idempotent;
different original observations receive distinct records. Writes are locked
and atomic. Corrupt records fail closed.

This is an evidence reuse index, not a measurement scheduler or independent
reviewer. Callers decide whether a reusable kind satisfies the next action.
Missing or changed evidence, environment drift, source/evaluator changes,
expired windows and insufficient coverage require new evidence. Synthetic
unit fixtures verify these boundaries without real kernel builds or guests.
