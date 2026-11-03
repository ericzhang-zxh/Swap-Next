# Durable contributor sessions

The session driver connects the existing controller, evaluator, research
metadata and report delivery. An active contributor supplies hypotheses,
implementation, independent review and explanations; verified artifacts
determine progress. The driver never invokes a model or promotes candidate code.

## Contributor ownership

Every contributor has a stable caller-supplied ID. Pass `--contributor <id>`
or export `SWAP_NEXT_CONTRIBUTOR=<id>` for all commands and delegated workers.
The driver never infers that identity from the target session, Git account,
machine, or model name. Several contributors can use the same model and host.

Fresh campaigns create immutable `owner.json`; the session, frozen line
contract and action identity carry the same contributor. Start and Resume may
only continue that owner's campaign. Every action rechecks ownership. Starting
a second campaign creates separate state; it does not import an active
candidate or to-do list from another campaign.

Automatic selection considers only agendas with a matching `contributor`.
An explicitly named foreign or unowned line cannot be frozen. Prepare a new
owned line if none is available. Historical unowned campaigns are not adopted
by Start or Resume. Deliberate ownership reconciliation is separate from this
automatic flow and must have explicit owner direction.

Controller mutations, execution and claim release enforce owned campaigns too.
A busy machine is a resource conflict, not permission to take over its campaign.
Baseline inheritance requires the same contributor. Read-only historical
reports, retained upstream references and validated cache evidence remain
shared. This is routing for cooperative contributors, not OS authentication
against someone who can rewrite the repository.

## CLI and API

The repository entry point is evolve/loop.py. Set your own identity first:

    export SWAP_NEXT_CONTRIBUTOR=your-stable-id

    evolve/.venv/bin/python evolve/loop.py start --campaign example --line research --idea first --machine worker
    evolve/.venv/bin/python evolve/loop.py resume --campaign example
    evolve/.venv/bin/python evolve/loop.py next-action --campaign example
    evolve/.venv/bin/python evolve/loop.py execute --campaign example --action action-...
    evolve/.venv/bin/python evolve/loop.py decide --campaign example --action action-... --decision decision.json
    evolve/.venv/bin/python evolve/loop.py value --campaign example --candidate candidate-one --decision value.json

The direct CLI is python3 -B evolve/session.py COMMAND --campaign NAME.
Commands are start, resume, next, execute, decide and value; next corresponds
to the wrapper's next-action. The required arguments are the same. Start can
select a prepared active line and proposed idea when their IDs are omitted.
It never invents baseline or protocol parameters.

Session(campaign, root, contributor=...) exposes start(line=..., idea=..., machine=...), resume(),
next(), execute(action_id), decide(action_id, payload), and
value(candidate, decision). Tests inject a clock, snapshotter or executor.
The production CLI has no bypass switches. The plan(snapshot) function is pure.

## Durable records

The campaign's machine-local ledger/session.json has schema version 1. It is
ignored by Git because live PID/start-tick receipts and executable paths belong
to this worker. Scientific ledgers, reservations and the immutable
ledger/session-closeout.json remain tracked for public audit.

Session fields:

| Field | Meaning |
| --- | --- |
| contributor | Stable owner, checked against owner.json before every action. |
| campaign, line, machine, idea_id | Exact campaign and current research selection. |
| mode | preparing, research, or legacy recovery. |
| allowed_tiers | Exactly probe and fast. |
| pins | Raw SHA-256 of protocol, policy and frozen research files. |
| rounds | Ordered ideas, proposals and selected candidate identities. |
| decisions | Immutable action-bound contributor judgments. |
| executions | Receipts persisted before launching framework commands. |
| stop_reason | Durable closeout reason, never permission to reset STOP or counters. |
| current_action, status | Latest reconciled action and active/blocked/complete status. |
| publication | Exact report commit and Pages run ID awaiting independent verification. |

A fresh start freezes research.json: scientific line contract, selected idea,
declared upstream alternatives, raw protocol/policy hashes and automatic tiers.
Changing backlog priority does not rewrite that snapshot. Changed pinned inputs
block execution. Recovery of an older campaign without this snapshot uses
legacy mode and finishes original closeout without inventing thresholds.

The ledger/session-closeout.json record preserves frozen inputs, contributor
decisions, command receipts and candidate reasons. The resource authority
remains ledger/budget.json; counted guest reservations, deadlines, STOP files
and machine ownership remain controller-owned.

## Actions, execution and recovery

Each action contains id, stage, kind, reason, identity, expects, input_hashes
and guard. Kinds are agent, command, blocked, running and complete. A command
also contains fixed command, parameters, argv and operation_key. There is no
arbitrary shell command action.

