# Principles and Hard Boundaries

## Correctness First, Performance Second

Data integrity, consistent references, no use-after-free, no double free, no lock
inversion, and symmetric charge/uncharge are mandatory gates. Throughput gains
cannot compensate for any failure. Do not describe “no crash,” “successful exit,”
or “successful build” as proof of correctness.

## Three Distinct Boundaries

- **Instruction boundary**: AGENTS instructions and task contracts require workers to stay within scope.
- **Mechanical gates**: diff allowlists, size budgets, input validation, and frozen configuration hashes reject noncompliant results.
- **Security boundary**: independent VMs/containers/permission principals, no credentials, no writable host mounts, and network and resource isolation.

The controller provides the first two layers. The Evolve pilot additionally
provides namespace-isolated builds and KVM guest isolation, which still require
verification in the deployment environment. The same Unix user can alter rules
and evidence, so worktrees, JSON, and hashes neither isolate a malicious agent
nor prove authenticity. Never let the host runner execute candidate-provided
Makefiles, scripts, model commands, or arbitrary shell commands.

## Scope

By default, changes are limited to a small set of designated swap-core files;
the exact list in config/policy.json is authoritative. mm/memory.c, mm/vmscan.c,
memcontrol, architecture code, Kconfig, Makefiles, UAPI, and global VM policy are
outside the initial automated search scope. If needed, the controller initiates
a task with a new scope; candidates cannot relax the allowlist themselves.
New regression-test source files with constrained names are allowed, but they do
not replace the immutable golden acceptance suite.

## Invariants

- Ownership of entries, slots, folios, and compressed objects must be explicit.
- Resources still usable by PTEs, caches, or in-flight I/O must not be freed early.
- Initialize fully before publishing a mapping; after teardown, follow the target code’s lifetime protocol.
- Every failure exit must undo completed allocations, reference acquisitions, and accounting charges.
- RCU does not replace object-state validation, folio locking, or correct reference acquisition.
- Allocation contexts in reclaim paths must not introduce reclaim recursion.
- Include large folios, partial failure, swapoff, memcg, and concurrent faults in the impact analysis.

## Do Not Change the Task to Improve the Score

Do not remove work, terminate early, reduce actual reclaim, hide errors, change
the seed set, or tamper with statistics, thresholds, baselines, timing intervals,
or holdouts. Agent-written score summaries cannot replace raw measurements.
Preserve failures and timeouts; never select only faster samples.

## Permissions and Actions

Only the controller/owner may change policies and baselines. Host root access,
credentials, publishing, email, pushing, rebooting, and modifying host swap or
the host kernel are not authorized. Automatic merging is disabled by default.
Candidates may express a complete change as a small local commit; do not add
DCO sign-offs automatically.
