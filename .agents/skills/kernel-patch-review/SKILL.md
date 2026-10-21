---
name: kernel-patch-review
description: Review Linux kernel patches for subsystem fit, ownership and concurrency, failure handling, and evidence-backed optimization claims. Use for kernel patch reviews and pre-experiment review in Swap Next; not for unrelated application code or general Linux administration.
---

# Kernel patch review

Review the requested patch against its exact base. Do not expand a review into
implementation, benchmark execution or publication unless those actions are
already authorized. In an explicitly read-only review, report suspected defects
and unperformed reproduction/fix steps without silently expanding into bug-fix
execution. Write repository artifacts and review text intended for this
repository in English; this skill sets no global conversation-language preference.

## Establish the contract

Locate the repository root and read `AGENTS.md`, `system/CODE_PATTERNS.md` and the
applicable policy. Follow the designated Linux-worker requirement. Inspect the
pinned kernel's `Documentation/process/coding-assistants.rst` and the process
documents it requires for the actual task. Use that source tree's APIs and
subsystem conventions, not assumptions from another kernel version.

Identify base/head commits, changed paths, the claimed benefit, and the relevant
caller contract. For an uncommitted patch, record its exact base and patch identity;
state that no candidate head commit exists rather than inventing one. Read enough surrounding callers, writers and release paths to
check the patch. Start with the most consequential uncertainty; the following
passes are review lenses, not a requirement to invent findings in every category.

## Review lenses

- **Design and readability:** Does the representation express the invariant?
  Are new flags, branches and helpers necessary? Does the patch follow subsystem
  idioms and express one coherent intent? Distinguish a justified local helper
  from speculative abstraction. Do not equate fewer lines with better design.
- **Ownership and concurrency:** Trace initialization, publication, reference
  acquisition, mutation, unpublication and final release. Check every relevant
  writer/free path, lock order, dropped-lock interval and revalidation. Holding a
  lock at a lookup does not prove that an allocator or teardown path uses it.
  Name what RCU and atomic operations actually protect; do not infer lifetime
  guarantees from their presence alone.
- **Failure and boundary cases:** Check partial success, cleanup order, return
  values and charge/uncharge symmetry. Consider swapoff, reclaim allocation
  context, overflow counts, large folios and memcg where the patch touches them.
  Do not demand unrelated matrices for a documentation-only change.
- **Performance evidence:** Connect the proposed mechanism to an exercised path.
  Separate a source-level reduction in work from measured improvement. Check
  provenance, workload coverage, noise and regressions before endorsing claims.
  Compilation, checkpatch and a passing pilot are not performance acceptance.

## Findings and disposition

Give actionable findings with file/line, trigger, mechanism and consequence.
Separate confirmed defects, unresolved assumptions, optional design suggestions,
and unverified performance claims. Do not label taste preferences as correctness
bugs, invent numerical confidence, or report skipped checks as passed.

Summarize what was inspected and tested, material gaps, and whether the patch is
ready for its requested next step. A patch may be suitable for a bounded experiment
without being ready to merge. If no actionable finding is supported, say so and
state the remaining coverage limits. Never approve promotion on the strength of
an uncalibrated discovery score, and never add AI-generated DCO signatures.
