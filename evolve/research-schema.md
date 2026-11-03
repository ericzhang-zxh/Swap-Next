# Research agendas and practical value

The research module adds metadata to the existing campaign workflow. It never
launches a model, build, guest or evaluator. Submitted ideas and reports are
data, not executable worker instructions.

## Integration API

| Function | Contract |
| --- | --- |
| load_profile(id, root) | Load a trusted evolve/profiles/<id>.json, never a candidate-supplied path. |
| capability_readout(profile, protocol, policy, root) | Check actual protocol parameters, profile coverage, tiers and caps. Ready is not authorization. |
| validate_line / validate_idea | Validate research intent, upstream alternatives, finite costs and semantic complexity. |
| line_contract(line, profile) | Freeze profile version/hash, anchor and value policy. Persist under research.json → line_contract before evaluation. |
| validate_contract(contract, root) | Detect changed profile or value-policy snapshots. |
| line_spending(root, line) | Derive totals and open commitments from existing budget ledgers. Missing history is unknown. |
| line_budget(line, spending, requested, exclude_campaign) | Check an allocation. The controller must serialize check and allocation under its allocation lock. |
| select_line(root, line_id) | Rank declared priorities and filter missing capabilities/budgets; return rationale without launching work. |
| performance_from_report(report) | Extract facts from retained trusted evaluator output. |
| assess_value(decision, contract, expected_identity) | Apply practical-value criteria; never promote code. |
| record_value(campaign_dir, candidate, decision, contract, expected_identity, root) | Verify retained evidence; atomically write candidates/<id>/value.json once. |

The controller still owns review vetoes, isolation, permissions, machine
ownership, STOP, runtime provenance and reservations. It must independently
reconcile expected_identity and structured review state before recording value;
an authored review_status is not a substitute for a review.

## Line record

campaigns/lines/<line>.json has schema version 1 and these fields:

- line, question, status (active, paused, retired), profile.
- Exact anchor_commit and current baseline_commit.
- value_policy: min_useful_effect, equivalence_margin,
  requires_upstream_comparison, and the rationale fixed before measurement.
  Effects are fractions of a higher-is-better ratio minus one: a
  baseline/candidate latency ratio of 1.10 has gain 0.10.
- resource_ceiling: lifetime guest_attempts and build_attempts across all
  campaigns on the line. Wall-clock deadlines remain campaign-local.
- upstream_refs, each with id, source_url, series revision, relevance, exact
  base_commit, resulting commit and tree. An empty list requires
  no_upstream_reason. Missing data never means no alternative exists.
- ideas: research backlog. Higher numeric priority is selected first;
  ties use line and idea IDs for deterministic recovery.

An idea includes id, status (proposed, selected, rejected, completed, blocked),
priority, change_type (optimize, simplify, redesign, repair), bottleneck,
mechanism, mechanism_evidence_type, affected_paths, expected_benefit,
simpler_alternative, falsifier, required_evidence, explicit upstream refs or a
none-relevant reason, estimated_cost (guest_attempts and build_attempts),
selection_reason, and complexity.

The frozen scientific snapshot excludes changing ideas, priorities and current
baseline. Updating them does not invalidate an active campaign. Each campaign
still freezes its own baseline and protocol independently. A new value threshold
or profile requires a new campaign contract.

Spending reads existing ledger/budget.json: guests + probe_guests is total
attempts; builds is build attempts. Closed and failed campaigns remain counted.
Unused open allocations are commitments. exclude_campaign removes only that
campaign's unused commitment, never spending. Missing historical ledgers must
be reconciled before more allocation. No second spending ledger is created.

## Profiles and capability gaps

swap-core preserves existing file scope and probe/fast measurements. Mechanism
choices are a counter shift or exact-tree reviewed structural evidence, so
same-count simplifications can describe their mechanism. Structural evidence
does not replace runtime correctness, metadata checks or latency.

swap-architecture describes broader representation/reclaim scope and is
explicitly non-executable. It names missing full correctness matrices,
total-metadata/reclaim-CPU endpoints and observable adapters. Candidate policies
can narrow trusted scope; they cannot widen it or enable missing capabilities.
New protocol revisions still need the trusted validity validator.

Preflight reports the existing plain-mode full-correctness gap. It never claims
fresh calibration or successful execution.

## Complexity and value

Both complexity.parent and complexity.baseline describe every dimension:
state, lifetime, locking, error_paths, configuration, test_burden, interfaces,
and memory_cost. Each has a change (decreased, unchanged, increased, mixed,
unknown) and concrete reason. There is no scalar complexity score or
lines-of-code reward.

A value decision binds scientific_sha256 to the frozen campaign contract.
Its identity has exact candidate_commit, candidate_tree, parent_commit,
parent_tree, baseline_commit, raw-file protocol_sha256, evaluation_id, and
repository-relative evaluation_report.

It additionally records:

- scientific_result: screen, incomplete, regression, correctness-failure;
  review_status: clear, pending, blocked.
- Both complexity comparisons, evidence paths, reason, learning_value, and
  complexity_justification when obligations increase.
- performance extracted by performance_from_report: normalized_gain,
  noise_relative, scored_guards_pass, and trusted gain_interval when available.
  Incomplete/failed evidence uses null, never fabricated zero measurements.
- upstream_comparison: complete, missing, incomparable, not-applicable; with
  reason and evidence paths. Relevant alternatives need a complete comparison
  before a positive research-value decision.
- Explicit frontier_eligible and frontier_reason supported by simpler
  alternatives. advisory_flags contains unresolved material evidence paths.

Results are rejected, exploratory, worthwhile-to-confirm, simplification, or
review-blocked. Small gains that do not justify new obligations are rejected.
A simpler candidate needs an interval wholly within the frozen equivalence
margin; a non-significant difference is insufficient. A child adding
parent-relative complexity remains exploratory when only cumulative baseline
performance is measured: inherited gains cannot establish marginal value.

These are research dispositions. Positive outcomes still require confirmation
and human code promotion. Numerical facts and evidence hashes use the same
retained files as evaluation. Identical writes are idempotent; value.json is
immutable. Revised interpretation needs an appended revision workflow.

## Read-only CLI

    python3 -B evolve/research.py validate campaigns/lines/<line>.json
    python3 -B evolve/research.py select --line <line>
    python3 -B evolve/research.py profile swap-core --protocol campaigns/<c>/protocol.json
    python3 -B evolve/research.py value <decision.json> <frozen-line-contract.json>

CLI previews do not reserve resources or persist decisions. The controller
records value only after reconciling runtime evidence and review.
