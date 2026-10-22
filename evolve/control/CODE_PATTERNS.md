# Kernel code taste and review rules

Follow the target subsystem's conventions and the pinned kernel's
`Documentation/process/coding-style.rst`. Checkpatch is necessary, not sufficient.

## One intent per patch

Before editing, state the workload, the profile evidence, the mechanism and
the expected cost. Keep formatting, renames and cleanup out of an
optimization patch. Split independent changes, but never so that an
intermediate commit breaks an invariant.

## Let the representation do the work

Repeated special cases usually mean the state representation is wrong. Look
for a data structure or helper that expresses the invariant before adding
flags or branches, and use existing kernel APIs rather than one-caller
abstractions. A helper earns its place by naming an operation or an invariant,
not by its number of callers.

Minimize what a reader has to remember. Use direct control flow and early
exits instead of deep nesting. Drop a redundant flag or check only when a
visible invariant makes it redundant. Keep assertions and defensive checks.

## Ownership and lifetime are explicit

For every affected resource, the review fills in this table:

| Resource | Owner / reference holder | Published when | Released when | Protected by |
|---|---|---|---|---|
| folio | | | | folio lock / reference |
| swap entry or slot | | | last-user condition | target-version locks |
| compressed object | | | | |
| memcg charge | | charge point | uncharge / rollback | accounting rules |

Trace protection across the whole lifetime: unlocked allocation, publication,
lock drop and reacquire, error cleanup, RCU callbacks, final release. Holding
a lock at one lookup does not cover publishers or free paths that skip that
lock. RCU protects specific lifetimes only. `READ_ONCE`/`WRITE_ONCE` do not
replace synchronization.

Move preparation outside a lock only when the allocation context allows it
and the shared state is revalidated afterwards. Document lock order and the
lifetime of any pointer kept across calls.

## Failure paths are design

Use cleanup labels where they make ownership transitions readable. Undo in
reverse order and handle partial success. Preserve these:

- error returns
- accounting
- NOFS/NOIO constraints
- swapoff behavior
- large folios

Never turn an allocation failure into success, swallow an I/O error or bypass
memcg charging. Comments explain why a transition is safe, not what each
statement does.

## Optimization claims need a path and a measurement

Name the path the change affects and show that the workload exercises it.
Removing a load or a branch is a hypothesis until an end-to-end measurement
confirms it. Account for code size, cache behavior, lock hold time, memory use
and any work shifted elsewhere. Report regressions next to wins. Never tune the
benchmark or specialize code for it.

## Review output

The review states:

- the problem and its evidence
- the minimal change
- the invariants, lock and failure paths
- the checks run and the checks missing
- the per-workload effects
- the commit to revert

Correctness findings, maintainability suggestions and performance
hypotheses go in separate sections. A blocking finding names a concrete
execution path and its consequence. Resolve any open lifetime question before
running experiments that depend on it.

Build with an external `O=` directory, so source worktrees stay clean. Do not
weaken sanitizers, warnings, assertions or tests. AI tools add no
`Signed-off-by`.