The action ID binds the requested work to observed evidence and guards.
Unchanged evidence yields the same ID. Execute recomputes the next action and
refuses a stale ID. Before subprocess creation it records a unique token,
launcher PID/start tick, command identity and log path. Spawn updates add the
child PID/start tick. Matching processes or a held runtime lock return running.

Repeating execute for a receipted action returns the receipt without launching.
Measurement operation keys bind command, tier and candidate/comparison identity
independently of unrelated file hashes. An unrelated note cannot buy another
measurement of a started arm. Receipts preserve failed and ambiguous attempts.
Recovery can reconcile a dead process from exact retained output; an ambiguous
measurement enters closeout without a silent retry.

After a failed render or live-verification command, `resume` issues a new
delivery action while retaining the failed receipt. It never relaunches a
measurement or republishes an upload. A changed deployment ID may be supplied
while delivery is blocked.

A zero exit code alone never advances an artifact stage. Exact output must be
visible in the snapshot. Automatic measurement dispatch is limited to probe
and fast, including their calibration and bound comparison commands.

## Contributor decisions

Every decision contains kind and a nonempty reason, except visual, whose
structured evidence carries the verification details. Decisions bind the
current action ID, exact identity and input hashes. Repeating identical content
is idempotent; different content cannot replace a recorded action decision.

| kind | Additional fields and permitted stage |
| --- | --- |
| propose | At propose: candidate, exact allowed parent, falsifiable hypothesis, mechanism. |
| fast_selection | At fast_selection: disposition screen/reject, candidate_commit, source_tree, probe_id. |
| reject | With an active candidate: concrete reason retained for candidate closeout. |
| stop | Before campaign closure: reason ending experiments while preserving report delivery. |
| continue | At next_idea: a distinct validated proposed idea, evidence paths and reason; existing profile and remaining budget must cover it. |
| skip_comparisons | At prepare_comparisons: reason and optional retained evidence paths; records missing coverage, never successful comparison. |
| visual | At visual_check: evidence accepted by delivery.record_visual_check. |
| publication | At publish: exact 40-hex commit, numeric run_id and reason; the next command verifies the deployment. |

A counter mechanism has the form CASE:KEY:up or CASE:KEY:down. A structural
declaration has kind reviewed_structure plus claim and falsifier strings.
It requires both profile and frozen-protocol capability. Structural proof
subsequently binds exact source tree, declaration, protocol hash and review.

Example fast selection:

    {
      "kind": "fast_selection",
      "disposition": "screen",
      "candidate_commit": "<exact commit from the action>",
      "source_tree": "<exact tree from the action>",
      "probe_id": "<exact probe ID from the action>",
      "reason": "The measured mechanism justifies one latency screen."
    }

A done, pass or accepted boolean cannot replace implementation, scope, review,
correctness, calibration, measurement, value or report evidence.

## Evidence and closeout

The session reads actual worktree commit/tree/dirty state. Scope results,
reviews and measurement rows must bind that identity. A plain review pass
cannot clear a recorded veto. Exact resolutions and descendant applicability
come from reviews.py. Correctness requires trusted raw provenance; a counted
attempt without a validated result remains incomplete.

Native reused calibration rows must pass calibration_cache.validate_alias,
which rechecks source hashes, current scientific identity, review vetoes and
expiry. The original measurement finish time controls freshness. Reuse does
not become an independent measurement or create a new guest reservation.

The value command uses the [research value schema](research-schema.md).
The session derives expected identity, numerical result, review state and
comparison coverage independently before writing the immutable value record.
The contributor explains complexity and engineering tradeoffs; authored
numbers cannot override the evaluator. Positive research value remains
unaccepted code.

STOP, deadline, exhausted resources, failed evidence and an explicit stop
retain patches and close candidates, then close the campaign and release its
claim. Other active comparison candidates are named for explicit closeout.
The session never clears STOP, resets counters or extends a deadline.

A closed campaign proceeds through explanation, rendering, visual inspection,
publication and independent live verification. Complete requires the exact
successful deployment, matching live HTML and report index entry.

## Verification boundary

The test_session.py suite exercises the public Session API with temporary Git
repositories and synthetic runtime callbacks. It covers start through report
delivery, recovery, stable receipts, guest/arm deduplication, STOP/deadline/budget
closeout, exact-tree reviews, calibration reuse and practical value.
Renderer output is real; screenshot and network fixtures are synthetic.
The suite launches no kernel builds, guests, publication or performance run.
