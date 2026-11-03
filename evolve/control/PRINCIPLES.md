# Principles

## Correctness gates performance

Data integrity, reference consistency, no use-after-free or double free, no
lock inversion, and symmetric charge/uncharge are hard gates. No speedup
compensates for a failure. A clean build, a clean exit or the absence of a
crash proves none of them.

## Scope

New research campaigns select a trusted profile from `evolve/profiles/` before
opening. The profile fixes allowed files, correctness coverage, observables,
measurement limits and resource caps. Campaign policies can only narrow it.
The executable `swap-core` profile preserves the existing swap-file scope;
`swap-architecture` records broader intent and missing capabilities and cannot
execute. A worker cannot approve a profile or alter an evaluator.

Frozen campaigns without research metadata retain the base list in
`config/policy.json`. Historical protocols are never rewritten.

## Invariants every candidate preserves

- Each entry, slot, folio and compressed object has an explicit owner.
- Nothing still reachable from a PTE, a cache or in-flight I/O is freed.
- An object is fully initialized before it is published, and teardown follows
  the target code's lifetime protocol.
- Every failure exit undoes allocations, references and charges.
- RCU does not replace state validation, the folio lock or reference acquisition.
- Reclaim-path allocations do not recurse into reclaim.
- The impact analysis covers large folios, partial failure, swapoff, memcg and
  concurrent faults.

## The task is fixed

The workload, seeds, statistics, thresholds, baselines, timing windows and holdout
stay as frozen. Candidates do not remove work, exit early, reduce reclaim
or hide errors. Every failure and timeout is kept in the results, and slow
samples are never dropped. Raw measurements outrank any summary an agent
writes.

## Trust boundary

There are three layers:

- **Instructions**: AGENTS.md and the task contract.
- **Mechanical gates**: the controller's diff allowlist, size budget and frozen hashes.
- **Isolation**: namespace-isolated builds and QEMU guests (KVM, or TCG on
  Grok Bot's cloud box).

The host never runs candidate-provided Makefiles, scripts or commands. The
same Unix user can rewrite rules and evidence, so hashes detect accidental
drift. They do not stop a malicious agent.

## Permissions

Campaign scope and baseline changes follow AGENTS.md and the owner-authorized
contract. The owner approves candidate promotion. No agent gets host root,
reboots the host, changes host swap or the host kernel, or adds a DCO sign-off.
Execution workers cannot access credentials, email, push or publish. The primary
agent commits experiment work directly to main without a pull request and
publishes the campaign report for the owner's review, as AGENTS.md requires.
Candidate code is never promoted automatically.
