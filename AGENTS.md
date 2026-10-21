# Swap Next contributor contract

- Write all project-authored documentation, code comments, commit messages and repository review artifacts in English. This rule applies only to this repository; preserve upstream and third-party source text.
- For kernel patch reviews, use `.agents/skills/kernel-patch-review/SKILL.md` and `evolve/control/CODE_PATTERNS.md`.
- Read README.md, evolve/control/PRINCIPLES.md, evolve/control/CODE_PATTERNS.md and evolve/control/config/policy.json first.
- Run all kernel and sparse work on the designated Linux worker, never the controller laptop.
- Do not modify the linux submodule checkout. Create candidate worktrees through evolve/control/controller.py.
- Read linux/Documentation/process/coding-assistants.rst and its required process documents before kernel work.
- Workers execute one assigned hypothesis; no further delegation, scope changes, evaluator changes or publishing.
- Preserve locks, reference ownership, warnings, accounting and failure handling.
- Never weaken correctness gates or treat missing evidence as PASS.
- No host reboot, host swap changes, raw host disks, sudo, automatic merge or promotion.
- Keep runtime state, secrets, machine paths and credentials out of commits.
- AI tools must not add Signed-off-by. A human must review and certify any upstream contribution.

## Kernel code taste

These core rules apply when authoring or reviewing kernel changes. See
`evolve/control/CODE_PATTERNS.md` for detailed rationale and review guidance.

- Express one coherent intent per patch. Keep unrelated renaming, formatting and refactoring separate; preserve valid intermediate commits.
- Follow the target subsystem's conventions and existing APIs. Prefer a clear state representation to accumulating special cases, but do not redesign beyond the task's scope.
- Introduce helpers that name meaningful operations or invariants. Avoid speculative frameworks and abstractions without a concrete use.
- Reduce the state readers must remember: avoid redundant flags and deep nesting when a simpler flow preserves semantics. Fewer lines alone are not an improvement.
- Make ownership, publication and final release explicit. Trace every relevant writer and free path before changing synchronization; a lock held at one lookup is not a lifetime proof.
- Preserve reference acquisition, lock ordering and revalidation after dropped locks. RCU and READ_ONCE/WRITE_ONCE do not replace the synchronization or ownership guarantees the path requires.
- Treat failure paths as part of the design. Preserve error returns, partial-success rollback, accounting and reclaim allocation constraints; use cleanup labels when they clarify resource ownership.
- Explain why subtle code is safe, rather than narrating its statements. Keep assertions and defensive checks unless a justified change establishes their replacement invariant.
- Connect each optimization to an exercised path and measurable mechanism. A removed load or branch is a hypothesis, not proof of overall improvement; report costs and regressions.
- Separate correctness defects, unresolved assumptions, maintainability suggestions and performance claims. Support findings with concrete execution paths; do not present stylistic preference as a bug.
- Use proportionate validation and state its limits. Checkpatch, compilation and a passing pilot do not establish complete correctness or performance acceptance.
