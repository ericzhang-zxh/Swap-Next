---
name: closed-loop-evolve
description: Run or resume bounded optimization campaigns that connect a concrete hypothesis, isolated candidate edits, fixed benchmark evidence, and feedback-driven next steps. Use for iterative experiment or OpenEvolve workflows; creating this skill or inspecting a campaign does not launch experiments.
---

# Closed-loop evolution

Own the experiment design and decisions; use existing controllers, evaluators,
and databases rather than inventing another orchestration layer. The outcome
may be a rejected hypothesis, a coverage gap, or an inconclusive result.

For Swap Next, read [the repository binding](references/swap-next.md) and the
checkout's current AGENTS instructions. For another project, identify equivalent
entrypoints and evidence requirements before adapting this workflow. Do not
apply Swap Next's kernel-specific gates to unrelated projects.

## Establish or recover the campaign

- Identify the user's objective: completing functionality, fixing a defect, or
  improving a measured cost. A runnable upstream draft is not a complete design.
  If unfinished functionality is the objective, establish the missing behavior
  before proposing heuristic tuning.
- Recover the baseline commit, current candidates, prior decisions, raw evidence,
  evaluator version, budgets, deadline, STOP state, and any owned active process.
  Reconcile controller records, evaluation reports and search ledger before
  creating another candidate. A new checkout or empty database does not reset
  an existing campaign's budget.
- Distinguish inspection, preparation, and execution. Continue actions already
  authorized by the user. If a missing scope or budget decision is necessary,
  finish independent preparation and ask only for that decision. Do not infer
  unattended scheduling or promotion from permission to experiment. Publication
  follows the project's standing rule; for Swap Next, AGENTS.md publishes every
  campaign report.
- Before execution, record the target behavior, one primary metric, guardrails,
  allowed edits, fixed baseline, required coverage, resource limits, total budget,
  stopping conditions and evidence destinations in the existing campaign format.
  Reuse the current contract; do not create a parallel ledger.

## Make the benchmark capable of answering the question

Inspect workloads and raw evidence, not only metric names. Explain the affected
path, unit of measurement, confounders, correctness checks and missing coverage.
A score can be computable without measuring the intended improvement.

Freeze workload, configuration, order/seeds, metrics and acceptance rules before
comparing candidates. Validate the baseline/environment and use calibration
appropriate to the protocol. If A/A varies enough to hide the proposed effect,
do not select a winner from means alone: investigate state, improve measurement,
or run a bounded diagnostic only if that remains within the campaign's scope.

A benchmark or baseline change is a new protocol revision with new calibration;
old evidence remains historical. Do not change measurements or thresholds during
a comparison to rescue a candidate. Instrumentation may support a hypothesis but
must be applied consistently and its cost distinguished from the target cost.

## Execute one feedback round

1. **Propose.** Use the latest evidence and selection feedback to state one
   mechanism, expected benefit, possible regression and falsifying observation.
   A selected reference is not permission to change the frozen patch base.
2. **Create and implement.** Use the project's controller and isolated candidate
   directory. Delegate bounded execution when useful and permitted; the primary
   agent retains scope, architecture, permissions and acceptance. Workers receive
   the existing task contract and must not alter the benchmark or delegate again.
3. **Review and check.** Inspect the actual diff and critical invariants, then run
   required static gates. For kernel changes, use the repository's kernel review
   skill and process rules. Reject unsafe or out-of-scope candidates before boots.
4. **Evaluate.** Use the trusted evaluator with the immutable candidate identity.
   Retain failed builds, timeouts, raw measurements, backend/configuration identity
   and per-run results. Never execute candidate-supplied host scripts. Do not run
   competing build/benchmark jobs that invalidate the measurement protocol.
5. **Reconcile.** Bind the result to its request, candidate commit, baseline,
   image/configuration, suite and raw evidence. Missing or mismatched evidence is
   incomplete, not PASS. After interruption or ambiguous completion, inspect
   artifacts and processes before deciding whether a retry is valid; never
   discard the attempt or silently rerun for a better score.
6. **Decide and record.** Separate correctness gates, mechanism observations,
   performance evidence and discovery score. Keep per-workload regressions and
   uncertainty visible. Close the candidate with a reason and record the next
   hypothesis or stop decision through the existing workflow. Never insert
   fabricated metrics into the search database.

## Continue, revise, or stop

Continue only when a next hypothesis is supported by evidence, fits the authorized
scope, and has enough budget for the required checks. Do not generate trivial
constant variations merely to fill an iteration count. Report budget units
separately: candidates, builds, guest attempts and elapsed time are not equivalent.

Stop the affected experiment on STOP/deadline/budget exhaustion, correctness
failure, invalid provenance, or measurement failure that prevents interpretation.
Diagnose and preserve evidence within scope; do not widen permissions, erase
state, or extend a frozen campaign. If the user authorized a new campaign, prepare
its distinct contract instead of rewriting the completed one.

A high sorting score does not establish a reliable improvement. Promotion requires
the project's actual acceptance evidence and authority; never auto-merge from a
pilot score. If nothing meets acceptance, say so.

## Close the campaign

When a campaign stops for any reason, closing it includes the project's review
artifact, not only the written report. Update the report's status and findings
first, then produce the review artifact the project defines (for Swap Next, the
explainer page; see the binding) from the same evidence, and link it from the
report. Do this even if nothing was accepted or the campaign ended early.
Generating the artifact is part of closing. Follow AGENTS.md for delivery,
independently of candidate promotion. For Swap Next, every campaign report is
uploaded and published, then handed to the owner for review, including rejected
and inconclusive outcomes. Experiment work is committed directly to main
without a pull request. Verify that commit's Pages deployment, live campaign
page and index. Only an explicit owner request withholds a push or keeps a
report private. Check current origin/main delivery rules when resuming an older
experiment branch. An agent-authored publication flag cannot revoke that
authorization. Frozen experiment inputs, STOP state, budgets and candidate
promotion gates remain unchanged. An experiment STOP or exhausted budget stops
builds and guests; it does not cancel this closeout.

For Swap Next, load `.agents/skills/explaining-campaign-results/SKILL.md` before
building the human-review HTML. Its presentation contract is: verdict first →
context and motivation → actual changes → results and explanation → next steps.
Explain changes from system to detail: locate the change in the larger architecture
and end-to-end path before zooming into its local before/after mechanism.
Use the approved three-level visual standard: whole-system scene → subsystem
location → concrete before/after, with consistent objects and optional step-through
interaction. Avoid prose disguised as chains of boxes.
Prefer diagrams and charts; exact data and full evidence stay closed by default,
including on mobile. Keep failed gates and material limits visible in the overview.
The reporting skill owns the detailed layout and visual acceptance checks.

## Handoff

Return the hypothesis and exact revision, work actually performed, passed/failed/
missing checks, per-workload findings and uncertainty, decision, evidence links,
and remaining budget or stop reason. Explicitly state whether anything is still
running. Keep sensitive/raw machine data private and follow existing publication
authorization. Document review, static tests, packaging, and real runtime
validation are different delivery states.
