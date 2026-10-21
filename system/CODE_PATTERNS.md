# Kernel code taste and review rules

Follow the target subsystem's existing conventions and the pinned kernel's
`Documentation/process/coding-style.rst`. These rules guide design and review;
checkpatch compliance alone does not establish maintainability or correctness.

## One coherent intent

State the triggering workload, available profile evidence, proposed mechanism,
and possible cost before editing. Prefer a small, reviewable change. Keep
unrelated formatting, renaming, cleanup and speculative abstractions out of an
optimization patch. Split independent changes; do not split a change so that an
intermediate commit breaks an invariant.

## Make the representation do the work

Repeated special cases can indicate a poor state representation. Consider whether
an existing data structure or helper expresses the invariant more directly before
adding flags or branches. Do not redesign a subsystem without evidence and scope.
Use existing kernel APIs rather than creating a parallel abstraction for one call.
A helper is useful when it gives a meaningful operation or invariant a name, even
if it has only one caller; reuse count alone does not decide its value.

Reduce the state a reader must remember. Prefer direct control flow and sensible
early exits to deeply nested branches, but do not minimize lines at the expense of
ownership or failure handling. Avoid unnecessary boolean state and redundant
checks when their removal is justified by a visible invariant. Do not remove
assertions or defensive checks merely because the expected path passes them.

## Make ownership and lifetime explicit

For each affected resource, record the following in the candidate review:

| Resource | Owner or reference holder | Publication | Release | Protection |
|---|---|---|---|---|
| folio | Identify the holder | State when visible | Identify final release | folio lock/reference |
| swap entry or slot | Identify the owner | State when usable | State the last-user condition | actual target-version locks |
| compressed object, if affected | Identify the owner | State publication | State release | relevant lock/reference |
| memcg charge, if affected | Identify the charged owner | State charge point | State uncharge/rollback | accounting rules |

Trace protection across the complete lifetime, including unlocked allocation,
publication, lock dropping, reacquisition, error cleanup, RCU callbacks and final
reference release. A lock held at one lookup does not prove every publisher or
free path takes that lock. RCU protects particular lifetimes; it does not replace
state validation, a folio lock or acquiring the required reference.

Use existing locking and reference helpers. Explain lock order and the lifetime
of pointers retained across calls. Expensive preparation may move outside a lock
only if the allocation context permits it and shared state is revalidated on
reentry. Never move allocation or I/O blindly. READ_ONCE/WRITE_ONCE are not
substitutes for required synchronization or lifetime protection.

## Treat failure paths as part of the design

Use cleanup labels when they make ownership transitions easier to follow. Undo
acquisitions in reverse order where appropriate, and handle partial success.
Preserve API errors, accounting, NOFS/NOIO restrictions, swapoff behavior and
large-folio cases. Do not turn allocation failure into false success, swallow I/O
errors or bypass memcg charging. Explain why a subtle transition is safe rather
than narrating each statement in C.

## Require evidence for optimization claims

Identify the affected path and whether the workload exercises it. A removed
load or branch is a mechanism hypothesis, not an end-to-end performance result.
Account for code size, cache behavior, lock hold time, memory use and shifted work
when relevant. Keep negative results and per-workload regressions visible.
Never change the benchmark, thresholds, seeds, timing window or warnings to make
a candidate look better. Do not specialize code for benchmark names or hosts.
Missing profiles or unmeasured effects remain explicit limitations.

## Review and validation

Report the problem/evidence, minimal change, invariants, lock and failure paths,
coverage and missing checks, per-workload effects, and the exact commit to revert.
Separate correctness findings from maintainability suggestions and performance
hypotheses. A preference is not a bug. Tie a blocking finding to a concrete
execution path and consequence; unresolved lifetime assumptions must be resolved
before runtime experimentation that depends on them.

Use checks appropriate to the changed paths and repository policy. Build with
external O= output directories; keep source worktrees clean. Do not weaken
sanitizers, warnings, assertions or tests. For bug work, follow the pinned kernel's
coding-assistants process, including reproduction and verification requirements.
AI tools must not add Signed-off-by; a human reviews and certifies any submission.
