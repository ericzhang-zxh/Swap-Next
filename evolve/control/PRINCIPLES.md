# Principles

## Correctness gates performance

Data integrity, reference consistency, no use-after-free or double free, no
lock inversion, and symmetric charge/uncharge are hard gates. No speedup
compensates for a failure. A clean build, a clean exit or the absence of a
crash proves none of them.

## Scope

Candidates may modify only the swap-core files listed in
`config/policy.json` and add `tools/testing/selftests/mm/swap_next_*.c`
tests. `mm/memory.c`, `mm/vmscan.c`, memcg, arch code, Kconfig, Makefiles, UAPI
and global VM policy are out of scope. Only the controller widens scope, by
creating a new campaign policy.

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
- **Isolation**: namespace-isolated builds and KVM guests.

The host never runs candidate-provided Makefiles, scripts or commands. The
same Unix user can rewrite rules and evidence, so hashes detect accidental
drift. They do not stop a malicious agent.

## Permissions

Only the owner changes policies and baselines. Agents get no host root, no
credentials, and may not publish, email, push, reboot, or change host swap or
the host kernel. Nothing merges automatically, and no agent adds a DCO sign-off.
